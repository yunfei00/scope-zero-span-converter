# Windows 安装与使用

支持 Windows 10 1809 或更新版本、Windows 11，x64；建议使用仍受 Microsoft
支持的系统。无需另装 Python。建议 8 GB 内存，大数据分析需要更多内存和磁盘空间。
安装/更新到 Program Files 需要管理员授权，日常运行使用普通用户权限。

## 安装器（推荐）

从项目的 GitHub Release 下载 `ScopeZeroSpanConverter-Setup-<version>.exe`，
运行并按向导安装。默认目录为 `C:\Program Files\ScopeZeroSpanConverter`。
开始菜单快捷方式自动创建；桌面快捷方式可选。启动后标题栏显示真实软件版本。

当前未配置生产签名证书时，安装器和 EXE 均未数字签名，Windows 可能显示
“未知发布者”或 SmartScreen 提示。只从项目可信发布页面获取文件，核对同页的
`SHA256SUMS.txt`；不要关闭系统安全防护。若组织策略禁止未签名程序，请联系管理员。
若后续启用签名，可在文件属性的“数字签名”页确认发布者。

## Portable ZIP

下载 `ScopeZeroSpanConverter-v<version>-Windows-x64.zip`，先完整解压，再运行
目录中的 `ScopeZeroSpanConverter.exe`。必须保留 `_internal` 目录，不能只复制 EXE。
无需安装器，也无需管理员权限。Portable 的用户配置同样保存在用户数据目录。

## 升级与卸载

关闭正在运行的程序后运行新安装器。所有版本共用稳定 AppId，更新同一个产品，
并优先使用已有安装目录；无需手动逐个删除旧版本。安装器不会迁移或删除分析输出。

在 Windows“已安装的应用”中选择 Scope Zero Span Converter → 卸载。
卸载移除安装程序创建的文件、快捷方式和注册项；默认保留用户配置、模板、日志和输出。
Portable 版本可以删除解压目录，但应先确认没有把自己的分析文件放在该目录中。

## 用户数据与资源

Windows 正式数据根目录为 `%LOCALAPPDATA%\ScopeZeroSpanConverter`：

| 路径 | 用途 |
|---|---|
| `app_state.json` | 最近使用状态、页签和 Workspace |
| `templates\` | 用户配置模板 |
| `logs\` | 轮转日志，单文件 10 MB，保留 5 个历史文件 |
| `output\`、`batch_output\` | 打包程序未选择绝对输出目录时的默认输出位置 |

旧版 `%USERPROFILE%\ScopeZeroSpanConverter` 的状态、模板和日志会首次复制到新位置，
已有新文件不会被覆盖，旧文件保留。用户原有的绝对输出路径保持原意。
源码运行在非 Windows 系统时继续使用 `~/ScopeZeroSpanConverter`。
`SCOPE_ZERO_SPAN_DATA_DIR` 可显式指定独立数据根目录，主要用于自动验证和支持诊断。

默认配置和图标是只读打包资源，位于 `_internal\configs` / `_internal\assets`。
不要编辑或写入 Program Files 中的运行时文件来保存分析结果。

## 问题诊断

先确认输入 CSV/metadata 的格式、采样质量和 Center/RBW 物理边界；错误不会通过
放宽质量策略自动绕过。在程序中点击“导出诊断包”，将生成 ZIP 交给维护者。
诊断默认包含版本、运行环境和应用日志，不包含客户波形和参数文件。

也可在命令行运行 `ScopeZeroSpanConverter.exe --smoke-test`。成功退出码为 0，
结果默认写入用户数据目录的 `smoke-report.json`；可用 `--smoke-report <文件>` 指定报告。
该模式不会恢复/保存客户 AppState，也不执行客户文件转换。

自动安装支持 `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`，可配合 `/DIR="目标目录"`。
自动卸载使用安装目录中 `unins000.exe` 的同名 silent 参数。
