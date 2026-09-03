# 版本变更记录

## v0.3.0

### 新增

- 单次转换 / 批量转换双页签 GUI。
- 批量递归扫描任务目录。
- 批量任务成功/失败表格。
- 每个任务独立输出目录。
- `batch_summary.csv` 和 `batch_summary.json`。
- 批量失败后继续执行选项。
- 客户配置模板保存、加载、删除、刷新。
- 用户模板目录：`~/ScopeZeroSpanConverter/templates/`。
- 应用日志：`~/ScopeZeroSpanConverter/logs/scope-zero-span-converter.log`。
- CLI `batch` 子命令。

### 兼容

- 保持 `schema_version = 1`。
- v0.1 / v0.2 JSON 缺失 v0.3 字段时自动使用默认值。
- 不修改 v0.2 已验证的 Zero Span 核心算法。

## v0.2.0

### 新增

- 导入 FSW Zero Span 实测 CSV。
- 示波器恢复曲线与 FSW 实测曲线叠加。
- MAE / RMSE / Bias / 最大绝对误差 / 相关系数。
- `comparison_to_fsw.csv`。
- `conversion_metadata.json`。
- Center / RBW / VBW 参数来源显示。
- FSW 对比自动测试。

## v0.1.0

### 首个基线版本

- 示波器时域波形 -> Zero Span 功率-时间曲线。
- Center 数字下变频。
- Gaussian RBW。
- RMS 功率检波。
- VBW 时域平滑。
- FSW Sweep Time / Points 重采样。
- JSON 参数加载/保存。
- PySide6 GUI。
- CLI。
- Matplotlib 中文字体适配。
- 200 MHz / Span 0 / RBW 10 MHz 算法基线测试。
- GitHub Actions 自动测试。
- `v*` Tag 自动构建 Windows ZIP 并创建 GitHub Release。
