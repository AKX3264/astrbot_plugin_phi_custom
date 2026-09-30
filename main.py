import os
import sys
import subprocess
import importlib

# ══════════════════════════════════════════════
# Windows: 注入 GTK3 路径 + 修复 fontconfig
# ══════════════════════════════════════════════
if sys.platform == "win32":
    for _p in [r"C:\Program Files\GTK3-Runtime Win64\bin",
               r"C:\Program Files (x86)\GTK3-Runtime Win64\bin"]:
        if os.path.isdir(_p):
            os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(_p)
                except Exception:
                    pass
            break

    _gtk_etc_fonts = r"C:\Program Files\GTK3-Runtime Win64\etc\fonts"
    _windows_fonts = r"C:\Windows\Fonts"
    if os.path.isdir(_gtk_etc_fonts) and os.path.isdir(_windows_fonts):
        _local_conf = os.path.join(_gtk_etc_fonts, "local.conf")
        if not os.path.exists(_local_conf):
            try:
                with open(_local_conf, "w", encoding="utf-8") as f:
                    f.write(f'''<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>{_windows_fonts}</dir>
  <cachedir>%LOCALAPPDATA%/fontconfig/cache</cachedir>
</fontconfig>
''')
            except Exception:
                pass

# ══════════════════════════════════════════════
# 依赖自检
# ══════════════════════════════════════════════
_REQUIRED_PACKAGES = [
    ("httpx",  "httpx"),
    ("qrcode", "qrcode[pil]"),
    ("PIL",    "Pillow"),
]


def _check_and_install_deps():
    missing = []
    for import_name, pip_name in _REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
        except Exception:
            missing.append(pip_name)
    if not missing:
        return []
    print(f"⚠️ [Phi插件] 检测到缺失依赖：{', '.join(missing)}，正在自动安装...")
    for pkg in missing:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg,
                 "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
            print(f"✅ [Phi插件] 已安装 {pkg}")
        except Exception as e:
            print(f"❌ [Phi插件] 安装 {pkg} 失败: {e}")
    return missing


_check_and_install_deps()

import json
import re
import asyncio
import time
import tempfile
import httpx
import base64
from io import BytesIO
from urllib.parse import quote
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
USER_DB = os.path.join(DATA_DIR, "users.json")
ALIAS_DB = os.path.join(DATA_DIR, "aliases.json")
TEMP_ALIAS_DB = os.path.join(DATA_DIR, "temp_aliases.json")
LOCAL_NEWS_DB = os.path.join(DATA_DIR, "local_news.json")
DEFAULT_ALIAS_FILE = os.path.join(os.path.dirname(__file__), "default_aliases.json")

ILLUSTRATION_CDN = "https://somnia.xtower.site/lilith/ill"

ALIAS_QUERY_TIMEOUT = 300
ALIAS_QUERY_PAGE_SIZE = 20

DEFAULT_NEWS_SOURCE = "https://r0semi.xtower.site/api/v1/open/song-updates"


def load_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载 {path} 失败: {e}")
    return default if default is not None else {}


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"保存 {path} 失败: {e}")


def load_default_aliases() -> dict:
    if os.path.exists(DEFAULT_ALIAS_FILE):
        try:
            with open(DEFAULT_ALIAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载 default_aliases.json 失败: {e}")
    return {}


def compress_image(img_bytes: bytes, max_width: int = 1000, quality: int = 85) -> bytes:
    try:
        from PIL import Image
        img = Image.open(BytesIO(img_bytes))
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (20, 24, 38))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        result = buf.getvalue()
        if len(result) >= len(img_bytes):
            return img_bytes
        return result
    except Exception as e:
        logger.error(f"图片压缩失败，使用原图: {e}")
        return img_bytes


def encode_image_hq(img_bytes: bytes, hard_max: int = 5 * 1024 * 1024) -> bytes:
    try:
        from PIL import Image
        img = Image.open(BytesIO(img_bytes))
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (20, 24, 38))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        try:
            buf = BytesIO()
            img.save(buf, format="PNG", optimize=True)
            png_data = buf.getvalue()
            if len(png_data) <= hard_max:
                logger.info(f"🎨 PNG 无损: {len(png_data)} 字节")
                return png_data
        except Exception:
            pass

        best = None
        for q in [98, 95, 92, 90, 88, 85, 82, 80, 78, 75, 72, 70, 65, 60, 55, 50, 45, 40]:
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=q, optimize=True, subsampling=0)
            data = buf.getvalue()
            if len(data) <= hard_max:
                best = data
                logger.info(f"🎨 JPEG q={q}: {len(data)} 字节")
                break
            best = data

        if best:
            return best

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()
    except Exception as e:
        logger.error(f"高质量编码失败: {e}")
        return img_bytes


def is_valid_image(data: bytes, min_size: int = 500) -> bool:
    return bool(data) and len(data) >= min_size


class PhiCustomPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self.api_url = self.config.get("phi_api_url", "https://r0semi.xtower.site").rstrip("/")
        self.api_key = self.config.get("lilith_api_key", "")
        self.proxy = self.config.get("proxy_url", "")
        self.timeout = self.config.get("timeout", 30)
        self.taptap_ver = self.config.get("default_taptap_version", "cn")
        self.aliases = load_json(ALIAS_DB, {})
        self._qrcode_polling_users = {}
        self._alias_query_mode = {}
        self.news_use_remote = self.config.get("news_use_remote", True)
        self.news_source_url = self.config.get("news_source_url", DEFAULT_NEWS_SOURCE).strip()
        self.news_local_show_count = self.config.get("news_local_show_count", 3)

        if self.config.get("auto_load_aliases", True):
            if not self.aliases:
                defaults = load_default_aliases()
                if defaults:
                    self.aliases = defaults
                    save_json(ALIAS_DB, self.aliases)
                    logger.info(f"✅ 已自动加载 {len(self.aliases)} 条默认别名")

        logger.info(f"✅ Phi 自定义查分插件已加载！远程公告：{'开' if self.news_use_remote else '关'}")

    def _headers(self):
        return {
            "X-OpenApi-Token": self.api_key,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    def _resolve_song_name(self, name: str) -> str:
        return self.aliases.get(name.strip(), name.strip())

    def _load_temp(self) -> list:
        return load_json(TEMP_ALIAS_DB, [])

    def _save_temp(self, data: list):
        save_json(TEMP_ALIAS_DB, data)

    def _extract_song_name(self, event: AstrMessageEvent) -> str:
        raw = event.message_str.strip()
        if raw.startswith("/"):
            raw = raw[1:]
        parts = raw.split(None, 1)
        if len(parts) > 1:
            return parts[1].strip()
        return ""

    def _extract_args_after_command(self, event: AstrMessageEvent, prefixes: list) -> str:
        raw = event.message_str
        if raw.startswith("/"):
            raw = raw[1:]
        low = raw.lower()
        for prefix in prefixes:
            if low.startswith(prefix.lower()):
                return raw[len(prefix):].strip()
        return raw.strip()

    def _build_aliases_reverse_map(self) -> dict:
        rev = {}
        for alias, real in self.aliases.items():
            rev.setdefault(real, []).append(alias)
        return rev

    def _load_news_db(self) -> dict:
        db = load_json(LOCAL_NEWS_DB, {"news": []})
        if not isinstance(db, dict):
            db = {"news": []}
        if "news" not in db or not isinstance(db["news"], list):
            db["news"] = []
        return db

    async def _upload_to_image_host(self, img_bytes: bytes) -> str | None:
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy if self.proxy else None, timeout=40
            ) as client:
                files = {"files[]": ("image.jpg", img_bytes, "image/jpeg")}
                resp = await client.post("https://uguu.se/upload.php", files=files)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") and data.get("files"):
                        url = data["files"][0].get("url")
                        if url:
                            logger.info(f"✅ 图床(uguu) 成功: {url}")
                            return url
        except Exception as e:
            logger.warning(f"uguu 异常: {e}")

        try:
            async with httpx.AsyncClient(
                proxy=self.proxy if self.proxy else None, timeout=40
            ) as client:
                files = {"fileToUpload": ("image.jpg", img_bytes, "image/jpeg")}
                resp = await client.post(
                    "https://catbox.moe/user/api.php",
                    data={"reqtype": "fileupload"}, files=files
                )
                if resp.status_code == 200 and resp.text.strip().startswith("http"):
                    logger.info(f"✅ 图床(catbox) 成功: {resp.text.strip()}")
                    return resp.text.strip()
        except Exception as e:
            logger.warning(f"catbox 异常: {e}")

        try:
            async with httpx.AsyncClient(
                proxy=self.proxy if self.proxy else None, timeout=40
            ) as client:
                files = {"file": ("image.jpg", img_bytes, "image/jpeg")}
                resp = await client.post("https://0x0.st", files=files)
                if resp.status_code == 200 and resp.text.strip().startswith("http"):
                    logger.info(f"✅ 图床(0x0) 成功: {resp.text.strip()}")
                    return resp.text.strip()
        except Exception as e:
            logger.warning(f"0x0 异常: {e}")

        return None

    async def _send_image(self, event: AstrMessageEvent, img_bytes: bytes, min_size: int = 500):
        if not is_valid_image(img_bytes, min_size=min_size):
            logger.error(f"❌ 图片数据无效，长度 {len(img_bytes)} 字节")
            return event.plain_result("❌ 图片生成失败（返回数据无效）")

        compressed = compress_image(img_bytes, max_width=1000, quality=85)
        logger.info(f"📷 图片最终大小: {len(compressed)} 字节（原 {len(img_bytes)}）")

        url = await self._upload_to_image_host(compressed)
        if url:
            try:
                return event.image_result(url)
            except Exception as e:
                logger.error(f"image_result(url) 失败: {e}")

        try:
            fd, path = tempfile.mkstemp(suffix=".jpg", prefix="phi_")
            with os.fdopen(fd, "wb") as f:
                f.write(compressed)
            try:
                return event.image_result(path)
            except Exception as e:
                logger.error(f"image_result(path) 失败: {e}")
        except Exception as e:
            logger.error(f"本地文件保存失败: {e}")

        return event.plain_result("❌ 图片发送失败")

    async def _send_raw_image(self, event: AstrMessageEvent, img_bytes: bytes):
        url = await self._upload_to_image_host(img_bytes)
        if url:
            try:
                return event.image_result(url)
            except Exception as e:
                logger.error(f"image_result(url) 失败: {e}")
        try:
            fd, path = tempfile.mkstemp(suffix=".jpg", prefix="phi_")
            with os.fdopen(fd, "wb") as f:
                f.write(img_bytes)
            try:
                return event.image_result(path)
            except Exception as e:
                logger.error(f"image_result(path) 失败: {e}")
        except Exception as e:
            logger.error(f"本地文件保存失败: {e}")
        return event.plain_result("❌ 图片发送失败")

    async def _get_json(self, path: str, params: dict = None):
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy if self.proxy else None, timeout=self.timeout
            ) as client:
                resp = await client.get(f"{self.api_url}{path}", params=params, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                logger.error(f"API [{path}] 失败 [{resp.status_code}]: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"API [{path}] 异常: {e}")
        return None

    async def _post_json(self, path: str, body: dict = None, params: dict = None):
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy if self.proxy else None, timeout=self.timeout
            ) as client:
                resp = await client.post(f"{self.api_url}{path}", json=body, params=params, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                logger.error(f"API [{path}] 失败 [{resp.status_code}]: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"API [{path}] 异常: {e}")
        return None

    async def _fetch_remote_news(self) -> list:
        if not self.news_use_remote:
            return []
        if not self.news_source_url:
            return []
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy if self.proxy else None, timeout=self.timeout
            ) as client:
                if self.api_url in self.news_source_url:
                    resp = await client.get(self.news_source_url, headers=self._headers())
                else:
                    resp = await client.get(self.news_source_url)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data
        except Exception as e:
            logger.error(f"拉取远程更新源失败: {e}")
        return []

    async def _post_svg(self, path: str, body: dict = None, params: dict = None) -> bytes | None:
        try:
            async with httpx.AsyncClient(
                proxy=self.proxy if self.proxy else None, timeout=self.timeout + 15
            ) as client:
                resp = await client.post(f"{self.api_url}{path}", json=body, params=params, headers=self._headers())
                if resp.status_code != 200:
                    logger.error(f"SVG API [{path}] 失败 [{resp.status_code}]: {resp.text[:200]}")
                    return None
                svg_text = resp.text

                try:
                    html = (
                        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
                        "<style>"
                        "html,body{margin:0;padding:0;background:#141826;}"
                        "*{font-family:'Microsoft YaHei','微软雅黑','SimHei','Noto Sans CJK SC','Arial',sans-serif !important;}"
                        "img,image{max-width:100%;}"
                        "</style></head><body>"
                        + svg_text +
                        "</body></html>"
                    )
                    img_result = await self.html_render(html, {})
                    if isinstance(img_result, bytes) and len(img_result) > 1000:
                        return img_result
                    elif isinstance(img_result, str):
                        if "base64," in img_result:
                            data = base64.b64decode(img_result.split("base64,")[-1])
                            if len(data) > 1000:
                                return data
                        elif img_result.startswith("http"):
                            async with httpx.AsyncClient(
                                proxy=self.proxy if self.proxy else None, timeout=30
                            ) as dl:
                                r = await dl.get(img_result)
                                if r.status_code == 200 and len(r.content) > 1000:
                                    return r.content
                        elif os.path.exists(img_result):
                            with open(img_result, "rb") as f:
                                data = f.read()
                            if len(data) > 1000:
                                return data
                    elif isinstance(img_result, BytesIO):
                        data = img_result.getvalue()
                        if len(data) > 1000:
                            return data
                except Exception as e:
                    logger.error(f"html_render 失败: {e}")

                try:
                    import cairosvg
                    png = cairosvg.svg2png(bytestring=svg_text.encode("utf-8"))
                    if png and len(png) > 1000:
                        return png
                except Exception:
                    pass

                return None
        except Exception as e:
            logger.error(f"SVG API [{path}] 异常: {e}")
        return None

    # ══════════════════════════════════════════════
    # /phi_help（英文）/phi帮助（中文）
    # ══════════════════════════════════════════════
    @filter.command("phi_help", alias={"phi帮助"})
    async def phi_help(self, event: AstrMessageEvent):
        raw = event.message_str.strip()
        if raw.startswith("/"):
            raw = raw[1:]
        cmd_name = raw.split(None, 1)[0] if raw else ""
        use_chinese = ("帮助" in cmd_name)

        if use_chinese:
            yield event.plain_result(
                "📋 Phigros 插件指令列表（中文）\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "🔗 /phi_bind <Token>          - 手动绑定账号\n"
                "📱 /phi_qrcode bind           - 二维码绑定账号\n"
                "📊 /phi查分                   - 查询 Best 30 图片\n"
                "🔍 /phi搜歌 <歌名>            - 搜索歌曲信息\n"
                "🖼️ /phi曲绘 <歌名>            - 获取歌曲曲绘\n"
                "🎵 /phi单曲 <歌名>            - 查询单曲成绩\n"
                "🔓 /phi解绑                   - 解绑账号\n"
                "🔄 /phi更新                   - 更新账号信息\n"
                "🆕 /phi新曲                   - 最新更新公告\n"
                "♻️ /phi重载                   - 重载插件配置\n"
                "❓ /phi<别名>是什么歌          - 查询别名对应歌名\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "管理员：/phi别名\n"
                "  · /phi别名 查询              - 进入别名查询模式\n"
                "  · /phi别名 add <别名> <歌名> - 添加别名\n"
                "  · /phi别名 delete <别名>     - 删除别名\n"
                "  · /phi别名 temp              - 审核队列\n"
                "  · /phi_new add §内容§         - 覆盖当前公告（旧版入历史）\n"
                "  · /phi_new all               - 查看全部历史公告\n"
                "  · /phi_new del               - 清空公告数据库\n"
                "💡 支持带空格的歌名（如：/phi搜歌 CROSS SOUL）"
            )
        else:
            yield event.plain_result(
                "📋 Phigros Plugin Commands (English)\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "🔗 /phi_bind <Token>          - Bind account manually\n"
                "📱 /phi_qrcode bind           - Bind via QR code\n"
                "📊 /phi_b30                   - Query Best 30 image\n"
                "🔍 /phi_search <song>         - Search song info\n"
                "🖼️ /phi_picture <song>        - Get song illustration\n"
                "🎵 /phi_song <song>           - Query single song score\n"
                "🔓 /phi_unbind                - Unbind account\n"
                "🔄 /phi_update                - Update account info\n"
                "🆕 /phi_new                   - Latest update news\n"
                "♻️ /phi_reload                - Reload plugin config\n"
                "❓ /phi<alias>是什么歌        - Look up song by alias\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "Admin: /phi_othername\n"
                "  · /phi_othername query       - Enter alias query mode\n"
                "  · /phi_othername add <alias> <song> - Add alias\n"
                "  · /phi_othername delete <alias>     - Delete alias\n"
                "  · /phi_othername temp              - Review queue\n"
                "  · /phi_new add §content§         - Overwrite current news\n"
                "  · /phi_new all               - View all historical news\n"
                "  · /phi_new del               - Clear news database\n"
                "💡 Song names with spaces are supported (e.g. /phi_search CROSS SOUL)"
            )

    # ══════════════════════════════════════════════
    # /phi_bind（单指令，无别名）
    # ══════════════════════════════════════════════
    @filter.command("phi_bind")
    async def phi_bind(self, event: AstrMessageEvent, token: str = None):
        if not token or len(token.strip()) != 25:
            yield event.plain_result("⚠️ 请提供25位SessionToken，例如：/phi_bind 你的Token")
            return
        uid = event.get_sender_id()
        db = load_json(USER_DB, {})
        db[uid] = token.strip()
        save_json(USER_DB, db)
        yield event.plain_result("✅ 绑定成功！发送 /phi_b30 或 /phi查分 即可查询成绩。")

    # ══════════════════════════════════════════════
    # /phi_qrcode（单指令，无别名）
    # ══════════════════════════════════════════════
    @filter.command("phi_qrcode")
    async def phi_qrcode(self, event: AstrMessageEvent, action: str = None):
        if not action or action.strip().lower() != "bind":
            yield event.plain_result("⚠️ 用法：/phi_qrcode bind")
            return

        uid = event.get_sender_id()
        if uid in self._qrcode_polling_users:
            yield event.plain_result(
                "⚠️ 你已有一个二维码正在等待扫码。\n"
                "请先完成扫码，或等待当前二维码过期（约 5 分钟）后再试。"
            )
            return

        self._qrcode_polling_users[uid] = True
        terminated = False
        try:
            yield event.plain_result("🔄 正在获取官方登录二维码，请稍候...")

            try:
                async with httpx.AsyncClient(
                    proxy=self.proxy if self.proxy else None, timeout=self.timeout
                ) as client:
                    resp = await client.post(
                        f"{self.api_url}/api/v1/open/auth/qrcode",
                        headers=self._headers(),
                        params={"taptapVersion": self.taptap_ver}
                    )
                    if resp.status_code != 200:
                        yield event.plain_result(f"❌ 获取二维码失败，API 返回 {resp.status_code}")
                        terminated = True
                        return
                    data = resp.json()
            except Exception as e:
                yield event.plain_result(f"❌ 请求出错：{str(e)}")
                terminated = True
                return

            qr_id = data.get("qrId")
            v_url = data.get("verificationUrl")

            if not qr_id or not v_url:
                yield event.plain_result("❌ 未能解析二维码数据。")
                terminated = True
                return

            qr_sent = False
            try:
                import qrcode as qr_lib
                qr = qr_lib.QRCode(box_size=10, border=4)
                qr.add_data(v_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buf = BytesIO()
                img.save(buf, format="PNG")
                yield await self._send_image(event, buf.getvalue(), min_size=200)
                qr_sent = True
            except Exception as e:
                logger.error(f"生成二维码图片失败: {e}")

            if not qr_sent:
                yield event.plain_result(
                    f"📱 二维码图片生成失败。\n"
                    f"请打开以下链接，跳转至 TapTap 登录页面完成授权：\n{v_url}"
                )
            else:
                yield event.plain_result("📱 请使用 TapTap App 扫描上方二维码登录。")

            yield event.plain_result(
                "⚠️ 授权后，若机器人未自动绑定，请前往 Lilith 网页，点击『展示完整凭证信息』，"
                "复制完整的 25 位 Token，然后发送：\n"
                "/phi_bind <你的Token>"
            )

            poll_done = False
            for i in range(150):
                if poll_done:
                    break
                await asyncio.sleep(2)
                try:
                    async with httpx.AsyncClient(
                        proxy=self.proxy if self.proxy else None, timeout=self.timeout
                    ) as client:
                        poll_resp = await client.get(
                            f"{self.api_url}/api/v1/open/auth/qrcode/{qr_id}/status",
                            headers=self._headers()
                        )
                        if poll_resp.status_code == 200:
                            poll_data = poll_resp.json()
                            status = poll_data.get("status")
                            if status in ["Success", "Confirmed", "Authorized"]:
                                session_token = (
                                    poll_data.get("sessionToken") or
                                    poll_data.get("token") or
                                    poll_data.get("data", {}).get("sessionToken") or
                                    poll_data.get("data", {}).get("token") or
                                    poll_data.get("credential", {}).get("token")
                                )
                                if session_token and "..." not in session_token and len(str(session_token)) == 25:
                                    db = load_json(USER_DB, {})
                                    db[uid] = session_token
                                    save_json(USER_DB, db)
                                    yield event.plain_result("✅ 扫码成功！账号已自动绑定。")
                                else:
                                    yield event.plain_result(
                                        "⚠️ 扫码成功，但获取到的是遮罩 Token。\n"
                                        "请前往 Lilith 网页，点击『展示完整凭证信息』，"
                                        "复制完整的 25 位 Token 后，发送 /phi_bind <Token> 手动绑定。"
                                    )
                                poll_done = True
                                terminated = True
                                break
                            elif status == "Expired":
                                yield event.plain_result("⏰ 二维码已过期，请重新发送 /phi_qrcode bind。")
                                poll_done = True
                                terminated = True
                                break
                            elif status in ["WaitScan", "WaitConfirm", "Pending"]:
                                continue
                except Exception as e:
                    logger.error(f"轮询异常: {e}")
                    continue

            if not terminated:
                yield event.plain_result("⏰ 二维码已超时（300秒），请重新发送 /phi_qrcode bind。")
        finally:
            self._qrcode_polling_users.pop(uid, None)

    # ══════════════════════════════════════════════
    # /phi_b30（英文）/phi查分（中文）
    # ══════════════════════════════════════════════
    @filter.command("phi_b30", alias={"phi查分"})
    async def phi_b30(self, event: AstrMessageEvent):
        uid = event.get_sender_id()
        db = load_json(USER_DB, {})
        token = db.get(uid)
        if not token:
            yield event.plain_result("❌ 尚未绑定，请先使用 /phi_bind <Token> 绑定账号。")
            return
        yield event.plain_result("🔍 正在生成 B30 成绩图，请稍候...")
        img = await self._post_svg(
            "/api/v1/open/image/bn",
            body={"sessionToken": token, "taptapVersion": self.taptap_ver, "n": 30, "theme": "black"},
            params={"format": "svg"}
        )
        if img:
            yield await self._send_image(event, img)
        else:
            yield event.plain_result("❌ 生成 B30 图片失败。请检查日志。")

    # ══════════════════════════════════════════════
    # /phi_search（英文）/phi搜歌（中文）
    # ══════════════════════════════════════════════
    @filter.command("phi_search", alias={"phi搜歌"})
    async def phi_search(self, event: AstrMessageEvent):
        song_name = self._extract_song_name(event)
        if not song_name:
            yield event.plain_result("⚠️ 请输入歌曲名：/phi搜歌 Spasmodic")
            return
        resolved = self._resolve_song_name(song_name)
        yield event.plain_result(f"🔍 正在搜索「{resolved}」...")
        data = await self._get_json("/api/v1/open/songs/search", {"q": resolved})
        if not data:
            yield event.plain_result("❌ 搜索失败，请检查网络。")
            return
        items = data.get("items", [])
        if not items:
            yield event.plain_result(f"⚠️ 未找到与「{resolved}」相关的歌曲。")
            return
        lines = [f"🔍 搜索「{resolved}」结果：\n━━━━━━━━━━━━━━━━"]
        for s in items[:10]:
            constants = s.get("chartConstants", {})
            lines.append(
                f"🎵 {s.get('name','?')} - {s.get('composer','?')}\n"
                f"   ID: {s.get('id','?')}\n"
                f"   定数：EZ {constants.get('ez','-')} / HD {constants.get('hd','-')} / IN {constants.get('in','-')} / AT {constants.get('at','-')}"
            )
        yield event.plain_result("\n".join(lines))

    # ══════════════════════════════════════════════
    # /phi_picture（英文）/phi曲绘（中文）
    # ══════════════════════════════════════════════
    @filter.command("phi_picture", alias={"phi曲绘"})
    async def phi_picture(self, event: AstrMessageEvent):
        song_name = self._extract_song_name(event)
        if not song_name:
            yield event.plain_result("⚠️ 请输入歌曲名：/phi曲绘 Spasmodic")
            return
        resolved = self._resolve_song_name(song_name)
        yield event.plain_result(f"🖼️ 正在获取「{resolved}」的曲绘...")

        search_data = await self._get_json("/api/v1/open/songs/search", {"q": resolved})
        if not search_data or not search_data.get("items"):
            yield event.plain_result(f"⚠️ 未找到歌曲「{resolved}」。")
            return

        item = search_data["items"][0]
        song_id = item["id"]
        song_display_name = item.get("name", resolved)

        encoded_id = quote(song_id, safe="")
        ill_url = f"{ILLUSTRATION_CDN}/{encoded_id}.webp"

        try:
            async with httpx.AsyncClient(
                proxy=self.proxy if self.proxy else None, timeout=self.timeout
            ) as client:
                r = await client.get(ill_url)
                if r.status_code == 200 and len(r.content) > 1000:
                    hq_bytes = encode_image_hq(r.content)
                    logger.info(f"🎨 曲绘编码: {len(r.content)} → {len(hq_bytes)} 字节")
                    yield await self._send_raw_image(event, hq_bytes)
                    return
        except Exception as e:
            logger.error(f"曲绘下载异常: {e}")

        yield event.plain_result(f"❌ 未找到「{song_display_name}」的曲绘。")

    # ══════════════════════════════════════════════
    # /phi_song（英文）/phi单曲（中文）
    # ══════════════════════════════════════════════
    @filter.command("phi_song", alias={"phi单曲"})
    async def phi_song(self, event: AstrMessageEvent):
        song_name = self._extract_song_name(event)
        if not song_name:
            yield event.plain_result("⚠️ 请输入歌曲名：/phi单曲 Spasmodic")
            return
        resolved = self._resolve_song_name(song_name)

        uid = event.get_sender_id()
        db = load_json(USER_DB, {})
        token = db.get(uid)
        if not token:
            yield event.plain_result("❌ 尚未绑定，请先使用 /phi_bind <Token> 绑定账号。")
            return

        yield event.plain_result(f"🎵 正在生成「{resolved}」的单曲成绩图，请稍候...")

        search_data = await self._get_json("/api/v1/open/songs/search", {"q": resolved})
        if not search_data or not search_data.get("items"):
            yield event.plain_result(f"⚠️ 未找到歌曲「{resolved}」。")
            return
        song_id = search_data["items"][0]["id"]

        img = await self._post_svg(
            "/api/v1/open/image/song",
            body={"sessionToken": token, "taptapVersion": self.taptap_ver, "song": song_id},
            params={"format": "svg"}
        )
        if img:
            yield await self._send_image(event, img)
        else:
            yield event.plain_result("❌ 生成单曲成绩图失败，请检查日志。")

    # ══════════════════════════════════════════════
    # /phi_unbind（英文）/phi解绑（中文）
    # ══════════════════════════════════════════════
    @filter.command("phi_unbind", alias={"phi解绑"})
    async def phi_unbind(self, event: AstrMessageEvent):
        uid = event.get_sender_id()
        db = load_json(USER_DB, {})
        if uid in db:
            del db[uid]
            save_json(USER_DB, db)
            yield event.plain_result("✅ 账号已解绑。")
        else:
            yield event.plain_result("⚠️ 你尚未绑定账号。")

    # ══════════════════════════════════════════════
    # /phi_update（英文）/phi更新（中文）
    # ══════════════════════════════════════════════
    @filter.command("phi_update", alias={"phi更新"})
    async def phi_update(self, event: AstrMessageEvent):
        uid = event.get_sender_id()
        db = load_json(USER_DB, {})
        token = db.get(uid)
        if not token:
            yield event.plain_result("❌ 尚未绑定，请先使用 /phi_bind <Token> 绑定账号。")
            return
        yield event.plain_result("🔄 正在更新账号信息...")
        data = await self._post_json(
            "/api/v1/open/save",
            body={"sessionToken": token, "taptapVersion": self.taptap_ver}
        )
        if not data:
            yield event.plain_result("❌ 更新失败，请检查网络。")
            return
        nickname = data.get("nickname", "未知")
        rks = data.get("rks", {}).get("totalRks", "未知")
        rks_str = f"{rks:.4f}" if isinstance(rks, float) else str(rks)
        yield event.plain_result(
            f"✅ 账号数据已更新\n"
            f"🎮 玩家：{nickname}\n"
            f"📈 RKS：{rks_str}"
        )

    # ══════════════════════════════════════════════
    # /phi_new（英文）/phi新曲（中文）
    # ══════════════════════════════════════════════
    @filter.command("phi_new", alias={"phi新曲"})
    async def phi_new(self, event: AstrMessageEvent):
        args = self._extract_args_after_command(event, ["phi_new", "phi新曲"])
        args_low = args.lower()

        if args_low.startswith("add"):
            if not event.is_admin():
                yield event.plain_result("❌ 只有管理员才能添加更新公告。")
                return
            rest = args[3:].strip()
            m = re.search(r"§(.*?)§", rest, re.DOTALL)
            if not m:
                yield event.plain_result(
                    "⚠️ 格式错误。用法：\n"
                    "/phi_new add §公告内容§\n"
                    "（内容支持空格、换行、标点，但不能包含 § 符号）"
                )
                return
            content = m.group(1).strip()
            if not content:
                yield event.plain_result("⚠️ 公告内容不能为空。")
                return

            db = self._load_news_db()
            news = db["news"]

            old_current = None
            for n in news:
                if n.get("current"):
                    n["current"] = False
                    old_current = n

            new_id = (max([n.get("id", 0) for n in news]) + 1) if news else 1
            new_entry = {
                "id": new_id,
                "content": content,
                "author_id": event.get_sender_id(),
                "author_name": event.get_sender_name(),
                "timestamp": int(time.time()),
                "current": True,
            }
            news.append(new_entry)
            save_json(LOCAL_NEWS_DB, db)

            msg_parts = [f"✅ 已发布新公告 #{new_id}"]
            if old_current:
                msg_parts.append(f"📦 旧公告 #{old_current['id']} 已归档到历史库")
            msg_parts.append("━━━━━━━━━━━━━━━━")
            msg_parts.append(content)
            msg_parts.append("━━━━━━━━━━━━━━━━")
            msg_parts.append(f"👤 发布者：{event.get_sender_name()}")
            yield event.plain_result("\n".join(msg_parts))
            return

        if args_low == "del":
            if not event.is_admin():
                yield event.plain_result("❌ 只有管理员才能清空公告库。")
                return
            db = self._load_news_db()
            total = len(db["news"])
            if total == 0:
                yield event.plain_result("📋 公告数据库已经是空的。")
                return
            db["news"] = []
            save_json(LOCAL_NEWS_DB, db)
            yield event.plain_result(f"🗑️ 已清空公告数据库（删除了 {total} 条记录）。")
            return

        if args_low == "all":
            db = self._load_news_db()
            news = db["news"]
            if not news:
                yield event.plain_result("📋 公告数据库为空。")
                return
            news_sorted = sorted(news, key=lambda n: n.get("timestamp", 0), reverse=True)
            lines = [f"📚 公告数据库（共 {len(news)} 条，按时间倒序）\n━━━━━━━━━━━━━━━━"]
            for n in news_sorted:
                tag = "🟢 当前" if n.get("current") else "⚪ 历史"
                lines.append(f"#{n['id']} {tag}　👤 {n.get('author_name', '?')}")
                lines.append(n['content'])
                lines.append("━━━━━━━━━━━━━━━━")
            yield event.plain_result("\n".join(lines))
            return

        yield event.plain_result("🆕 正在获取最新更新信息...")

        parts = []

        remote_news = await self._fetch_remote_news()
        if remote_news:
            latest = remote_news[0]
            version = latest.get("version", "?")
            date = latest.get("updateDate", "?")
            content = latest.get("content", "")
            parts.append(
                f"🌐 远程更新公告（v{version}）\n"
                f"📅 {date}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"{content}"
            )

        db = self._load_news_db()
        news = db["news"]
        current_entry = None
        for n in news:
            if n.get("current"):
                current_entry = n
                break

        if current_entry:
            parts.append(
                f"📰 当前本地公告 #{current_entry['id']}　👤 {current_entry.get('author_name', '?')}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"{current_entry['content']}"
            )
        elif news:
            news_sorted = sorted(news, key=lambda n: n.get("timestamp", 0), reverse=True)
            latest_local = news_sorted[0]
            parts.append(
                f"📰 当前本地公告 #{latest_local['id']}　👤 {latest_local.get('author_name', '?')}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"{latest_local['content']}"
            )

        if not parts:
            yield event.plain_result("⚠️ 暂无更新信息。")
            return

        yield event.plain_result("\n\n".join(parts))

    # ══════════════════════════════════════════════
    # /phi_reload（英文）/phi重载（中文）
    # ══════════════════════════════════════════════
    @filter.command("phi_reload", alias={"phi重载"})
    async def phi_reload(self, event: AstrMessageEvent):
        try:
            self.api_url = self.config.get("phi_api_url", "https://r0semi.xtower.site").rstrip("/")
            self.api_key = self.config.get("lilith_api_key", "")
            self.proxy = self.config.get("proxy_url", "")
            self.timeout = self.config.get("timeout", 30)
            self.taptap_ver = self.config.get("default_taptap_version", "cn")
            self.aliases = load_json(ALIAS_DB, {})
            self.news_use_remote = self.config.get("news_use_remote", True)
            self.news_source_url = self.config.get("news_source_url", DEFAULT_NEWS_SOURCE).strip()
            self.news_local_show_count = self.config.get("news_local_show_count", 3)
            yield event.plain_result("✅ 插件配置已重载！")
        except Exception as e:
            yield event.plain_result(f"❌ 重载失败：{str(e)}")

    # ══════════════════════════════════════════════
    # /phi_othername（英文）/phi别名（中文）
    # ══════════════════════════════════════════════
    @filter.command("phi_othername", alias={"phi别名"})
    async def phi_othername(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        if msg.startswith("/"):
            msg = msg[1:]
        low = msg.lower()
        for prefix in ("phi_othername", "phi别名"):
            if low.startswith(prefix.lower()):
                msg = msg[len(prefix):].strip()
                break
        parts = msg.split()
        if not parts:
            yield event.plain_result(
                "📋 别名管理指令：\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "🔍 /phi别名 查询               - 进入别名查询模式\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "【普通成员】提交添加申请：\n"
                "  /phi别名 add <别名> <歌名>\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "【管理员】直接操作：\n"
                "  /phi别名 add <别名> <歌名>     - 直接添加\n"
                "  /phi别名 delete <别名>         - 直接删除\n"
                "  /phi别名 delete all            - 重置别名库\n"
                "  /phi别名 temp [页码]           - 查看待审核队列\n"
                "  /phi别名 temp approved <id>[,<id>...] - 通过指定申请"
            )
            return

        action = parts[0].lower()
        is_admin = event.is_admin()
        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name()

        if action in ("查询", "query"):
            rev_map = self._build_aliases_reverse_map()
            songs_list = sorted(rev_map.keys())

            if not songs_list:
                yield event.plain_result("📋 别名库为空，暂无可查询的歌曲。")
                return

            self._alias_query_mode[sender_id] = {
                "songs": songs_list,
                "map": rev_map,
                "time": time.time(),
            }

            lines = [f"🔍 **别名查询模式已开启**（共 {len(songs_list)} 首歌）"]
            lines.append("━" * 16)
            for i, name in enumerate(songs_list[:ALIAS_QUERY_PAGE_SIZE], 1):
                lines.append(f"{i}. {name}  ({len(rev_map[name])} 个别名)")
            if len(songs_list) > ALIAS_QUERY_PAGE_SIZE:
                lines.append(f"... 还有 {len(songs_list) - ALIAS_QUERY_PAGE_SIZE} 首未显示")
            lines.append("━" * 16)
            lines.append("💡 回复**序号**或**歌名**查看该歌的所有别名")
            lines.append("💡 输入「取消」退出查询模式")
            yield event.plain_result("\n".join(lines))
            return

        if action == "add":
            if len(parts) < 3:
                yield event.plain_result("⚠️ 用法：/phi别名 add <别名> <歌名>")
                return
            alias_name = parts[1]
            song_name = " ".join(parts[2:])
            if alias_name in self.aliases:
                yield event.plain_result(f"⚠️ 别名「{alias_name}」已存在，对应歌曲为「{self.aliases[alias_name]}」。")
                return
            if is_admin:
                self.aliases[alias_name] = song_name
                save_json(ALIAS_DB, self.aliases)
                yield event.plain_result(f"✅ 已添加别名：「{alias_name}」→「{song_name}」")
            else:
                temp = self._load_temp()
                for t in temp:
                    if t.get("alias") == alias_name:
                        yield event.plain_result(f"⚠️ 已有待审核的同名申请：「{alias_name}」，请等待管理员处理。")
                        return
                new_id = (max([t.get("id", 0) for t in temp]) + 1) if temp else 1
                temp.append({
                    "id": new_id, "type": "add",
                    "submitter_id": sender_id, "submitter_name": sender_name,
                    "alias": alias_name, "song": song_name
                })
                self._save_temp(temp)
                yield event.plain_result(
                    f"✅ 已提交别名申请，等待管理员审核。\n"
                    f"申请编号：{new_id}\n别名：「{alias_name}」→「{song_name}」"
                )

        elif action == "delete":
            if not is_admin:
                yield event.plain_result("❌ 只有管理员才能删除别名。")
                return
            if len(parts) >= 2 and parts[1].lower() == "all":
                defaults = load_default_aliases()
                if not defaults:
                    yield event.plain_result("⚠️ 默认别名文件为空或不存在，无法重置。")
                    return
                self.aliases = defaults
                save_json(ALIAS_DB, self.aliases)
                yield event.plain_result(f"✅ 已重置别名库，当前共 {len(self.aliases)} 条默认别名。")
                return
            if len(parts) < 2:
                yield event.plain_result("⚠️ 用法：/phi别名 delete <别名> 或 /phi别名 delete all")
                return
            alias_name = parts[1]
            if alias_name in self.aliases:
                del self.aliases[alias_name]
                save_json(ALIAS_DB, self.aliases)
                yield event.plain_result(f"✅ 已删除别名：「{alias_name}」")
            else:
                yield event.plain_result(f"⚠️ 未找到别名：「{alias_name}」")

        elif action == "temp":
            if not is_admin:
                yield event.plain_result("❌ 只有管理员才能查看审核队列。")
                return
            if len(parts) >= 2 and parts[1].lower() == "approved":
                if len(parts) < 3:
                    yield event.plain_result("⚠️ 用法：/phi别名 temp approved <id>[,<id>...]")
                    return
                id_str = parts[2]
                id_list = [int(x) for x in re.split(r"[,，\s]+", id_str.strip()) if x.isdigit()]
                if not id_list:
                    yield event.plain_result("⚠️ 无效的编号，请输入数字（可多个，用英文逗号隔开）。")
                    return
                temp = self._load_temp()
                if not temp:
                    yield event.plain_result("📋 当前没有待审核的别名申请。")
                    return
                approved_items, rejected_items = [], []
                for item in temp:
                    (approved_items if item["id"] in id_list else rejected_items).append(item)
                if not approved_items:
                    yield event.plain_result(
                        f"⚠️ 你输入的编号均不在当前队列中。\n"
                        f"当前队列编号：{', '.join(str(t['id']) for t in temp)}"
                    )
                    return
                for item in approved_items:
                    self.aliases[item["alias"]] = item["song"]
                save_json(ALIAS_DB, self.aliases)
                self._save_temp([])
                result_msg = f"📋 审核完毕！通过 {len(approved_items)} 条，驳回 {len(rejected_items)} 条。\n━━━━━━━━━━━━━━━━\n"
                if approved_items:
                    result_msg += "✅ 【已通过】：\n"
                    for item in approved_items:
                        result_msg += f"   {item['submitter_name']}「{item['alias']}」→「{item['song']}」\n"
                if rejected_items:
                    result_msg += "\n❌ 【已驳回】：\n"
                    for item in rejected_items:
                        result_msg += f"   {item['submitter_name']}「{item['alias']}」→「{item['song']}」\n"
                yield event.plain_result(result_msg)
                return
            temp = self._load_temp()
            if not temp:
                yield event.plain_result("📋 当前没有待审核的别名申请。")
                return
            PAGE_SIZE = 10
            total = len(temp)
            total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
            page = 1
            if len(parts) >= 2 and parts[1].isdigit():
                page = int(parts[1])
            if page < 1 or page > total_pages:
                yield event.plain_result(f"⚠️ 页码 {page} 无效，当前共 {total_pages} 页。")
                return
            start, end = (page - 1) * PAGE_SIZE, page * PAGE_SIZE
            page_items = temp[start:end]
            lines = [f"📋 待审核别名申请（第 {page}/{total_pages} 页，共 {total} 条）：\n━━━━━━━━━━━━━━━━"]
            for item in page_items:
                lines.append(f"{item['id']}.{item['song']} 别名:{item['alias']}")
            lines.append("")
            if page < total_pages:
                lines.append(f"➡️ 下一页：/phi别名 temp {page+1}")
            if page > 1:
                lines.append(f"⬅️ 上一页：/phi别名 temp {page-1}")
            lines.append("✅ 通过：/phi别名 temp approved <id>[,<id>...]")
            lines.append("⚠️ 未被选中的申请将被自动驳回。")
            yield event.plain_result("\n".join(lines))
        else:
            yield event.plain_result("⚠️ 未知操作。发送 /phi别名 查看用法。")

    # ══════════════════════════════════════════════
    # 别名查询模式消息监听
    # ══════════════════════════════════════════════
    @filter.regex(r".+")
    async def on_alias_query_input(self, event: AstrMessageEvent):
        uid = event.get_sender_id()
        if uid not in self._alias_query_mode:
            return

        state = self._alias_query_mode[uid]
        if time.time() - state["time"] > ALIAS_QUERY_TIMEOUT:
            del self._alias_query_mode[uid]
            return

        msg = event.message_str.strip()
        if not msg:
            return

        if msg.startswith("/"):
            return

        if msg in ("取消", "退出", "exit", "quit", "q", "Q"):
            del self._alias_query_mode[uid]
            yield event.plain_result("✅ 已退出别名查询模式。")
            return

        state["time"] = time.time()

        songs_list = state["songs"]
        rev_map = state["map"]

        target = None

        if msg.isdigit():
            idx = int(msg)
            if 1 <= idx <= len(songs_list):
                target = songs_list[idx - 1]
            else:
                yield event.plain_result(f"⚠️ 序号超出范围（1~{len(songs_list)}）。")
                return

        if target is None:
            msg_low = msg.lower()
            for name in songs_list:
                if name.lower() == msg_low:
                    target = name
                    break
            if target is None:
                for name in songs_list:
                    if msg_low in name.lower():
                        target = name
                        break

        if target is None:
            yield event.plain_result(
                f"⚠️ 未找到「{msg}」。\n"
                f"请输入正确的**序号**或**歌名**，或输入「取消」退出。"
            )
            return

        aliases = rev_map.get(target, [])
        lines = [f"🔍 **{target}** 的别名（{len(aliases)} 个）\n━━━━━━━━━━━━━━━━"]
        for i, a in enumerate(aliases, 1):
            lines.append(f"{i}. {a}")
        lines.append("━━━━━━━━━━━━━━━━")
        lines.append("💡 继续输入其他序号/歌名查询，或输入「取消」退出。")
        yield event.plain_result("\n".join(lines))

    # ══════════════════════════════════════════════
    # /phi<别名>是什么歌
    # ══════════════════════════════════════════════
    @filter.regex(r"phi(.+?)是什么歌")
    async def alias_query(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        m = re.search(r"phi(.+?)是什么歌", msg, re.IGNORECASE)
        if not m:
            return
        alias = m.group(1).strip().lstrip("/／@ ").strip()
        if not alias:
            return
        real = self.aliases.get(alias)
        if real:
            yield event.plain_result(f"「{alias}」是 {real}")
        else:
            yield event.plain_result(f"未找到别名「{alias}」对应的歌曲。")

    async def terminate(self):
        logger.info("❌ Phi 自定义查分插件已卸载。")