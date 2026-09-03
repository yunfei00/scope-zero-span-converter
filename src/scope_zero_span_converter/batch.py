from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

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
            "schema_version": 1,
            "software": {
                "name": "scope-zero-span-converter",
                "version": __version__,
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_directory": str(result.source_directory),
            "output_directory": str(result.output_directory),
            "jobs_found": result.jobs_found,
            "succeeded": result.succeeded,
            "failed": result.failed,
            "batch_config": asdict(config.batch),
            "items": rows,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        result.summary_json = path

    return result


def run_batch(config: AppConfig) -> BatchRunResult:
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

    for index, job in enumerate(jobs, start=1):
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
            result.items.append(
                BatchItemResult(
                    name=job.name,
                    source_directory=str(job.directory),
                    status="success",
                    output_directory=str(item_output),
                    center_frequency_hz=conversion.center_frequency_hz,
                    rbw_hz=conversion.rbw_hz,
                    vbw_hz=conversion.vbw_hz,
                    sample_rate_hz=conversion.sample_rate_hz,
                    mae_db=comparison.mae_db if comparison else None,
                    rmse_db=comparison.rmse_db if comparison else None,
                    bias_db=comparison.bias_db if comparison else None,
                    correlation=comparison.correlation if comparison else None,
                )
            )
            result.succeeded += 1
        except Exception as exc:
            result.items.append(
                BatchItemResult(
                    name=job.name,
                    source_directory=str(job.directory),
                    status="failed",
                    output_directory=str(item_output),
                    error=str(exc),
                )
            )
            result.failed += 1
            if not config.batch.continue_on_error:
                break

    return _write_summary(result, config)
