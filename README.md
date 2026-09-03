# Scope Zero Span Converter

示波器 Zero Span 离线转换工具。

用于将示波器采集的时域波形数据，按照中心频率、RBW、VBW、检波方式、阻抗及校准参数，离线转换为类似频谱仪 Zero Span 模式下的功率-时间曲线。

> 当前项目定位：**独立离线转换工具**。不负责连接或控制示波器、频谱仪；仪表采集由其他系统完成，本工具只负责 `waveform.csv + metadata.json -> Zero Span 时域结果`。

## 当前转换链路

```text
示波器时域 waveform.csv
        ↓
按 Center Frequency 数字下变频到基带
        ↓
Gaussian RBW 滤波
        ↓
RMS 功率检波
        ↓
VBW 时域平滑
        ↓
按 FSW Sweep Time / Points 重采样
        ↓
time_s, amplitude_dbm
```

最终结果是 **功率随时间变化**，不是普通 FFT 频谱。

## v0.2 当前功能

- PySide6 中文参数 GUI
- 选择 `waveform.csv` 与 `metadata.json`
- 可选导入 FSW Zero Span 实测 CSV
- Center / Span / RBW / VBW 参数
- 可选择是否优先使用 metadata 中的 FSW 参数
- GUI 显示 Center / RBW / VBW 的实际参数来源
- RMS Detector
- Gaussian RBW Filter
- VBW 开关
- FSW Sweep Time / Points 时间轴重采样
- 50 Ω 阻抗及 dB 校准
- 示波器模拟带宽保护
- JSON 配置保存与加载
- v0.1 JSON 配置向后兼容
- Zero Span CSV 导出
- 原始时域 + Zero Span 时域上下对比图
- FSW 实测与恢复曲线叠加
- MAE / RMSE / Bias / 最大误差 / 相关系数
- 对齐后的 `comparison_to_fsw.csv`
- 自动生成 `conversion_metadata.json`
- Matplotlib 中文字体自动适配（Windows 优先 Microsoft YaHei）
- CLI 命令行模式
- 合成 200 MHz CW 自动测试
- GitHub CI 自动测试
- `v*` Tag 自动构建 Windows x64 ZIP 并创建 GitHub Release

## 输入

必选：

```text
waveform.csv
metadata.json
```

可选：

```text
FSW Zero Span 实测 CSV
```

标准示波器波形格式：

```csv
time_s,voltage_v
0.0,...
...
```

FSW Zero Span 参考格式：

```csv
time_s,amplitude_dbm
0.0,...
...
```

也兼容 `level_dbm` / `power_dbm` 作为功率列名。

## 输出

默认输出：

```text
output/
├─ zero_span_from_scope.csv
├─ waveform_zero_span_compare.png
├─ conversion_metadata.json
└─ comparison_to_fsw.csv        # 提供 FSW 实测 CSV 时生成
```

Zero Span CSV：

```csv
time_s,amplitude_dbm,envelope_v_rms
...
```

FSW 对比 CSV：

```csv
time_s,reconstructed_dbm,fsw_reference_dbm,error_db
...
```

## conversion_metadata.json

每次转换可自动保存完整转换记录，包括：

- 软件版本
- 转换时间
- 输入文件路径
- 实际 Center / RBW / VBW
- 参数来自 metadata 还是 GUI/JSON
- Detector / RBW Filter / VBW
- 阻抗和校准值
- 示波器采样率
- 输入点数 / 输出点数
- FSW Sweep Time / Trace Points
- 是否执行 FSW 时间轴重采样
- FSW 对比误差指标
- 完整配置快照

这样后续拿到某条结果时，可以追溯它到底是用什么参数生成的。

## JSON 配置

项目使用 JSON 保存整个转换过程参数，默认配置位于：

```text
configs/default.json
```

配置包含：

- waveform / metadata 路径
- 可选 FSW 实测 CSV 路径
- Center Frequency
- Span（Zero Span 固定为 0）
- RBW
- VBW
- 是否优先使用 metadata 参数
- Detector
- RBW Filter
- 输入阻抗
- dB 校准值
- 示波器模拟带宽
- 是否按 FSW 时间轴重采样
- 是否进行 FSW 对比
- 输出目录与保存选项

配置文件继续使用 `schema_version = 1`。v0.2 新增字段都有默认值，因此 v0.1 保存的 JSON 可以直接加载。

## 当前默认基线

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

默认勾选“优先使用 metadata 中的 FSW 参数”。如果取消勾选，则完全使用 GUI / JSON 中的 Center、RBW、VBW 参数。

## 安装

建议 Python 3.11+：

```bash
pip install -e .
```

开发测试：

```bash
pip install -e ".[dev]"
pytest
```

## GUI 使用

```bash
scope-zero-span-gui
```

或者：

```bash
python -m scope_zero_span_converter.gui
```

GUI 中可以：

1. 选择 waveform CSV 与 metadata JSON；
2. 可选选择 FSW Zero Span 实测 CSV；
3. 修改整个转换过程参数；
4. 保存为客户自己的 JSON 模板；
5. 下次直接加载 JSON 恢复参数；
6. 点击“开始转换”；
7. 查看原始时域波形和恢复后的 Zero Span 功率-时间曲线；
8. 有 FSW 实测数据时直接叠加比较并显示误差指标。

## CLI 使用

普通转换：

```bash
scope-zero-span-converter convert waveform.csv metadata.json
```

指定配置：

```bash
scope-zero-span-converter convert waveform.csv metadata.json --config configs/default.json
```

加入 FSW 实测对比：

```bash
scope-zero-span-converter convert waveform.csv metadata.json --fsw-reference fsw_zero_span.csv
```

生成新的默认配置：

```bash
scope-zero-span-converter init-config customer-config.json
```

## Tag 自动发布 Windows 版本

仓库已配置 `.github/workflows/release.yml`。

推送符合 `v*` 的 Tag 后，会自动：

1. 在 `windows-latest` 上安装 Python 3.11 与依赖；
2. 执行 `compileall` 和 `pytest`；
3. 使用 PyInstaller 构建 `ScopeZeroSpanConverter.exe`；
4. 使用 onedir 方式保留 Qt / Matplotlib 运行依赖，提高稳定性；
5. 将程序、README 和默认 JSON 配置打包为 ZIP；
6. 自动创建 GitHub Release 并上传 ZIP。

例如：

```bash
git tag -a v0.2.0 -m "v0.2.0 FSW 对比与转换记录版本"
git push origin v0.2.0
```

Release 附件名称类似：

```text
ScopeZeroSpanConverter-v0.2.0-Windows-x64.zip
```

## 重要说明

### 示波器带宽

转换目标频率必须位于示波器模拟前端有效带宽内。当前默认按 DSO-X 3034A 的 350 MHz 模拟带宽检查。

### 绝对 dBm 校准

如果示波器支路与频谱仪支路的功分器、线缆、阻抗、探头或衰减不同，则曲线形状可以直接比较，但绝对 dBm 应通过 `calibration_db` 校准。

### FSW 对比不自动“找最佳对齐”

v0.2 按两条曲线的真实共同时间范围直接比较，不自动平移时间轴去获得更漂亮的误差。如果后续确认存在固定链路时延，可以再增加显式 Time Offset 校准参数。

### Zero Span 不是普通频谱

例如 `Center=200 MHz, Span=0`，表示固定在 200 MHz 附近通过 RBW 滤波器观察功率随时间变化，因此输出横轴必须是 `time_s`。

## 版本规划

### v0.1 已发布

- 转换核心模块化
- JSON 配置加载/保存
- CLI
- PySide6 GUI
- 上下时域预览
- Matplotlib 中文字体适配
- 基础算法测试
- GitHub CI
- Windows PyInstaller 构建
- Tag 自动创建 Release

### v0.2 开发中

- GUI 参数来源提示
- 转换参数校验
- `conversion_metadata.json`
- FSW 实测 CSV 对比
- MAE / RMSE / Bias 等误差指标
- 对比 CSV 导出
- v0.1 JSON 向后兼容

### v1.0

- 客户正式版本
- 稳定配置兼容
- 完整日志
- 用户说明书
