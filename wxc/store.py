"""SQLite 存储：捕获到的媒体条目、按 host 的请求头、设置、分片计数。"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .config import DB_PATH, data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL,
    mime        TEXT DEFAULT '',
    host        TEXT DEFAULT '',
    size        INTEGER NOT NULL DEFAULT -1,
    title       TEXT DEFAULT '',
    referer     TEXT DEFAULT '',
    headers     TEXT DEFAULT '{}',
    ignored     INTEGER NOT NULL DEFAULT 0,
    hits        INTEGER NOT NULL DEFAULT 1,
    first_seen  REAL NOT NULL DEFAULT 0,
    last_seen   REAL NOT NULL DEFAULT 0,
    dl_state    TEXT NOT NULL DEFAULT 'idle',
    dl_path     TEXT DEFAULT '',
    dl_error    TEXT DEFAULT '',
    dl_bytes    INTEGER NOT NULL DEFAULT 0,
    dl_total    INTEGER NOT NULL DEFAULT 0,
    dl_out_time REAL NOT NULL DEFAULT 0,
    dl_duration REAL NOT NULL DEFAULT 0,
    dl_updated  REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS media_seen ON media(last_seen DESC);
CREATE INDEX IF NOT EXISTS media_state ON media(dl_state);

CREATE TABLE IF NOT EXISTS host_headers (
    host    TEXT PRIMARY KEY,
    headers TEXT NOT NULL,
    updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segments (
    prefix  TEXT PRIMARY KEY,
    count   INTEGER NOT NULL DEFAULT 0,
    updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS seg_prefix (
    prefix  TEXT PRIMARY KEY,
    updated REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS stream_token (
    token   TEXT PRIMARY KEY,
    updated REAL NOT NULL
);
"""

# 这些请求头不含身份信息或与播放无关，重放时丢掉
_DROP_HEADERS = {
    "host", "content-length", "content-type", "connection", "accept-encoding",
    "range", "if-range", "if-none-match", "if-modified-since", "cache-control",
    "pragma", "upgrade-insecure-requests", "te", "trailer", "transfer-encoding",
    "expect", "proxy-authorization", "proxy-connection", "keep-alive",
}
_DROP_PREFIX = ("sec-", ":")
# 优先保留的头（排序靠前，方便日志/调试阅读）
_PRIORITY = ("cookie", "referer", "origin", "user-agent", "authorization")


def sanitize_req_headers(headers: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in _DROP_HEADERS or lk.startswith(_DROP_PREFIX):
            continue
        if v is None or len(str(v)) > 4096:
            continue
        out[k] = str(v)
    return out


def merge_headers(primary: dict[str, str], fallback: dict[str, str]) -> dict[str, str]:
    """primary 优先，fallback（同 host 最近一次请求头）补齐缺失项。"""
    out = dict(fallback or {})
    low = {k.lower(): k for k in out}
    for k, v in (primary or {}).items():
        if k.lower() in low:
            out[low[k.lower()]] = v
        else:
            out[k] = v
    return out


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    data_dir()
    con = sqlite3.connect(str(path or DB_PATH), timeout=20, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA busy_timeout=15000")
    con.executescript(SCHEMA)
    return con


# --------------------------------------------------------------------------- 媒体条目

def upsert_media(
    con: sqlite3.Connection,
    *,
    url: str,
    kind: str,
    mime: str = "",
    size: int = -1,
    title: str = "",
    headers: dict[str, str] | None = None,
    referer: str = "",
) -> tuple[int, bool]:
    """返回 (id, 是否为新增)。重复抓到的只累加 hits 并补齐信息。"""
    from urllib.parse import urlsplit

    now = time.time()
    host = urlsplit(url).netloc
    hjson = json.dumps(headers or {}, ensure_ascii=False)
    row = con.execute("SELECT id FROM media WHERE url = ?", (url,)).fetchone()
    if row is None:
        cur = con.execute(
            """INSERT INTO media(url, kind, mime, host, size, title, referer, headers,
                                 first_seen, last_seen)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (url, kind, mime, host, size, title, referer or (headers or {}).get("Referer", ""),
             hjson, now, now),
        )
        con.commit()
        return int(cur.lastrowid), True

    con.execute(
        """UPDATE media SET
             hits = hits + 1,
             last_seen = ?,
             kind = ?,
             mime = CASE WHEN ? <> '' THEN ? ELSE mime END,
             size = CASE WHEN ? > 0 THEN ? ELSE size END,
             title = CASE WHEN (title IS NULL OR title = '') THEN ? ELSE title END,
             host = CASE WHEN ? <> '' THEN ? ELSE host END,
             referer = CASE WHEN (referer IS NULL OR referer = '') THEN ? ELSE referer END,
             headers = CASE WHEN ? <> '{}' THEN ? ELSE headers END
           WHERE id = ?""",
        (now, kind, mime, mime, size, size, title, host, host,
         referer or (headers or {}).get("Referer", ""), hjson, hjson, int(row["id"])),
    )
    con.commit()
    return int(row["id"]), False


def get_item(con: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM media WHERE id = ?", (int(item_id),)).fetchone()


def list_items(
    con: sqlite3.Connection,
    *,
    include_ignored: bool = True,
    q: str = "",
    limit: int = 2000,
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM media WHERE 1=1"
    args: list[Any] = []
    if not include_ignored:
        sql += " AND ignored = 0"
    if q:
        sql += " AND (title LIKE ? OR url LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY last_seen DESC LIMIT ?"
    args.append(limit)
    return list(con.execute(sql, args).fetchall())


def item_ids(con: sqlite3.Connection, *, only_idle: bool = True, q: str = "") -> list[int]:
    sql = "SELECT id FROM media WHERE ignored = 0 AND dl_state NOT IN ('queued','running')"
    args: list[Any] = []
    if only_idle:
        sql += " AND dl_state <> 'done'"
    if q:
        sql += " AND (title LIKE ? OR url LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY last_seen DESC"
    return [int(r["id"]) for r in con.execute(sql, args).fetchall()]


def set_state(
    con: sqlite3.Connection,
    item_id: int,
    state: str,
    *,
    error: str | None = None,
    path: str | None = None,
    total: int | None = None,
    duration: float | None = None,
) -> None:
    sets = ["dl_state = ?", "dl_updated = ?"]
    args: list[Any] = [state, time.time()]
    if error is not None:
        sets.append("dl_error = ?")
        args.append(error)
    if path is not None:
        sets.append("dl_path = ?")
        args.append(path)
    if total is not None:
        sets.append("dl_total = ?")
        args.append(total)
    if duration is not None:
        sets.append("dl_duration = ?")
        args.append(duration)
    if state in ("idle", "queued"):
        sets += ["dl_bytes = 0", "dl_out_time = 0"]
    args.append(int(item_id))
    con.execute(f"UPDATE media SET {', '.join(sets)} WHERE id = ?", args)
    con.commit()


def update_progress(
    con: sqlite3.Connection,
    item_id: int,
    *,
    nbytes: int | None = None,
    total: int | None = None,
    out_time: float | None = None,
    duration: float | None = None,
) -> None:
    sets = ["dl_updated = ?"]
    args: list[Any] = [time.time()]
    for col, val in (("dl_bytes", nbytes), ("dl_total", total),
                     ("dl_out_time", out_time), ("dl_duration", duration)):
        if val is not None:
            sets.append(f"{col} = ?")
            args.append(val)
    args.append(int(item_id))
    con.execute(f"UPDATE media SET {', '.join(sets)} WHERE id = ?", args)
    con.commit()


def set_title(con: sqlite3.Connection, item_id: int, title: str) -> None:
    con.execute("UPDATE media SET title = ? WHERE id = ?", (title, int(item_id)))
    con.commit()


def set_url(con: sqlite3.Connection, item_id: int, url: str) -> None:
    con.execute("UPDATE media SET url = ? WHERE id = ?", (url, int(item_id)))
    con.commit()


def set_ignored(con: sqlite3.Connection, item_id: int, ignored: bool) -> None:
    con.execute("UPDATE media SET ignored = ? WHERE id = ?", (1 if ignored else 0, int(item_id)))
    con.commit()


def delete_item(con: sqlite3.Connection, item_id: int) -> None:
    con.execute("DELETE FROM media WHERE id = ?", (int(item_id),))
    con.commit()


def pending_states(con: sqlite3.Connection) -> None:
    """进程重启后把中断的任务标为可重试。"""
    now = time.time()
    con.execute(
        "UPDATE media SET dl_state = 'error', dl_error = '上次下载被中断' "
        "WHERE dl_state IN ('queued','running') AND dl_updated < ?", (now,))
    con.commit()


def counts(con: sqlite3.Connection) -> dict[str, int]:
    out = {"total": 0, "done": 0, "running": 0, "error": 0}
    for r in con.execute("SELECT dl_state, COUNT(*) c FROM media GROUP BY dl_state"):
        out["total"] += int(r["c"])
        if r["dl_state"] in out:
            out[str(r["dl_state"])] = int(r["c"])
    return out


# --------------------------------------------------------------------------- host 请求头

def set_host_headers(con: sqlite3.Connection, host: str, headers: dict[str, str]) -> None:
    if not host:
        return
    con.execute(
        "INSERT INTO host_headers(host, headers, updated) VALUES(?,?,?) "
        "ON CONFLICT(host) DO UPDATE SET headers = excluded.headers, updated = excluded.updated",
        (host, json.dumps(headers, ensure_ascii=False), time.time()),
    )
    con.commit()


def get_host_headers(con: sqlite3.Connection, host: str) -> dict[str, str]:
    row = con.execute("SELECT headers FROM host_headers WHERE host = ?", (host,)).fetchone()
    if row is None:
        return {}
    try:
        return dict(json.loads(row["headers"]))
    except Exception:
        return {}


# --------------------------------------------------------------------------- 分片计数

def hls_prefix_exists(con: sqlite3.Connection, url: str) -> bool:
    prefix = url.rsplit("/", 1)[0] + "/"
    row = con.execute(
        "SELECT 1 FROM media WHERE kind = 'hls' AND url LIKE ? LIMIT 1", (prefix + "%",)
    ).fetchone()
    return row is not None


def url_dir(url: str) -> str:
    return (url.rsplit("/", 1)[0] + "/") if "/" in url else url


def load_seg_prefixes(con: sqlite3.Connection) -> set[str]:
    """清单里出现过的分片目录（跨 CDN 主机也能认出），这些地址不再单独入库。"""
    return {str(r["prefix"]) for r in con.execute("SELECT prefix FROM seg_prefix")}


def add_seg_prefixes(con: sqlite3.Connection, prefixes: Iterable[str]) -> int:
    now = time.time()
    rows = [(p, now) for p in prefixes if p]
    if not rows:
        return 0
    before = con.total_changes
    con.executemany(
        "INSERT INTO seg_prefix(prefix, updated) VALUES(?,?) "
        "ON CONFLICT(prefix) DO UPDATE SET updated = excluded.updated", rows)
    con.commit()
    return con.total_changes - before


def cleanup_segments(con: sqlite3.Connection, *, delete: bool = False) -> int:
    """清理被当成视频条目抓进来的 .ts 分片：默认只忽略，delete=True 才真删。"""
    if delete:
        cur = con.execute("DELETE FROM media WHERE kind = 'ts'")
    else:
        cur = con.execute("UPDATE media SET ignored = 1 WHERE kind = 'ts'")
    con.commit()
    return int(cur.rowcount or 0)


# --------------------------------------------------------------------------- 流 ID（分片识别）

def load_stream_tokens(con: sqlite3.Connection) -> set[str]:
    return {str(r["token"]).lower() for r in con.execute("SELECT token FROM stream_token")}


def add_stream_tokens(con: sqlite3.Connection, tokens: Iterable[str]) -> int:
    from . import detect

    rows = [(t.lower(), time.time()) for t in tokens if t]
    if not rows:
        return 0
    before = con.total_changes
    con.executemany(
        "INSERT INTO stream_token(token, updated) VALUES(?,?) "
        "ON CONFLICT(token) DO UPDATE SET updated = excluded.updated", rows)
    con.commit()
    return con.total_changes - before


def backfill_stream_tokens(con: sqlite3.Connection) -> set[str]:
    """从库里已有的清单条目补出流 ID。

    这样即使播放器这次没重新拉清单（接着上次播放），新冒出来的跨主机 .ts 也能被认成分片。
    """
    from . import detect

    toks: set[str] = set()
    for r in con.execute("SELECT url FROM media WHERE kind IN ('hls','dash')"):
        toks |= set(detect.stream_tokens(r["url"]))
    if toks:
        add_stream_tokens(con, toks)
    return toks


def _quality_score(q: str) -> int:
    m = re.fullmatch(r"(\d+)x(\d+)", q or "")
    return int(m.group(1)) * int(m.group(2)) if m else 0


def find_related_playlist(con: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    """找出与给定地址属于同一「流」的 HLS/DASH 条目（优先清晰度最高的）。"""
    from . import detect

    toks = {t.lower() for t in detect.stream_tokens(url)}
    if not toks:
        return None
    best: tuple[int, sqlite3.Row] | None = None
    for r in con.execute("SELECT * FROM media WHERE kind IN ('hls','dash')"):
        rt = {t.lower() for t in detect.stream_tokens(r["url"])}
        if not (rt & toks):
            continue
        score = _quality_score(detect.quality(r["url"]))
        if best is None or score > best[0]:
            best = (score, r)
    return best[1] if best else None


def bump_segment(con: sqlite3.Connection, url: str) -> None:
    prefix = url_dir(url)
    con.execute(
        "INSERT INTO segments(prefix, count, updated) VALUES(?,1,?) "
        "ON CONFLICT(prefix) DO UPDATE SET count = count + 1, updated = excluded.updated",
        (prefix, time.time()),
    )
    con.commit()


# --------------------------------------------------------------------------- 设置

def get_setting(con: sqlite3.Connection, key: str, default: str = "") -> str:
    row = con.execute("SELECT v FROM settings WHERE k = ?", (key,)).fetchone()
    return str(row["v"]) if row else default


def set_setting(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO settings(k, v) VALUES(?,?) "
        "ON CONFLICT(k) DO UPDATE SET v = excluded.v",
        (key, str(value)),
    )
    con.commit()
