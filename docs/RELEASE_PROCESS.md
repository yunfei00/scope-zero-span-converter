# Release process

## 正常发布流程

1. 确认 main 的 Tests 全绿；完成 Windows Release Candidate 的手动构建验证。
2. 更新 CHANGELOG，并由产品所有者确认发布说明、授权/版权主体及商业分发清单。
3. 人工创建并推送 `vX.Y.Z` tag（例如最终确认后的 `v1.0.0`）。
4. Actions 自动执行源码测试 → EXE → smoke → ZIP → Installer → 安装/已安装 smoke/
   卸载 → artifacts → GitHub Release。任一验证失败，发布 job 不运行。

main 保持 `0.8.0.dev0`。只有 tag 构建将 `_version.py` 注入为 tag 的版本；Python 包、
标题、metadata、Windows VersionInfo、Installer 和文件名共用这个来源。
数字资源规则为 `X.Y.Z -> X.Y.Z.0`，`X.Y.Z.devN -> X.Y.Z.N`，每段限制 0–65535。
开发版本设置 Windows prerelease flag；字符串 ProductVersion 保留完整 `.devN`。
数字 tuple 不用于比较开发版本和正式版本的先后次序。

## 不发布 Release 的 RC 验证

在 Actions → **Windows Release Candidate** → Run workflow，选择 main。
或执行 `gh workflow run release.yml --ref main`。该入口上传 CI artifacts，
不会创建 tag 或 Release。查看每个步骤最终状态，不能把 queued/running 当作成功。

验证包括独立 dist EXE、Program Files 语义的安装器、临时目录静默安装、
实际安装出来的 EXE、同一 AppId 再安装、快捷方式、静默卸载和用户数据保留。
发布 job 仅接受 `push` 且 `refs/tags/v*`；它依赖整个 Windows 验证 job 成功。
不存在跳过测试的发布快捷路径。

下载 `windows-distributables` 获取 ZIP、Setup EXE 和 SHA256SUMS；
`windows-verification` 包含 smoke JSON、依赖/许可清单、构建信息及 PyInstaller 告警。
请保留最后一次 RC run URL 作为人工发布确认依据。

## 构建维护

- spec：`packaging/ScopeZeroSpanConverter.spec`，使用 onedir/windowed，QtAgg + Agg。
- 产品名称、作者标识、AppId：`src/scope_zero_span_converter/product.py`。
- 版本/Installer defines：`packaging/windows_metadata.py`，不要手改生成文件。
- 原创图标：`assets/generate_icon.py` 生成 `app.png` 和多尺寸 `app.ico`。
- Windows 构建 Python 3.11.15（由固定版本 uv 0.11.2 安装 managed runtime，
  不依赖 setup-python 缺少的 Windows 3.11 安全更新二进制）、Inno Setup 6.4.3；直接/间接 Python 依赖均在
  `packaging/requirements-windows.txt` 固定版本并校验 hash。
- 更新依赖时修改 `.in` 后按文件头的 uv 命令重新生成 lock，重新跑完整 RC。
- Wheel license 文件自动复制，额外许可文本来自版本化 URL 并验证 SHA256。
  这固定了构建输入，但 hosted runner/签名时间戳不同不承诺 EXE 字节级一致。

## 可选代码签名

在仓库 Actions Secrets 配置 `WINDOWS_CERTIFICATE_BASE64`（PFX 的 base64）和
`WINDOWS_CERTIFICATE_PASSWORD`。不要提交证书、密码或私钥。
脚本使用 SHA256 和时间戳，分别签主 EXE 与 Installer，并验证签名。
两项都不存在时标记 **UNSIGNED BUILD**；部分配置或签名失败使流水线失败。
PFX 仅临时写入 runner 临时目录，签名后立即删除，不进入 artifacts。当前未配置证书的 RC 只验证 unsigned 分支，
配置生产证书后应再运行 RC 验证 signed 分支。

## 发布前所有者确认

查看 [商业分发确认清单](RELEASE_COMPLIANCE_CHECKLIST.md) 与
[第三方许可说明](../THIRD_PARTY_NOTICES.md)。仓库没有自动选择 MIT/Apache 或
其他产品许可证。技术 RC green 不代表已经签署商业 EULA 或完成组织法律审查。
DSO-X / FSW 实机验收属于可选后续验证，不是本软件发布流水线的门禁。
