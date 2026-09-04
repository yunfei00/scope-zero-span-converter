# Scope Zero Span Converter

示波器时域波形研究、区域截取与 Zero Span 联动转换工具。

> 当前重点已经从“继续提高频谱恢复精度”切换到 **原始波形研究与波形区域提取**。现有 Zero Span 算法先作为稳定基线保留，后续有需要再继续研究。

当前开发版本：**v0.4.0**。

## 研究文档

面向研究人员的 DCM SW 参数化波形生成理论说明：

- [DCM 模式开关电源 SW 节点参数化波形生成模型说明](docs/DCM_SW_WAVEFORM_GENERATION_THEORY.md)

文档说明模型的物理背景、时间定义、理想边沿、有限边沿、尖峰/寄生振铃、DCM 断续谐振、指数衰减、示波器底噪、采样率、真值分量及模型适用边界，并给出从合成波形走向真实波形参数提取的推荐研究路线。

## v0.4 核心工作流

```text
原始 waveform.csv
        ↓
加载完整时域波形
        ↓
在图上鼠标框选研究区域 ROI
        ↓
查看起点 / 终点 / 时长 / 点数
        ↓
放大到选区 / 恢复全波形 / 重新框选
        ↓
保存截取后的 waveform CSV
        ↓
下方 Zero Span 转换波形按当前 ROI 自动重新计算
```

当前先实现 **通用手动 ROI**。后续针对 DCM SW 波形的自动识别、周期定位、边沿判定、脉冲/开关段提取等逻辑，会作为独立提取策略继续加入，不需要重新设计 GUI 和数据接口。

同时新增 **DCM SW 生成器**，用于根据已知参数生成可解释、可重复、真值已知的合成波形，为后续自动提取算法研究提供受控实验数据。

## 波形研究功能

### 1. 鼠标框选研究区域

加载 `waveform.csv` 后，在上方原始波形图中按住鼠标左键横向拖动，即可得到一个研究区域。

工具自动记录：

- ROI 起始时间
- ROI 结束时间
- ROI 时长
- ROI 点数
- 原始波形中的起始/结束索引

左侧也可以直接输入起点和终点，通过数值精确设置 ROI。

### 2. 放大、恢复和重新截取

支持：

- `放大到选区`
- `恢复全波形`
- `清除选区`
- 恢复全波形后重新拖动选择新的 ROI
- Matplotlib 自带 Zoom / Pan / Home 工具栏

因此研究过程不是“一次裁剪后就固定”，可以反复定位和调整。

### 3. 保存截取数据

点击 `保存截取波形 CSV` 后输出标准：

```csv
time_s,voltage_v
...
```

默认还会生成同名：

```text
xxx_region.region.json
```

用于记录：

- 原 waveform 文件
- 起止时间
- 持续时间
- 点数
- 原始索引
- 保存后的时间轴是否从 0 开始

可选择：

- 保留原始时间轴
- 保存时将截取区域时间轴重新从 0 开始

### 4. 下方转换波形实时联动

默认勾选：

```text
研究区域变化后自动更新下方转换波形
```

ROI 改变后：

```text
当前 ROI waveform
        ↓
现有 Center / RBW / VBW 算法
        ↓
下方功率-时间曲线自动刷新
```

研究模式下 **不会把 ROI 强行重采样回原始 FSW Sweep Time / Points**，下方时间轴始终对应当前选中的真实波形区域。

## DCM SW 参数化波形生成器

`DCM SW 生成器`页面不需要加载真实数据即可直接生成单个 DCM 开关事件。

当前支持：

- 基线电压
- 开通高电平电压
- 续流低电平电压
- 总显示时长
- 开关起始时间
- 导通时间
- 续流时间
- 上升沿时间 / 下降沿时间（允许 `0 ns` 表示理想阶跃）
- 上升沿尖峰电压 / 下降沿尖峰电压（支持正负方向）
- 尖峰寄生振荡频率和衰减速率
- DCM 断续谐振初始振幅、频率和衰减速率
- 示波器底噪 RMS
- 采样率
- 固定随机种子

主要参数采用“滑块粗调 + 数值框精调”双向联动。

生成后的波形可保存为 CSV 和参数真值 JSON，也可重新加载历史合成波形，或者直接发送到“波形研究”页面进行 ROI 研究。

默认仅显示大的最终 SW 主波形；需要算法研究时可勾选“显示真值分量分析”，查看尖峰/振铃、DCM 断续谐振和底噪等独立分量。

完整理论见：

- [DCM 模式开关电源 SW 节点参数化波形生成模型说明](docs/DCM_SW_WAVEFORM_GENERATION_THEORY.md)

## 当前 Zero Span 算法基线

```text
示波器时域 waveform
        ↓
Center Frequency 数字下变频
        ↓
Gaussian RBW
        ↓
RMS 功率检波
        ↓
VBW 时域平滑
        ↓
time_s, amplitude_dbm
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

这个算法当前先保持稳定，不作为 v0.4 的主要研究方向。

## GUI

安装：

```bash
pip install -e .
```

运行：

```bash
scope-zero-span-gui
```

GUI 当前三个主页面：

```text
波形研究
DCM SW 生成器
批量转换
```

其中 `波形研究` 和 `DCM SW 生成器` 是 v0.4 的主要研究页面。

## 输入文件

### Waveform

推荐格式：

```csv
time_s,voltage_v
0.0,...
...
```

### Metadata

`metadata.json` 用于当前 Zero Span 联动转换时读取 Center / RBW / VBW 等参数。

### FSW 实测 CSV

原有完整转换功能继续支持可选：

```csv
time_s,amplitude_dbm
...
```

## JSON 配置

默认：

```text
configs/default.json
```

v0.4 新增：

```json
"waveform_research": {
  "enabled": true,
  "extraction_mode": "manual",
  "selection_start_s": null,
  "selection_end_s": null,
  "auto_update_conversion": true,
  "time_unit": "us",
  "min_points": 32,
  "save_region_metadata": true,
  "reset_saved_time_to_zero": false
}
```

继续保持：

```text
schema_version = 1
```

因此 v0.1 / v0.2 / v0.3 JSON 缺少 `waveform_research` 时，会自动使用默认值。

## v0.3 已保留能力

- 单次完整 Zero Span 转换
- FSW 实测 CSV 对比
- MAE / RMSE / Bias / 最大误差 / 相关系数
- `conversion_metadata.json`
- `comparison_to_fsw.csv`
- 配置模板
- 最近使用状态
- 应用日志
- 批量转换
- `batch_summary.csv / json`
- Windows Tag 自动 Release

## Windows 自动发布

推送 `v*` Tag 后自动：

1. Windows Python 3.11 测试；
2. PyInstaller onedir 打包；
3. 生成 Windows x64 ZIP；
4. 自动创建 GitHub Release。

## 版本演进

### v0.1

Zero Span 算法、JSON、GUI、CLI、Windows 自动发布。

### v0.2

FSW 实测对比、误差指标、转换元数据。

### v0.3

批量转换、客户配置模板、日志、最近使用状态。

### v0.4

当前阶段：

- 原始波形研究
- ROI 手动框选
- 数值起止时间
- ROI 放大/恢复/重新选择
- 截取波形保存
- 截取参数记录
- ROI 与下方 Zero Span 转换联动
- DCM SW 参数化真值波形生成
- 参数滑块与输入框实时联动
- 0 ns 理想上升沿/下降沿
- 有符号开关尖峰
- 合成波形 CSV + 参数 JSON 保存与重新加载
- 真值分量按需显示
- 为后续 DCM SW 自动提取算法预留统一接口

## 后续 DCM SW 提取

待拿到真实 DCM SW 波形和客户规则后，重点研究：

- 如何定义一个完整有效波形段
- 周期/重复单元识别
- 上升沿/下降沿
- 高低电平阈值
- 脉冲宽度
- 开关瞬态区域
- 前后保护时间
- 自动选择一个或多个研究区域
- 批量提取一致性

这部分会在现有 `waveform_research` 框架上继续实现。
