"""Scope Zero Span Converter."""

from .plotting import configure_matplotlib_chinese

__version__ = "0.4.0"

# 在 GUI / CLI 创建任何 Figure 之前统一配置中文字体。
# Windows 客户机优先使用 Microsoft YaHei；没有候选字体时安全回退。
MATPLOTLIB_CHINESE_FONT = configure_matplotlib_chinese()
