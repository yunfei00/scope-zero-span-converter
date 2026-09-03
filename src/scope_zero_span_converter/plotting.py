from __future__ import annotations

from matplotlib import font_manager, rcParams


# 按 Windows / macOS / Linux 常见中文字体顺序尝试。
# 不随程序分发字体文件，优先使用客户操作系统已有字体。
_CHINESE_FONT_CANDIDATES = (
    "Microsoft YaHei",
    "Microsoft JhengHei",
    "SimHei",
    "SimSun",
    "PingFang SC",
    "Heiti SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
)


def configure_matplotlib_chinese() -> str | None:
    """配置 Matplotlib 中文显示并返回实际选中的字体名。

    如果系统没有候选中文字体，不抛异常，继续使用 Matplotlib 默认字体。
    Windows 客户机通常会命中 Microsoft YaHei。
    """

    selected: str | None = None
    for family in _CHINESE_FONT_CANDIDATES:
        try:
            font_manager.findfont(
                font_manager.FontProperties(family=family),
                fallback_to_default=False,
            )
        except ValueError:
            continue
        selected = family
        break

    if selected is not None:
        current = list(rcParams.get("font.sans-serif", []))
        rcParams["font.family"] = "sans-serif"
        rcParams["font.sans-serif"] = [selected, *[x for x in current if x != selected]]

    # 避免中文字体下负号显示成方框。
    rcParams["axes.unicode_minus"] = False
    return selected
