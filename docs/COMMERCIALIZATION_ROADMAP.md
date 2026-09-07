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
- [ ] CHANGELOG 补齐 v0.5 / v0.6 / v0.7 与 v0.8 开发说明。
- [ ] 增加版本一致性自动测试。

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
    state.py
```

### 工作项

- [ ] 保持 `dcm_analysis_widget.py` 作为稳定兼容入口。
- [ ] 抽离 FFT 幅度/相位计算为纯算法模块。
- [ ] 抽离坐标自动/手动/回填逻辑。
- [ ] 抽离 Rectangle zoom / Space history。
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

- [ ] `WaveformQualityReport`：点数、起止时间、duration、Fs、Nyquist、dt median、dt jitter。
- [ ] 重复时间戳检测。
- [ ] 非递增时间检测。
- [ ] 非均匀采样检测。
- [ ] 大间隔/疑似缺点检测。
- [ ] GUI 显示 `PASS / WARNING / FAIL`。
- [ ] FFT / Zero Span 在严重时间轴异常时拒绝计算，而不是只用 median(dt) 继续。

### Zero Span

- [ ] FSW Sweep Time 超出 Scope 实际时间范围时禁止静默首尾值延伸。
- [ ] 增加明确的 Sweep/Scope 时间覆盖检查。
- [ ] 保持 `Center + RBW/2 < Nyquist`。
- [ ] 保持 `Center + RBW/2 <= Scope analog BW`。

### FFT / Phase

- [ ] 明确显示 FFT：去 DC / Hann / single-sided / dBV-bin 定义。
- [ ] 相位显示 `Wrapped Phase` 和参考定义。
- [ ] 明确：相位参考当前记录/FFT 窗口，不等同于网络分析仪器件绝对相位。
- [ ] 相位有效门限从固定 `-120 dBV` 升级为“绝对门限 + 相对峰值动态范围”策略。

### 验收

- 异常 CSV 有明确诊断。
- 不产生静默伪数据。
- 每个物理限制都有自动测试。

---

## Phase 4：商业使用体验与诊断

目标：让无开发背景客户也能稳定完成分析，并能把问题反馈回来。

### 分析体验

- [ ] 时域 Marker A / B / ΔT / ΔV。
- [ ] 频域 Marker：Frequency / Magnitude / Phase 联动。
- [ ] FFT Peak Table。
- [ ] Center / RBW marker 信息卡。
- [ ] 导出当前四图 PNG / CSV / analysis metadata。

### Workspace

- [ ] 保存 DCM 当前参数。
- [ ] 保存 Zero Span Profile。
- [ ] 保存图表基础坐标范围。
- [ ] 保存折叠面板状态。
- [ ] 保存 splitter 比例。
- [ ] 保存最近文件。
- [ ] 不保存临时 zoom history。

### 性能

- [ ] 大 CSV FFT 放入 Worker。
- [ ] 全局精修放入 Worker。
- [ ] 批量转换支持 Progress。
- [ ] 支持 Cancel。
- [ ] GUI 主线程不长时间阻塞。

### 日志/诊断

- [ ] RotatingFileHandler。
- [ ] 日志大小/保留数量限制。
- [ ] `帮助 → 打开日志目录`。
- [ ] `帮助 → 导出诊断包`。
- [ ] 诊断包包含 version / OS / config / latest logs，不包含原始客户波形，除非客户主动选择。

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
