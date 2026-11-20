#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity 2.0 桌面端主题工坊 & 中文汉化伴随引擎 v2.1 (零弹窗静默防多开版)
修复与核心能力：
1. 采用 ctypes 直接调用 Windows 原生 version.dll 获取版本号，彻底消除后台定时弹出 PowerShell 黑框的问题；
2. 内置 Windows 命名互斥锁 + PID 文件，严格保证后台伴随守护单实例运行，绝不重复堆叠；
3. 桌面快捷方式直连 pythonw.exe 静默启动，全程无任何 CMD/PowerShell 闪框；
4. 100% 非侵入式热加载 WorkBuddy 主题 + 高精度中文汉化 + 随客户端更新自动同步。
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import mimetypes
import os
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
THEMES_DIR = BASE_DIR / "themes"
ASSETS_DIR = BASE_DIR / "assets"
I18N_DIR = BASE_DIR / "i18n"
LOGS_DIR = BASE_DIR / "logs"
CATALOG_PATH = THEMES_DIR / "catalog.json"
I18N_PATH = I18N_DIR / "zh-CN.json"
DISCOVERED_I18N_PATH = I18N_DIR / "discovered_new_ui_terms.json"
CONFIG_PATH = BASE_DIR / "config.json"
VERSION_STATE_PATH = BASE_DIR / "client_version_state.json"
DAEMON_PID_PATH = BASE_DIR / "companion_daemon.pid"

STYLE_TAG_ID = "agy-custom-theme-studio"
__version__ = "3.2.0"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
MUTEX_NAME = "Global\\AntigravityThemeStudioCompanionDaemon_v2"
_MUTEX_HANDLE = None


class SimpleWebSocket:
    """轻量级纯标准库 RFC6455 WebSocket 客户端，用于与本地 CDP 通信。"""

    def __init__(self, ws_url: str, timeout: float = 5.0) -> None:
        parsed = urllib.parse.urlparse(ws_url)
        if parsed.scheme != "ws":
            raise ValueError(f"仅支持本地 ws:// 协议，当前为: {ws_url}")
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path or "/"
        if parsed.query:
            self.path += f"?{parsed.query}"
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    def __enter__(self) -> "SimpleWebSocket":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(handshake.encode("ascii"))

        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("WebSocket 握手失败：连接提前关闭")
            response += chunk

        header_text = response.split(b"\r\n\r\n", 1)[0].decode("latin1")
        if " 101 " not in header_text.splitlines()[0]:
            raise ConnectionError(f"WebSocket 握手被拒绝: {header_text.splitlines()[0]}")

        expected_accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
        ).decode("ascii")
        if expected_accept not in header_text:
            raise ConnectionError("WebSocket 握手校验码不匹配")

    def _recv_exact(self, length: int) -> bytes:
        assert self.sock is not None
        buf = bytearray()
        while len(buf) < length:
            chunk = self.sock.recv(length - len(buf))
            if not chunk:
                raise ConnectionError("读取 WebSocket 帧时连接中断")
            buf.extend(chunk)
        return bytes(buf)

    def send_text(self, text: str) -> None:
        assert self.sock is not None
        payload = text.encode("utf-8")
        mask_key = os.urandom(4)
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        header.extend(mask_key)
        masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def recv_text(self) -> str:
        fragments: List[bytes] = []
        while True:
            b1, b2 = self._recv_exact(2)
            fin = (b1 & 0x80) != 0
            opcode = b1 & 0x0F
            masked = (b2 & 0x80) != 0
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask_key = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length)
            if masked:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            if opcode == 0x8:
                raise ConnectionError("服务端关闭了 WebSocket 连接")
            if opcode == 0x9:
                self._send_pong(payload)
                continue
            if opcode == 0xA:
                continue

            fragments.append(payload)
            if fin:
                return b"".join(fragments).decode("utf-8", errors="replace")

    def _send_pong(self, payload: bytes) -> None:
        assert self.sock is not None
        mask_key = os.urandom(4)
        header = bytearray([0x8A, 0x80 | len(payload)])
        header.extend(mask_key)
        masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


def log_event(message: str) -> None:
    """记录伴随守护日志。"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}\n"
    try:
        with (LOGS_DIR / "companion.log").open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def detect_antigravity_exe() -> str:
    """自动在当前 Windows 用户的常见安装目录与快捷方式中查找 Antigravity.exe（开箱零配置）。"""
    if os.name != "nt":
        return ""
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))
    prog_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    candidates = [
        local_app / "Programs" / "Antigravity" / "Antigravity.exe",
        local_app / "Programs" / "antigravity" / "Antigravity.exe",
        local_app / "Antigravity" / "Antigravity.exe",
        prog_files / "Antigravity" / "Antigravity.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    # 通过桌面与开始菜单快捷方式反查真实安装路径
    user_profile = Path(os.environ.get("USERPROFILE", ""))
    appdata = Path(os.environ.get("APPDATA", ""))
    search_dirs = [
        user_profile / "Desktop",
        appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
    ]
    ps_probe = """
$sh = New-Object -ComObject WScript.Shell
$dirs = @($env:USERPROFILE + '\\Desktop', $env:APPDATA + '\\Microsoft\\Windows\\Start Menu\\Programs', 'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs')
foreach ($d in $dirs) {
  if (Test-Path $d) {
    Get-ChildItem -Path $d -Recurse -Filter '*Antigravity*.lnk' -ErrorAction SilentlyContinue | ForEach-Object {
      $t = $sh.CreateShortcut($_.FullName).TargetPath
      if ($t -and $t.ToLower().EndsWith('antigravity.exe') -and (Test-Path $t)) {
        Write-Output $t
        exit 0
      }
    }
  }
}
"""
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps_probe],
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=4,
        ).decode("utf-8", errors="ignore").strip()
        if out and Path(out).exists():
            return out
    except Exception:
        pass
    return ""


def load_config() -> Dict[str, Any]:
    """读取用户配置文件；若未填客户端路径则自动探测。"""
    default_cfg = {
        "antigravity_exe": "",
        "debug_port": 9222,
        "active_theme": "wb-partner",
        "enable_zh_cn": True,
        "auto_follow_client_updates": True,
        "auto_watch_interval_sec": 2.0,
    }
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            default_cfg.update(data)
        except Exception:
            pass
    exe_str = str(default_cfg.get("antigravity_exe", "")).strip()
    if not exe_str or not Path(exe_str).exists():
        detected = detect_antigravity_exe()
        if detected:
            default_cfg["antigravity_exe"] = detected
    return default_cfg


def save_config(cfg: Dict[str, Any]) -> None:
    """持久化用户配置。"""
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def load_catalog() -> List[Dict[str, Any]]:
    """读取所有可用主题目录。"""
    if not CATALOG_PATH.exists():
        return []
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def load_i18n_dict() -> Dict[str, Any]:
    """读取中文汉化词典。"""
    if not I18N_PATH.exists():
        return {"exact": {}, "placeholders": {}, "regex": []}
    return json.loads(I18N_PATH.read_text(encoding="utf-8"))


def resolve_css_assets(css_text: str) -> str:
    """将 CSS 中的 {{ASSET:filename}} 编译为 Base64 Data URI，并自动剥离会破坏 Electron 顶栏右上角点击的 backdrop-filter。"""
    pattern = re.compile(r"\{\{ASSET:([^}]+)\}\}")

    def _replace(match: re.Match) -> str:
        rel_name = match.group(1).strip()
        asset_path = ASSETS_DIR / rel_name
        if not asset_path.exists():
            return ""
        mime, _ = mimetypes.guess_type(str(asset_path))
        if asset_path.suffix.lower() == ".svg":
            mime = "image/svg+xml"
        elif not mime:
            mime = "image/png"
        b64 = base64.b64encode(asset_path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    resolved = pattern.sub(_replace, css_text)
    # 关键修复：移除所有 backdrop-filter 避免在 Electron 无边框窗口创建异常层叠上下文导致右上角按钮与下拉菜单无法点击/选择
    resolved = re.sub(r"(-webkit-)?backdrop-filter\s*:[^;{}]+;\s*", "", resolved)
    safe_guard = """
/* === Electron 顶栏与右上角按钮防拦截保护 === */
header, [role="banner"], [class*="titlebar"], [class*="TitleBar"] {
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}
header button, header [role="button"], header a, header input, header select,
[class*="titlebar"] button, [class*="TitleBar"] button,
[class*="titlebar"] [role="button"], [class*="TitleBar"] [role="button"],
[role="menu"], [role="listbox"], [role="combobox"], [data-radix-popper-content-wrapper] {
  -webkit-app-region: no-drag !important;
  pointer-events: auto !important;
}
"""
    return resolved + "\n" + safe_guard


def import_custom_wallpaper(image_path: str, display_name: str = "自定义主图") -> Dict[str, Any]:
    """一键将用户本地图片导入为新的 WorkBuddy 风格主图主题。"""
    from PIL import Image

    src = Path(image_path)
    if not src.exists():
        raise FileNotFoundError(f"找不到图片文件: {src}")

    slug = f"custom-{int(time.time())}"
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    (ASSETS_DIR / "thumbs").mkdir(parents=True, exist_ok=True)
    (ASSETS_DIR / "previews").mkdir(parents=True, exist_ok=True)

    img = Image.open(src).convert("RGB")
    img_opt = img.resize((1600, 900), Image.Resampling.LANCZOS)
    bg_file = f"{slug}.jpg"
    img_opt.save(ASSETS_DIR / bg_file, "JPEG", quality=84, optimize=True)
    img_opt.resize((220, 128), Image.Resampling.LANCZOS).save(ASSETS_DIR / "thumbs" / f"{slug}.png", "PNG")
    img_opt.resize((720, 380), Image.Resampling.LANCZOS).save(ASSETS_DIR / "previews" / f"{slug}.png", "PNG")

    css_content = f"""/* 自定义主图主题：{display_name} */
:root {{
  color-scheme: light;
  --agy-bg-base: #f8faff;
  --agy-bg-elevated: rgba(255, 255, 255, 0.84);
  --agy-bg-sidebar: rgba(244, 247, 255, 0.80);
  --agy-bg-input: rgba(255, 255, 255, 0.92);
  --agy-bg-code: rgba(246, 248, 252, 0.92);
  --agy-text-primary: #181c24;
  --agy-text-secondary: #4e5969;
  --agy-accent: #5b6cf9;
  --agy-accent-soft: rgba(91, 108, 249, 0.14);
  --agy-border: rgba(145, 164, 232, 0.28);
  --agy-font-sans: "PingFang SC", "HarmonyOS Sans SC", "Microsoft YaHei UI", system-ui, sans-serif;
  --agy-font-mono: "JetBrains Mono", "Cascadia Code", Consolas, monospace;
}}
html, body {{
  background-color: var(--agy-bg-base) !important;
  background-image: url("{{{{ASSET:{bg_file}}}}}") !important;
  background-size: cover !important;
  background-position: center center !important;
  background-repeat: no-repeat !important;
  background-attachment: fixed !important;
  color: var(--agy-text-primary) !important;
  font-family: var(--agy-font-sans) !important;
}}
#root, #app, main, [role="main"] {{ background-color: transparent !important; }}
aside, nav, [role="navigation"], [data-sidebar], [class*="sidebar"] {{
  background: var(--agy-bg-sidebar) !important;
  backdrop-filter: blur(16px) !important;
  border-color: var(--agy-border) !important;
}}
form:has(textarea), form:has([contenteditable="true"]), [class*="composer"] {{
  background: rgba(255, 255, 255, 0.88) !important;
  backdrop-filter: blur(14px) !important;
  border: 1.5px solid var(--agy-border) !important;
  border-radius: 16px !important;
}}
"""
    css_name = f"{slug}.css"
    (THEMES_DIR / css_name).write_text(css_content, encoding="utf-8")

    catalog = load_catalog()
    entry = {
        "id": slug,
        "name": display_name[:8],
        "english": slug,
        "mode": "light",
        "badge": "自定义",
        "stage_bg": "#dce7ff",
        "accent": "#5b6cf9",
        "sidebar_tint": "#eef2ff",
        "description": f"用户自定义主图主题（来源：{src.name}）",
        "thumb": f"thumbs/{slug}.png",
        "preview": f"previews/{slug}.png",
        "file": css_name,
    }
    catalog.append(entry)
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def get_theme_css(theme_id: str) -> Tuple[Dict[str, Any], str, Path]:
    """根据主题 ID 获取元数据、已解析内嵌主图的 CSS 源码及文件路径。"""
    catalog = load_catalog()
    for item in catalog:
        if item["id"] == theme_id:
            css_path = THEMES_DIR / item["file"]
            if not css_path.exists():
                raise FileNotFoundError(f"找不到主题 CSS 文件: {css_path}")
            raw_css = css_path.read_text(encoding="utf-8")
            return item, resolve_css_assets(raw_css), css_path

    direct_path = THEMES_DIR / (theme_id if theme_id.endswith(".css") else f"{theme_id}.css")
    if direct_path.exists():
        meta = {
            "id": direct_path.stem,
            "name": direct_path.stem,
            "english": direct_path.stem,
            "mode": "light",
            "description": "用户自定义 CSS 主题文件",
            "file": direct_path.name,
        }
        return meta, resolve_css_assets(direct_path.read_text(encoding="utf-8")), direct_path

    valid_ids = ", ".join(item["id"] for item in catalog)
    raise ValueError(f"未找到主题 '{theme_id}'。可选主题: {valid_ids}")


def _read_win32_file_version(path_str: str) -> str:
    """纯 ctypes 调用 Windows version.dll 读取 PE 文件版本号，绝对不创建任何子进程、绝不弹黑框。"""
    if os.name != "nt":
        return "unknown"
    try:
        version_dll = ctypes.windll.version
        dummy = ctypes.c_uint(0)
        size = version_dll.GetFileVersionInfoSizeW(path_str, ctypes.byref(dummy))
        if not size:
            return "unknown"
        buf = ctypes.create_string_buffer(size)
        if not version_dll.GetFileVersionInfoW(path_str, 0, size, buf):
            return "unknown"

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [
                ("dwSignature", ctypes.c_uint32),
                ("dwStrucVersion", ctypes.c_uint32),
                ("dwFileVersionMS", ctypes.c_uint32),
                ("dwFileVersionLS", ctypes.c_uint32),
                ("dwProductVersionMS", ctypes.c_uint32),
                ("dwProductVersionLS", ctypes.c_uint32),
                ("dwFileFlagsMask", ctypes.c_uint32),
                ("dwFileFlags", ctypes.c_uint32),
                ("dwFileOS", ctypes.c_uint32),
                ("dwFileType", ctypes.c_uint32),
                ("dwFileSubtype", ctypes.c_uint32),
                ("dwFileDateMS", ctypes.c_uint32),
                ("dwFileDateLS", ctypes.c_uint32),
            ]

        ptr = ctypes.c_void_p()
        length = ctypes.c_uint(0)
        if version_dll.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)):
            if ptr.value and length.value >= ctypes.sizeof(VS_FIXEDFILEINFO):
                info = ctypes.cast(ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
                ms = info.dwProductVersionMS or info.dwFileVersionMS
                ls = info.dwProductVersionLS or info.dwFileVersionLS
                return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:
        pass
    return "unknown"


def get_client_fingerprint(exe_path_str: str) -> Dict[str, Any]:
    """零子进程读取 Antigravity.exe 文件指纹，用于检测客户端版本更新。"""
    p = Path(exe_path_str)
    if not p.exists():
        return {"exists": False, "path": exe_path_str}
    st = p.stat()
    return {
        "exists": True,
        "path": str(p),
        "size": st.st_size,
        "mtime": int(st.st_mtime),
        "version": _read_win32_file_version(str(p)),
    }


def check_client_updated(exe_path_str: str) -> Tuple[bool, Dict[str, Any]]:
    """对比上次记录的客户端指纹，判断 Antigravity 2.0 是否刚发生版本更新。"""
    current = get_client_fingerprint(exe_path_str)
    if not current.get("exists"):
        return False, current

    prev: Dict[str, Any] = {}
    if VERSION_STATE_PATH.exists():
        try:
            prev = json.loads(VERSION_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

    changed = bool(prev) and (
        prev.get("version") != current.get("version")
        or prev.get("size") != current.get("size")
        or prev.get("mtime") != current.get("mtime")
    )
    if changed or not prev:
        current["checked_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        VERSION_STATE_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        if changed:
            log_event(
                f"检测到 Antigravity 客户端已更新：{prev.get('version')} -> {current.get('version')}，已自动同步主题与中文汉化。"
            )
    return changed, current


def _acquire_daemon_singleton() -> bool:
    """使用 Windows 命名互斥体保证后台伴随守护严格单实例运行。"""
    global _MUTEX_HANDLE
    if os.name != "nt":
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True
    last_err = kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183
    if last_err == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _MUTEX_HANDLE = handle
    return True


def fetch_cdp_targets(port: int, timeout: float = 2.0) -> List[Dict[str, Any]]:
    """从本地 CDP 端口拉取可注入的渲染目标列表。"""
    url = f"http://127.0.0.1:{port}/json"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            targets = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"无法连接到本地 CDP 端口 {port}。\n"
            f"请先完全退出 Antigravity（含托盘图标），再双击桌面「Antigravity (WorkBuddy主题+汉化)」启动。"
        ) from exc

    valid: List[Dict[str, Any]] = []
    for t in targets:
        if t.get("type") in ("page", "webview", "app") and t.get("webSocketDebuggerUrl"):
            target_url = str(t.get("url", ""))
            if target_url.startswith("devtools://"):
                continue
            valid.append(t)
    return valid


def cdp_eval(ws_url: str, expression: str, timeout: float = 4.0) -> Dict[str, Any]:
    """通过 CDP Runtime.evaluate 在目标渲染页执行 JS 表达式。"""
    cmd = {
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expression,
            "returnByValue": True,
        },
    }
    with SimpleWebSocket(ws_url, timeout=timeout) as ws:
        ws.send_text(json.dumps(cmd))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = ws.recv_text()
            msg = json.loads(raw)
            if msg.get("id") == 1:
                return msg
    raise TimeoutError("等待 CDP 响应超时")


def build_theme_inject_js(theme_id: str, css_text: str, meta: Optional[Dict[str, Any]] = None) -> str:
    """
    构造 v3.1.0 全界面几何语义自适应换肤 JS（零层叠冲突 + 零点击打断版）：
    1. 严格幂等签名校验：相同主题与样式直接跳过，伴随守护轮询时 0 次 DOM 修改、0 次 Reflow；
    2. 壁纸层位于 z-index: -1，绝不篡改 body 直接子元素的 position / z-index，彻底保护 React Portal / Radix 下拉框与左侧列表点击；
    3. 「伙伴」探头小猫采用独立 pointer-events:none 悬浮贴纸精准定位，不改动输入框容器的任何 position/overflow 属性；
    4. 检测到页面已打开下拉菜单/列表框时自动暂停几何扫描，杜绝打断选项点击或菜单自动关闭。
    """
    meta = meta or {}
    is_dark = meta.get("mode") == "dark"
    sidebar_bg = meta.get("sidebar_tint", "#ecf1fe")
    accent = meta.get("accent", "#5b6cf9")
    has_cat = bool(meta.get("has_cat", False))
    bg_asset_uri = ""
    m_bg = re.search(r'background-image\s*:\s*url\("(data:image/[^"]+)"\)', css_text)
    if m_bg:
        bg_asset_uri = m_bg.group(1)
    cat_uri = _encode_asset_uri("partner-cat.svg") if has_cat else ""

    adaptive_css = f"""
/* === v3.1.0 全界面几何语义自适应增强层（零点击拦截） === */
#agy-wb-wallpaper-layer {{
  position: fixed !important;
  inset: 0 !important;
  z-index: -1 !important;
  pointer-events: none !important;
  background-size: cover !important;
  background-position: center bottom !important;
  background-repeat: no-repeat !important;
}}
#agy-wb-cat-sticker {{
  position: fixed !important;
  width: 82px !important;
  height: 48px !important;
  pointer-events: none !important;
  z-index: 40 !important;
  background-size: contain !important;
  background-repeat: no-repeat !important;
  background-position: bottom center !important;
}}
[data-agy-role="canvas"] {{
  background-color: transparent !important;
  background-image: none !important;
}}
[data-agy-role="sidebar"] {{
  background-color: {("rgba(19, 21, 26, 0.88)" if is_dark else f"color-mix(in srgb, {sidebar_bg} 84%, transparent)")} !important;
  border-right: 1px solid {("rgba(255,255,255,0.08)" if is_dark else "rgba(145, 164, 232, 0.28)")} !important;
}}
[data-agy-role="titlebar"] {{
  background-color: {("rgba(19, 21, 26, 0.78)" if is_dark else "rgba(255, 255, 255, 0.62)")} !important;
  border-bottom: 1px solid {("rgba(255,255,255,0.07)" if is_dark else "rgba(145, 164, 232, 0.22)")} !important;
}}
[data-agy-role="auxpane"] {{
  background-color: {("rgba(24, 26, 31, 0.84)" if is_dark else "rgba(255, 255, 255, 0.78)")} !important;
  border-left: 1px solid {("rgba(255,255,255,0.08)" if is_dark else "rgba(145, 164, 232, 0.24)")} !important;
}}
[data-agy-role="composer"] {{
  background-color: {("rgba(32, 35, 42, 0.92)" if is_dark else "rgba(255, 255, 255, 0.92)")} !important;
  border: 1.5px solid {("rgba(78, 139, 255, 0.35)" if is_dark else "rgba(145, 164, 232, 0.55)")} !important;
  border-radius: 18px !important;
  box-shadow: 0 12px 32px -12px {("rgba(0,0,0,0.55)" if is_dark else "rgba(91, 108, 249, 0.22)")} !important;
}}
[data-agy-role="composer"]:focus-within {{
  border-color: {accent} !important;
  box-shadow: 0 0 0 3px {("rgba(78, 139, 255, 0.20)" if is_dark else "rgba(91, 108, 249, 0.16)")}, 0 14px 36px -12px {("rgba(0,0,0,0.6)" if is_dark else "rgba(91, 108, 249, 0.28)")} !important;
}}
/* 强力保护所有下拉菜单、模型选择器、侧边栏列表项与弹窗交互 100% 畅通 */
[role="listbox"], [role="menu"], [role="option"], [role="menuitem"],
[data-radix-popper-content-wrapper], [data-radix-menu-content], [data-state="open"] {{
  pointer-events: auto !important;
  -webkit-app-region: no-drag !important;
}}
[data-agy-role="sidebar"] button,
[data-agy-role="sidebar"] a,
[data-agy-role="sidebar"] [role="button"],
[data-agy-role="sidebar"] [role="listitem"],
[data-agy-role="composer"] button,
[data-agy-role="composer"] [role="button"],
[data-agy-role="composer"] [role="combobox"] {{
  pointer-events: auto !important;
  -webkit-app-region: no-drag !important;
}}
"""
    # 清除旧主题 CSS 中可能残留的 ::before 小猫与 position/overflow 强改（改由独立贴纸层实现）
    cleaned_css = re.sub(
        r"form:has\([^)]+\)::before[^{]*\{[^}]*\}",
        "",
        css_text,
        flags=re.DOTALL,
    )
    cleaned_css = re.sub(r"^\s*(position\s*:\s*relative|overflow\s*:\s*visible)\s*!important;\s*$", "", cleaned_css, flags=re.MULTILINE)

    full_css = cleaned_css + "\n" + adaptive_css
    theme_sig = hashlib.md5(f"v3.1.0|{theme_id}|{full_css}|{bg_asset_uri}|{cat_uri}".encode("utf-8")).hexdigest()

    css_json = json.dumps(full_css)
    theme_json = json.dumps(theme_id)
    tag_json = json.dumps(STYLE_TAG_ID)
    bg_json = json.dumps(bg_asset_uri)
    cat_json = json.dumps(cat_uri)
    sig_json = json.dumps(theme_sig)
    has_bg = bool(bg_asset_uri)

    return f"""(() => {{
  const SIG = {sig_json};
  const id = {tag_json};
  const css = {css_json};
  const themeId = {theme_json};
  const bgUri = {bg_json};
  const catUri = {cat_json};
  const hasBg = {json.dumps(has_bg)};

  // 严格幂等跳过：若当前版本主题已生效，不碰任何 DOM、不打断任何下拉框或点击事件
  if (window.__AGY_THEME_SIG__ === SIG && document.getElementById(id)) {{
    return {{ ok: true, skipped: true, theme: themeId }};
  }}

  // 主动清理旧版 v3.0 可能遗留在 body 直接子元素上的内联 position / zIndex 脏样式（立刻释放被压住的 Portal 下拉框）
  if (document.body) {{
    Array.from(document.body.children).forEach(ch => {{
      if (ch.id === 'agy-wb-wallpaper-layer' || ch.id === 'agy-wb-theme-picker-host' || ch.id === 'agy-wb-cat-sticker') return;
      if (ch.style && ch.style.zIndex === '1' && ch.style.position === 'relative') {{
        ch.style.removeProperty('position');
        ch.style.removeProperty('z-index');
      }}
    }});
  }}

  let el = document.getElementById(id);
  if (!el) {{
    el = document.createElement('style');
    el.id = id;
    (document.head || document.documentElement).appendChild(el);
  }}
  if (el.textContent !== css) {{
    el.textContent = css;
  }}
  document.documentElement.setAttribute('data-agy-theme', themeId);

  // 移除旧版遗留的额外壁纸 div（直接由 html, body 原生承载主图，零额外全屏图层）
  const oldWp = document.getElementById('agy-wb-wallpaper-layer');
  if (oldWp) oldWp.remove();

  // 独立探头小猫贴纸（不修改输入框任何布局属性）
  let catEl = document.getElementById('agy-wb-cat-sticker');
  if (catUri) {{
    if (!catEl) {{
      catEl = document.createElement('div');
      catEl.id = 'agy-wb-cat-sticker';
      if (document.body) document.body.appendChild(catEl);
    }}
    catEl.style.backgroundImage = 'url("' + catUri + '")';
  }} else if (catEl) {{
    catEl.remove();
    catEl = null;
  }}

  const positionCatSticker = () => {{
    const sticker = document.getElementById('agy-wb-cat-sticker');
    if (!sticker) return;
    const comp = document.querySelector('[data-agy-role="composer"]');
    if (!comp) {{
      sticker.style.display = 'none';
      return;
    }}
    const r = comp.getBoundingClientRect();
    if (r.width < 150 || r.height < 30 || r.top < 50) {{
      sticker.style.display = 'none';
      return;
    }}
    sticker.style.display = 'block';
    sticker.style.top = Math.round(r.top - 42) + 'px';
    sticker.style.left = Math.round(r.right - 104) + 'px';
  }};

  const applyGeometryRoles = () => {{
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (vw < 400 || vh < 300 || !document.body) return;

    // 关键防打断：若当前有展开的下拉菜单/模型选择器/弹窗，暂停 DOM 扫描以免触发菜单失焦关闭
    if (document.querySelector('[role="listbox"], [role="menu"], [data-radix-popper-content-wrapper]')) {{
      return;
    }}

    const isOpaqueBg = (bg) => {{
      if (!bg || bg === 'transparent' || bg === 'rgba(0, 0, 0, 0)') return false;
      const m = bg.match(/rgba?\\(\\s*(\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\s*\\)/);
      if (!m) return false;
      const a = m[4] === undefined ? 1 : parseFloat(m[4]);
      return a >= 0.88;
    }};

    const skipRole = (node) => {{
      if (!node || node.nodeType !== 1) return true;
      if (node.id === 'agy-wb-wallpaper-layer' || node.id === 'agy-wb-theme-picker-host' || node.id === 'agy-wb-cat-sticker') return true;
      if (node.hasAttribute('data-radix-portal') || node.closest('[data-radix-portal], [role="dialog"], [role="menu"], [role="listbox"], [data-radix-popper-content-wrapper], pre, code, .monaco-editor')) return true;
      const cs = getComputedStyle(node);
      if (cs.position === 'fixed' || cs.position === 'absolute') return true;
      return false;
    }};

    const setRoleIfDiff = (node, role) => {{
      if (node.getAttribute('data-agy-role') !== role) {{
        node.setAttribute('data-agy-role', role);
      }}
    }};

    const getDepth = (node) => {{
      let d = 0, p = node;
      while (p && p !== document.body && d < 15) {{ d++; p = p.parentElement; }}
      return d;
    }};

    // 清理旧的布局观察器（v3.2.0 不再挂载高频布局 MutationObserver，彻底消除悬停/点击时的重排卡顿与选项失灵）
    if (window.__AGY_LAYOUT_OBSERVER__) {{
      try {{ window.__AGY_LAYOUT_OBSERVER__.disconnect(); }} catch (e) {{}}
      window.__AGY_LAYOUT_OBSERVER__ = null;
    }}

    let foundSidebar = false;
    let foundTitlebar = false;
    const nodes = document.body.querySelectorAll('div, main, section, aside, nav, header');
    nodes.forEach(node => {{
      if (skipRole(node)) return;
      const depth = getDepth(node);
      if (depth > 6) return;
      const rect = node.getBoundingClientRect();
      if (rect.width < 120 || rect.height < 26) return;

      if (!foundTitlebar && rect.top <= 4 && rect.height >= 28 && rect.height <= 64 && rect.width >= vw * 0.55) {{
        setRoleIfDiff(node, 'titlebar');
        foundTitlebar = true;
        return;
      }}
      if (!foundSidebar && rect.left <= 6 && rect.width >= 160 && rect.width <= 360 && rect.height >= vh * 0.65) {{
        setRoleIfDiff(node, 'sidebar');
        foundSidebar = true;
        return;
      }}
      if (rect.right >= vw - 6 && rect.left >= vw * 0.40 && rect.width >= 240 && rect.width <= vw * 0.62 && rect.height >= vh * 0.65 && depth <= 5) {{
        setRoleIfDiff(node, 'auxpane');
        return;
      }}
      // 仅对浅层（depth <= 5）的全屏/主区实心底板设透明，绝不触碰内部卡片、列表或弹出菜单
      if (hasBg && depth <= 5 && rect.width >= vw * 0.45 && rect.height >= vh * 0.45) {{
        const cs = getComputedStyle(node);
        if (isOpaqueBg(cs.backgroundColor)) {{
          setRoleIfDiff(node, 'canvas');
        }}
      }}
    }});

    // 仅向上找最近一层输入胶囊外壳（找到第一个符合尺寸的即停止，绝不标记外层大容器）
    const activeComposers = new Set();
    const inputs = document.querySelectorAll('textarea, [contenteditable="true"][role="textbox"], [contenteditable="true"]');
    inputs.forEach(inp => {{
      if (skipRole(inp)) return;
      const r = inp.getBoundingClientRect();
      if (r.width < 200 || r.height < 18 || r.top < vh * 0.15) return;
      let cur = inp.parentElement;
      let best = null;
      for (let depth = 0; depth < 5 && cur && cur !== document.body; depth++) {{
        const cr = cur.getBoundingClientRect();
        if (cr.width >= 260 && cr.width <= Math.min(1050, vw * 0.85) && cr.height >= 48 && cr.height <= 240) {{
          best = cur;
          break;
        }}
        cur = cur.parentElement;
      }}
      if (best) {{
        activeComposers.add(best);
        setRoleIfDiff(best, 'composer');
      }}
    }});
    document.querySelectorAll('[data-agy-role="composer"]').forEach(old => {{
      if (!activeComposers.has(old)) old.removeAttribute('data-agy-role');
    }});

    positionCatSticker();
  }};

  applyGeometryRoles();

  if (window.__AGY_RESIZE_HANDLER__) {{
    window.removeEventListener('resize', window.__AGY_RESIZE_HANDLER__);
  }}
  window.__AGY_RESIZE_HANDLER__ = () => {{
    applyGeometryRoles();
  }};
  window.addEventListener('resize', window.__AGY_RESIZE_HANDLER__);
  window.__AGY_THEME_SIG__ = SIG;

  return {{ ok: true, theme: themeId, hasBg }};
}})()"""


def build_i18n_inject_js(dict_data: Dict[str, Any]) -> str:
    """构造带作用域保护 + MutationObserver 实时追踪 + 可无痕回滚的中文汉化 JS。"""
    dict_json = json.dumps(dict_data, ensure_ascii=False)
    dict_sig = hashlib.md5(dict_json.encode("utf-8")).hexdigest()
    return f"""(() => {{
  const DICT_SIG = {json.dumps(dict_sig)};
  if (window.__AGY_I18N_ACTIVE_SIG__ === DICT_SIG && window.__AGY_I18N_OBSERVER__) {{
    return {{ ok: true, skipped: true }};
  }}
  const DICT = {dict_json};
  const EXACT = DICT.exact || {{}};
  const PLACEHOLDERS = DICT.placeholders || {{}};
  const REGEX_LIST = (DICT.regex || []).map(([pat, rep]) => [new RegExp(pat, 'i'), rep]);
  const SKIP_TAGS = new Set(['PRE', 'CODE', 'SCRIPT', 'STYLE', 'TEXTAREA', 'SVG', 'PATH', 'NOSCRIPT', 'KBD']);

  const translateStr = (raw, isPlaceholder = false) => {{
    if (!raw || typeof raw !== 'string') return null;
    const trimmed = raw.trim();
    if (!trimmed || trimmed.length > 80) return null;
    if (/[\\u4e00-\\u9fff]/.test(trimmed)) return null;
    if (/^(https?:\\/\\/|file:\\/\\/|[A-Za-z]:\\\\|\\/)/.test(trimmed)) return null;

    if (isPlaceholder && Object.prototype.hasOwnProperty.call(PLACEHOLDERS, trimmed)) {{
      return PLACEHOLDERS[trimmed];
    }}
    if (Object.prototype.hasOwnProperty.call(EXACT, trimmed)) {{
      return raw.replace(trimmed, EXACT[trimmed]);
    }}
    for (const [re, rep] of REGEX_LIST) {{
      if (re.test(trimmed)) {{
        return raw.replace(trimmed, trimmed.replace(re, rep));
      }}
    }}
    return null;
  }};

  const isInsideProtectedArea = (node) => {{
    let el = node.nodeType === 1 ? node : node.parentElement;
    while (el) {{
      if (SKIP_TAGS.has(el.tagName)) return true;
      if (el.isContentEditable) return true;
      const role = el.getAttribute ? (el.getAttribute('role') || '') : '';
      if (role === 'listbox' || role === 'option' || role === 'combobox') return true;
      if (el.hasAttribute && (el.hasAttribute('data-radix-portal') || el.hasAttribute('data-radix-popper-content-wrapper'))) return true;
      const cls = typeof el.className === 'string' ? el.className : '';
      if (cls.includes('monaco-editor') || cls.includes('xterm') || cls.includes('markdown-body') || cls.includes('prose')) {{
        return true;
      }}
      el = el.parentElement;
    }}
    return false;
  }};

  const origTextMap = window.__AGY_I18N_ORIG_TEXT__ || new Map();
  window.__AGY_I18N_ORIG_TEXT__ = origTextMap;

  const translateElementAttrs = (el) => {{
    if (!el || el.nodeType !== 1 || SKIP_TAGS.has(el.tagName)) return 0;
    let count = 0;
    for (const attr of ['placeholder', 'title', 'aria-label']) {{
      const val = el.getAttribute(attr);
      if (!val) continue;
      const tr = translateStr(val, attr === 'placeholder');
      if (tr && tr !== val) {{
        const origAttr = 'data-agy-orig-' + attr;
        if (!el.hasAttribute(origAttr)) el.setAttribute(origAttr, val);
        el.setAttribute(attr, tr);
        count++;
      }}
    }}
    return count;
  }};

  const walkAndTranslate = (root) => {{
    if (!root) return 0;
    let count = 0;
    if (root.nodeType === 1) {{
      count += translateElementAttrs(root);
      root.querySelectorAll('input[placeholder], textarea[placeholder], [title], [aria-label]').forEach(el => {{
        count += translateElementAttrs(el);
      }});
    }}
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    let node;
    while ((node = walker.nextNode())) {{
      if (!node.nodeValue || !node.nodeValue.trim()) continue;
      if (isInsideProtectedArea(node)) continue;
      const tr = translateStr(node.nodeValue, false);
      if (tr && tr !== node.nodeValue) {{
        if (!origTextMap.has(node)) origTextMap.set(node, node.nodeValue);
        node.nodeValue = tr;
        count++;
      }}
    }}
    return count;
  }};

  if (window.__AGY_I18N_OBSERVER__) {{
    try {{ window.__AGY_I18N_OBSERVER__.disconnect(); }} catch (e) {{}}
  }}

  const initialCount = walkAndTranslate(document.body || document.documentElement);

  let timer = null;
  const pendingRoots = new Set();
  const observer = new MutationObserver((mutations) => {{
    for (const m of mutations) {{
      if (m.addedNodes) {{
        m.addedNodes.forEach(n => {{
          if (n && n.nodeType === 1 && !isInsideProtectedArea(n)) pendingRoots.add(n);
        }});
      }}
    }}
    if (pendingRoots.size === 0 || timer) return;
    timer = setTimeout(() => {{
      timer = null;
      if (document.querySelector('[role="listbox"], [role="menu"], [data-radix-popper-content-wrapper], [aria-expanded="true"]')) {{
        pendingRoots.clear();
        return;
      }}
      pendingRoots.forEach(r => {{
        if (r && r.isConnected) walkAndTranslate(r);
      }});
      pendingRoots.clear();
    }}, 400);
  }});
  if (document.body) {{
    observer.observe(document.body, {{ childList: true, subtree: true, characterData: false }});
  }}
  window.__AGY_I18N_OBSERVER__ = observer;
  window.__AGY_I18N_ACTIVE_SIG__ = DICT_SIG;
  document.documentElement.setAttribute('data-agy-i18n', 'zh-CN');
  return {{ ok: true, translated: initialCount }};
}})()"""


def build_i18n_reset_js() -> str:
    """断开汉化观察器并无痕恢复所有原英文 UI 文本。"""
    return """(() => {
  if (window.__AGY_I18N_OBSERVER__) {
    try { window.__AGY_I18N_OBSERVER__.disconnect(); } catch (e) {}
    window.__AGY_I18N_OBSERVER__ = null;
  }
  window.__AGY_I18N_ACTIVE_SIG__ = null;
  let restored = 0;
  if (window.__AGY_I18N_ORIG_TEXT__) {
    for (const [node, orig] of window.__AGY_I18N_ORIG_TEXT__.entries()) {
      try {
        if (node && node.parentNode) {
          node.nodeValue = orig;
          restored++;
        }
      } catch (e) {}
    }
    window.__AGY_I18N_ORIG_TEXT__.clear();
  }
  for (const attr of ['placeholder', 'title', 'aria-label']) {
    const origAttr = 'data-agy-orig-' + attr;
    document.querySelectorAll('[' + origAttr + ']').forEach(el => {
      el.setAttribute(attr, el.getAttribute(origAttr));
      el.removeAttribute(origAttr);
      restored++;
    });
  }
  document.documentElement.removeAttribute('data-agy-i18n');
  return { ok: true, restored };
})()"""


def build_theme_reset_js() -> str:
    """无痕移除主题样式表、底层壁纸、小猫贴纸与所有几何语义标注。"""
    tag_json = json.dumps(STYLE_TAG_ID)
    return f"""(() => {{
  if (window.__AGY_LAYOUT_OBSERVER__) {{
    try {{ window.__AGY_LAYOUT_OBSERVER__.disconnect(); }} catch (e) {{}}
    window.__AGY_LAYOUT_OBSERVER__ = null;
  }}
  if (window.__AGY_RESIZE_HANDLER__) {{
    window.removeEventListener('resize', window.__AGY_RESIZE_HANDLER__);
    window.__AGY_RESIZE_HANDLER__ = null;
  }}
  window.__AGY_THEME_SIG__ = null;
  const el = document.getElementById({tag_json});
  if (el) el.remove();
  const wp = document.getElementById('agy-wb-wallpaper-layer');
  if (wp) wp.remove();
  const cat = document.getElementById('agy-wb-cat-sticker');
  if (cat) cat.remove();
  document.querySelectorAll('[data-agy-role]').forEach(n => n.removeAttribute('data-agy-role'));
  document.documentElement.removeAttribute('data-agy-theme');
  return {{ ok: true, reset: true }};
}})()"""


def build_scan_untranslated_js() -> str:
    """仅扫描按钮、菜单、标签页和导航中的短英文 UI 词条，用于随客户端新版自动扩充词库。"""
    return """(() => {
  const found = new Set();
  const selectors = 'nav button, aside button, header button, [role="tab"], [role="menuitem"], [role="dialog"] label, [role="dialog"] button, [role="dialog"] h1, [role="dialog"] h2, [role="dialog"] h3';
  document.querySelectorAll(selectors).forEach(el => {
    const txt = (el.innerText || '').trim();
    if (!txt || txt.length < 2 || txt.length > 42) return;
    if (/[\\u4e00-\\u9fff]/.test(txt)) return;
    if (!/[A-Za-z]{2,}/.test(txt)) return;
    if (/[\\n\\r]/.test(txt)) return;
    if (/^(https?:|file:|[A-Za-z]:\\\\)/.test(txt)) return;
    found.add(txt);
  });
  return Array.from(found).sort();
})()"""


def _encode_asset_uri(rel_path: str) -> str:
    """将 assets 下的缩略图/预览图编码为 Data URI。"""
    if not rel_path:
        return ""
    p = ASSETS_DIR / rel_path
    if not p.exists():
        return ""
    mime, _ = mimetypes.guess_type(str(p))
    if p.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    elif not mime:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def build_inapp_picker_js(active_theme_id: str, enable_zh_cn: bool) -> str:
    """
    在 Antigravity 2.0 客户端内部右上角安全区注入 WorkBuddy 同款主题切换按钮与弹窗（Shadow DOM 隔离）：
    - 自动避开 Windows 系统控制按钮与原生顶栏区域（默认 top:52px; right:16px，支持鼠标按住自由拖拽）；
    - 点击弹出 WorkBuddy 截图同款「全部主题」大圆角选择面板，点击任意缩略图立即触发热切换并回传伴随守护持久化；
    - 仅在主窗口页面注入，绝不遮挡原生右上角任何菜单与下拉框。
    """
    items_payload = []
    for item in load_catalog():
        items_payload.append(
            {
                "id": item["id"],
                "name": item["name"],
                "badge": item.get("badge", "永久有效"),
                "stage_bg": item.get("stage_bg", "#c5d6ff"),
                "accent": item.get("accent", "#5b6cf9"),
                "desc": item.get("description", ""),
                "thumb": _encode_asset_uri(item.get("thumb", "")),
            }
        )
    data_json = json.dumps(items_payload, ensure_ascii=False)
    sig = hashlib.md5(f"{data_json}|{active_theme_id}|{enable_zh_cn}".encode("utf-8")).hexdigest()
    return f"""(() => {{
  const SIG = {json.dumps(sig)};
  const ACTIVE_ID = {json.dumps(active_theme_id)};
  const ZH_ON = {json.dumps(bool(enable_zh_cn))};
  const ITEMS = {data_json};
  const HOST_ID = 'agy-wb-theme-picker-host';

  // 只在较大尺寸的主页面注入，不在小 iframe/webview 里注入
  if (window.innerWidth < 500 || window.innerHeight < 350) return {{ ok: true, skipped: 'small' }};

  let host = document.getElementById(HOST_ID);
  if (host && host.dataset.sig === SIG) {{
    return {{ ok: true, skipped: 'same' }};
  }}
  if (!host) {{
    host = document.createElement('div');
    host.id = HOST_ID;
  }}
  // 关键修复：host 容器自身设为 0x0 尺寸，绝不以 inset:0 全屏覆盖窗口拦截任何点击
  host.style.cssText = 'position:fixed;top:0;left:0;width:0;height:0;overflow:visible;pointer-events:none;z-index:2147483000;';
  if (!host.parentElement) {{
    document.documentElement.appendChild(host);
  }}
  host.dataset.sig = SIG;
  const shadow = host.shadowRoot || host.attachShadow({{ mode: 'open' }});
  const savedPos = (() => {{
    try {{ return JSON.parse(localStorage.getItem('agy_wb_fab_pos') || 'null'); }} catch (e) {{ return null; }}
  }})();
  const initTop = savedPos && typeof savedPos.top === 'number' ? Math.max(46, Math.min(window.innerHeight - 44, savedPos.top)) : 52;
  const initRight = savedPos && typeof savedPos.right === 'number' ? Math.max(20, Math.min(window.innerWidth - 100, savedPos.right)) : 24;

  const activeItem = ITEMS.find(x => x.id === ACTIVE_ID) || ITEMS[ITEMS.length - 1] || {{}};
  shadow.innerHTML = `
    <style>
      * {{ box-sizing: border-box; font-family: "PingFang SC","HarmonyOS Sans SC","Microsoft YaHei UI",system-ui,sans-serif; }}
      .fab {{
        position: fixed;
        top: ${{initTop}}px;
        right: ${{initRight}}px;
        pointer-events: auto;
        -webkit-app-region: no-drag;
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 5px 11px;
        border-radius: 999px;
        background: rgba(255,255,255,0.88);
        color: #1c2233;
        border: 1px solid rgba(91,108,249,0.32);
        box-shadow: 0 6px 18px -6px rgba(28,34,51,0.22);
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        opacity: 0.78;
        transition: opacity 0.16s ease, transform 0.16s ease, box-shadow 0.16s ease;
        user-select: none;
      }}
      .fab:hover {{ opacity: 1; transform: translateY(-1px); box-shadow: 0 8px 22px -6px rgba(91,108,249,0.38); }}
      .mask {{
        position: fixed;
        inset: 0;
        background: rgba(15,23,42,0.32);
        display: none;
        align-items: center;
        justify-content: center;
        pointer-events: auto;
        -webkit-app-region: no-drag;
      }}
      .mask.open {{ display: flex; }}
      .modal {{
        width: min(820px, 92vw);
        max-height: 88vh;
        overflow-y: auto;
        background: #ffffff;
        border-radius: 20px;
        padding: 20px 24px 18px;
        box-shadow: 0 24px 64px rgba(15,23,42,0.28);
        color: #181c24;
      }}
      .head {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }}
      .head-title {{ font-size:16px; font-weight:700; }}
      .close-btn {{
        width:28px; height:28px; border-radius:8px; border:none; background:#f1f5f9;
        color:#475569; font-size:16px; cursor:pointer; line-height:1;
      }}
      .close-btn:hover {{ background:#e2e8f0; }}
      .stage {{
        position:relative;
        border-radius:16px;
        padding:18px 42px 0;
        height:200px;
        overflow:hidden;
        background:${{activeItem.stage_bg || '#c5d6ff'}};
        margin-bottom:16px;
      }}
      .stage-badge {{
        position:absolute; top:10px; right:12px; background:rgba(74,83,102,0.75);
        color:#fff; font-size:11px; font-weight:600; padding:3px 10px; border-radius:999px;
      }}
      .stage img {{
        width:100%; height:100%; object-fit:cover; border-radius:12px 12px 0 0;
        box-shadow:0 12px 28px rgba(24,28,36,0.16); display:block;
      }}
      .sec {{ font-size:14px; font-weight:700; margin:4px 0 12px; display:flex; justify-content:space-between; align-items:center; }}
      .sec small {{ font-size:12px; font-weight:400; color:#64748b; }}
      .grid {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; }}
      .tile {{ cursor:pointer; text-align:center; }}
      .tile-box {{
        border-radius:12px; overflow:hidden; border:2.5px solid #e5e8ef;
        aspect-ratio:16/10; background:#f3f4f6; transition:transform 0.14s ease, border-color 0.14s ease;
      }}
      .tile:hover .tile-box {{ transform:translateY(-2px); }}
      .tile.active .tile-box {{ border-color:#181c24; box-shadow:0 6px 14px rgba(24,28,36,0.14); }}
      .tile-box img {{ width:100%; height:100%; object-fit:cover; display:block; }}
      .tile-name {{ margin-top:6px; font-size:12px; color:#1e293b; font-weight:500; }}
      .tile.active .tile-name {{ font-weight:700; color:#000; }}
      .foot {{
        margin-top:16px; padding-top:12px; border-top:1px solid #e5e8ef;
        display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;
      }}
      .chk {{ display:inline-flex; align-items:center; gap:6px; font-size:13px; font-weight:600; cursor:pointer; }}
      .btn-reset {{
        padding:6px 14px; border-radius:8px; border:none; background:#fff1f2;
        color:#be123c; font-size:12px; font-weight:600; cursor:pointer;
      }}
      .btn-reset:hover {{ background:#ffe4e6; }}
    </style>
    <button class="fab" id="fab" title="点击切换 WorkBuddy 主题（按住可拖动位置）">🎨 主题</button>
    <div class="mask" id="mask">
      <div class="modal" id="modal">
        <div class="head">
          <span class="head-title">主题中心 · WorkBuddy 风格</span>
          <button class="close-btn" id="closeBtn">×</button>
        </div>
        <div class="stage" id="stage">
          <span class="stage-badge" id="stageBadge">${{activeItem.badge || '永久有效'}}</span>
          <img id="stageImg" src="${{activeItem.thumb || ''}}" alt="preview" />
        </div>
        <div class="sec">
          <span>全部主题</span>
          <small id="themeDesc">${{activeItem.desc || ''}}</small>
        </div>
        <div class="grid" id="grid"></div>
        <div class="foot">
          <label class="chk"><input type="checkbox" id="zhChk" ${{ZH_ON ? 'checked' : ''}} /> 启用全界面中文汉化</label>
          <button class="btn-reset" id="resetBtn">无痕还原默认界面</button>
        </div>
      </div>
    </div>
  `;

  const fab = shadow.getElementById('fab');
  const mask = shadow.getElementById('mask');
  const closeBtn = shadow.getElementById('closeBtn');
  const grid = shadow.getElementById('grid');
  const stage = shadow.getElementById('stage');
  const stageImg = shadow.getElementById('stageImg');
  const stageBadge = shadow.getElementById('stageBadge');
  const themeDesc = shadow.getElementById('themeDesc');
  const zhChk = shadow.getElementById('zhChk');
  const resetBtn = shadow.getElementById('resetBtn');

  let dragging = false, moved = false, startX = 0, startY = 0, startTop = initTop, startRight = initRight;
  fab.addEventListener('mousedown', (e) => {{
    if (e.button !== 0) return;
    dragging = true; moved = false;
    startX = e.clientX; startY = e.clientY;
    startTop = parseFloat(fab.style.top || initTop);
    startRight = parseFloat(fab.style.right || initRight);
  }});
  window.addEventListener('mousemove', (e) => {{
    if (!dragging) return;
    const dx = e.clientX - startX, dy = e.clientY - startY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) moved = true;
    const nt = Math.max(44, Math.min(window.innerHeight - 40, startTop + dy));
    const nr = Math.max(8, Math.min(window.innerWidth - 90, startRight - dx));
    fab.style.top = nt + 'px';
    fab.style.right = nr + 'px';
  }});
  window.addEventListener('mouseup', () => {{
    if (!dragging) return;
    dragging = false;
    if (moved) {{
      try {{ localStorage.setItem('agy_wb_fab_pos', JSON.stringify({{ top: parseFloat(fab.style.top), right: parseFloat(fab.style.right) }})); }} catch (e) {{}}
    }}
  }});

  fab.addEventListener('click', () => {{ if (!moved) mask.classList.add('open'); }});
  closeBtn.addEventListener('click', () => mask.classList.remove('open'));
  mask.addEventListener('click', (e) => {{ if (e.target === mask) mask.classList.remove('open'); }});

  ITEMS.forEach(item => {{
    const el = document.createElement('div');
    el.className = 'tile' + (item.id === ACTIVE_ID ? ' active' : '');
    el.innerHTML = `<div class="tile-box"><img src="${{item.thumb}}" alt="${{item.name}}"/></div><div class="tile-name">${{item.name}}</div>`;
    el.addEventListener('click', () => {{
      stage.style.background = item.stage_bg || '#c5d6ff';
      stageImg.src = item.thumb || '';
      stageBadge.textContent = item.badge || '永久有效';
      themeDesc.textContent = item.desc || '';
      shadow.querySelectorAll('.tile').forEach(t => t.classList.remove('active'));
      el.classList.add('active');
      window.__AGY_PENDING_CMD__ = {{ action: 'apply', theme_id: item.id, enable_zh_cn: !!zhChk.checked, ts: Date.now() }};
    }});
    grid.appendChild(el);
  }});

  zhChk.addEventListener('change', () => {{
    window.__AGY_PENDING_CMD__ = {{ action: 'apply', theme_id: ACTIVE_ID, enable_zh_cn: !!zhChk.checked, ts: Date.now() }};
  }});

  resetBtn.addEventListener('click', () => {{
    mask.classList.remove('open');
    window.__AGY_PENDING_CMD__ = {{ action: 'reset', ts: Date.now() }};
  }});

  return {{ ok: true, mounted: true }};
}})()"""


def build_inapp_picker_reset_js() -> str:
    """无痕移除客户端内注入的悬浮主题按钮与弹窗。"""
    return """(() => {
  const host = document.getElementById('agy-wb-theme-picker-host');
  if (host) host.remove();
  window.__AGY_PENDING_CMD__ = null;
  return { ok: true };
})()"""


def build_poll_pending_cmd_js() -> str:
    """读取并消费用户在客户端内弹窗中点击的切换/汉化/还原指令。"""
    return """(() => {
  const cmd = window.__AGY_PENDING_CMD__ || null;
  if (cmd) window.__AGY_PENDING_CMD__ = null;
  return cmd;
})()"""


def apply_theme(
    theme_id: str,
    port: Optional[int] = None,
    enable_zh_cn: Optional[bool] = None,
    save_active: bool = True,
) -> Tuple[int, int, str, bool]:
    """向所有 Antigravity 2.0 渲染页热注入主题、中文汉化与客户端内右上角主题面板。"""
    cfg = load_config()
    use_port = port or int(cfg.get("debug_port", 9222))
    use_zh = bool(cfg.get("enable_zh_cn", True)) if enable_zh_cn is None else bool(enable_zh_cn)
    meta, css_text, _ = get_theme_css(theme_id)
    targets = fetch_cdp_targets(use_port)
    if not targets:
        raise RuntimeError(f"端口 {use_port} 已连接，但未检测到正在渲染的 Antigravity 窗口。")

    theme_js = build_theme_inject_js(meta["id"], css_text, meta=meta)
    i18n_js = build_i18n_inject_js(load_i18n_dict()) if use_zh else build_i18n_reset_js()
    picker_js = build_inapp_picker_js(meta["id"], use_zh)

    success = 0
    for target in targets:
        try:
            r1 = cdp_eval(target["webSocketDebuggerUrl"], theme_js)
            cdp_eval(target["webSocketDebuggerUrl"], i18n_js)
            cdp_eval(target["webSocketDebuggerUrl"], picker_js)
            if "error" not in r1:
                success += 1
        except Exception:
            continue

    if save_active and success > 0:
        cfg["active_theme"] = meta["id"]
        cfg["enable_zh_cn"] = use_zh
        cfg["debug_port"] = use_port
        save_config(cfg)

    return success, len(targets), meta["name"], use_zh


def reset_all(port: Optional[int] = None) -> Tuple[int, int]:
    """从所有渲染页无痕清除自定义主题、中文汉化与内嵌主题按钮。"""
    cfg = load_config()
    use_port = port or int(cfg.get("debug_port", 9222))
    targets = fetch_cdp_targets(use_port)
    theme_reset_js = build_theme_reset_js()
    i18n_reset_js = build_i18n_reset_js()
    picker_reset_js = build_inapp_picker_reset_js()
    success = 0
    for target in targets:
        try:
            r1 = cdp_eval(target["webSocketDebuggerUrl"], theme_reset_js)
            cdp_eval(target["webSocketDebuggerUrl"], i18n_reset_js)
            cdp_eval(target["webSocketDebuggerUrl"], picker_reset_js)
            if "error" not in r1:
                success += 1
        except Exception:
            continue
    return success, len(targets)


def scan_untranslated_terms(port: Optional[int] = None) -> List[str]:
    """扫描新版客户端尚未汉化的短英文 UI 词条，保存到 discovered_new_ui_terms.json。"""
    cfg = load_config()
    use_port = port or int(cfg.get("debug_port", 9222))
    targets = fetch_cdp_targets(use_port)
    js = build_scan_untranslated_js()
    existing_exact = set(load_i18n_dict().get("exact", {}).keys())
    collected = set()
    for target in targets:
        try:
            res = cdp_eval(target["webSocketDebuggerUrl"], js)
            vals = res.get("result", {}).get("result", {}).get("value", [])
            if isinstance(vals, list):
                for item in vals:
                    if isinstance(item, str) and item not in existing_exact:
                        collected.add(item)
        except Exception:
            continue

    result = sorted(collected)
    I18N_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(result),
        "terms_template": {k: "" for k in result},
    }
    DISCOVERED_I18N_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _poll_window_states(port: int, expected_theme_id: str) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    轻量心跳检查（仅读取 1 个属性，绝不修改 DOM）：
    返回 (客户端内待执行指令 cmd, 是否存在未同步/新打开的窗口 needs_sync)。
    """
    try:
        targets = fetch_cdp_targets(port, timeout=1.0)
    except Exception:
        return None, False
    if not targets:
        return None, False

    probe_js = """(() => {
  const cmd = window.__AGY_PENDING_CMD__ || null;
  if (cmd) window.__AGY_PENDING_CMD__ = null;
  return {
    cmd,
    theme: document.documentElement.getAttribute('data-agy-theme') || '',
    hasStyle: !!document.getElementById('agy-custom-theme-studio')
  };
})()"""
    needs_sync = False
    for target in targets:
        try:
            res = cdp_eval(target["webSocketDebuggerUrl"], probe_js, timeout=1.5)
            val = res.get("result", {}).get("result", {}).get("value")
            if isinstance(val, dict):
                cmd = val.get("cmd")
                if isinstance(cmd, dict) and cmd.get("action"):
                    return cmd, True
                if val.get("theme") != expected_theme_id or not val.get("hasStyle"):
                    needs_sync = True
        except Exception:
            continue
    return None, needs_sync


def companion_daemon(port: Optional[int] = None, interval: float = 1.8) -> None:
    """
    v3.2.0 静默单实例伴随守护（零打扰心跳模式）：
    1. 平时仅通过 60 字节只读探针检查窗口状态，0 次 DOM 修改、0 次重排，绝不打断下拉框与列表点击；
    2. 仅当用户在客户端内切换主题、外部修改 config.json 或新窗口打开/重载时才执行一次注入；
    3. 持续零子进程检测 Antigravity.exe 版本升级。
    """
    if not _acquire_daemon_singleton():
        log_event("检测到已有伴随守护进程在运行，自动跳过重复启动。")
        return

    try:
        DAEMON_PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass

    log_event(f"伴随守护进程 v3.2.0 已静默启动 (PID={os.getpid()})。")
    last_version_check = 0.0
    last_cfg_tuple: Optional[Tuple[str, bool]] = None
    paused_by_reset = False
    try:
        while True:
            cfg = load_config()
            use_port = port or int(cfg.get("debug_port", 9222))
            theme_id = str(cfg.get("active_theme", "wb-partner"))
            use_zh = bool(cfg.get("enable_zh_cn", True))
            exe_path = str(cfg.get("antigravity_exe", ""))
            cur_cfg_tuple = (theme_id, use_zh)

            cmd, needs_sync = _poll_window_states(use_port, theme_id)
            if cmd:
                action = cmd.get("action")
                if action == "apply":
                    paused_by_reset = False
                    new_tid = str(cmd.get("theme_id") or theme_id)
                    new_zh = bool(cmd.get("enable_zh_cn", use_zh))
                    try:
                        apply_theme(new_tid, port=use_port, enable_zh_cn=new_zh, save_active=True)
                        last_cfg_tuple = (new_tid, new_zh)
                        log_event(f"客户端内切换主题成功：{new_tid}（中文汉化={'开' if new_zh else '关'}）")
                    except Exception:
                        pass
                elif action == "reset":
                    paused_by_reset = True
                    try:
                        reset_all(port=use_port)
                        log_event("客户端内已执行无痕还原默认界面，暂停自动注入。")
                    except Exception:
                        pass
            else:
                # 仅当外部配置变更或检测到未注入的新窗口时才执行一次 apply_theme
                cfg_changed = last_cfg_tuple is not None and last_cfg_tuple != cur_cfg_tuple
                if cfg_changed:
                    paused_by_reset = False
                if not paused_by_reset and (needs_sync or cfg_changed):
                    try:
                        apply_theme(theme_id, port=use_port, enable_zh_cn=use_zh, save_active=False)
                        last_cfg_tuple = cur_cfg_tuple
                    except Exception:
                        pass

            now = time.time()
            if now - last_version_check >= 25.0:
                last_version_check = now
                updated, info = check_client_updated(exe_path)
                if updated and not paused_by_reset:
                    try:
                        apply_theme(theme_id, port=use_port, enable_zh_cn=use_zh, save_active=False)
                        new_terms = scan_untranslated_terms(port=use_port)
                        log_event(f"新版 {info.get('version')} 自动扫描完成，发现 {len(new_terms)} 条待补充 UI 新词。")
                    except Exception:
                        pass

            time.sleep(max(1.2, interval))
    except KeyboardInterrupt:
        log_event("伴随守护进程已手动停止。")
    finally:
        try:
            if DAEMON_PID_PATH.exists() and DAEMON_PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
                DAEMON_PID_PATH.unlink()
        except OSError:
            pass


def launch_antigravity_with_companion(
    theme_id: Optional[str] = None,
    port: Optional[int] = None,
    enable_zh_cn: Optional[bool] = None,
    start_daemon: bool = True,
) -> None:
    """无黑框启动 Antigravity 2.0 并自动拉起唯一一个静默伴随守护。"""
    cfg = load_config()
    use_port = port or int(cfg.get("debug_port", 9222))
    use_theme = theme_id or str(cfg.get("active_theme", "wb-partner"))
    use_zh = bool(cfg.get("enable_zh_cn", True)) if enable_zh_cn is None else bool(enable_zh_cn)
    exe_path = Path(str(cfg.get("antigravity_exe", "")))

    if not exe_path.exists():
        raise FileNotFoundError(
            f"未找到 Antigravity 可执行文件: {exe_path}\n请在 {CONFIG_PATH} 中修改 antigravity_exe 路径。"
        )

    check_client_updated(str(exe_path))

    subprocess.Popen(
        [str(exe_path), f"--remote-debugging-port={use_port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=DETACHED_PROCESS,
    )

    for _ in range(36):
        time.sleep(0.5)
        try:
            ok, total, name, zh = apply_theme(
                use_theme, port=use_port, enable_zh_cn=use_zh, save_active=True
            )
            if ok > 0:
                log_event(f"启动完成，已套用主题「{name}」({use_theme})，中文汉化={'开' if zh else '关'} [{ok}/{total}]")
                break
        except Exception:
            continue

    if start_daemon and cfg.get("auto_follow_client_updates", True):
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        py_bin = str(pythonw if pythonw.exists() else sys.executable)
        subprocess.Popen(
            [py_bin, str(Path(__file__).resolve()), "daemon", "--port", str(use_port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
        )


def create_desktop_shortcut() -> Path:
    """在桌面创建零黑框直连 pythonw.exe 的专属启动快捷方式。"""
    if os.name != "nt":
        raise RuntimeError("桌面快捷方式生成仅支持 Windows 系统。")
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    shortcut_path = desktop / "Antigravity (WorkBuddy主题+汉化).lnk"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    py_bin = str(pythonw if pythonw.exists() else sys.executable)
    engine_script = str(Path(__file__).resolve())
    cfg = load_config()
    exe_icon = str(cfg.get("antigravity_exe", ""))

    ps_script = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut('{str(shortcut_path)}')
$sc.TargetPath = '{py_bin}'
$sc.Arguments = '"{engine_script}" launch'
$sc.WorkingDirectory = '{str(BASE_DIR)}'
$sc.Description = '零黑框启动 Antigravity 2.0 (WorkBuddy 主题 + 中文汉化 + 自动伴随守护)'
if (Test-Path '{exe_icon}') {{ $sc.IconLocation = '{exe_icon},0' }}
$sc.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        check=True,
        creationflags=CREATE_NO_WINDOW,
    )
    return shortcut_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Antigravity 2.0 主题工坊与中文汉化伴随引擎 v2.1")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出全部可用主题")

    p_apply = sub.add_parser("apply", help="立即热应用指定主题与汉化状态")
    p_apply.add_argument("theme_id", help="主题 ID")
    p_apply.add_argument("--port", type=int, default=None, help="CDP 调试端口")
    p_apply.add_argument("--no-zh", action="store_true", help="仅应用主题，不启用中文汉化")
    p_apply.add_argument("--zh", action="store_true", help="强制同时启用中文汉化")

    p_reset = sub.add_parser("reset", help="无痕还原默认主题与原英文界面")
    p_reset.add_argument("--port", type=int, default=None, help="CDP 调试端口")

    p_daemon = sub.add_parser("daemon", help="开启零弹窗单实例伴随守护")
    p_daemon.add_argument("--port", type=int, default=None, help="CDP 调试端口")
    p_daemon.add_argument("--interval", type=float, default=2.0, help="同步间隔（秒）")

    p_scan = sub.add_parser("scan-i18n", help="扫描新版客户端尚未汉化的英文 UI 词条")
    p_scan.add_argument("--port", type=int, default=None, help="CDP 调试端口")

    p_launch = sub.add_parser("launch", help="无黑框带主题与汉化伴随模式启动 Antigravity 2.0")
    p_launch.add_argument("--theme", default=None, help="启动后自动应用的主题 ID")
    p_launch.add_argument("--port", type=int, default=None, help="CDP 调试端口")
    p_launch.add_argument("--no-daemon", action="store_true", help="启动后不常驻后台守护")

    sub.add_parser("install-shortcut", help="在桌面创建零黑框专属启动图标")

    args = parser.parse_args()

    try:
        if args.command == "list":
            cfg = load_config()
            active = cfg.get("active_theme", "")
            zh_state = "已开启" if cfg.get("enable_zh_cn", True) else "已关闭"
            print(f"可用 WorkBuddy 风格 Antigravity 2.0 主题列表（中文汉化：{zh_state}）：")
            for item in load_catalog():
                mark = " ★(当前默认)" if item["id"] == active else ""
                mode_zh = "深色" if item["mode"] == "dark" else "浅色"
                print(f"  - {item['id']:<14} | {item['name']} ({mode_zh}){mark}")
                print(f"    {item['description']}")
            print("\n快捷切换用法：")
            print("  switch.bat wb-partner     切换为「伙伴」主图主题 + 探头小猫 + 中文汉化")
            print("  switch.bat wb-breeze      切换为「有风」清风森林水彩主图")
            print("  switch.bat wb-penguin     切换为「经典萌企」红围巾小企鹅主图")
            print("  switch.bat wb-companion   切换为「同行」冰青水波主图")
            print("  switch.bat wb-ripple      切换为「涟漪」静谧湖面睡猫主图")
            print("  switch.bat wb-light       切换为「浅色」WorkBuddy 极简浅色")
            print("  switch.bat wb-dark        切换为「深色」WorkBuddy 暗夜深色")
            print("  switch.bat reset          一键无痕还原默认样式与原英文")
            return 0

        if args.command == "apply":
            zh_flag: Optional[bool] = None
            if args.no_zh:
                zh_flag = False
            elif args.zh:
                zh_flag = True
            ok, total, name, zh = apply_theme(args.theme_id, port=args.port, enable_zh_cn=zh_flag)
            zh_str = " + 中文汉化已生效" if zh else "（已保持原英文）"
            print(f"[成功] 已将主题「{name}」{zh_str}，同步至 {ok}/{total} 个客户端窗口！")
            return 0

        if args.command == "reset":
            ok, total = reset_all(port=args.port)
            print(f"[成功] 已从 {ok}/{total} 个窗口无痕移除主题样式与中文汉化，恢复原生界面。")
            return 0

        if args.command == "daemon":
            companion_daemon(port=args.port, interval=args.interval)
            return 0

        if args.command == "scan-i18n":
            terms = scan_untranslated_terms(port=args.port)
            print(f"[扫描完成] 发现 {len(terms)} 条待补充的新版英文 UI 词条，已输出至：{DISCOVERED_I18N_PATH}")
            return 0

        if args.command == "launch":
            launch_antigravity_with_companion(
                theme_id=args.theme, port=args.port, start_daemon=not args.no_daemon
            )
            return 0

        if args.command == "install-shortcut":
            sc = create_desktop_shortcut()
            print(f"[成功] 已在桌面创建零黑框专属启动快捷方式：{sc}")
            return 0

    except Exception as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
