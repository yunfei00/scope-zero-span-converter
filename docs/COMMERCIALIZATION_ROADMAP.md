# Scope Zero Span Converter 商业化整改路线

当前稳定客户版本：`v0.7.0`  
当前商业化开发线：`v0.8.0.dev0`

目标：在不破坏已经验证的 Zero Span 核心算法和 DCM 四视图联动能力的前提下，把当前研究/工程工具收口为可稳定交付、可维护、可诊断、可升级的商业桌面软件。

## 总原则

1. `v0.7.0` 作为当前功能基线，商业化整改期间不随意重写 Zero Span 核心算法。
2. 新功能优先通过稳定模块入口接入，停止继续增长 `*_v11.py`、`*_v12.py` 一类版本化 GUI 文件。
3. 所有“看起来正常但数据其实不可相信”的情况，优先增加验证/告警，而不是静默计算。
4. 每阶段完成后必须通过自动测试和 Windows Release 构建验证，再进入下一阶段。

---

## Phase 1：版本与产品基线收口

目标：先消除“Release 是 v0.7，但程序内部仍显示 v0.4”这一类商业交付风险。

### 工作项

- [x] 建立 `_version.py` 单一版本来源。
- [x] `pyproject.toml` 改为动态读取统一版本。
- [x] Release workflow 从 Git tag 注入正式版本。
- [x] GUI 标题显示真实软件版本。
- [x] `conversion_metadata.json` / batch summary 继续读取同一 `__version__`。
- [x] 建立 `dcm_analysis_widget.py` 稳定 GUI 入口。
- [x] 主界面不再直接依赖 `dcm_zero_span_widget_v10`。
- [x] `DCM → Zero Span` 页签调整为 `DCM 综合分析`。
- [x] AppState 增加稳定 `selected_tab_id`，同时兼容旧数字索引。
- [x] README 更新到当前五工作区和四视图能力。
- [x] Release 使用说明更新为当前功能集。
- [x] CHANGELOG 补齐 v0.5 / v0.6 / v0.7 与 v0.8 开发说明。
- [x] 增加版本一致性自动测试，并兼容 main 开发版本与 tag 正式版本。
- [x] Tests workflow 增加同分支并发取消、20 分钟硬超时和慢测试统计，防止 GUI 测试无限挂起。

### 验收

- `main` 显示 `0.8.0.dev0`。
- tag `vX.Y.Z` 构建出的 Python 包、GUI、metadata、Release 均显示 `X.Y.Z`。
- 老 `app_state.json` 仍可恢复。
- 新增/调整页签后不会因数字索引变化打开错误页。

---

## Phase 2：架构收口

目标：把快速迭代阶段形成的多层 `v2...v10` 继承结构整理为正式可维护模块。

### 目标结构

```text
src/scope_zero_span_converter/
  dcm_analysis/
    __init__.py
    widget.py
    model.py
    spectrum.py
    phase.py
    plots.py
    axis.py
    zoom.py
    peaks.py
    markers.py
    time_markers.py
    exporter.py
    state.py
```

### 工作项

- [x] 保持 `dcm_analysis_widget.py` 作为稳定兼容入口。
- [x] 抽离 FFT 幅度/相位计算为纯算法模块 `dcm_analysis/spectrum.py`。
- [x] 抽离坐标自动/手动/回填公共逻辑到 `dcm_analysis/axis.py`。
- [x] 抽离 Rectangle zoom / Space history 状态到 `dcm_analysis/zoom.py`。
- [x] 抽离 Peak 检测、频域 Marker、时域 Marker 为独立模型模块。
- [x] 抽离综合分析导出逻辑到 `dcm_analysis/exporter.py`，GUI 只负责选择目录和传入当前状态。
- [ ] 抽离四图绘制层。
- [ ] 将 v4~v10 行为合并到正式 widget。
- [ ] 保留旧模块一段兼容期，但主程序与新测试不再引用旧版本模块。
- [ ] DCM parameter extractor / generator 同样建立稳定入口，停止继续增加 `*_vN`。

### 验收

- 主程序只引用正式稳定模块。
- 四视图行为与 v0.7 完全一致。
- 旧 JSON / CSV 兼容测试全部通过。
- 不再新增版本号 widget 文件。

---

## Phase 3：数据可靠性与物理有效性

目标：商业软件不能只“能算”，还必须明确告诉客户什么时候结果可信、什么时候不可信。

### 输入数据质量

- [x] `WaveformQualityReport`：点数、起止时间、duration、Fs、Nyquist、dt median、dt jitter。
- [x] 重复时间戳检测。
- [x] 非递增/时间倒序检测与可追溯 WARNING。
- [x] 非均匀采样检测。
- [x] 大间隔/疑似缺点检测。
- [x] GUI 显示 `PASS / WARN / FAIL` 相关质量信息。
- [x] FFT / Zero Span 在严重时间轴异常时拒绝计算，而不是只用 median(dt) 继续。
- [x] 建立 `waveform_io.py` 统一安全 CSV 加载入口，并记录清理无效行数量。
- [x] DCM 参数提取 GUI 接入同一质量门禁。
- [x] 波形研究 ROI 转换补齐统一质量门禁和 `waveform_quality` 结果，保持 ROI 相对时间轴及不重采样语义不变。
- [x] 批量 summary 增加质量状态、dt 最大偏差、最大间隔比。
- [x] 核心 DCM extractor 删除旧 5% 时间轴容差，统一复用 `WaveformQualityReport` 的均匀采样策略；DCM 算法额外保留严格递增要求。

### Zero Span

- [x] FSW Sweep Time 超出 Scope 实际时间范围时禁止静默首尾值延伸。
- [x] 增加明确的 Sweep/Scope 时间覆盖检查。
- [x] 保持 `Center + RBW/2 < Nyquist`。
- [x] 保持 `Center + RBW/2 <= Scope analog BW`。
- [ ] 明确“名义 Sweep Time 与最后一个采样点相差一个 dt”时的边界容差策略，并用实机 metadata 验证。

### FFT / Phase

- [x] 明确 FFT：去 DC / Hann / single-sided / peak dBV per bin 定义。
- [x] 相位显示 `Wrapped Phase` 和参考定义。
- [x] 明确：相位参考当前记录/FFT 窗口，不等同于网络分析仪器件绝对相位。
- [x] 相位有效门限升级为“绝对门限 + 相对峰值 60 dB 动态范围”策略，并记录实际有效阈值。

### 验收

- 异常 CSV 有明确诊断。
- 不产生静默伪数据。
- 每个物理限制都有自动测试。

---

## Phase 4：商业使用体验与诊断

目标：让无开发背景客户也能稳定完成分析，并能把问题反馈回来。

### 分析体验

- [x] 时域 Marker A / B / ΔT / ΔV；Marker 吸附真实采样点并同步标记 Zero Span 时间轴。
- [x] 频域 Marker：Frequency / Magnitude / Phase 同频联动。
- [x] FFT Peak Table；直接复用当前幅相 FFT bins，不重复计算另一份频谱。
- [x] Center / RBW 信息卡；明确 Span=0、3 dB 接收带宽、VBW、Scope BW、Fs/Nyquist 与当前有效性。
- [x] 一键导出当前四图 PNG、DCM 时域 CSV、Zero Span Time-vs-Power CSV、幅相频谱 CSV 与 `analysis_metadata.json`。
- [x] 分析导出 metadata 明确 Zero Span/FFT 语义，并主动排除 Rectangle Zoom 临时历史。

### Workspace

- [x] AppState 升级到 schema v3，并继续兼容旧 schema v1/v2。
- [x] 保存 DCM 当前参数。
- [x] 保存 Zero Span Profile。
- [x] 保存图表基础坐标输入范围。
- [x] 保存折叠面板状态。
- [x] 保存 DCM 综合分析左右 Splitter 比例。
- [x] 保存频域 Marker 与时域 A/B Marker 状态。
- [ ] 保存最近文件；等待统一 File/Project 模型后实现，不从 QLabel 文本反向解析路径。
- [x] 不保存临时 zoom history。

### 性能

- [ ] 大 CSV FFT 放入 Worker。
- [ ] 全局精修放入 Worker。
- [ ] 批量转换支持 Progress。
- [ ] 支持 Cancel。
- [ ] GUI 主线程不长时间阻塞。

### 日志/诊断

- [x] RotatingFileHandler。
- [x] 日志限制为单文件 10 MB、保留 5 个历史文件。
- [x] 已有“打开日志目录”入口。
- [x] GUI 增加“一键导出诊断包”。
- [x] 诊断包包含软件版本、OS/Python 运行环境和轮转日志。
- [x] 诊断包默认不包含客户原始波形和参数/config 文件。
- [ ] 后续增加可选的客户主动授权附件机制时，必须显式勾选而不能默认收集。

---

## Phase 5：正式商业发布

目标：进入 `v1.0.0` 前完成安装、许可、品牌和真实设备验收。

### 发布

- [ ] Windows Installer (`Setup-v1.0.0.exe`)。
- [ ] Start Menu / Desktop shortcut / uninstall。
- [ ] EXE VersionInfo：ProductName / FileVersion / ProductVersion / Company。
- [ ] 正式应用 icon。
- [ ] Windows code signing。

### 合规

- [ ] 第三方依赖清单。
- [ ] PySide6 / Qt 分发许可审查。
- [ ] NOTICE。
- [ ] EULA。
- [ ] Copyright / Company 信息。
- [ ] 明确源码公开/私有与商业授权策略。

### 验收数据

- [ ] DSO-X 3034A + FSW 实机固定验收数据集。
- [ ] 200 MHz / RBW 10 MHz 基线验收。
- [ ] 多组 Center/RBW/VBW 验收。
- [ ] FSW MAE/RMSE/Bias 门限记录。
- [ ] DCM 参数提取真实波形适用边界记录。

### 客户资料

- [ ] 快速上手手册。
- [ ] 数据格式说明。
- [ ] 参数物理含义说明。
- [ ] 常见错误与诊断手册。
- [ ] Release Notes。

---

## 版本规划

```text
v0.7.0  功能基线：时域 + Zero Span + 幅度频谱 + 相位频谱
v0.8.x  产品/架构/数据可靠性整改
v0.9.x  Customer Beta：Marker、Peak、Workspace、后台任务、诊断
v1.0.0  正式商业发布
```
