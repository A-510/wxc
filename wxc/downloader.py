"""下载引擎：HLS/DASH 走 ffmpeg 合并（自动带 Referer/Cookie，支持 AES-128），
直链 mp4/ts/音频走 httpx 分片下载并支持断点续传。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit, unquote

import httpx

from . import detect, store
from .config import DEFAULT_CONCURRENCY, ffmpeg_path, ffprobe_path, ssl_context

UA_FALLBACK = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 MicroMessenger/3.9.12 MiniProgramEnv/Windows"
)
TIMEOUT = httpx.Timeout(connect=20.0, read=60.0, write=60.0, pool=20.0)
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_EXT_BY_KIND = {"hls": ".mp4", "dash": ".mp4", "mp4": ".mp4", "ts": ".ts", "flv": ".flv",
                "mkv": ".mkv", "webm": ".webm", "audio": ".m4a"}


class DownloadError(RuntimeError):
    pass


class Unsupported(DownloadError):
    pass


class Canceled(Exception):
    pass


# --------------------------------------------------------------------------- 工具

def safe_name(name: str, fallback: str = "video") -> str:
    s = _BAD_CHARS.sub("_", (name or "").strip()).strip(" .")
    s = re.sub(r"\s+", " ", s)
    if len(s) > 90:
        s = s[:90].rstrip()
    return s or fallback


def guess_name(item) -> str:
    path = urlsplit(item["url"]).path
    base = unquote(path.rsplit("/", 1)[-1]) or "video"
    base = base.rsplit(".", 1)[0]
    return safe_name(f"{item['kind']}-{base}")


def _client(timeout: httpx.Timeout | None = None) -> httpx.Client:
    """下载/拉清单一律直连。

    trust_env=False：否则 httpx 会经 urllib 读 Windows 注册表里的系统代理，把请求又送回
    本机抓包代理（mitmproxy），于是报 CERTIFICATE_VERIFY_FAILED。
    verify=系统证书存储：兼容证书链不完整的 CDN。
    """
    return httpx.Client(timeout=timeout or TIMEOUT, follow_redirects=True,
                        trust_env=False, verify=ssl_context())


def replay_headers(con, item) -> dict[str, str]:
    host = item["host"] or urlsplit(item["url"]).netloc
    try:
        own = json.loads(item["headers"] or "{}")
    except Exception:
        own = {}
    merged = store.merge_headers(own, store.get_host_headers(con, host))
    if not any(k.lower() == "user-agent" for k in merged):
        merged["User-Agent"] = UA_FALLBACK
    return merged


def _http_header_args(headers: dict[str, str]) -> list[str]:
    lines = "".join(f"{k}: {v}\r\n" for k, v in headers.items() if k.lower() != "user-agent")
    args: list[str] = []
    if lines:
        args += ["-headers", lines]
    ua = next((v for k, v in headers.items() if k.lower() == "user-agent"), UA_FALLBACK)
    args += ["-user_agent", ua]
    return args


_NAMES_LOCK = threading.Lock()
_RESERVED: set[str] = set()


def reserve_path(out_dir: Path, name: str, ext: str) -> Path:
    """原子分配一个还没被别的任务占用的文件名（落 0 字节占位文件，跨进程也唯一）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    with _NAMES_LOCK:
        i = 1
        while True:
            cand = out_dir / (f"{name}{ext}" if i == 1 else f"{name} ({i}){ext}")
            key = str(cand).lower()
            if key not in _RESERVED and not cand.exists():
                _RESERVED.add(key)
                try:
                    cand.touch()
                except OSError:
                    pass
                return cand
            i += 1


def release_path(path: Path) -> None:
    with _NAMES_LOCK:
        _RESERVED.discard(str(path).lower())
    try:
        if path.exists() and path.stat().st_size == 0:
            path.unlink()
    except OSError:
        pass


def probe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            [ffprobe_path(), "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return float((r.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


# --------------------------------------------------------------------------- 播放列表

_PLAYLIST_KINDS = ("hls",)


def parse_playlist(text: str) -> dict:
    lines = [l.strip() for l in (text or "").splitlines()]
    info = {"segments": 0, "duration": 0.0, "key_method": "", "endlist": False,
            "variants": []}
    pending_bw: int | None = None
    for line in lines:
        if not line:
            continue
        if line.startswith("#EXT-X-KEY"):
            m = re.search(r"METHOD=([A-Za-z0-9-]+)", line)
            if m and m.group(1).upper() != "NONE":
                info["key_method"] = m.group(1).upper()
        elif line.startswith("#EXT-X-STREAM-INF"):
            m = re.search(r"BANDWIDTH=(\d+)", line)
            pending_bw = int(m.group(1)) if m else 0
        elif line.startswith("#EXTINF"):
            m = re.search(r"#EXTINF:\s*([\d.]+)", line)
            info["segments"] += 1
            info["duration"] += float(m.group(1)) if m else 0.0
        elif line.startswith("#EXT-X-ENDLIST"):
            info["endlist"] = True
        elif not line.startswith("#"):
            if pending_bw is not None:
                info["variants"].append((pending_bw, line))
                pending_bw = None
    return info


def fetch_playlist(url: str, headers: dict[str, str], depth: int = 0) -> tuple[str, str] | None:
    """返回 (最终播放列表地址, 文本)。master 列表自动选码率最高的一路。"""
    if depth > 2:
        return None
    try:
        with _client(timeout=TIMEOUT) as c:
            r = c.get(url, headers=headers)
            if r.status_code >= 400:
                return None
            text = r.text
            final = str(r.url)
    except Exception:
        return None
    info = parse_playlist(text)
    if info["variants"]:
        best = max(info["variants"], key=lambda v: v[0])
        from urllib.parse import urljoin
        return fetch_playlist(urljoin(final, best[1]), headers, depth + 1)
    return final, text


def inspect_hls(url: str, headers: dict[str, str]) -> dict | None:
    got = fetch_playlist(url, headers)
    if not got:
        return None
    _, text = got
    return parse_playlist(text)


# --------------------------------------------------------------------------- 进度上报

class Reporter:
    """把进度写进 DB，节流到 0.5s。"""

    def __init__(self, con, item_id: int):
        self.con = con
        self.item_id = item_id
        self.last = 0.0
        self.latest: dict = {}

    def __call__(self, *, nbytes=None, total=None, out_time=None, duration=None) -> None:
        for k, v in (("nbytes", nbytes), ("total", total),
                     ("out_time", out_time), ("duration", duration)):
            if v is not None:
                self.latest[k] = v
        now = time.time()
        if now - self.last < 0.5:
            return
        self.last = now
        self.flush()

    def flush(self) -> None:
        d = self.latest
        try:
            store.update_progress(
                self.con, self.item_id,
                nbytes=d.get("nbytes"), total=d.get("total"),
                out_time=d.get("out_time"), duration=d.get("duration"),
            )
        except Exception:
            pass


# --------------------------------------------------------------------------- 直链下载

def download_direct(url: str, headers: dict[str, str], dest: Path, report, cancel) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    done = part.stat().st_size if part.exists() else 0
    total = 0
    last_err: Exception | None = None
    for attempt in range(4):
        if cancel.is_set():
            raise Canceled()
        h = dict(headers)
        if done:
            h["Range"] = f"bytes={done}-"
        try:
            with _client() as c:
                with c.stream("GET", url, headers=h) as r:
                    if r.status_code == 206:
                        cr = r.headers.get("content-range", "")
                        m = re.search(r"/(\d+)\s*$", cr)
                        total = int(m.group(1)) if m else (done + int(r.headers.get("content-length", 0) or 0))
                    elif r.status_code == 200:
                        if done:
                            done = 0
                        total = int(r.headers.get("content-length", 0) or 0)
                    else:
                        raise DownloadError(f"HTTP {r.status_code} {r.reason_phrase}")
                    mode = "ab" if done else "wb"
                    if mode == "wb" and done:
                        done = 0
                    report(nbytes=done, total=total)
                    with open(part, mode) as f:
                        for chunk in r.iter_bytes(256 * 1024):
                            if cancel.is_set():
                                raise Canceled()
                            f.write(chunk)
                            done += len(chunk)
                            report(nbytes=done, total=total)
            break
        except Canceled:
            raise
        except Exception as e:  # 网络中断：保留 .part，下次带着 Range 续传
            last_err = e
            if attempt == 3:
                raise DownloadError(f"下载失败：{e}") from e
            time.sleep(1.5 * (attempt + 1))
    if total and part.stat().st_size != total:
        # 服务器没给 206 且长度不符 → 当作失败，但保留分片供续传
        raise DownloadError(f"文件不完整：{part.stat().st_size}/{total}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    part.replace(dest)
    report(nbytes=dest.stat().st_size, total=dest.stat().st_size)
    return dest


# --------------------------------------------------------------------------- ffmpeg 合并

_STRATEGIES = (
    (["-c", "copy", "-movflags", "+faststart"], ".mp4"),
    (["-c", "copy", "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart"], ".mp4"),
    (["-c", "copy", "-bsf:a", "aac_adtstoasc"], ".ts"),
    (["-c", "copy"], ".mkv"),
)


_PROXY_ENV = ("http_proxy", "https_proxy", "all_proxy", "ftp_proxy", "no_proxy")


def _clean_env() -> dict[str, str]:
    """ffmpeg 自己会读 http_proxy 等环境变量，那会把下载送回本机抓包代理。

    `-http_proxy ""` 只挡得住清单请求，分片和 AES 密钥仍会走代理（实测），所以直接剥掉环境变量。
    """
    return {k: v for k, v in os.environ.items() if k.lower() not in _PROXY_ENV}


def run_ffmpeg(src_url: str, dest: Path, headers: dict[str, str], report, cancel,
               duration: float, extra: list[str]) -> Path:
    cmd = [ffmpeg_path(), "-hide_banner", "-nostdin", "-loglevel", "error",
           "-progress", "pipe:1", "-y",
           "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
           *_http_header_args(headers),
           "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
           "-i", src_url, *extra, str(dest)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1, encoding="utf-8", errors="replace",
                            env=_clean_env())
    err_tail: list[str] = []

    def pump_out() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    report(out_time=int(line.split("=", 1)[1]) / 1_000_000)
                except ValueError:
                    pass
            elif line.startswith("total_size="):
                try:
                    report(nbytes=int(line.split("=", 1)[1]))
                except ValueError:
                    pass

    def pump_err() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            err_tail.append(line.rstrip())
            if len(err_tail) > 40:
                del err_tail[0]

    threads = [threading.Thread(target=pump_out, daemon=True),
               threading.Thread(target=pump_err, daemon=True)]
    for t in threads:
        t.start()
    try:
        while proc.poll() is None:
            if cancel.is_set():
                proc.kill()
                proc.wait(timeout=10)
                raise Canceled()
            time.sleep(0.3)
        code = proc.returncode
    finally:
        for t in threads:
            t.join(timeout=5)
    if dest.exists():
        sz = dest.stat().st_size
        if code == 0 and sz > 1024:
            report(nbytes=sz, out_time=duration or None, duration=duration or None)
            return dest
        try:
            dest.unlink()
        except OSError:
            pass
    tail = " | ".join(err_tail[-4:]) if err_tail else f"ffmpeg 退出码 {code}"
    raise DownloadError(tail)


# --------------------------------------------------------------------------- 单条目

def download_item(con, item, out_dir: Path, report: Reporter, cancel: threading.Event) -> Path:
    url = item["url"]
    kind = item["kind"]
    headers = replay_headers(con, item)
    base_name = safe_name(item["title"] or "") or guess_name(item)
    q = detect.quality(url)
    if q and q not in base_name:  # 同一节课多个清晰度时，文件名带上清晰度避免分不清
        base_name = safe_name(f"{base_name} [{q}]")

    if kind in _PLAYLIST_KINDS or kind == "dash":
        info = inspect_hls(url, headers) if kind in _PLAYLIST_KINDS else None
        if info:
            if info["key_method"] in ("SAMPLE-AES", "SAMPLE-AES-CTR"):
                raise Unsupported("该视频使用 SAMPLE-AES 加密（DRM），本工具不支持解密")
            if info["segments"] == 0 and not info["endlist"]:
                raise DownloadError("这不是点播播放列表（没有分片或未结束），请播放后暂停重新抓取")
            duration = info["duration"]
            report(duration=duration or None)
        else:
            duration = 0.0
        last_err: Exception | None = None
        dest: Path | None = None
        for extra, ext in _STRATEGIES:
            if cancel.is_set():
                if dest is not None:
                    release_path(dest)
                raise Canceled()
            if dest is None or dest.suffix.lower() != ext:
                if dest is not None:
                    release_path(dest)
                dest = reserve_path(out_dir, base_name, ext)
            try:
                out = run_ffmpeg(url, dest, headers, report, cancel, duration, extra)
                _RESERVED.discard(str(out).lower())
                return out
            except Canceled:
                release_path(dest)
                raise
            except DownloadError as e:
                last_err = e
        if dest is not None:
            release_path(dest)
        raise DownloadError(f"ffmpeg 合并失败：{last_err}")

    if kind == "f4m":
        raise Unsupported("f4m 清单（Adobe HDS）暂不支持，请在微信里换清晰度或改用其它课时链接")

    if kind == "ts":
        # 单独一个 .ts 往往是加密 HLS 的分片（约几秒、未解密），存下来必然播放不了
        alt = store.find_related_playlist(con, url)
        if alt is not None:
            store.set_ignored(con, int(item["id"]), True)
            raise Unsupported(
                "这是同一节课的 HLS 分片（片段、且是加密原文），单独保存无法播放；已把它忽略。"
                f"请下载列表里同一节课的 HLS 条目"
                f"（清晰度 {detect.quality(alt['url']) or '?'}，它能解密并合成整节课）。")

    ext = _EXT_BY_KIND.get(kind, ".mp4")
    dest = reserve_path(out_dir, base_name, ext)
    try:
        out = download_direct(url, headers, dest, report, cancel)
    except BaseException:
        release_path(dest)
        raise
    _RESERVED.discard(str(out).lower())
    return out


# --------------------------------------------------------------------------- 任务管理

class Manager:
    def __init__(self, out_dir: Path, concurrency: int = DEFAULT_CONCURRENCY):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.concurrency = max(1, int(concurrency))
        self._pool = ThreadPoolExecutor(max_workers=self.concurrency, thread_name_prefix="wxc-dl")
        self._cancels: dict[int, threading.Event] = {}
        self._lock = threading.Lock()

    # --- 配置
    def set_options(self, *, out_dir: Path | None = None, concurrency: int | None = None) -> None:
        if out_dir is not None:
            out_dir = Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            self.out_dir = out_dir
        if concurrency is not None:
            concurrency = max(1, int(concurrency))
            if concurrency != self.concurrency:
                self.concurrency = concurrency
                with self._lock:
                    self._pool.shutdown(wait=False, cancel_futures=False)
                    self._pool = ThreadPoolExecutor(max_workers=concurrency,
                                                    thread_name_prefix="wxc-dl")

    @property
    def active(self) -> int:
        with self._lock:
            return len(self._cancels)

    # --- 调度
    def submit(self, ids: list[int]) -> list[int]:
        con = store.connect()
        accepted: list[int] = []
        for item_id in ids:
            item = store.get_item(con, item_id)
            if item is None:
                continue
            with self._lock:
                if item_id in self._cancels:
                    continue
                self._cancels[item_id] = threading.Event()
            store.set_state(con, item_id, "queued", error="")
            accepted.append(item_id)
            self._pool.submit(self._run, item_id)
        con.close()
        return accepted

    def cancel(self, item_id: int) -> bool:
        with self._lock:
            ev = self._cancels.get(item_id)
        if ev is None:
            return False
        ev.set()
        return True

    def cancel_all(self) -> int:
        with self._lock:
            evs = list(self._cancels.values())
        for ev in evs:
            ev.set()
        return len(evs)

    def _run(self, item_id: int) -> None:
        con = store.connect()
        with self._lock:
            cancel = self._cancels.get(item_id) or threading.Event()
        try:
            item = store.get_item(con, item_id)
            if item is None:
                return
            store.set_state(con, item_id, "running", error="")
            report = Reporter(con, item_id)
            path = download_item(con, item, self.out_dir, report, cancel)
            report.flush()
            dur = probe_duration(path)
            store.set_state(con, item_id, "done", error="", path=str(path),
                            total=path.stat().st_size, duration=dur)
        except Canceled:
            store.set_state(con, item_id, "canceled", error="已取消")
        except DownloadError as e:
            store.set_state(con, item_id, "error", error=str(e)[:800])
        except Exception as e:  # 兜底，别让线程静默死掉
            store.set_state(con, item_id, "error", error=f"{type(e).__name__}: {e}"[:800])
        finally:
            with self._lock:
                self._cancels.pop(item_id, None)
            con.close()
