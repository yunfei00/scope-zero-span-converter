from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from .config import AppConfig
from .converter import ConversionResult, convert, save_result


@dataclass(frozen=True)
class FullConversionWorkerResult:
    config: AppConfig
    conversion: ConversionResult


class FullConversionWorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class FullConversionWorkerTask(QRunnable):
    """Run one complete conversion + save outside the GUI thread."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        # Freeze the GUI settings for this run. The customer may keep using the
        # window while the worker is active without changing the active job.
        self.config = deepcopy(config)
        self.signals = FullConversionWorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        cfg = deepcopy(self.config)
        try:
            waveform = Path(cfg.input.waveform_file)
            metadata = Path(cfg.input.metadata_file)
            reference = (
                Path(cfg.input.fsw_reference_file)
                if cfg.input.fsw_reference_file
                else None
            )
            if not waveform.exists():
                raise FileNotFoundError(f"找不到波形文件：{waveform}")
            if not metadata.exists():
                raise FileNotFoundError(f"找不到 metadata 文件：{metadata}")
            if reference is not None and not reference.exists():
                raise FileNotFoundError(f"找不到 FSW 实测 CSV：{reference}")

            conversion = convert(waveform, metadata, cfg)
            # A Qt desktop worker must never call pyplot.show(). The original GUI
            # already suppressed show_plot during save; preserve that behavior.
            requested_show_plot = cfg.output.show_plot
            cfg.output.show_plot = False
            save_result(
                conversion,
                waveform,
                cfg,
                metadata_path=metadata,
                reference_fsw_path=reference,
            )
            cfg.output.show_plot = requested_show_plot
        except Exception as exc:
            self.signals.failed.emit(str(exc))
            return

        self.signals.finished.emit(
            FullConversionWorkerResult(config=cfg, conversion=conversion)
        )


__all__ = [
    "FullConversionWorkerResult",
    "FullConversionWorkerSignals",
    "FullConversionWorkerTask",
]
