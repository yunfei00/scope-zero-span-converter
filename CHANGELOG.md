# 版本变更记录

## v0.8.0（开发中）

### 商业化整改

- 建立 `src/scope_zero_span_converter/_version.py` 作为单一版本来源。
- `pyproject.toml` 改为动态读取统一版本。
- `main` 使用 `0.8.0.dev0` 开发版本。
- Release workflow 在 tag 构建时把 `vX.Y.Z` 注入软件版本，确保包版本、GUI、metadata 与 Release 一致。
- 主窗口显示真实软件版本。
- `DCM → Zero Span` 页签更名为 `DCM 综合分析`。
- 新增 `dcm_analysis_widget.py` 稳定入口；主程序不再直接依赖具体 `dcm_zero_span_widget_v10` 名称。
- AppState 升级为 schema v2，新增稳定 `selected_tab_id`，继续兼容旧数字页签索引。
- README 更新为当前五工作区与四视图能力。
- 新增 `docs/COMMERCIALIZATION_ROADMAP.md`，明确 v0.8/v0.9/v1.0 产品化阶段。
- Release 客户说明同步更新为当前功能集。

### 架构收口

- 新建正式 `dcm_analysis/` 包，停止继续增加 `v11/v12` 风格页面。
- 抽离 `dcm_analysis/spectrum.py`，幅度与相位统一来自同一次复数 FFT。
- 抽离 `dcm_analysis/axis.py`，统一固定范围、刻度、自动范围和步长策略。
- 抽离 `dcm_analysis/zoom.py`，统一时域/频域框选放大和 Space 多级撤销状态。
- 迁移期曾保留旧 `vN` 模块作为兼容层，主程序通过稳定入口访问 DCM 综合分析。
- 正式页面完成收口后，退休版本化 GUI、过渡 shim、重复 MainWindow 与旧 manual tuner；生产与正式测试只使用无版本 package API。
- 增加架构防回退测试，禁止生产代码重新 import 或新增版本化 GUI 模块。

### 数据可靠性

- 新增 `WaveformQualityReport`：点数、时间范围、Duration、Fs、Nyquist、dt 偏差、最大间隔比等。
- 检测重复时间戳、时间倒序、非均匀采样和疑似缺点。
- FFT、Zero Span 在严重时间轴异常时直接拒绝计算，不再静默使用 `median(dt)` 继续。
- 新增 `waveform_io.py` 统一安全 CSV 读取入口，并记录被清理的无效行数。
- 波形研究页显示输入数据质量摘要和 Nyquist。
- DCM 参数提取 GUI 接入同一时间轴质量门禁。
- `conversion_metadata.json` 写入完整 `time_axis_quality`。
- `batch_summary.csv/json` 增加质量状态、dt 最大偏差和最大间隔比。
- FSW Sweep Time 超出 Scope 实际记录范围时直接报错，不再静默用首尾值外推。

### FFT / Phase 定义

- 明确幅度频谱为：去 DC + Hann + single-sided FFT + coherent-gain corrected peak dBV/bin。
- 相位明确为当前 FFT 记录起点参考下的 Wrapped Phase，不等同于网络分析仪的器件绝对相位。
- 相位有效性从固定 `-120 dBV` 升级为“绝对门限 + 当前峰值向下 60 dB 动态范围”的联合门限。
- 相位图显示当前实际有效幅度阈值，低于阈值的频点相位隐藏。
- 幅度与相位的全频、自动显示抽样、Rectangle Zoom 和手动频率范围均复用同一组 FFT display indices；Zoom 从完整 FFT 缓存恢复当前视窗真实 bins。
- 修复右侧共享 X 轴建立后 Center/RBW 辅助图元触发二次 autoscale，导致最终频率范围与输入框回填不一致的问题。

### P0 快照与异步一致性

- 新增 DCM 分析快照一致性门禁：DCM 参数、当前波形、Zero Span Profile/结果、FFT 幅度/相位必须来自同一数据版本才允许一键导出。
- DCM FFT 与 Zero Span 结果均记录完整源波形签名；Zero Span 额外记录涵盖 Center/RBW/VBW、阻抗、校准和示波器模拟带宽的 Profile 签名。
- DCM 参数 debounce、DCM/FFT Worker 运行中或存在 latest pending request 时拒绝导出，并明确提示等待联动/FFT 完成。
- 补强 DCM recompute、FFT、ROI 和全局精修异步结果保护；旧请求或已变化的输入不能释放/覆盖更新的 GUI 状态。
- 修复 64 位平台把 Python waveform identity 通过 Qt 32 位 `int` 信号传递时可能溢出、令 FFT Worker 状态无法释放的问题。
- DCM 生成结果保留独立参数快照，后续原位修改参数对象不会伪造已有波形的生成参数。

### 商业支持能力

- 日志改为 `RotatingFileHandler`：单文件最大 10 MB，保留 5 个历史日志。
- 新增一键“导出诊断包”。
- 诊断 ZIP 包含软件版本、系统/Python 运行环境和应用日志。
- 诊断包默认不包含客户波形、参数 JSON 或配置快照。
- 修复波形加载失败后可能继续附加上一份波形质量摘要的状态误导问题。

### 后续重点

- Windows 预发布构建与基本 smoke validation。
- Installer、VersionInfo、签名、许可与客户手册。

## v0.7.0

### DCM 幅度/相位频域联动

- 四格分析区最终形成：
  - 左上：DCM SW 时域。
  - 左下：Zero Span。
  - 右上：DCM 幅度频谱。
  - 右下：DCM 相位频谱。
- 幅度与相位来自同一次去直流 + Hann 窗单边复数 FFT，使用完全相同的 frequency bins。
- 相位采用 wrapped phase `-180°~+180°`。
- 低幅度频点相位按当前门限隐藏，避免无意义相位乱跳。
- 右上/右下共享 Frequency X 轴。
- Center / RBW 在幅度与相位频谱中对应显示。
- 修正相位门限测试对默认噪声底的错误假设。

## v0.6.0

### DCM 时域 / 完整频域 / Zero Span 三联动

- DCM 联动页面升级为 2×2 四格布局。
- 保留左上 DCM 时域、左下 Zero Span 的严格时间轴对齐。
- 右上新增完整 FFT 幅度频谱。
- 频谱显示 Zero Span Center 与 RBW 区域。
- 完整频域支持 X/Y Min / Max / Step。
- 频域正常数据更新时始终自动适配；手工输入只改变当前显示。
- 自动坐标更新后把实际 X/Y Min / Max / Step 回填左侧输入框。
- DCM 时域与完整频域支持鼠标矩形框选放大。
- `Space` 支持逐级返回放大前状态。
- DCM 时域放大时 Zero Span 时间轴同步跟随。

## v0.5.0

### DCM → Zero Span 实时联动

- 新增独立 DCM / Zero Span 联动页面。
- 左侧全部 DCM 模型参数采用滑块 + 数值框联动。
- 加载已提取 DCM 参数 JSON 后可直接生成波形并实时调参。
- 复用既有 Zero Span 核心算法，不另写转换链。
- 上方 DCM 时域、下方 Zero Span 功率-时间曲线同步更新。
- Zero Span 参数支持保存/加载 Profile，并默认折叠。
- 增加 DCM 与 Zero Span 纵轴 Min / Max / Step 固定显示设置。
- 波形超过用户设定 Y 范围时坐标轴不自动扩展，超出部分直接裁剪。
- Zero Span 参数无效时不再阻塞 DCM 时域调参，错误状态与 DCM 波形更新解耦。

## v0.4.0

### 波形研究与 DCM 参数化建模

- 新增波形研究 ROI：鼠标框选、数值设置、放大/恢复、保存截取 CSV/region.json。
- ROI 改变后 Zero Span 自动联动，研究模式保持真实 ROI 时间轴。
- 新增 DCM SW 参数化生成器。
- 支持绝对时间轴起点、总时长、上下沿、导通/续流、尖峰/寄生振铃、DCM 断续谐振、噪声、采样率和随机种子。
- 上升/下降沿允许 `0 ns` 表示理想阶跃。
- 支持合成 CSV + 参数 JSON 保存/恢复以及真值分量显示。
- 新增 DCM 参数提取：基础参数、开关沿振铃、DCM 断续谐振三阶段识别。
- 新增全局联合精修、RMSE、R²、残差和置信度提示。
- 提取结果可导出生成器同源参数 JSON 和重建 CSV。
- 参数提取/生成器保留原始 CSV 绝对时间轴起点。

## v0.3.0

- 单次转换 / 批量转换 GUI。
- 批量递归扫描、失败继续、独立输出目录。
- `batch_summary.csv` / `batch_summary.json`。
- 客户配置模板保存、加载、删除、刷新。
- 用户模板目录与应用日志目录。
- CLI `batch` 子命令。
- 最近使用状态保存。

## v0.2.0

- 导入 FSW Zero Span 实测 CSV。
- 示波器恢复曲线与 FSW 实测曲线叠加。
- MAE / RMSE / Bias / 最大绝对误差 / 相关系数。
- `comparison_to_fsw.csv`。
- `conversion_metadata.json`。
- Center / RBW / VBW 参数来源显示。

## v0.1.0

- 建立示波器时域到 Zero Span 的离线转换基线。
- Center 数字下变频。
- Gaussian RBW。
- RMS 功率检波。
- 一阶 VBW。
- FSW Sweep Time / Points 重采样。
- Nyquist 与示波器模拟带宽约束。
- CSV / PNG / metadata 输出。
