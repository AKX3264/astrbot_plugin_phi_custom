# Phigros 自定义查分插件 (astrbot_plugin_phi_custom)

## 📖 简介

本插件基于 Lilith 开放平台 API，为 AstrBot 提供轻量化的 Phigros 查分、歌曲搜索、曲绘获取、B30 图片生成等功能。支持手动绑定与二维码扫码引导，并内置歌曲别名系统，管理员可审核普通成员提交的别名申请。

## 🎮 指令列表

所有指令均以 `/` 开头。

| 指令 | 参数 | 输出 | 说明 | 权限 |
| :--- | :--- | :--- | :--- | :--- |
| `/phi_help` | 无 | 文本 | 显示所有可用指令 | 所有人 |
| `/phi_bind` | `<SessionToken>` | 文本 | 手动绑定账号（25位Token） | 所有人 |
| `/phi_qrcode` | `bind` | 图片/链接 | 生成二维码引导扫码登录 | 所有人 |
| `/phi_b30` | 无 | 图片 | 查询 Best 30 成绩图 | 已绑定 |
| `/phi_search` | `<歌名或别名>` | 文本 | 搜索歌曲信息 | 所有人 |
| `/phi_picture` | `<歌名或别名>` | 图片 | 获取歌曲曲绘（纯图） | 所有人 |
| `/phi_song` | `<歌名或别名>` | 图片 | 查询单曲成绩图 | 已绑定 |
| `/phi_unbind` | 无 | 文本 | 解绑账号 | 已绑定 |
| `/phi_update` | 无 | 文本 | 更新账号信息（RKS、昵称） | 已绑定 |
| `/phi_new` | 无 | 文本 | 获取最新歌曲更新公告 | 所有人 |
| `/phi_reload` | 无 | 文本 | 重载插件配置 | 所有人 |
| `/<别名>是什么歌` | 无 | 文本 | 查询别名对应的正式歌名 | 所有人 |

> **说明**：`已绑定` 指用户已成功执行 `/phi_bind` 或扫码绑定。
> **提示**：支持带空格的歌名，例如 `/phi_search CROSS SOUL`。

## 🏷️ 别名管理系统

插件内置一份社区常用别名库（存储于 `default_aliases.json`）。普通成员可提交新的别名申请，管理员审核后生效。

| 指令 | 参数 | 说明 | 权限 |
| :--- | :--- | :--- | :--- |
| `/phi_othername add` | `<别名> <歌名>` | 普通成员：提交添加申请（进入待审核队列）<br>管理员：直接添加别名 | 所有人 / 管理员 |
| `/phi_othername delete` | `<别名>` | 删除指定别名 | 仅管理员 |
| `/phi_othername delete all` | 无 | 重置别名库为 `default_aliases.json` 中的默认别名 | 仅管理员 |
| `/phi_othername temp` | `[页码]` | 查看待审核队列，每页10条 | 仅管理员 |
| `/phi_othername temp approved` | `<id>[,<id>...]` | 通过指定编号的申请，其余自动驳回 | 仅管理员 |

**审核机制**：
- 普通成员提交的申请进入待审核队列，无数量上限。
- 管理员通过 `/phi_othername temp` 翻页查看，每页显示10条。
- 使用 `/phi_othername temp approved 1,3,5` 可一次通过多条，未被选中的自动驳回。
- 审核完毕后队列清空，机器人会在群内公示通过和驳回名单（含提交者昵称）。

## ⚙️ 配置项说明

在 AstrBot WebUI 的插件配置页面可修改以下内容：

| 配置项 | 主标题 | 说明 | 类型 | 默认值 |
| :--- | :--- | :--- | :--- | :--- |
| `lilith_api_key` | Lilith API Key | 请前往 https://lilith.xtower.site/open-platform 使用 GitHub 登录，创建 API Key 并复制以 `pgr_live_` 开头的密钥。 | string (secret) | 空 |
| `phi_api_url` | API 基础地址 | Lilith API 基础地址，末尾不要带斜杠或路径。 | string | `https://r0semi.xtower.site` |
| `proxy_url` | 网络代理地址 | 可选。如果无法直接访问 Lilith API，可填写本地代理，如 `http://127.0.0.1:7890`。 | string | 空 |
| `timeout` | 请求超时时间（秒） | API 请求超时时间，范围 5-120。 | int | `30` |
| `default_taptap_version` | 默认 TapTap 版本 | `cn` 为国服，`global` 为国际服。 | string | `cn` |
| `auto_load_aliases` | 自动加载默认别名 | 开启后，插件启动时若别名库为空，会从 `default_aliases.json` 加载默认别名。 | bool | `true` |

## 🔧 手动安装依赖

本插件需要以下 Python 依赖：

| 依赖包 | 用途 |
| :--- | :--- |
| `httpx` | 异步 HTTP 请求 |
| `qrcode[pil]` | 生成二维码图片 |
| `Pillow` | 图片处理与压缩 |
| `cairosvg` | 将 SVG 转为 PNG（备选方案，依赖 GTK3 运行时） |

插件启动时会**自动检测并安装缺失的依赖**（使用清华源）。但由于网络、权限或环境差异，自动安装**可能失败**。此时请按以下方法手动安装。

### 方法一：通过 AstrBot WebUI 安装（推荐）

1. 打开 AstrBot 的 **WebUI 管理面板**。
2. 进入 **平台日志** 页面。
3. 在页面右上角找到 **「安装 Pip 库」** 按钮，点击。
4. 在弹窗中：
   - **库名** 填入：`httpx qrcode[pil] Pillow cairosvg`
   - **强制 PyPI 软件仓库链接** 填入：`https://pypi.tuna.tsinghua.edu.cn/simple`
5. 点击 **「安装」**，等待完成。
6. **完全退出并重启 AstrBot**（不是重载插件，是整个进程重启）。

### 方法二：在 AstrBot 的 Python 环境中手动安装

如果你能进入 AstrBot 的安装目录，可以打开命令行执行：

```bash
# 进入 AstrBot 的虚拟环境（路径按实际调整）
cd C:\Users\Administrator\.astrbot_launcher\instances\<实例ID>\venv\Scripts
activate

# 安装依赖（使用清华源）
pip install httpx "qrcode[pil]" Pillow cairosvg -i https://pypi.tuna.tsinghua.edu.cn/simple