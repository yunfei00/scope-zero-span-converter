from __future__ import annotations

import argparse
from pathlib import Path

from .config import AppConfig, load_config, save_config
from .converter import convert, save_result


def _default_config_path() -> Path:
    return Path("configs/default.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scope-zero-span-converter",
        description="示波器时域波形 -> 频谱仪 Zero Span 时域曲线",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    convert_cmd = sub.add_parser("convert", help="执行 Zero Span 转换")
    convert_cmd.add_argument("waveform", help="waveform.csv")
    convert_cmd.add_argument("metadata", help="metadata.json")
    convert_cmd.add_argument(
        "--config",
        default=str(_default_config_path()),
        help="JSON 配置文件，默认 configs/default.json",
    )
    convert_cmd.add_argument(
        "--no-show",
        action="store_true",
        help="不弹出图形窗口",
    )

    init_cmd = sub.add_parser("init-config", help="生成一份默认 JSON 配置")
    init_cmd.add_argument("path", nargs="?", default="converter-config.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "init-config":
        path = Path(args.path)
        save_config(AppConfig(), path)
        print(f"已生成默认配置: {path}")
        return 0

    config = load_config(args.config)
    if args.no_show:
        config.output.show_plot = False

    result = convert(args.waveform, args.metadata, config)
    save_result(result, args.waveform, config)

    print("Zero Span 转换完成")
    print(f"Center : {result.center_frequency_hz / 1e6:.6g} MHz")
    print(f"RBW    : {result.rbw_hz / 1e6:.6g} MHz")
    if result.vbw_hz is not None:
        print(f"VBW    : {result.vbw_hz / 1e6:.6g} MHz")
    print(f"Fs     : {result.sample_rate_hz / 1e6:.6g} MSa/s")
    if result.output_csv:
        print(f"CSV    : {result.output_csv}")
    if result.output_plot:
        print(f"Plot   : {result.output_plot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
