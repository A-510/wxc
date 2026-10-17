"""mitmdump 插件：拦截小程序播放网课的媒体请求，写入本地库。

由 `wxc capture` 以 `mitmdump -s wxc/capture.py` 方式加载，所以这里手动补 sys.path，
不能依赖包内相对导入。
"""
from __future__ import annotations

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mitmproxy import ctx, http  # noqa: E402

from wxc import detect, store  # noqa: E402
from wxc.config import PARSE_BODY_LIMIT  # noqa: E402

# 这些响应体值得读出来找内嵌视频地址
_PARSE_CTS = (
    "application/json", "text/json", "text/plain", "text/html",
    "application/javascript", "text/javascript", "application/x-javascript",
    "application/xml", "text/xml", "application/xhtml+xml",
)
# 这些请求的请求头适合当作该 host 的可重放头（含 Cookie/token）
_HDR_CTS = (
    "application/json", "text/json", "application/javascript",
    "text/javascript", "application/vnd.apple.mpegurl", "application/x-mpegurl",
    "video/", "audio/", "application/octet-stream",
)


def _log(msg: str) -> None:
    try:
        ctx.log.info(msg)
    except Exception:
        print(msg, flush=True)


def _warn(msg: str) -> None:
    try:
        ctx.log.warn(msg)
    except Exception:
        print(msg, flush=True)


class WxcCapture:
    def __init__(self) -> None:
        self.con = store.connect()
        self.seg = store.load_seg_prefixes(self.con)
        # 流 ID：来自库里的清单条目 + 本次新抓到的清单；不需要重新拉清单也能认出跨主机分片
        self.streams = store.load_stream_tokens(self.con) | store.backfill_stream_tokens(self.con)
        self.seen = 0

    def load(self, loader) -> None:
        _log("[wxc] 抓包插件就绪：播放小程序网课，媒体地址会在这里记录下来")
        if self.streams:
            _log(f"[wxc] 已从库里认出 {len(self.streams)} 个流 ID，它们的 .ts 分片不会再入库")

    def response(self, flow: http.HTTPFlow) -> None:
        try:
            self._handle(flow)
        except Exception:
            _warn("[wxc] 记录失败: " + traceback.format_exc(limit=3).replace("\n", " | "))

    def _learn_stream(self, url: str) -> None:
        new = set(detect.stream_tokens(url)) - self.streams
        if new:
            store.add_stream_tokens(self.con, new)
            self.streams |= new
            _log(f"[wxc] 记下流 ID {sorted(new)}（同流的 .ts 分片不再单独入库）")

    def _is_segment(self, url: str) -> bool:
        low = url.lower()
        return (store.url_dir(url) in self.seg
                or store.hls_prefix_exists(self.con, url)
                or any(t in low for t in self.streams))

    def _learn_segments(self, text: str, base: str) -> None:
        """从清单里学出分片地址的目录。分片常挂在另一台 CDN 主机上，只靠同目录判断会漏。"""
        urls = detect.playlist_urls(text, base)
        if not urls:
            return
        new = {store.url_dir(u) for u in urls} - self.seg
        if new:
            store.add_seg_prefixes(self.con, new)
            self.seg |= new
            _log(f"[wxc] 清单里含 {len(urls)} 个分片地址，已记下 {len(new)} 个目录（分片不再单独入库）")

    # ---------------------------------------------------------------- internals
    @staticmethod
    def _size(resp: http.Response) -> int:
        cl = resp.headers.get("content-length")
        if cl and cl.isdigit():
            return int(cl)
        try:
            raw = resp.raw_content
            return len(raw) if raw else -1
        except Exception:
            return -1

    @staticmethod
    def _text(resp: http.Response) -> str | None:
        cl = resp.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > PARSE_BODY_LIMIT:
            return None
        try:
            return resp.get_text(strict=False)
        except Exception:
            return None

    def _store(
        self,
        *,
        url: str,
        kind: str,
        mime: str,
        size: int,
        headers: dict[str, str],
        title: str = "",
    ) -> None:
        if kind == "ts" and self._is_segment(url):
            store.bump_segment(self.con, url)
            return
        item_id, created = store.upsert_media(
            self.con, url=url, kind=kind, mime=mime, size=size, title=title, headers=headers
        )
        if created:
            self.seen += 1
            label = title or url.rsplit("/", 1)[-1][:60]
            _log(f"[wxc] 发现 #{item_id} [{kind}] {label}")

    def _handle(self, flow: http.HTTPFlow) -> None:
        resp = flow.response
        if resp is None:
            return
        req = flow.request
        url = req.pretty_url
        ct = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        headers = store.sanitize_req_headers(dict(req.headers))
        kind = detect.classify(url, ct)

        if kind:
            self._store(url=url, kind=kind, mime=ct, size=self._size(resp), headers=headers)
            if kind in ("hls", "dash"):
                self._learn_stream(url)
                text = self._text(resp)
                if text:
                    self._learn_segments(text, url)

        if headers and (kind or ct in _HDR_CTS or not ct):
            store.set_host_headers(self.con, req.pretty_host, headers)

        # 接口返回里内嵌的视频地址（小程序常见：先拿课程目录/播放地址接口，再交给 video 组件）
        if ct in _PARSE_CTS or ct == "" or ct.startswith("text/"):
            text = self._text(resp)
            if text:
                for u, title in detect.urls_with_titles(text, base=url):
                    if u == url:
                        continue
                    k = detect.classify(u)
                    if not k:
                        continue
                    self._store(url=u, kind=k, mime="", size=-1, headers=headers,
                                title=title or "")


addons = [WxcCapture()]
