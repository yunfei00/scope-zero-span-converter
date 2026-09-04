# Scope Zero Span Converter

示波器时域波形研究、区域截取与 Zero Span 联动转换工具。

> 当前重点已经从“继续提高频谱恢复精度”切换到 **原始波形研究、DCM SW 波形生成与参数提取**。现有 Zero Span 算法先作为稳定基线保留，后续有需要再继续研究。

当前开发版本：**v0.4.0**。

## 研究文档

面向研究人员的 DCM SW 参数化波形生成理论说明：

- [DCM 模式开关电源 SW 节点参数化波形生成模型说明](docs/DCM_SW_WAVEFORM_GENERATION_THEORY.md)

文档说明模型的物理背景、时间定义、理想边沿、有限边沿、尖峰/寄生振铃、DCM 断续谐振、指数衰减、示波器底噪、采样率、真值分量及模型适用边界，并给出从合成波形走向真实波形参数提取的推荐研究路线。

## v0.4 核心研究闭环

```text
已知参数
   ↓
DCM SW 生成器
   ↓
合成 time_s, voltage_v CSV
   ↓
DCM 参数提取器（只读取 time_s / voltage_v）
   ↓
反演基础电平与时间参数
   ↓
提取结果 vs 生成真值
   ↓
逐步扩展尖峰 / 振铃 / DCM 谐振参数
   ↓
最终迁移到真实示波器 CSV
```

同时保留通用原始波形研究流程：

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

## DCM 基础参数提取

新增 `DCM 参数提取` 页面，用于从只有：

```csv
time_s,voltage_v
...
```

的单个 DCM SW 事件中反演第一阶段基础参数。

当前提取：

- 采样率与总显示时长
- 基线电压
- 开通高电平电压
- 续流低电平电压
- 开关起始时间
- 上升时间（模型完整边沿）
- 上升时间（10%~90%）
- 导通时间
- 下降时间（模型完整边沿）
- 下降时间（10%~90%）
- 续流时间
- 基线区估计噪声 RMS

### 提取原则

第一阶段采用“稳健统计 + 主边沿检测 + 阈值穿越 + 当前半余弦边沿模型反解”的方法。

其中 10%~90% 时间和生成模型中的完整边沿时间分别显示，不混为同一个指标。

为了保证真值测试有效，参数提取器 **只读取 `time_s` 和 `voltage_v`**。即使合成 CSV 中还带有：

```text
ideal_voltage_v
spike_component_v
discontinuous_component_v
noise_component_v
```

也不会读取这些真值列，更不会读取对应的参数 JSON。

### 可视化结果

提取页面右侧叠加：

```text
CSV 实测波形
+
基础参数拟合理想轨迹
+
关键时刻标记
```

关键时刻包括：

- 开关起始
- 上升结束
- 下降开始
- 下降结束
- 断续区开始

可选勾选 `显示拟合残差`。残差定义为：

```text
Residual = CSV 实测波形 - 基础理想轨迹
```

开关尖峰、寄生振铃、DCM 断续谐振等尚未拟合的高频特征会主要保留在残差中，作为下一阶段参数提取的输入。

### 置信度

基础参数页面会给出各主要参数的初步置信度和总体置信度，并在以下情况给出提示：

- 主高低电平相对于噪声分离度不足
- 续流低电平与基线过于接近
- 无法明确找到续流结束 / DCM 断续区开始点
- 边沿采样点过少，受到采样率限制

当前第一阶段假设 CSV 中包含一个主要 DCM 开关事件。多周期自动选择、尖峰/寄生振铃参数和 DCM 谐振参数将在后续阶段继续实现。

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

GUI 当前四个主要页面：

```text
波形研究
DCM SW 生成器
DCM 参数提取
批量转换
```

其中前三个页面构成当前 v0.4 的主要研究链路。

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
- DCM 基础参数反演
- 实测 CSV 与拟合理想轨迹叠加
- 提取结果 JSON 导出
- 参数置信度与告警
- 残差视图，为后续振铃拟合预留数据入口

## 后续 DCM SW 提取

下一阶段重点研究残差中的开关尖峰和寄生振铃：

- 上升沿尖峰幅度
- 下降沿尖峰幅度
- 寄生振铃频率
- 寄生振铃衰减速率
- 相位作为内部拟合参数

后续再扩展：

- DCM 断续谐振初始振幅
- DCM 谐振频率
- DCM 谐振衰减速率
- 更完整的噪声估计
- 多周期自动选择
- 全局参数联合优化

最终目标是形成“正向生成 + 反向参数识别 + 真值验证 + 真实 CSV 分析”的完整研究闭环。
