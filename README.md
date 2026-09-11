# Scope Zero Span Converter

示波器时域波形研究、DCM SW 建模/参数识别、幅相频域分析与 Zero Span 联动转换工具。

> 当前稳定客户版本：**v0.7.0**  
> 当前 `main` 开发版本：**v0.8.0.dev0**（v1.0 发布候选验证中，尚未发布 v1.0.0）

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
   - 后台全局联合精修，可安全取消并保留前三阶段结果和当前参数
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

Windows 用户数据位于 `%LOCALAPPDATA%\ScopeZeroSpanConverter`：`logs/` 保存日志，
`templates/` 保存用户模板，`app_state.json` 保存最近状态/Workspace。旧版用户目录中的
状态和模板首次迁移时会复制保留，不覆盖已存在的新文件。程序关闭时会等待必要的后台
保存完成，避免损坏输出。

GUI 提供“导出诊断包”，生成 ZIP 供客户支持定位问题。默认包含：

- 软件版本
- OS / Python 运行环境
- 当前应用轮转日志

默认**不包含**客户波形、参数 JSON 或配置快照。

## 安装与运行

Windows 客户端支持 **Windows 10 1809+ / Windows 11 x64**，建议 8 GB 内存。
无需安装 Python；推荐使用仍受支持的 Windows 版本。

从 [项目 Releases](https://github.com/yunfei00/scope-zero-span-converter/releases) 获取对应版本：

- 推荐：运行 `ScopeZeroSpanConverter-Setup-<version>.exe`，默认安装到 Program Files，
  创建开始菜单快捷方式，可选桌面快捷方式。安装需要管理员授权，日常运行不需要。
- Portable：完整解压 `ScopeZeroSpanConverter-v<version>-Windows-x64.zip` 后运行
  `ScopeZeroSpanConverter.exe`；保留 `_internal` 目录。

新安装器用于即将发布的版本；历史 v0.7.0 Release 可能只有 portable ZIP。
当前没有配置数字签名证书的构建显示未知发布者，Windows 可能触发 SmartScreen。
请使用可信发布页面并核对 `SHA256SUMS.txt`。不要关闭系统安全防护。

升级运行新版安装器即可；卸载保留用户模板、日志、状态及生成数据。
详见 [Windows 安装说明](docs/WINDOWS_INSTALLATION.md)。

源码开发环境：

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

## 输出与快速上手

先在“波形研究”选择 `time_s,voltage_v` CSV 与 metadata，确认采样质量摘要，再设置
Center/RBW、选择输出目录并转换。也可先在“DCM SW 生成器”生成一个事件，发送到
波形研究；在“DCM 参数提取”载入波形完成前三阶段分析后，再按需精修/人工调整。

- 单次/批量 Zero Span：功率-时间 CSV、PNG、转换 metadata、可选 FSW 对比 CSV；
  批量另保存 summary CSV/JSON。
- Generator：标准波形 CSV 与可往返的参数 JSON。
- Extractor：参数 JSON、包含源波形/重建/残差/分量的 reconstruction CSV。
- DCM 综合分析：当前四图 PNG、DCM/Zero Span/Spectrum CSV 与 analysis metadata；
  快照仍在更新时暂不允许导出。

打包程序的相对输出目录写入用户数据目录下的 `output/` 或 `batch_output/`；
可以选择任意可写的绝对目录。不要把客户文件放进 Program Files 安装目录。

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
- FSW Sweep Time 不得超出实际记录范围；仅允许浮点舍入误差，不会复制末值扩展一整个采样间隔。
- DSO-X 3034A 的 350 MHz 模拟带宽是物理限制，不能通过提高数字采样率恢复超出模拟前端带宽的 RF 内容。

## 开发与发布

正式 GUI 入口为 `app.py → main_window.py`，页面位于 `dcm_analysis/`、
`dcm_generator/`、`dcm_extractor/`；历史版本化 GUI 已从源码树退休。
开发者发布操作见 [Release process](docs/RELEASE_PROCESS.md)，进度见
[Roadmap](docs/COMMERCIALIZATION_ROADMAP.md)。人工确认前不创建 v1.0.0 tag。

## 研究文档

- [DCM 模式开关电源 SW 节点参数化波形生成模型说明](docs/DCM_SW_WAVEFORM_GENERATION_THEORY.md)

## License / 商业分发

第三方信息见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)。当前产品自身未另行授予
MIT/Apache 等开源许可；EULA、版权主体和组织合规复核由产品所有者在对外分发前确认，
见 [商业分发确认清单](docs/RELEASE_COMPLIANCE_CHECKLIST.md)。
