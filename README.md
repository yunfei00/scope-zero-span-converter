# Scope Zero Span Converter

示波器 Zero Span 离线转换工具。

用于将示波器采集的时域波形，按照 Center、RBW、VBW、Detector、阻抗和校准参数，离线转换为类似频谱仪 Zero Span 模式下的功率-时间曲线。

> 项目定位：**独立离线转换工具**。不负责连接或控制示波器、频谱仪；仪表采集由其他系统完成，本工具负责 `waveform.csv + metadata.json -> Zero Span 时域结果`。

当前版本：**v0.3.0 开发基线**。

## 转换链路

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

## v0.3 当前功能

### 单次转换

- PySide6 中文 GUI
- `waveform.csv + metadata.json` 转换
- 可选导入 FSW Zero Span 实测 CSV
- Center / Span / RBW / VBW 参数
- 可选择优先使用 metadata 参数或 GUI/JSON 参数
- RMS Detector
- Gaussian RBW Filter
- VBW 开关
- FSW Sweep Time / Points 时间轴重采样
- 50 Ω 阻抗与 dB 校准
- 示波器模拟带宽保护
- 原始时域 + Zero Span 时域上下对比图
- Matplotlib 中文字体自动适配
- FSW 实测曲线叠加
- MAE / RMSE / Bias / 最大误差 / 相关系数
- `conversion_metadata.json` 转换记录
- `comparison_to_fsw.csv` 对比数据

### 批量转换

GUI 新增“批量转换”页签，可以一次处理整个目录树。

默认要求每个任务目录包含：

```text
case_001/
├─ waveform.csv
└─ metadata.json

case_002/
├─ waveform.csv
└─ metadata.json
```

如果还需要与 FSW 实测值比较，可以统一指定 FSW 文件名，例如：

```text
case_001/
├─ waveform.csv
├─ metadata.json
└─ fsw_zero_span.csv
```

批量输出保持原目录层级：

```text
batch_output/
├─ case_001/
│  ├─ zero_span_from_scope.csv
│  ├─ waveform_zero_span_compare.png
│  ├─ conversion_metadata.json
│  └─ comparison_to_fsw.csv
├─ case_002/
│  └─ ...
├─ batch_summary.csv
└─ batch_summary.json
```

批量汇总记录：

- 成功/失败状态
- Center
- RBW
- VBW
- Scope Sample Rate
- MAE
- RMSE
- Bias
- Correlation
- 输出目录
- 错误原因

单个任务失败时默认继续执行后续任务。

### 配置模板

除了普通 JSON 配置加载/保存，v0.3 增加客户模板管理：

- 另存为模板
- 加载模板
- 删除模板
- 刷新模板
- 打开模板目录

模板默认保存在用户目录：

```text
~/ScopeZeroSpanConverter/templates/
```

例如可以保存：

```text
客户A_200M_10M.json
客户B_210M_5M.json
实验室默认.json
```

v0.1 / v0.2 保存的 JSON 仍然兼容，缺失的 v0.3 字段自动使用默认值。

### 日志

应用日志默认保存到：

```text
~/ScopeZeroSpanConverter/logs/scope-zero-span-converter.log
```

GUI 可直接点击“打开日志目录”。转换失败、批量失败和配置异常都会写入日志，便于客户现场问题定位。

## 默认参数

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

默认优先读取 `metadata.json` 中可用的 FSW Center / RBW / VBW；如果取消“优先使用 metadata”，则完全使用 GUI / JSON 参数。

## 输入格式

### Waveform

推荐：

```csv
time_s,voltage_v
0.0,...
...
```

### FSW Zero Span 实测 CSV

支持仓库当前 Zero Span 标准：

```csv
time_s,amplitude_dbm
0.0,...
...
```

## 单次输出

默认：

```text
output/
├─ zero_span_from_scope.csv
├─ waveform_zero_span_compare.png
├─ conversion_metadata.json
└─ comparison_to_fsw.csv      # 提供 FSW 实测 CSV 时
```

`zero_span_from_scope.csv`：

```csv
time_s,amplitude_dbm,envelope_v_rms
...
```

## JSON 配置

默认配置：

```text
configs/default.json
```

配置完整覆盖：

- 单次输入文件
- FSW 实测参考文件
- Center / Span / RBW / VBW
- 参数来源策略
- Detector / RBW Filter / VBW
- 阻抗 / Calibration
- Scope 模拟带宽
- FSW 对比设置
- 单次输出设置
- 批量输入根目录
- 批量文件名规则
- 是否递归扫描
- 出错后是否继续
- 批量汇总输出

配置继续使用 `schema_version = 1`，v0.3 新字段都有默认值，以保证旧配置兼容。

## 安装开发版

建议 Python 3.11+：

```bash
pip install -e .
```

开发测试：

```bash
pip install -e ".[dev]"
pytest
```

## GUI

```bash
scope-zero-span-gui
```

或者：

```bash
python -m scope_zero_span_converter.gui
```

GUI 有两个主页面：

```text
单次转换
批量转换
```

## CLI 单次转换

```bash
scope-zero-span-converter convert waveform.csv metadata.json
```

带 FSW 参考：

```bash
scope-zero-span-converter convert waveform.csv metadata.json \
  --fsw-reference fsw_zero_span.csv
```

## CLI 批量转换

先在 JSON 中配置 `batch`，然后：

```bash
scope-zero-span-converter batch --config customer-config.json
```

也可以临时覆盖目录：

```bash
scope-zero-span-converter batch \
  --config customer-config.json \
  --source data \
  --output batch_output
```

## Windows 自动发布

仓库已经配置：

```text
.github/workflows/release.yml
```

推送 `v*` Tag 后自动：

1. Windows Python 3.11 构建；
2. `compileall + pytest`；
3. PyInstaller onedir 打包；
4. 打包 Windows x64 ZIP；
5. 自动创建 GitHub Release；
6. 上传 Release 附件。

例如：

```bash
git tag -a v0.3.0 -m "v0.3.0"
git push origin v0.3.0
```

客户下载 ZIP 后解压并运行：

```text
ScopeZeroSpanConverter.exe
```

## 重要说明

### 示波器带宽

目标 `Center + RBW/2` 必须位于示波器模拟前端有效带宽内。当前默认按 DSO-X 3034A 的 350 MHz 模拟带宽检查。

### 绝对 dBm

如果示波器支路与频谱仪支路的功分器、线缆、阻抗、探头或衰减不同，绝对 dBm 应通过 `calibration_db` 标定。

### Zero Span 不是普通频谱

例如 `Center=200 MHz, Span=0` 表示固定在 200 MHz 附近经过 RBW 滤波后观察功率随时间变化，所以输出横轴必须是 `time_s`。

## 版本演进

### v0.1

- Zero Span 核心算法
- JSON 配置
- CLI
- 基础 GUI
- 中文绘图
- Windows 自动 Release

### v0.2

- FSW 实测 CSV 对比
- MAE / RMSE / Bias 等误差指标
- conversion metadata
- 参数来源显示

### v0.3

- 单次 / 批量双页签 GUI
- 递归批量转换
- 批量结果表格
- batch_summary.csv / JSON
- 客户配置模板管理
- 应用日志
- 旧 JSON 配置兼容

### 后续 v1.0

- 客户正式版本
- 完整用户说明书
- 更完整的 Detector / RBW 模型
- 校准流程与标定模板
- 更严格的版本兼容策略
