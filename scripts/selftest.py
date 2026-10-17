"""离线端到端自检：不需要微信，也不联网。

造一个带 AES-128 加密的 HLS 和一个普通 mp4，起本地 HTTP 服务，
让请求走 mitmproxy（模拟小程序播放）→ 检查抓包入库与标题提取 → 下载合并 → ffprobe 校验。

用法： .venv/Scripts/python.exe scripts/selftest.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="wxc-selftest-"))
os.environ["WXC_DATA"] = str(TMP / "data")  # 必须在 import wxc 之前设置

from wxc import detect, store                      # noqa: E402
from wxc.config import PARSE_BODY_LIMIT, ffmpeg_path, ffprobe_path  # noqa: E402
from wxc.downloader import Manager, Unsupported, download_direct, download_item  # noqa: E402

SRC = TMP / "src"
OUT = TMP / "out"
COURSE_TITLE = "第1章 绪论"
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def free_port(port: int) -> int:
    while True:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1


# 分片故意放在另一台「主机」（不同端口）上：清单里的分片地址是跨主机的绝对地址，
# 只按「同目录」判断分片会漏，这里就是那个回归用例。
MEDIA_PORT = free_port(18123)
SEG_PORT = free_port(18124)
PROXY_PORT = free_port(18899)

# 假装是平台的流 ID：清单和分片路径里都带它，但分片在另一台主机、另一个目录里
STREAM = "dtest1773822105VXnP"
PL_DIR = SRC / "player" / STREAM      # 清单目录
SEG_DIR = SRC / "media" / STREAM      # 分片目录（走 SEG_PORT 那台「主机」）
OTHER_DIR = SRC / "other" / STREAM    # 从没在清单里出现过的目录：只有流 ID 能认出来


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


# --------------------------------------------------------------------------- 1. 造素材

def build_media() -> None:
    SRC.mkdir(parents=True, exist_ok=True)
    for d in (PL_DIR, SEG_DIR, OTHER_DIR):
        d.mkdir(parents=True, exist_ok=True)
    mp4 = SRC / "test.mp4"
    r = run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=6",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(mp4)])
    if r.returncode != 0:
        raise SystemExit("生成测试 mp4 失败：\n" + r.stderr)

    key = os.urandom(16)
    (SRC / "enc.key").write_bytes(key)
    keyinfo = SRC / "keyinfo.txt"
    keyinfo.write_text(
        f"http://127.0.0.1:{MEDIA_PORT}/enc.key\n{SRC / 'enc.key'}\n" + "0" * 31 + "1\n",
        encoding="utf-8",
    )
    r = run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp4),
             "-c", "copy", "-hls_time", "2", "-hls_playlist_type", "vod",
             "-hls_key_info_file", str(keyinfo),
             "-hls_segment_filename", str(SEG_DIR / "seg%03d.ts"), str(PL_DIR / "video.m3u8")])
    if r.returncode != 0:
        raise SystemExit("生成测试 HLS 失败：\n" + r.stderr)

    # 分片地址改成「另一台主机」的绝对地址（真实平台就是这样：清单在一台，分片在 CDN 另一台）
    pl = PL_DIR / "video.m3u8"
    lines = [f"http://127.0.0.1:{SEG_PORT}/media/{STREAM}/{l}" if (l and not l.startswith("#")) else l
             for l in pl.read_text(encoding="utf-8").splitlines()]
    pl.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 目录从未在清单里出现过：只能靠流 ID 认出它是分片
    shutil.copy(SEG_DIR / "seg000.ts", OTHER_DIR / "x1.ts")
    shutil.copy(SEG_DIR / "seg000.ts", OTHER_DIR / "x2.ts")


# --------------------------------------------------------------------------- 2. 本地服务

COURSE_JSON = {
    "code": 0,
    "data": {
        "courseName": "测试课程",
        "chapters": [
            {"name": COURSE_TITLE,
             "videoUrl": f"http://127.0.0.1:{MEDIA_PORT}/player/{STREAM}/video.m3u8",
             "playUrl": f"http://127.0.0.1:{MEDIA_PORT}/test.mp4"},
        ],
    },
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(SRC), **kw)

    def log_message(self, *a):  # 静音
        pass

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/course"):
            body = json.dumps(COURSE_JSON, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def start_media_server(port: int) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# --------------------------------------------------------------------------- 3. 抓包

def start_capture() -> subprocess.Popen:
    from wxc.cli import capture_argv
    proc = subprocess.Popen(capture_argv(PROXY_PORT), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace",
                            encoding="utf-8")
    threading.Thread(target=lambda: [None for _ in proc.stdout], daemon=True).start()
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", PROXY_PORT), timeout=0.3):
                return proc
        except OSError:
            if proc.poll() is not None:
                raise SystemExit(f"mitmdump 启动失败，输出：\n{proc.stdout.read() if proc.stdout else ''}")
            time.sleep(0.5)
    raise SystemExit("mitmdump 端口未就绪")


def play_through_proxy() -> None:
    import httpx

    ca = Path(os.environ.get("MITM_CONFDIR", Path.home() / ".mitmproxy")) / "mitmproxy-ca-cert.pem"
    headers = {"User-Agent": "MicroMessenger/3.9.12 MiniProgramEnv/Windows",
               "Referer": f"http://127.0.0.1:{MEDIA_PORT}/"}
    with httpx.Client(proxy=f"http://127.0.0.1:{PROXY_PORT}", verify=str(ca),
                      trust_env=False, timeout=30, headers=headers) as c:
        c.get(f"http://127.0.0.1:{MEDIA_PORT}/api/course").raise_for_status()
        r = c.get(f"http://127.0.0.1:{MEDIA_PORT}/player/{STREAM}/video.m3u8")
        r.raise_for_status()
        # 模拟播放器拉分片与密钥（分片地址是跨主机的绝对地址）
        for seg in detect.playlist_urls(r.text, base=str(r.url)):
            c.get(seg).raise_for_status()
        c.get(f"http://127.0.0.1:{MEDIA_PORT}/enc.key")
        c.get(f"http://127.0.0.1:{MEDIA_PORT}/test.mp4", headers={"Range": "bytes=0-1023"})
        # 第二阶段：播放器没重新拉清单（接着上次播放），分片出现在一个从未见过的目录里
        c.get(f"http://127.0.0.1:{SEG_PORT}/other/{STREAM}/x1.ts").raise_for_status()


# --------------------------------------------------------------------------- 4. 校验

def db_items() -> dict[str, dict]:
    con = store.connect()
    try:
        return {r["kind"] + "|" + r["url"]: dict(r) for r in store.list_items(con)}
    finally:
        con.close()


def wait_state(con, iid: int, timeout: float = 180) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        row = store.get_item(con, iid)
        if row and row["dl_state"] in ("done", "error", "canceled"):
            return dict(row)
        time.sleep(0.5)
    return dict(store.get_item(con, iid))


def main() -> int:
    build_media()
    srv = start_media_server(MEDIA_PORT)
    segsrv = start_media_server(SEG_PORT)  # 分片所在的「另一台主机」
    cap = start_capture()
    try:
        time.sleep(1)
        print("\n== 抓包层 ==")
        play_through_proxy()
        time.sleep(1.5)
        rows = db_items()
        m3u8 = next((r for r in rows.values() if r["kind"] == "hls"), None)
        mp4 = next((r for r in rows.values() if r["kind"] == "mp4"), None)
        check("抓到 m3u8", m3u8 is not None, m3u8["url"] if m3u8 else "")
        check("抓到 mp4", mp4 is not None, mp4["url"] if mp4 else "")
        check("标题从接口 JSON 提取", bool(m3u8) and m3u8["title"] == COURSE_TITLE,
              (m3u8 or {}).get("title", ""))
        con = store.connect()
        ts_rows = con.execute("SELECT COUNT(*) c FROM media WHERE kind = 'ts'").fetchone()["c"]
        prefixes = store.load_seg_prefixes(con)
        tokens = store.load_stream_tokens(con)
        seg = con.execute("SELECT SUM(count) c FROM segments").fetchone()["c"] or 0
        con.close()
        check("跨主机 .ts 分片不入列表", ts_rows == 0, f"条目数={len(rows)} ts={ts_rows}")
        check("清单里的分片目录已记下", len(prefixes) > 0, str(sorted(prefixes)))
        check("流 ID 已记下", STREAM.lower() in tokens, str(sorted(tokens)))
        check("没重新拉清单时的分片也能认出（靠流 ID）",
              store.url_dir(f"http://x/other/{STREAM}/x1.ts") not in prefixes)
        check("分片计数 > 0", seg > 0, f"{seg} 个")
        check("请求头被记下（含 Referer）",
              bool(m3u8) and "Referer" in json.loads(m3u8["headers"] or "{}"))

        print("\n== 下载层 ==")
        mgr = Manager(OUT, 2)
        ids = [r["id"] for r in (m3u8, mp4) if r]
        mgr.submit(ids)
        con = store.connect()
        try:
            done = {i: wait_state(con, i) for i in ids}
        finally:
            con.close()
        for iid, row in done.items():
            check(f"下载 #{iid} 成功", row["dl_state"] == "done",
                  row["dl_error"] or row["dl_path"])

        hls_row = done.get(m3u8["id"]) if m3u8 else None
        if hls_row and hls_row["dl_state"] == "done":
            p = Path(hls_row["dl_path"])
            check("HLS 合并文件存在且有内容", p.exists() and p.stat().st_size > 10240,
                  f"{p.name} {p.stat().st_size} B")
            check("HLS 时长与源一致(≈6s)", abs(float(hls_row["dl_duration"]) - 6.0) < 1.0,
                  f"{hls_row['dl_duration']}s")
            check("文件名用了课程标题", p.stem.startswith(COURSE_TITLE), p.name)

        mp4_row = done.get(mp4["id"]) if mp4 else None
        if mp4_row and mp4_row["dl_state"] == "done":
            p = Path(mp4_row["dl_path"])
            src = SRC / "test.mp4"
            h = lambda f: hashlib.md5(f.read_bytes()).hexdigest()
            check("mp4 直链内容完整(字节一致)", h(p) == h(src),
                  f"{p.stat().st_size} B vs {src.stat().st_size} B")

        print("\n== 分片下载防护 ==")
        con = store.connect()
        fake_ts = f"http://127.0.0.1:{SEG_PORT}/other/{STREAM}/x2.ts"
        ts_id, _ = store.upsert_media(con, url=fake_ts, kind="ts", title="伪造的分片条目")
        related = store.find_related_playlist(con, fake_ts)
        check("能从分片找到同一节课的 HLS 条目",
              related is not None and int(related["id"]) == int(m3u8["id"]) if m3u8 else False,
              f"related={(dict(related)['id'] if related else None)} hls={m3u8['id'] if m3u8 else None}")
        try:
            download_item(con, store.get_item(con, ts_id), OUT, lambda **kw: None, threading.Event())
            check("单独下载分片被拒绝", False, "居然没报错")
        except Unsupported as e:
            check("单独下载分片被拒绝", "HLS 分片" in str(e), str(e)[:70])
        check("被拒后该分片自动忽略", bool(store.get_item(con, ts_id)["ignored"]))
        con.close()

        print("\n== 下载必须直连（不受系统/环境代理影响）==")
        # 系统代理可能正指向本机抓包端口；httpx 默认会读它，把下载又送回 mitmproxy →
        # 报 CERTIFICATE_VERIFY_FAILED。这里用死端口模拟，必须仍然直连成功。
        old_env = {k: os.environ.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")}
        os.environ["HTTP_PROXY"] = os.environ["HTTPS_PROXY"] = "http://127.0.0.1:9"
        try:
            direct = TMP / "direct" / "d.mp4"
            download_direct(f"http://127.0.0.1:{MEDIA_PORT}/test.mp4", {}, direct,
                            lambda **kw: None, threading.Event())
            check("设了代理环境变量仍直连成功",
                  direct.read_bytes() == (SRC / "test.mp4").read_bytes(),
                  f"{direct.stat().st_size} B")
        finally:
            for k, v in old_env.items():
                (os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v))

        print("\n== 断点续传 ==")
        src = SRC / "test.mp4"
        dest = TMP / "resume" / "r.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        prefix = src.read_bytes()[:1500]
        part.write_bytes(prefix)
        download_direct(f"http://127.0.0.1:{MEDIA_PORT}/test.mp4", {}, dest,
                        lambda **kw: None, threading.Event())
        check("续传后文件完整", dest.read_bytes() == src.read_bytes(),
              f"{dest.stat().st_size} B")
        check("未重复下载前缀", dest.read_bytes()[:1500] == prefix)
    finally:
        cap.terminate()
        srv.shutdown()
        segsrv.shutdown()

    print(f"\n{'全部通过' if not FAILED else '失败项: ' + ', '.join(FAILED)}")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
