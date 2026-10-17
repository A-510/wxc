"""媒体识别：URL/Content-Type 分类，以及从 JSON/HTML 文本里挖出视频地址与标题。"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlsplit

KIND_BY_EXT = {
    ".m3u8": "hls",
    ".mpd": "dash",
    ".mp4": "mp4",
    ".m4v": "mp4",
    ".mov": "mp4",
    ".ts": "ts",
    ".m2ts": "ts",
    ".flv": "flv",
    ".mkv": "mkv",
    ".webm": "webm",
    ".mp3": "audio",
    ".m4a": "audio",
    ".aac": "audio",
    ".wav": "audio",
    ".f4m": "f4m",
}

KIND_BY_MIME = {
    "application/vnd.apple.mpegurl": "hls",
    "application/x-mpegurl": "hls",
    "audio/mpegurl": "hls",
    "audio/x-mpegurl": "hls",
    "application/dash+xml": "dash",
    "video/mp4": "mp4",
    "video/quicktime": "mp4",
    "video/mp2t": "ts",
    "video/x-flv": "flv",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
    "audio/mpeg": "audio",
    "audio/mp4": "audio",
    "audio/aac": "audio",
}

# 标题字段白名单（小写比较）；比 “key 以 name 结尾” 之类的启发式更不容易抓错
TITLE_KEYS = {
    "title", "name", "course_name", "coursename", "course_title", "coursetitle",
    "chapter_name", "chaptername", "chapter_title", "chaptertitle", "chapter",
    "section_name", "sectionname", "section_title", "sectiontitle", "section",
    "lesson_name", "lessonname", "lesson_title", "lessontitle", "lesson",
    "video_name", "videoname", "video_title", "videotitle", "video",
    "file_name", "filename", "res_name", "resname", "resource_name", "resourcename",
    "subject", "subject_name", "subjectname", "kcmc", "kcmc_name", "kecheng",
    "catalog_name", "catalogname", "catalog",
}

MEDIA_EXTS = "|".join(e.lstrip(".") for e in sorted(KIND_BY_EXT))
_MEDIA_URL_RE = re.compile(
    rf"https?://[^\s\"'<>\\\]\)]+?\.(?:{MEDIA_EXTS})(?:\?[^\s\"'<>\\\]\)]*)?",
    re.IGNORECASE,
)
_REL_MEDIA_URL_RE = re.compile(
    rf"(?<![:/\w])//[^\s\"'<>\\\]\)]+?\.(?:{MEDIA_EXTS})(?:\?[^\s\"'<>\\\]\)]*)?",
    re.IGNORECASE,
)


def _path(url: str) -> str:
    try:
        return urlsplit(url).path or ""
    except Exception:
        return ""


def classify(url: str, content_type: str = "") -> str | None:
    ext = ""
    p = _path(url)
    if "." in p.rsplit("/", 1)[-1]:
        ext = "." + p.rsplit("/", 1)[-1].rsplit(".", 1)[-1].lower()
    if ext in KIND_BY_EXT:
        return KIND_BY_EXT[ext]
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in KIND_BY_MIME:
        return KIND_BY_MIME[ct]
    return None


def is_media_url(url: str) -> bool:
    return bool(classify(url))


_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def stream_tokens(url: str) -> list[str]:
    """从地址里取出「流 ID」这类 token（如 goDt1773822105VXnP、dtest1773822105VXnP）。

    为什么需要：分片常挂在另一台 CDN 主机、目录也完全不同，但路径里通常带同一个流 ID。
    靠它才能把「清单都没重新拉过」的情况下出现的跨主机 .ts 认出来是分片。
    """
    out: list[str] = []
    for part in _path(url).split("/"):
        p = part.strip()
        if (len(p) >= 10 and "." not in p and _TOKEN_RE.match(p)
                and any(c.isdigit() for c in p) and any(c.isalpha() for c in p)):
            out.append(p.lower())
    return out


def quality(url: str) -> str:
    """从地址里取清晰度，如 1280x720；取不到返回空串。"""
    m = re.search(r"(\d{3,4})x(\d{3,4})", _path(url))
    if not m:
        return ""
    return f"{int(m.group(1))}x{int(m.group(2))}"


def playlist_urls(text: str, base: str = "") -> list[str]:
    """把 HLS/DASH 清单里的分片/变体地址补全成绝对地址（含 URI="..." 属性）。

    关键点：清单里的地址可能指向另一台 CDN 主机，靠它们才能认出跨主机的 .ts 分片。
    """
    if not text:
        return []
    raw: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            raw += [m.group(1) for m in re.finditer(r'URI="([^"]+)"', line)]
        else:
            raw.append(line)
    seen: set[str] = set()
    out: list[str] = []
    for u in raw:
        absu = urljoin(base, u) if base else u
        if absu.startswith(("http://", "https://")) and absu not in seen:
            seen.add(absu)
            out.append(absu)
    return out


def _valid_title(v: str) -> bool:
    s = v.strip()
    if not (1 < len(s) <= 100):
        return False
    if s.lower().startswith(("http://", "https://", "data:")):
        return False
    if re.fullmatch(r"[0-9a-fA-F\-_]{8,}", s):  # id / uuid
        return False
    if re.fullmatch(r"[\d\s\-_./:]*", s):  # 纯数字、日期、时长
        return False
    return True


def _walk(node, title: str | None, out: list[tuple[str, str | None]], base: str, depth: int) -> None:
    if depth > 10:
        return
    if isinstance(node, dict):
        local = title
        for k, v in node.items():
            if isinstance(v, str) and k.lower() in TITLE_KEYS and _valid_title(v):
                local = v.strip()
                break
        for v in node.values():
            _walk(v, local, out, base, depth + 1)
    elif isinstance(node, list):
        for v in node[:3000]:
            _walk(v, title, out, base, depth + 1)
    elif isinstance(node, str):
        for m in _MEDIA_URL_RE.finditer(node):
            out.append((urljoin(base, m.group(0)) if base else m.group(0), title))
        if not _MEDIA_URL_RE.search(node):
            for m in _REL_MEDIA_URL_RE.finditer(node):
                out.append((urljoin(base, m.group(0)) if base else m.group(0), title))


def urls_with_titles(text: str, base: str = "") -> list[tuple[str, str | None]]:
    """从响应文本里提取 (媒体地址, 猜测标题)。base 用于补全相对地址。"""
    if not text:
        return []
    raw: list[tuple[str, str | None]] = []
    stripped = text.lstrip()
    if stripped[:1] in ("{", "["):
        try:
            _walk(json.loads(text), None, raw, base, 0)
        except Exception:
            raw = []
    if not raw:
        flat = text.replace("\\/", "/")
        flat = re.sub(r"\\u002[fF]", "/", flat)
        for m in _MEDIA_URL_RE.finditer(flat):
            raw.append((m.group(0), None))
        for m in _REL_MEDIA_URL_RE.finditer(flat):
            raw.append((urljoin(base, m.group(0)) if base else m.group(0), None))

    seen: set[str] = set()
    out: list[tuple[str, str | None]] = []
    for url, title in raw:
        url = url.rstrip("\\,")
        if url in seen or not is_media_url(url):
            continue
        seen.add(url)
        out.append((url, title))
    return out
