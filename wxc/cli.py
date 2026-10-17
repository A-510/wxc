"""命令行入口：capture / ui / start / dl / doctor / cert / proxy。"""
from __future__ import annotations

import argparse
import atexit
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import proxy, store
from .config import (DEFAULT_CAPTURE_PORT, DEFAULT_CONCURRENCY, DEFAULT_UI_PORT,
                     STREAM_LARGE_BODIES, capture_script, default_download_dir, ffmpeg_path,
                     mitm_ca_cer, mitmdump_argv)

_CREATE_NEW_PROCESS_GROUP = 0x00000200 if sys.platform == "win32" else 0


def _cfg(con, key: str, default):
    return type(default)(store.get_setting(con, key, str(default)))


def capture_argv(port: int, mode: str = "regular") -> list[str]:
    return mitmdump_argv() + [
        "-s", capture_script(),
        "--listen-host", "127.0.0.1",
        "--listen-port", str(port),
        "--mode", mode,
        "--set", f"stream_large_bodies={STREAM_LARGE_BODIES}",
        "--set", "connection_strategy=lazy",
        "--set", "termlog_verbosity=info",
    ]


def _spawn_capture(port: int, mode: str = "regular") -> subprocess.Popen:
    proc = subprocess.Popen(capture_argv(port, mode), creationflags=_CREATE_NEW_PROCESS_GROUP)

    @atexit.register
    def _stop() -> None:
        if proc.poll() is None:
            proc.terminate()
    return proc


def _print_steps(ui_port: int, capture_port: int) -> None:
    print()
    print(f"  界面：   http://127.0.0.1:{ui_port}")
    print(f"  抓包：   127.0.0.1:{capture_port}（mitmproxy）")
    print("  流程：   ① 装证书  ② 开系统代理  ③ 微信里打开小程序播放网课  ④ 回界面点下载")
    print()


# --------------------------------------------------------------------------- 子命令

def cmd_capture(args) -> int:
    con = store.connect()
    store.pending_states(con)
    port = args.port or _cfg(con, "capture_port", DEFAULT_CAPTURE_PORT)
    con.close()
    print(f"[wxc] 抓包启动：127.0.0.1:{port}（Ctrl+C 停止）")
    proc = _spawn_capture(port, args.mode)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return 0


def _proxy_points_at_us(port: int) -> bool:
    try:
        px = proxy.get_proxy()
    except Exception:
        return False
    return bool(px.get("enabled")) and px.get("server") == f"127.0.0.1:{port}"


def restore_proxy_if_ours(port: int) -> bool:
    """退出时把「指向本机抓包端口」的系统代理关掉，并还原用户原来的代理设置。"""
    if not _proxy_points_at_us(port):
        return False
    con = store.connect()
    try:
        proxy.disable_capture_proxy(con)
    finally:
        con.close()
    print("[wxc] 已自动关闭系统代理并还原你原来的代理设置")
    return True


def cmd_ui(args) -> int:
    import uvicorn

    from .webui import create_app

    con = store.connect()
    store.pending_states(con)
    port = args.port or _cfg(con, "ui_port", DEFAULT_UI_PORT)
    cap_port = _cfg(con, "capture_port", DEFAULT_CAPTURE_PORT)
    con.close()

    if _proxy_points_at_us(cap_port):
        print("[wxc] 提示：系统代理正指向本机抓包端口（上次没关？），退出时会自动还原")

    proc = None
    if not args.no_capture:
        proc = _spawn_capture(cap_port, args.mode)
    try:
        if not args.no_browser:
            import threading
            import webbrowser
            threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
        _print_steps(port, cap_port)
        uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
        restore_proxy_if_ours(cap_port)


def cmd_start(args) -> int:
    return cmd_ui(args)


def cmd_dl(args) -> int:
    import httpx

    from . import detect
    from .downloader import Manager

    url = args.url.strip()
    kind = detect.classify(url)
    if not kind:
        print("[wxc] 无法从地址判断媒体类型", file=sys.stderr)
        return 2
    con = store.connect()
    headers = store.get_host_headers(con, httpx.URL(url).host)
    iid, _ = store.upsert_media(con, url=url, kind=kind, title=args.title or "", headers=headers)
    out_dir = Path(args.out) if args.out else Path(store.get_setting(con, "out_dir", str(default_download_dir())))
    con.close()
    mgr = Manager(out_dir, args.concurrency)
    mgr.submit([iid])
    con = store.connect()
    while True:
        item = store.get_item(con, iid)
        state = item["dl_state"]
        line = f"\r[{state}] {item['dl_bytes'] or 0} bytes {item['dl_error'] or ''}"
        print(line.ljust(90)[:90], end="", flush=True)
        if state in ("done", "error", "canceled"):
            print()
            if state == "done":
                print(f"[wxc] 已保存：{item['dl_path']}")
                return 0
            print(f"[wxc] 失败：{item['dl_error']}", file=sys.stderr)
            return 1
        time.sleep(0.5)


def cmd_doctor(args) -> int:
    con = store.connect()
    out_dir = store.get_setting(con, "out_dir", str(default_download_dir()))
    cap_port = _cfg(con, "capture_port", DEFAULT_CAPTURE_PORT)
    con.close()
    from .webui import port_open
    cert = proxy.cert_status()
    busy = port_open(cap_port)
    try:
        px = proxy.get_proxy()
    except Exception:
        px = {"enabled": False, "server": ""}
    px_state = ("开启 → " + px["server"]) if px["enabled"] else "关闭"
    checks = [
        ("ffmpeg", bool(shutil.which(ffmpeg_path())), ffmpeg_path()),
        ("mitmproxy CA 已生成", cert["exists"], cert["path"]),
        ("CA 已装进系统根证书", cert["installed"], "wxc cert --install"),
        ("抓包端口可用", not busy,
         f"127.0.0.1:{cap_port} " + ("已被占用（可能已有抓包在跑）" if busy else "空闲")),
        ("系统代理", True, px_state),
        ("下载目录", Path(out_dir).exists(), out_dir),
    ]
    ok = True
    for name, good, detail in checks:
        mark = "OK " if good else "!! "
        if not good:
            ok = False
        print(f"  [{mark}] {name:<22} {detail}")
    print("\n  提示：CA 未装 → 执行 `wxc cert --install`；抓包在跑或要开始抓包 → `wxc start`。")
    return 0 if ok else 1


def cmd_cert(args) -> int:
    if args.install:
        print(proxy.cert_install())
    st = proxy.cert_status()
    print(f"  证书文件：{st['path']}（{'存在' if st['exists'] else '未生成'}）")
    print(f"  系统信任：{'已安装' if st['installed'] else '未安装'}")
    if not st["exists"]:
        print("  先运行一次 `wxc capture` 生成证书，再执行 `wxc cert --install`")
        return 1
    return 0


def cmd_proxy(args) -> int:
    con = store.connect()
    try:
        port = _cfg(con, "capture_port", DEFAULT_CAPTURE_PORT)
        if args.action == "status":
            print(proxy.get_proxy())
            return 0
        out = (proxy.enable_capture_proxy(con, port) if args.action == "on"
               else proxy.disable_capture_proxy(con))
    finally:
        con.close()
    print(out)
    return 0


def main(argv: list[str] | None = None) -> int:
    from . import __version__

    p = argparse.ArgumentParser(prog="wxc", description="微信小程序网课 → 本地下载器")
    p.add_argument("-V", "--version", action="version", version=f"wxc {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--port", type=int, default=None, help="端口（默认取库里的设置）")
        sp.add_argument("--mode", default="regular", choices=["regular", "local"],
                        help="local = WinDivert 透明拦截，需管理员权限")

    sp = sub.add_parser("capture", help="只启动抓包代理")
    add_common(sp)
    sp.set_defaults(func=cmd_capture)

    sp = sub.add_parser("ui", help="只启动网页界面")
    add_common(sp)
    sp.add_argument("--no-capture", action="store_true")
    sp.add_argument("--no-browser", action="store_true")
    sp.set_defaults(func=cmd_ui)

    sp = sub.add_parser("start", help="抓包 + 界面一起起（推荐）")
    add_common(sp)
    sp.add_argument("--no-capture", action="store_true")
    sp.add_argument("--no-browser", action="store_true")
    sp.set_defaults(func=cmd_start)

    sp = sub.add_parser("dl", help="直接下载一个地址")
    sp.add_argument("url")
    sp.add_argument("-t", "--title", default="")
    sp.add_argument("-o", "--out", default="")
    sp.add_argument("-c", "--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    sp.set_defaults(func=cmd_dl)

    sp = sub.add_parser("doctor", help="环境自检")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("cert", help="查看/安装 mitmproxy 根证书")
    sp.add_argument("--install", action="store_true")
    sp.set_defaults(func=cmd_cert)

    sp = sub.add_parser("proxy", help="开关 Windows 系统代理")
    sp.add_argument("action", choices=["on", "off", "status"])
    sp.set_defaults(func=cmd_proxy)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
