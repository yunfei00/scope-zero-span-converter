# Project Status

更新时间：2026-09-12

## 基本状态

- 状态：ACTIVE
- 优先级：P1
- 当前稳定客户版本：v0.7.0
- 当前开发版本：v0.8.0.dev0
- 当前阶段：v1.0 发布候选验证与商业化收口

## 一句话目标

把示波器时域波形、DCM SW 参数化研究、幅相分析和 Zero Span 转换统一成一个稳定、可诊断、可交付的工程桌面工具。

## 当前真实状态

项目已经远超“简单格式转换工具”阶段，当前已经形成完整的 DCM 信号分析工作台，包括波形研究、ROI、参数化生成、参数提取、四视图联动、批量转换、FSW 实测对比和商业化发布能力。

商业化路线中，版本统一、正式模块结构、时间轴质量门禁、Zero Span 物理有效性、FFT/Phase 语义、Workspace、后台 Worker、导出一致性等主体工作已经完成。

## 最近完成

最近提交已经直接覆盖了本轮用户提出的问题：

- 修复 WSLg/Ubuntu 下 Qt 平台后端选择问题。
- 增加波形研究侧边栏折叠状态与持久化。
- 隐藏固定 Zero Span 行。
- 将 GUI 参数改为 FSW 运行参数的唯一权威来源。
- 在波形研究 UI 暴露全部 FSW 运行参数。
- 转换逻辑和测试均已切换到 GUI-only 参数来源。
- Windows v1 发布流水线已开始准备并修复固定 Python 构建环境。

## 当前问题 / 阻塞

GitHub 当前没有开放 Issue，这意味着本轮用户反馈还没有完全转成正式 Issue 管理。

当前最需要完成的是验收，而不是继续扩功能：

1. Ubuntu/WSLg 是否真的可以正常全屏。
2. 波形研究区域保存 CSV 时“时间轴从 0 开始”是否已经按预期生效。
3. “清除选区”和“恢复全波形”的交互语义是否足够清晰，是否需要合并或重新命名。
4. metadata 仅作为加载初值，后续所有联动是否始终以当前 GUI 参数为准。
5. Windows v1 安装版/Portable/Release 流水线是否可以稳定交付。

## 下一步唯一动作

> **在 Ubuntu/WSLg 与 Windows 各做一次完整人工验收，把当前 4 个用户问题逐项验证并记录结果；只有验收通过后再进入 v1.0 tag。**

## 后续候选动作

1. 将人工验收中未通过的项创建 GitHub Issue。
2. 验证 v1 Windows 安装包、Portable 包和 Release artifact。
3. 复核商业分发确认清单、EULA/版权主体和数字签名策略。
4. 人工确认后再创建正式 `v1.0.0` tag。

## 恢复上下文提示

重新进入项目时优先查看：

1. `README.md`
2. `docs/COMMERCIALIZATION_ROADMAP.md`
3. `docs/RELEASE_PROCESS.md`
4. `docs/RELEASE_COMPLIANCE_CHECKLIST.md`
5. 最近 commits
6. GitHub Actions / Release 构建结果

正式 GUI 入口是：

`app.py -> main_window.MainWindow`

不要重新引入历史版本化 GUI 文件。

## 下一里程碑完成标准

- Ubuntu/WSLg 与 Windows 的核心 GUI 行为一致。
- ROI CSV 时间轴语义符合预期。
- 清除选区/恢复全波形的行为有明确、可理解的产品定义。
- GUI 参数成为唯一运行时权威来源，metadata 只负责初始化。
- Windows 安装版和 Portable 包均通过人工启动/分析/导出验收。
- 满足发布清单后，由人工确认创建 `v1.0.0` tag。
