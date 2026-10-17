"""路径、端口与外部程序探测。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PKG_DIR.parent
DATA_DIR = Path(os.environ.get("WXC_DATA") or (PROJECT_DIR / ".data")).resolve()
DB_PATH = DATA_DIR / "wxc.sqlite3"
STATIC_DIR = PROJECT_DIR / "static"
# 界面背景插画（用户提供的素材，见 DESIGN.md 的替换点）。可用 WXC_ART 指向别的等比例图像。
ART_FILE = Path(os.environ.get("WXC_ART") or (PROJECT_DIR / "背景.jpg"))

DEFAULT_CAPTURE_PORT = 8899
DEFAULT_UI_PORT = 8900
DEFAULT_CONCURRENCY = 2

# mitmproxy 单条响应体超过该值时直接透传，不在内存里缓存（避免下载大视频吃内存）
STREAM_LARGE_BODIES = "512k"
# 只有小于该值的响应体才会被读出来做 JSON/HTML 解析
PARSE_BODY_LIMIT = 512 * 1024


def data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def default_download_dir() -> Path:
    d = data_dir() / "downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ffmpeg_path() -> str:
    return os.environ.get("WXC_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_path() -> str:
    return os.environ.get("WXC_FFPROBE") or shutil.which("ffprobe") or "ffprobe"


def mitmdump_argv() -> list[str]:
    """返回可直接 subprocess 调用的 mitmdump 命令。"""
    exe = Path(sys.executable).parent / ("mitmdump.exe" if os.name == "nt" else "mitmdump")
    if exe.exists():
        return [str(exe)]
    found = shutil.which("mitmdump")
    if found:
        return [found]
    return [sys.executable, "-c", "from mitmproxy.tools.main import mitmdump; mitmdump()"]


def capture_script() -> str:
    return str(PKG_DIR / "capture.py")


def mitm_confdir() -> Path:
    return Path(os.environ.get("MITM_CONFDIR") or (Path.home() / ".mitmproxy"))


def mitm_ca_cer() -> Path:
    return mitm_confdir() / "mitmproxy-ca-cert.cer"


_SSL_CONTEXT = None


def ssl_context():
    """用系统证书存储校验。

    httpx 默认用 certifi 的证书包，遇到证书链不完整的国内 CDN 会报
    "unable to get local issuer certificate"；Windows 系统存储里通常已有中间证书。
    """
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        import ssl

        ctx = ssl.create_default_context()
        ctx.load_default_certs()
        _SSL_CONTEXT = ctx
    return _SSL_CONTEXT
