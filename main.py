import os
import sys

# ══════════════════════════════════════════════
# 1. 手动注入 GTK3 运行时路径
# ══════════════════════════════════════════════
_GTK_BIN_CANDIDATES = [
    r"C:\Program Files\GTK3-Runtime Win64\bin",
    r"C:\Program Files (x86)\GTK3-Runtime Win64\bin",
]
for _p in _GTK_BIN_CANDIDATES:
    if os.path.isdir(_p):
        os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(_p)
            except Exception:
                pass
        print(f"✅ [Phi插件] 已注入 GTK3 路径: {_p}")
        break

# ══════════════════════════════════════════════
# 2. 修复 fontconfig
# ══════════════════════════════════════════════
_gtk_etc_fonts = r"C:\Program Files\GTK3-Runtime Win64\etc\fonts"
_windows_fonts = r"C:\Windows\Fonts"
if os.path.isdir(_gtk_etc_fonts) and os.path.isdir(_windows_fonts):
    _local_conf = os.path.join(_gtk_etc_fonts, "local.conf")
    _conf_content = f'''<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>{_windows_fonts}</dir>
  <cachedir>%LOCALAPPDATA%/fontconfig/cache</cachedir>
</fontconfig>
'''
    try:
        if not os.path.exists(_local_conf):
            with open(_local_conf, "w", encoding="utf-8") as f:
                f.write(_conf_content)
            print(f"✅ [Phi插件] 已写入 fontconfig 配置: {_local_conf}")
    except Exception as e:
        print(f"⚠️ [Phi插件] 写入 fontconfig 失败: {e}")

# ══════════════════════════════════════════════
# 3. 依赖自检与自动安装
# ══════════════════════════════════════════════
import subprocess
import importlib

_REQUIRED_PACKAGES = [
    ("httpx",    "httpx"),
    ("qrcode",   "qrcode[pil]"),
    ("PIL",      "Pillow"),
    ("cairosvg", "cairosvg"),
]


def _check_and_install_deps():
    missing = []
    for import_name, pip_name in _REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
        except ImportError:
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


_missing_before = _check_and_install_deps()

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
DEFAULT_ALIAS_FILE = os.path.join(os.path.dirname(__file__), "default_aliases.json")

ILLUSTRATION_CDN = "https://somnia.xtower.site/lilith/ill"


def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


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

        if self.config.get("auto_load_aliases", True):
            if not self.aliases:
                defaults = load_default_aliases()
                if defaults:
                    self.aliases = defaults
                    save_json(ALIAS_DB, self.aliases)
                    logger.info(f"✅ 已自动加载 {len(self.aliases)} 条默认别名")

        logger.info("✅ Phi 自定义查分插件已加载！")

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
            return event.image_result(url)

        try:
            fd, path = tempfile.mkstemp(suffix=".jpg", prefix="phi_")
            with os.fdopen(fd, "wb") as f:
                f.write(compressed)
            return event.image_result(path)
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
                    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html,body {{ margin:0; padding:0; background:#141826; }}
  * {{ font-family: 'Microsoft YaHei','微软雅黑','SimHei','Arial',sans-serif !important; }}
  image, img {{ max-width:100%; }}
</style>
</head><body>{svg_text}</body></html>"""
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
                except Exception as e:
                    logger.warning(f"cairosvg 失败: {e}")

                return None
        except Exception as e:
            logger.error(f"SVG API [{path}] 异常: {e}")
        return None

    @filter.command("phi_help")
    async def phi_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "📋 Phigros 插件指令列表\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🔗 /phi_bind <Token>   - 手动绑定账号\n"
            "📱 /phi_qrcode bind    - 二维码绑定账号\n"
            "📊 /phi_b30            - 查询 Best 30 图片\n"
            "🔍 /phi_search <歌名>  - 搜索歌曲信息\n"
            "🖼️ /phi_picture <歌名> - 获取歌曲曲绘（纯图）\n"
            "🎵 /phi_song <歌名>    - 查询单曲成绩（图）\n"
            "🔓 /phi_unbind         - 解绑账号\n"
            "🔄 /phi_update         - 更新账号信息\n"
            "🆕 /phi_new            - 最新更新歌曲\n"
            "❓ /<别名>是什么歌     - 查询别名对应歌名\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "管理员：/phi_othername\n"
            "💡 支持带空格的歌名（如：/phi_search CROSS SOUL）"
        )

    @filter.command("phi_bind")
    async def phi_bind(self, event: AstrMessageEvent, token: str = None):
        if not token or len(token.strip()) != 25:
            yield event.plain_result("⚠️ 请提供25位SessionToken，例如：/phi_bind 你的Token")
            return
        uid = event.get_sender_id()
        db = load_json(USER_DB, {})
        db[uid] = token.strip()
        save_json(USER_DB, db)
        yield event.plain_result("✅ 绑定成功！发送 /phi_b30 即可查询成绩。")

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

    @filter.command("phi_b30")
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

    @filter.command("phi_search")
    async def phi_search(self, event: AstrMessageEvent):
        song_name = self._extract_song_name(event)
        if not song_name:
            yield event.plain_result("⚠️ 请输入歌曲名：/phi_search Spasmodic")
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

    @filter.command("phi_picture")
    async def phi_picture(self, event: AstrMessageEvent):
        song_name = self._extract_song_name(event)
        if not song_name:
            yield event.plain_result("⚠️ 请输入歌曲名：/phi_picture Spasmodic")
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
                    yield await self._send_image(event, r.content)
                    return
        except Exception as e:
            logger.error(f"曲绘下载异常: {e}")

        yield event.plain_result(f"❌ 未找到「{song_display_name}」的曲绘。")

    @filter.command("phi_song")
    async def phi_song(self, event: AstrMessageEvent):
        song_name = self._extract_song_name(event)
        if not song_name:
            yield event.plain_result("⚠️ 请输入歌曲名：/phi_song Spasmodic")
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

    @filter.command("phi_unbind")
    async def phi_unbind(self, event: AstrMessageEvent):
        uid = event.get_sender_id()
        db = load_json(USER_DB, {})
        if uid in db:
            del db[uid]
            save_json(USER_DB, db)
            yield event.plain_result("✅ 账号已解绑。")
        else:
            yield event.plain_result("⚠️ 你尚未绑定账号。")

    @filter.command("phi_update")
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

    @filter.command("phi_new")
    async def phi_new(self, event: AstrMessageEvent):
        yield event.plain_result("🆕 正在获取最新歌曲信息...")
        data = await self._get_json("/api/v1/open/song-updates")
        if not data or not isinstance(data, list):
            yield event.plain_result("❌ 获取失败，请检查网络。")
            return
        latest = data[0]
        version = latest.get("version", "?")
        date = latest.get("updateDate", "?")
        content = latest.get("content", "")
        yield event.plain_result(f"🆕 Phigros {version} 更新 ({date})\n\n{content}")

    @filter.command("phi_reload")
    async def phi_reload(self, event: AstrMessageEvent):
        try:
            self.api_url = self.config.get("phi_api_url", "https://r0semi.xtower.site").rstrip("/")
            self.api_key = self.config.get("lilith_api_key", "")
            self.proxy = self.config.get("proxy_url", "")
            self.timeout = self.config.get("timeout", 30)
            self.taptap_ver = self.config.get("default_taptap_version", "cn")
            self.aliases = load_json(ALIAS_DB, {})
            yield event.plain_result("✅ 插件配置已重载！")
        except Exception as e:
            yield event.plain_result(f"❌ 重载失败：{str(e)}")

    @filter.command("phi_othername")
    async def phi_othername(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        if msg.startswith("/"):
            msg = msg[1:]
        parts = msg.split()
        if len(parts) < 2:
            yield event.plain_result(
                "📋 别名管理指令：\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "【普通成员】提交添加申请：\n"
                "  /phi_othername add <别名> <歌名>\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "【管理员】直接操作：\n"
                "  /phi_othername add <别名> <歌名>     - 直接添加\n"
                "  /phi_othername delete <别名>         - 直接删除\n"
                "  /phi_othername delete all            - 重置别名库\n"
                "  /phi_othername temp [页码]           - 查看待审核队列（每页10条）\n"
                "  /phi_othername temp approved <id>[,<id>...]  - 通过指定申请\n"
                "  ⚠️ 审核后，队列中未通过的申请将被自动驳回。"
            )
            return
        action = parts[1].lower()
        is_admin = event.is_admin()
        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name()
        if action == "add":
            if len(parts) < 4:
                yield event.plain_result("⚠️ 用法：/phi_othername add <别名> <歌名>")
                return
            alias_name = parts[2]
            song_name = " ".join(parts[3:])
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
            if len(parts) >= 3 and parts[2].lower() == "all":
                defaults = load_default_aliases()
                if not defaults:
                    yield event.plain_result("⚠️ 默认别名文件为空或不存在，无法重置。")
                    return
                self.aliases = defaults
                save_json(ALIAS_DB, self.aliases)
                yield event.plain_result(f"✅ 已重置别名库，当前共 {len(self.aliases)} 条默认别名。")
                return
            if len(parts) < 3:
                yield event.plain_result("⚠️ 用法：/phi_othername delete <别名> 或 /phi_othername delete all")
                return
            alias_name = parts[2]
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
            if len(parts) >= 3 and parts[2].lower() == "approved":
                if len(parts) < 4:
                    yield event.plain_result("⚠️ 用法：/phi_othername temp approved <id>[,<id>...]")
                    return
                id_str = parts[3]
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
            if len(parts) >= 3 and parts[2].isdigit():
                page = int(parts[2])
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
                lines.append(f"➡️ 下一页：/phi_othername temp {page+1}")
            if page > 1:
                lines.append(f"⬅️ 上一页：/phi_othername temp {page-1}")
            lines.append("✅ 通过：/phi_othername temp approved <id>[,<id>...]")
            lines.append("⚠️ 未被选中的申请将被自动驳回。")
            yield event.plain_result("\n".join(lines))
        else:
            yield event.plain_result("⚠️ 未知操作。")

    # ══════════════════════════════════════════════
    # /<别名>是什么歌  —— 宽松匹配（兼容带 / 和不带 / 的情况）
    # ══════════════════════════════════════════════
    @filter.regex(r"(.+?)是什么歌")
    async def alias_query(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        logger.info(f"🔍 alias_query 收到消息: {msg!r}")

        m = re.search(r"(.+?)是什么歌", msg)
        if not m:
            return

        alias = m.group(1).strip()
        # 去掉可能的前缀符号（/、/、@机器人 等）
        alias = alias.lstrip("/／@ ").strip()

        logger.info(f"🔍 提取到的别名: {alias!r}")

        if not alias:
            return

        real = self.aliases.get(alias)
        if real:
            yield event.plain_result(f"「{alias}」是 {real}")
        else:
            yield event.plain_result(f"未找到别名「{alias}」对应的歌曲。")

    async def terminate(self):
        logger.info("❌ Phi 自定义查分插件已卸载。")