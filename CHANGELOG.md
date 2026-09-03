# 版本变更记录

## v0.4.0（开发中）

### 方向调整

- 当前重点从继续优化 Zero Span 恢复精度，切换到原始时域波形研究与波形区域提取。
- v0.1~v0.3 已验证的 Zero Span 算法作为稳定基线保留，v0.4 不主动修改其核心逻辑。

### 新增

- 新增“波形研究”主页面。
- 在原始波形图中鼠标横向拖动选择 ROI。
- 支持通过数值精确设置 ROI 起点/终点。
- 显示 ROI 起止时间、时长、点数和原始索引。
- 支持放大到研究区域。
- 支持恢复完整波形视图后重新选择。
- 支持清除 ROI。
- 支持保存截取后的标准 `time_s,voltage_v` CSV。
- 可选保存 `.region.json`，记录 ROI 参数和来源。
- 可选将截取 CSV 的时间轴重新从 0 开始。
- ROI 改变后，下方 Zero Span 转换曲线自动联动刷新。
- 研究模式不重采样到原始 FSW Sweep Time，确保转换结果对应当前真实 ROI 时间范围。
- 新增 `waveform_research` JSON 配置段。
- 为后续 DCM SW 自动提取策略预留 `extraction_mode` 接口。
- 新增 ROI 裁剪、保存和联动转换自动测试。

### 兼容

- 继续保持 `schema_version = 1`。
- v0.1 / v0.2 / v0.3 JSON 没有 `waveform_research` 字段时自动使用默认值。
- v0.3 批量转换、配置模板、日志和最近使用状态继续保留。

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
