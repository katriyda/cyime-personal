# CyIME Personal

非官方个人构建，基于 [Cyletix/CyIME](https://github.com/Cyletix/CyIME)（GPL-3.0）。

这个仓库只维护“发行身份”和自动发布流程，不保存上游源码：

- `packages.json`：要发布的全部包名。每一项都会构建、校验并发布到自己的 Release。
- `scripts/prepare_build.py`：读取官方最新正式版 Release 标签，按包名计算独立版本。
- `scripts/patch_upstream.py`：在官方源码副本上只改包名、应用名、更新通道、签名白名单和版本号。
- `.github/workflows/build.yml`：按包名矩阵构建、校验 APK 身份与签名、每个包名独立发布。
- `.github/workflows/ci.yml`：只校验包名清单和脚本语法，不构建。

## 跟随官方版本

每次运行都取官方最新、非草稿、非预发布的 `x.y.z` Release 标签源码，不跟踪 `main`。官方发布新版本后，定时任务自动构建并发布对应的独立包；同一上游版本已经发布过的包会跳过，手动运行可加 `force` 重建。

## 发布方式

每个包名的 Release tag 是 `<suffix>-v<version>`，安装包只包含该包自己的资产。应用内更新只接受本包前缀的 tag，因此不同包名不会互相下载。

定时任务每天检查官方最新正式版。也可以手动运行 `Build packages`：`package_id` 留空构建全部包名，`publish` 默认开启。

## 添加包名

在 `packages.json` 增加一项：

```json
{
  "id": "third",
  "applicationId": "com.katriyda.cyime.third",
  "label": "CyIME Third",
  "suffix": "third"
}
```

`id`、`applicationId`、`suffix` 必须唯一。新增后下一次运行会自动多构建一个包并发布一个独立 Release。

## 签名

`signing/ci-cert-sha256.txt` 是公开的证书指纹，不是私钥。真实 keystore 与口令只放在 GitHub Actions Secrets：

- `SIGNING_KEY`（base64 编码的 keystore）
- `KEY_STORE_PASSWORD`
- `KEY_PASSWORD`
- `ALIAS`

不要提交 keystore、口令或 `signing/` 下的私钥文件。

当前 keystore 是 PKCS12 格式，所以 `KEY_PASSWORD` 必须与 `KEY_STORE_PASSWORD` 相同；只改其中一个会导致 CI 在签名时报 “Given final block not properly padded”。

首次发布后不要再更换 keystore，否则已安装的用户无法覆盖升级。

## 小米全面屏

HyperOS 的“输入法全面屏优化”不是公开的静态包名名单。系统按包名和最低 versionCode 只放行定制输入法，第三方输入法需要 LSPosed 解锁模块。这里的包名只是你自己的独立身份，不冒充任何厂商应用。

## 许可证

上游代码遵循 GPL-3.0，详见 `LICENSE`。本仓库的构建脚本和配置同样按 GPL-3.0 发布。应用名、图标等品牌资产的使用边界见 `TRADEMARKS.md`；这是非官方构建。
