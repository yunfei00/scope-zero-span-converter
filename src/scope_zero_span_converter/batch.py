from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from . import __version__
from .config import AppConfig
from .converter import convert, save_result


@dataclass(frozen=True)
class BatchJob:
    name: str
    directory: Path
    waveform_path: Path
    metadata_path: Path
    fsw_reference_path: Path | None = None


@dataclass
class BatchItemResult:
    name: str
    source_directory: str
    status: str
    output_directory: str
    error: str | None = None
    center_frequency_hz: float | None = None
    rbw_hz: float | None = None
    vbw_hz: float | None = None
    sample_rate_hz: float | None = None
    quality_status: str | None = None
    dt_max_deviation_percent: float | None = None
    max_gap_ratio: float | None = None
    mae_db: float | None = None
    rmse_db: float | None = None
    bias_db: float | None = None
    correlation: float | None = None


@dataclass
class BatchRunResult:
    source_directory: Path
    output_directory: Path
    jobs_found: int
    succeeded: int
    failed: int
    items: list[BatchItemResult]
    summary_csv: Path | None = None
    summary_json: Path | None = None
    cancelled: bool = False

    @property
    def jobs_processed(self) -> int:
        return len(self.items)


BatchStartCallback = Callable[[int], None]
BatchProgressCallback = Callable[[int, int, BatchItemResult], None]
BatchCancelCheck = Callable[[], bool]


def discover_batch_jobs(config: AppConfig) -> list[BatchJob]:
    root = Path(config.batch.source_directory).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"批量输入目录不存在：{root}")
    if not root.is_dir():
        raise NotADirectoryError(f"批量输入路径不是目录：{root}")

    waveform_name = config.batch.waveform_filename.strip()
    metadata_name = config.batch.metadata_filename.strip()
    reference_name = config.batch.fsw_reference_filename.strip()

    iterator = root.rglob(waveform_name) if config.batch.recursive else root.glob(waveform_name)
    jobs: list[BatchJob] = []

    for waveform in sorted(iterator):
        directory = waveform.parent
        metadata = directory / metadata_name
        if not metadata.exists():
            continue

        reference: Path | None = None
        if reference_name:
            candidate = directory / reference_name
            if candidate.exists():
                reference = candidate

        relative = directory.relative_to(root)
        name = str(relative) if str(relative) != "." else directory.name
        jobs.append(
            BatchJob(
                name=name,
                directory=directory,
                waveform_path=waveform,
                metadata_path=metadata,
                fsw_reference_path=reference,
            )
        )

    return jobs


def _item_to_dict(item: BatchItemResult) -> dict:
    return asdict(item)


def _write_summary(result: BatchRunResult, config: AppConfig) -> BatchRunResult:
    result.output_directory.mkdir(parents=True, exist_ok=True)
    rows = [_item_to_dict(item) for item in result.items]

    if config.batch.save_summary_csv:
        path = result.output_directory / "batch_summary.csv"
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
        result.summary_csv = path

    if config.batch.save_summary_json:
        path = result.output_directory / "batch_summary.json"
        payload = {
            "schema_version": 2,
            "software": {
                "name": "scope-zero-span-converter",
                "version": __version__,
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_directory": str(result.source_directory),
            "output_directory": str(result.output_directory),
            "jobs_found": result.jobs_found,
            "jobs_processed": result.jobs_processed,
            "succeeded": result.succeeded,
            "failed": result.failed,
            "cancelled": result.cancelled,
            "batch_config": asdict(config.batch),
            "items": rows,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        result.summary_json = path

    return result


def run_batch(
    config: AppConfig,
    *,
    start_callback: BatchStartCallback | None = None,
    progress_callback: BatchProgressCallback | None = None,
    should_cancel: BatchCancelCheck | None = None,
) -> BatchRunResult:
    """Run batch conversion with optional progress and cooperative cancellation.

    Existing callers can keep calling ``run_batch(config)`` unchanged.

    Cancellation is intentionally checked *between* jobs. A conversion already
    running is allowed to finish and save atomically; the next job will not be
    started after cancellation is requested. This avoids leaving half-written
    customer outputs while still making a long multi-job batch stoppable.
    """

    config.validate()
    source_root = Path(config.batch.source_directory).expanduser()
    output_root = Path(config.batch.output_directory).expanduser()
    jobs = discover_batch_jobs(config)

    result = BatchRunResult(
        source_directory=source_root,
        output_directory=output_root,
        jobs_found=len(jobs),
        succeeded=0,
        failed=0,
        items=[],
    )

    if start_callback is not None:
        start_callback(len(jobs))

    for index, job in enumerate(jobs, start=1):
        if should_cancel is not None and should_cancel():
            result.cancelled = True
            break

        relative = job.directory.relative_to(source_root)
        item_output = output_root / relative
        item_config = deepcopy(config)
        item_config.input.waveform_file = str(job.waveform_path)
        item_config.input.metadata_file = str(job.metadata_path)
        item_config.input.fsw_reference_file = (
            str(job.fsw_reference_path) if job.fsw_reference_path else ""
        )
        item_config.output.directory = str(item_output)
        item_config.output.show_plot = False

        try:
            conversion = convert(
                job.waveform_path,
                job.metadata_path,
                item_config,
            )
            save_result(
                conversion,
                job.waveform_path,
                item_config,
                metadata_path=job.metadata_path,
                reference_fsw_path=job.fsw_reference_path,
            )

            comparison = conversion.comparison
            quality = conversion.waveform_quality
            item_result = BatchItemResult(
                name=job.name,
                source_directory=str(job.directory),
                status="success",
                output_directory=str(item_output),
                center_frequency_hz=conversion.center_frequency_hz,
                rbw_hz=conversion.rbw_hz,
                vbw_hz=conversion.vbw_hz,
                sample_rate_hz=conversion.sample_rate_hz,
                quality_status=quality.status,
                dt_max_deviation_percent=quality.max_dt_deviation_fraction * 100.0,
                max_gap_ratio=quality.max_gap_ratio,
                mae_db=comparison.mae_db if comparison else None,
                rmse_db=comparison.rmse_db if comparison else None,
                bias_db=comparison.bias_db if comparison else None,
                correlation=comparison.correlation if comparison else None,
            )
            result.items.append(item_result)
            result.succeeded += 1
        except Exception as exc:
            item_result = BatchItemResult(
                name=job.name,
                source_directory=str(job.directory),
                status="failed",
                output_directory=str(item_output),
                error=str(exc),
            )
            result.items.append(item_result)
            result.failed += 1

        if progress_callback is not None:
            progress_callback(index, len(jobs), item_result)

        if item_result.status == "failed" and not config.batch.continue_on_error:
            break

    # A cancel requested while the final active job was running should still be
    # visible in the result even though there is no next loop iteration.
    if should_cancel is not None and should_cancel() and result.jobs_processed < result.jobs_found:
        result.cancelled = True

    return _write_summary(result, config)
