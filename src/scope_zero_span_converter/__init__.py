"""Scope Zero Span Converter."""

from ._version import __version__
from .plotting import configure_matplotlib_chinese

# 在 GUI / CLI 创建任何 Figure 之前统一配置中文字体。
# Windows 客户机优先使用 Microsoft YaHei；没有候选字体时安全回退。
MATPLOTLIB_CHINESE_FONT = configure_matplotlib_chinese()

__all__ = ["__version__", "MATPLOTLIB_CHINESE_FONT"]
