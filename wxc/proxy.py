"""Windows 系统代理开关（HKCU，不需要管理员）与 mitmproxy CA 证书安装。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import mitm_ca_cer

INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
DEFAULT_OVERRIDE = "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;192.168.*;<local>"
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _winreg():
    if sys.platform != "win32":
        raise RuntimeError("系统代理开关只支持 Windows")
    import winreg
    return winreg


def get_proxy() -> dict:
    winreg = _winreg()
    out = {"enabled": False, "server": "", "override": ""}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS) as k:
        for name, key in (("ProxyEnable", "enabled"), ("ProxyServer", "server"),
                          ("ProxyOverride", "override")):
            try:
                val, _ = winreg.QueryValueEx(k, name)
                out[key] = bool(val) if key == "enabled" else str(val)
            except FileNotFoundError:
                pass
    return out


def _notify() -> None:
    import ctypes
    wininet = ctypes.windll.Wininet
    wininet.InternetSetOptionW(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
    wininet.InternetSetOptionW(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH


def set_proxy(enable: bool, server: str = "127.0.0.1:8899",
              override: str = DEFAULT_OVERRIDE) -> dict:
    winreg = _winreg()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enable else 0)
        if enable:
            winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
            winreg.SetValueEx(k, "ProxyOverride", 0, winreg.REG_SZ, override)
    _notify()
    return get_proxy()


def _write_raw(server: str, override: str) -> None:
    winreg = _winreg()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as k:
        if server:
            winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
        if override:
            winreg.SetValueEx(k, "ProxyOverride", 0, winreg.REG_SZ, override)
    _notify()


def enable_capture_proxy(con, port: int) -> dict:
    """开启抓包代理。先记住用户原本的代理配置，关闭时原样还回去。"""
    from . import store

    prev = get_proxy()
    ours = f"127.0.0.1:{port}"
    if prev["server"] and prev["server"] != ours:
        store.set_setting(con, "prev_proxy_server", prev["server"])
        store.set_setting(con, "prev_proxy_override", prev["override"])
    return set_proxy(True, server=ours, override=DEFAULT_OVERRIDE)


def disable_capture_proxy(con) -> dict:
    """关掉抓包代理，并把用户原来的 ProxyServer/ProxyOverride 还原。"""
    from . import store

    out = set_proxy(False)
    prev_server = store.get_setting(con, "prev_proxy_server", "")
    prev_override = store.get_setting(con, "prev_proxy_override", "")
    if prev_server:
        _write_raw(prev_server, prev_override)
        store.set_setting(con, "prev_proxy_server", "")
        store.set_setting(con, "prev_proxy_override", "")
    return get_proxy()


# --------------------------------------------------------------------------- 证书

def cert_status() -> dict:
    cer = mitm_ca_cer()
    installed = False
    if sys.platform == "win32":
        try:
            # certutil 输出是 GBK 中文，text=True 在 UTF-8 环境下会解码失败（读到空 stdout），
            # 所以按字节判断，不碰编码。
            r = subprocess.run(["certutil", "-user", "-store", "Root"],
                               capture_output=True, creationflags=_CREATE_NO_WINDOW)
            installed = b"mitmproxy" in (r.stdout or b"")
        except FileNotFoundError:
            installed = False
    return {"path": str(cer), "exists": cer.exists(), "installed": installed}


def cert_install() -> str:
    """把 mitmproxy 根证书装进「当前用户 → 受信任的根证书颁发机构」。"""
    if sys.platform != "win32":
        raise RuntimeError("仅支持 Windows")
    cer: Path = mitm_ca_cer()
    if not cer.exists():
        raise RuntimeError("证书尚未生成：先运行一次 `wxc capture`（启动即生成）")
    r = subprocess.run(["certutil", "-user", "-addstore", "Root", str(cer)],
                       capture_output=True, creationflags=_CREATE_NO_WINDOW)
    if r.returncode != 0:
        msg = (r.stdout or b"").decode("gbk", "replace") + (r.stderr or b"").decode("gbk", "replace")
        raise RuntimeError(msg.strip()[-500:])
    return "已安装到当前用户受信任根证书"
