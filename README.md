# Phigros 自定义查分插件 (astrbot_plugin_phi_custom)

## 📖 简介

基于 Lilith 开放平台 API，为 AstrBot 提供 Phigros 查分、歌曲搜索、曲绘获取、B30 图片生成、别名审核、本地更新库等功能。**中英双语指令**，支持带空格的歌名。

## 🎮 指令列表（中英双语）

所有指令均以 `/` 开头。

| 中文 | 英文 | 输出 | 说明 | 权限 |
| :--- | :--- | :--- | :--- | :--- |
| `/phi帮助` | `/phi_help` | 文本 | 显示帮助（各自显示对应语言） | 所有人 |
| — | `/phi_bind <Token>` | 文本 | 手动绑定账号（25位Token） | 所有人 |
| — | `/phi_qrcode bind` | 图片/链接 | 二维码扫码登录 | 所有人 |
| `/phi查分` | `/phi_b30` | 图片 | 查询 Best 30 成绩图 | 已绑定 |
| `/phi搜歌 <歌名>` | `/phi_search <song>` | 文本 | 搜索歌曲信息 | 所有人 |
| `/phi曲绘 <歌名>` | `/phi_picture <song>` | 图片 | 获取歌曲曲绘（高质量，≤5MB） | 所有人 |
| `/phi单曲 <歌名>` | `/phi_song <song>` | 图片 | 查询单曲成绩图 | 已绑定 |
| `/phi解绑` | `/phi_unbind` | 文本 | 解绑账号 | 已绑定 |
| `/phi更新` | `/phi_update` | 文本 | 更新账号信息（RKS、昵称） | 已绑定 |
| `/phi新曲` | `/phi_new` | 文本 | 最新更新公告 | 所有人 |
| `/phi重载` | `/phi_reload` | 文本 | 重载插件配置 | 所有人 |
| `/phi别名` | `/phi_othername` | 文本 | 别名管理 | 所有人/管理员 |
| `/phi<别名>是什么歌` | 同 | 文本 | 查询别名对应的正式歌名 | 所有人 |

> **说明**：`已绑定` 指用户已成功执行 `/phi_bind` 或扫码绑定。
> **提示**：支持带空格的歌名，例如 `/phi搜歌 CROSS SOUL`。
> **注意**：`/绑定`、`/扫码`、`/查分` 这些纯中文短词**已移除**，避免与其它音游查分插件冲突。

## 🏷️ 别名管理系统

插件内置一份社区常用别名库（存储于 `default_aliases.json`）。普通成员可提交新的别名申请，管理员审核后生效。

| 子指令 | 说明 | 权限 |
| :--- | :--- | :--- |
| `/phi别名 查询` | 进入别名查询模式，按序号或歌名查看该歌所有别名 | 所有人 |
| `/phi别名 add <别名> <歌名>` | 普通成员：提交添加申请（进待审核队列）<br>管理员：直接添加 | 所有人 / 管理员 |
| `/phi别名 delete <别名>` | 删除指定别名 | 仅管理员 |
| `/phi别名 delete all` | 重置为 `default_aliases.json` 中的默认别名 | 仅管理员 |
| `/phi别名 temp [页码]` | 查看待审核队列，每页10条 | 仅管理员 |
| `/phi别名 temp approved <id>[,<id>...]` | 通过指定编号的申请，其余自动驳回 | 仅管理员 |

**别名查询模式**：
- `/phi别名 查询` 会列出所有有别名的歌曲（最多20首），附带每首歌的别名数量。
- 之后**直接回复序号或歌名**即可查看该歌的所有别名。
- 输入 `取消` / `退出` / `q` 退出查询模式。
- 5分钟无操作自动退出。

**审核机制**：
- 普通成员提交的申请进入待审核队列，无数量上限。
- 管理员通过 `/phi别名 temp` 翻页查看，每页显示10条。
- `/phi别名 temp approved 1,3,5` 可一次通过多条，未被选中的自动驳回。
- 审核完毕后队列清空，机器人会在群内公示通过和驳回名单。

## 📰 本地更新库

`/phi新曲` 除了展示远程公告，还支持管理员发布本地公告。

| 指令 | 说明 | 权限 |
| :--- | :--- | :--- |
| `/phi新曲` | 显示远程公告 + 当前本地公告 | 所有人 |
| `/phi新曲 all` | 显示全部历史公告（🟢当前 / ⚪历史） | 所有人 |
| `/phi新曲 add §内容§` | 发布新公告，旧公告自动归档 | 仅管理员 |
| `/phi新曲 del` | 清空公告数据库 | 仅管理员 |

> **add 语法**：用 `§` 包裹内容，支持空格、换行、标点，但不能包含 `§` 本身。
> 示例：`/phi新曲 add §【3.20更新】新曲 NWAD (IN 15.6)§`

公告数据保存在 `data/local_news.json`。

## ⚙️ 配置项说明

在 AstrBot WebUI 的插件配置页面可修改以下内容：

| 配置项 | 主标题 | 说明 | 类型 | 默认值 |
| :--- | :--- | :--- | :--- | :--- |
| `lilith_api_key` | Lilith API Key | 请前往 https://lilith.xtower.site/open-platform 使用 GitHub 登录，创建 API Key 并复制以 `pgr_live_` 开头的密钥。 | string (secret) | 空 |
| `phi_api_url` | API 基础地址 | Lilith API 基础地址，末尾不要带斜杠或路径。 | string | `https://r0semi.xtower.site` |
| `proxy_url` | 网络代理地址 | 可选。如 `http://127.0.0.1:7890`。 | string | 空 |
| `timeout` | 请求超时时间（秒） | 范围 5-120。 | int | `30` |
| `default_taptap_version` | 默认 TapTap 版本 | `cn` 国服 / `global` 国际服。 | string | `cn` |
| `auto_load_aliases` | 自动加载默认别名 | 开启后若别名库为空，会从 `default_aliases.json` 加载。 | bool | `true` |
| `news_source_url` | 更新公告源地址 | 远程更新公告 API 地址，留空则只用本地库。 | string | Lilith song-updates 接口 |
| `news_local_show_count` | 本地公告显示条数 | `/phi新曲` 时最多显示几条本地公告。 | int | `3` |

---

## 🔧 依赖安装说明

本插件依赖分三类：

| # | 类别 | 内容 | 是否必装 |
| :--- | :--- | :--- | :--- |
| 一 | Python 库（pip） | `httpx`、`qrcode[pil]`、`Pillow` | **必装** |
| 二 | 系统组件 | Playwright Chromium | **必装**（图片渲染核心） |
| 三 | 系统组件 | GTK3 Runtime | 可选（仅 cairosvg 降级时用到） |

---

### 一、Python 库（pip，必装）

插件启动时会自动检测并安装缺失的 pip 库（清华源）。如自动失败，请手动安装：

**方法 A：AstrBot WebUI**
1. 打开 **平台日志** 页面
2. 点右上角 **「安装 Pip 库」**
3. 库名填：`httpx qrcode[pil] Pillow`
4. 强制 PyPI 源填：`https://pypi.tuna.tsinghua.edu.cn/simple`
5. 安装后**完全重启** AstrBot

**方法 B：命令行**

```cmd
cd C:\Users\Administrator\.astrbot_launcher\instances\<实例ID>\venv\Scripts
activate
pip install httpx "qrcode[pil]" Pillow -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

### 二、Playwright Chromium（必装）

插件渲染 B30、单曲、曲绘等图片时，优先使用 AstrBot 内置的 `html_render`（基于 Playwright），所以需要 Chromium 内核。

#### 方式 1：命令行在线安装（推荐）

**Windows**

```cmd
playwright install chromium
```

国内网络慢，先设置镜像（仅当前窗口生效）：

```cmd
set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
playwright install chromium
```

想永久生效：

```cmd
setx PLAYWRIGHT_DOWNLOAD_HOST "https://npmmirror.com/mirrors/playwright"
```

然后**重开命令行窗口**，再执行 `playwright install chromium`。

**Linux**

```bash
# 先装系统依赖（需要 sudo）
sudo playwright install-deps chromium

# 再装 Chromium 内核
playwright install chromium
```

国内网络慢：

```bash
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
playwright install chromium
```

**macOS**

```bash
playwright install chromium
```

国内网络慢：

```bash
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
playwright install chromium
```

#### 方式 2：离线手动安装（网络不好时用）

**第 1 步：确认需要的版本号**

报错信息里会明确写出需要哪个版本，例如：

```
Executable doesn't exist at C:\Users\Administrator\AppData\Local\ms-playwright\chromium_headless_shell-1243\chrome-headless-shell-win64\chrome-headless-shell.exe
```

其中 `chromium_headless_shell-1243` 里的 `1243` 就是版本号。

**第 2 步：下载对应压缩包**

Playwright 浏览器文件托管在官方 CDN，可直接下载：

| 平台 | 下载链接 |
| :--- | :--- |
| Windows | `https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/<版本号>/chromium-headless-shell-win64.zip` |
| Linux | `https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/<版本号>/chromium-headless-shell-linux.zip` |
| macOS (Intel) | `https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/<版本号>/chromium-headless-shell-mac.zip` |
| macOS (Apple Silicon) | `https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/<版本号>/chromium-headless-shell-mac-arm64.zip` |

把 `<版本号>` 替换成第 1 步确认的数字（如 `1243`）。

> 完整版 Chromium（非 headless-shell）也一样规律，把 `chromium-headless-shell` 换成 `chromium` 即可。

**第 3 步：解压到指定目录**

Playwright 浏览器缓存目录：
- **Windows**：`C:\Users\<用户名>\AppData\Local\ms-playwright\`
- **Linux/macOS**：`~/.cache/ms-playwright/`

按报错信息里的路径创建对应文件夹，把解压后的目录放进去。例如 Windows：

```
C:\Users\Administrator\AppData\Local\ms-playwright\
└── chromium_headless_shell-1243\
    └── chrome-headless-shell-win64\
        └── chrome-headless-shell.exe
```

**第 4 步：验证**

重启 AstrBot，再次尝试渲染图片。路径对了就不会再报错。

#### 方式 3：使用国内镜像站（备用）

官方 CDN 也慢时，可以试国内镜像：

```
https://npmmirror.com/mirrors/playwright/
```

按版本号找到对应目录，下载 `chromium-headless-shell-<平台>.zip`。注意镜像站可能不是所有版本都齐全。

---

### 三、GTK3 Runtime（可选）

GTK3 是 `cairosvg` 的系统依赖。只有当 `html_render` 失败、插件降级到 `cairosvg` 兜底时才会用到。

**如果你的 Playwright Chromium 装好了，图片渲染走 `html_render` 路径，就不需要 GTK3。** 本节可跳过。

#### Windows

**方式 1：在线安装（推荐）**

1. 访问 [GTK-for-Windows-Runtime-Environment-Installer](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases)
2. 下载最新版 `.exe` 安装包（如 `gtk3-runtime-3.24.31-2022-01-04-ts-win64.exe`）
3. 安装时：
   - 勾选 **"Set up PATH environment variable to include GTK+"**
   - DLL 位置保持默认 **`<instdir>\bin (recommended)`**
4. 安装完**重启电脑**
5. 验证：新开终端，PATH 里应包含 `C:\Program Files\GTK3-Runtime Win64\bin`

**方式 2：离线安装包**

同一 GitHub Releases 页面下载 `.exe` 文件，拷贝到目标机器执行即可，流程一样。适合内网/无外网服务器。

**装完还是报 `no library called "cairo-2"`？**

插件代码已在启动时自动注入 `C:\Program Files\GTK3-Runtime Win64\bin`，并给 fontconfig 写入 Windows 字体目录。如果还是报错：
- 检查 GTK3 是否装在默认路径。装在别的盘，需要修改 `main.py` 顶部的 `_GTK_BIN_CANDIDATES` 列表。
- 或者把 GTK3 的 `bin` 目录手动加到系统 PATH。

#### Linux

Linux 上通过系统包管理器安装，**不需要** Windows 安装包。

**Debian / Ubuntu**

```bash
sudo apt-get install libgtk-3-0
sudo apt-get install libgtk-3-dev
sudo apt-get install libcairo2
```

**Fedora / CentOS / RHEL**

```bash
sudo dnf install gtk3
# 或
sudo yum install gtk3
```

**Arch Linux**

```bash
sudo pacman -S gtk3
```

**离线安装（无外网服务器）**

去 [packages.debian.org](https://packages.debian.org/)（Debian）或 [pkgs.org](https://pkgs.org/)（通用）下载对应 `.deb` / `.rpm` 包，拷贝到目标机器后用 `dpkg -i` 或 `rpm -ivh` 安装。注意手动解决依赖。

#### macOS

**在线安装**

```bash
brew install gtk+3
```

**离线安装**

Homebrew 支持从本地 `.tar.gz` 瓶子（bottle）安装：

```bash
brew install --force-bottle /path/to/gtk+3--3.24.xx.tarball.tar.gz
```

或者用 `brew bundle` 配合本地 formula 文件。macOS 部署 AstrBot 的场景较少，一般直接 `brew install` 即可。

---

## 📁 文件结构

```
astrbot_plugin_phi_custom/
├── main.py
├── default_aliases.json
├── metadata.yaml
├── requirements.txt
├── _conf_schema.json
├── README.md
├── logo.png
└── data/                      # 运行时生成（.gitignore 忽略）
    ├── users.json
    ├── aliases.json
    ├── temp_aliases.json
    └── local_news.json
```

## 📌 注意事项

1. **Token 安全**：SessionToken 和 API Key 均为敏感信息，请勿公开分享。
2. **图片渲染**：优先使用 AstrBot 内置 HTML 渲染（Playwright），失败时尝试 cairosvg。
3. **曲绘质量**：`/phi曲绘` 走高质量路径（≤5MB，PNG 优先），其他图片走 1000px/85 压缩。
4. **别名同音字**：精确字符串匹配，同音字不会被视为重复。
5. **API 域名**：所有请求发往 `https://r0semi.xtower.site`。
6. **中文触发说明**：与其它音游查分插件共存时，用 `/phi` 前缀的中文指令更保险，避免纯中文短词（如"查分""绑定"）冲突。

*本文档适用于插件版本 v1.2.0 及以上。*