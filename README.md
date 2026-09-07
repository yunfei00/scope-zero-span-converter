# Scope Zero Span Converter

示波器时域波形研究、DCM SW 建模/参数识别、幅相频域分析与 Zero Span 联动转换工具。

> 当前稳定客户版本：**v0.7.0**  
> 当前 `main` 开发版本：**v0.8.0.dev0**（商业化整改阶段）

## 产品定位

本项目最初用于把示波器时域波形离线转换为类似频谱仪 Zero Span 的功率-时间曲线。随着 DCM SW 波形研究能力完善，目前已经形成一个完整的 DCM 信号分析工作台：

```text
Scope waveform / DCM parameters
          │
          ├── 波形研究 / ROI
          ├── DCM SW 参数化生成
          ├── DCM 参数提取与联合精修
          ├── DCM 时域 / 幅度频谱 / 相位频谱 / Zero Span 四视图联动
          └── 批量 Zero Span 转换与 FSW 实测对比
```

## GUI 工作区

当前 GUI 有 5 个主要页面：

1. **波形研究**
   - 加载 `waveform.csv`、`metadata.json`
   - 可选加载 FSW Zero Span 实测 CSV
   - 鼠标框选 ROI、数值设置 ROI
   - 放大、恢复、清除选区
   - 保存 ROI CSV 与 `.region.json`
   - ROI 改变后 Zero Span 自动联动
   - 加载后显示采样质量摘要、Fs 与 Nyquist；严重非均匀采样/缺点会被拒绝

2. **DCM SW 生成器**
   - 单个 DCM 开关事件参数化建模
   - 绝对时间轴起点、总时长、采样率、噪声、随机种子
   - 高/低电平、上升/下降沿、导通/续流时间
   - 上升/下降尖峰、寄生振铃频率/衰减
   - DCM 断续谐振幅度/频率/衰减
   - 滑块粗调 + 数值框精调
   - 保存/加载 CSV + 参数 JSON
   - 可查看理想轨迹与真值分量

3. **DCM 参数提取**
   - 输入仅要求 `time_s,voltage_v`
   - 进入提取前执行统一时间轴质量门禁
   - 基础电平与时间参数提取
   - 开关沿尖峰/寄生振铃提取
   - DCM 断续谐振提取
   - 全局联合精修
   - RMSE / R² / 残差 / 置信度
   - 导出参数 JSON 与当前重建 CSV
   - 保留原始 CSV 的绝对时间轴起点

4. **DCM 综合分析**

```text
┌──────────────────────┬──────────────────────┐
│ DCM SW 时域           │ DCM 幅度频谱         │
│ Voltage vs Time      │ dBV vs Frequency    │
├──────────────────────┼──────────────────────┤
│ Zero Span            │ DCM 相位频谱         │
│ dBm vs Time          │ Phase vs Frequency  │
└──────────────────────┴──────────────────────┘
```

   - 全部 DCM 模型参数实时联动
   - 时域与 Zero Span 保持同一绝对时间轴
   - 幅度/相位来自同一次去直流 + Hann 窗的单边复数 FFT
   - 幅度频谱显示 Zero Span Center 与 RBW 区域
   - 幅度与相位共享 Frequency X 轴
   - 相位为当前 FFT 记录起点参考下的 Wrapped Phase
   - 相位有效性采用绝对门限 + 峰值向下 60 dB 动态范围联合策略
   - 左侧显示当前 FFT Top 8 峰值表：Frequency / Magnitude / Phase
   - 时域、幅度频谱支持鼠标框选放大，`Space` 逐级返回
   - 幅度频谱正常数据刷新时自动适配坐标，并回填实际坐标值
   - 可手工输入频域 X/Y Min / Max / Step 调整当前显示

5. **批量转换**
   - 递归扫描目录
   - 自动发现 waveform + metadata 任务
   - 单任务失败后继续
   - 独立输出目录
   - `batch_summary.csv` / `batch_summary.json`
   - 可汇总 FSW 对比误差
   - summary 同时记录输入质量状态、dt 最大偏差和最大间隔比，便于批量定位坏数据

## 输入数据质量门禁

`v0.8.0.dev0` 已建立统一时间轴检查。FFT、参数提取入口和 Zero Span 主转换不再只依赖 `median(dt)` 静默继续，而会检查：

```text
有效点数
时间起点 / 终点 / Duration
Median dt / Fs / Nyquist
重复时间戳
时间倒序
采样间隔最大偏差 / RMS 偏差
异常大间隔 / 疑似缺点
```

严重异常会拒绝进入 FFT / Zero Span；可排序恢复但原始顺序异常的数据会保留 WARNING 记录。转换后的 `conversion_metadata.json` 会保存 `time_axis_quality`，批量 summary 也保存关键质量字段。

## Zero Span 算法基线

当前稳定基线：

```text
real RF waveform
  → remove DC
  → reflect padding
  → 2*x*exp(-j2πfc t)
  → Gaussian complex baseband RBW filter
  → Vrms = abs(complex envelope)/sqrt(2)
  → power = Vrms² / impedance
  → optional causal first-order VBW lowpass
  → optional FSW sweep-time/points resample
  → dBm + calibration
```

默认参数：

```text
Center     = 200 MHz
Span       = 0 Hz
RBW        = 10 MHz
VBW        = 10 MHz
Impedance  = 50 Ω
Detector   = RMS
RBW Filter = Gaussian
Scope BW   = 350 MHz
```

物理边界检查：

```text
Center + RBW/2 < Nyquist
Center + RBW/2 <= Scope analog bandwidth
Span = 0
```

当开启 FSW Sweep Time / Points 重采样时，如果 FSW Sweep Time 明显超出示波器实际记录范围，程序会直接报错，不再静默用末值延伸生成伪数据。

## FSW 实测对比

可导入 FSW Zero Span 实测 CSV，并计算：

- MAE
- RMSE
- Bias
- Max Absolute Error
- Correlation

标准 FSW CSV：

```csv
time_s,amplitude_dbm
```

同时兼容 `level_dbm` / `power_dbm` 幅度列名。

## 输入格式

推荐示波器波形格式：

```csv
time_s,voltage_v
0.0,...
...
```

`metadata.json` 用于读取 FSW Center / Span / RBW / VBW / Sweep Time / Points 等信息。

## 日志与诊断

应用日志采用轮转策略：

```text
scope-zero-span-converter.log
单文件最大 10 MB
最多保留 5 个历史日志
```

GUI 提供“导出诊断包”，生成 ZIP 供客户支持定位问题。默认包含：

- 软件版本
- OS / Python 运行环境
- 当前应用轮转日志

默认**不包含**客户波形、参数 JSON 或配置快照。

## 安装与运行

开发环境：

```bash
pip install -e .
scope-zero-span-gui
```

CLI：

```bash
scope-zero-span-converter convert waveform.csv metadata.json
scope-zero-span-converter batch --config configs/default.json
scope-zero-span-converter init-config converter-config.json
```

Windows 客户版使用 GitHub Release 中的 `ScopeZeroSpanConverter-vX.Y.Z-Windows-x64.zip`，解压后运行 `ScopeZeroSpanConverter.exe`。

## 版本规则

版本只从 `src/scope_zero_span_converter/_version.py` 读取。

- `main` 使用下一开发版本，例如 `0.8.0.dev0`
- Release workflow 在 tag 构建时把 `vX.Y.Z` 注入 `_version.py`
- Python 包版本、GUI 标题、导出 metadata 和 Release 版本保持一致

## 当前限制

- DCM 参数提取当前主要针对**单个主要 DCM 开关事件**；多周期与复杂拓扑属于后续验证范围。
- 幅度频谱是当前记录的 Hann-window 单边 FFT（peak dBV/bin 语义），不能直接等同于频谱仪 trace。
- 相位频谱是当前 FFT 记录起点参考下的 wrapped phase（-180°~+180°），不是网络分析仪意义上的绝对器件相位；低能量频点相位会被隐藏。
- FFT / Zero Span 目前要求时间轴满足统一采样质量门禁；不支持直接对任意非均匀采样数据计算。
- FSW Sweep Time 与示波器最后采样点之间的名义边界（例如相差一个采样间隔）仍需要结合实机 metadata 固化最终容差规则。
- DSO-X 3034A 的 350 MHz 模拟带宽是物理限制，不能通过提高数字采样率恢复超出模拟前端带宽的 RF 内容。

## 商业化整改

`v0.8.x` 的重点不是继续堆图，而是产品化收口。当前已经完成/正在推进：

- 版本与发布一致性
- 稳定 GUI 入口与页签 ID
- `dcm_analysis` 的 spectrum / axis / zoom / peaks 正式模块
- 输入数据质量检查与可追溯 metadata
- FFT / Phase 物理定义与动态相位门限
- FSW Sweep 越界保护
- Rotating Log / 一键诊断包

后续继续：

- 完成四图绘制层与旧 `vN` 继承链收口
- Marker / Cursor
- Workspace 状态
- 后台计算 / Progress / Cancel
- Installer / VersionInfo / License / 客户手册

详细计划见 `docs/COMMERCIALIZATION_ROADMAP.md`。

## 研究文档

- [DCM 模式开关电源 SW 节点参数化波形生成模型说明](docs/DCM_SW_WAVEFORM_GENERATION_THEORY.md)

## License / 商业分发

正式商业版本发布前，需要单独完成第三方依赖许可、PySide6/Qt 分发合规、EULA、版权信息与 Windows 签名策略。当前仓库不应被视为已经完成这些商业许可审查。
