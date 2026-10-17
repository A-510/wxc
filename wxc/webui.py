"""本地网页界面：FastAPI 接口 + 单页静态页。"""
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import httpx
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from . import detect, proxy, store
from .config import (ART_FILE, DEFAULT_CAPTURE_PORT, DEFAULT_CONCURRENCY,
                     DEFAULT_UI_PORT, STATIC_DIR, default_download_dir,
                     ffmpeg_path, PARSE_BODY_LIMIT, ssl_context)
from .downloader import Manager, safe_name, UA_FALLBACK

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=0.4):
            return True
    except OSError:
        return False


def item_json(r, out_dir: Path, con=None) -> dict:
    out_time = float(r["dl_out_time"] or 0)
    duration = float(r["dl_duration"] or 0)
    nbytes = int(r["dl_bytes"] or 0)
    total = int(r["dl_total"] or 0)
    if duration > 0:
        progress = min(1.0, out_time / duration)
    elif total > 0:
        progress = min(1.0, nbytes / total)
    else:
        progress = None
    path = r["dl_path"] or ""
    related = (store.find_related_playlist(con, r["url"])
               if (con is not None and r["kind"] == "ts") else None)
    return {
        "id": int(r["id"]),
        "url": r["url"],
        "kind": r["kind"],
        "mime": r["mime"] or "",
        "host": r["host"] or "",
        "size": int(r["size"] or -1),
        "title": r["title"] or "",
        "quality": detect.quality(r["url"]),
        "related_id": int(related["id"]) if related is not None else 0,
        "referer": r["referer"] or "",
        "ignored": bool(r["ignored"]),
        "hits": int(r["hits"] or 0),
        "first_seen": float(r["first_seen"] or 0),
        "last_seen": float(r["last_seen"] or 0),
        "state": r["dl_state"] or "idle",
        "error": r["dl_error"] or "",
        "file": path,
        "file_name": Path(path).name if path else "",
        "file_exists": bool(path) and Path(path).exists(),
        "bytes": nbytes,
        "total": total,
        "out_time": out_time,
        "duration": duration,
        "progress": progress,
    }


def settings(con) -> dict:
    out_dir = store.get_setting(con, "out_dir", str(default_download_dir()))
    return {
        "out_dir": out_dir,
        "concurrency": int(store.get_setting(con, "concurrency", str(DEFAULT_CONCURRENCY))),
        "capture_port": int(store.get_setting(con, "capture_port", str(DEFAULT_CAPTURE_PORT))),
        "ui_port": int(store.get_setting(con, "ui_port", str(DEFAULT_UI_PORT))),
    }


def create_app(manager: Manager | None = None) -> FastAPI:
    app = FastAPI(title="wxc 网课下载器")

    con0 = store.connect()
    cfg = settings(con0)
    con0.close()
    manager = manager or Manager(Path(cfg["out_dir"]), cfg["concurrency"])

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        page = STATIC_DIR / "index.html"
        return HTMLResponse(page.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ 界面背景插画
    @app.get("/art/background")
    def art_background() -> FileResponse:
        """用户提供的背景插画；文件不在时返回 404，页面自动回退到渐变底。"""
        if not ART_FILE.is_file():
            raise HTTPException(404, "背景插画不存在")
        return FileResponse(ART_FILE, headers={"Cache-Control": "max-age=3600"})

    # ------------------------------------------------------------------ 列表 / 状态
    @app.get("/api/items")
    def api_items(q: str = "", include_ignored: bool = True) -> dict:
        con = store.connect()
        try:
            cfg = settings(con)
            items = [item_json(r, Path(cfg["out_dir"]), con)
                     for r in store.list_items(con, include_ignored=include_ignored, q=q)]
            return {"items": items}
        finally:
            con.close()

    @app.get("/api/status")
    def api_status() -> dict:
        con = store.connect()
        try:
            cfg = settings(con)
            cert = proxy.cert_status()
            try:
                px = proxy.get_proxy()
            except Exception:
                px = {"enabled": False, "server": "", "override": ""}
            return {
                "counts": store.counts(con),
                "settings": cfg,
                "proxy": px,
                "cert": cert,
                "capture_running": port_open(cfg["capture_port"]),
                "active_downloads": manager.active,
                "ffmpeg": ffmpeg_path(),
                "ffmpeg_ok": bool(_which(ffmpeg_path())),
                "platform": sys.platform,
            }
        finally:
            con.close()

    # ------------------------------------------------------------------ 下载控制
    @app.post("/api/download")
    def api_download(payload: dict = Body(default={})) -> dict:
        con = store.connect()
        try:
            ids = [int(i) for i in payload.get("ids") or []]
            if not ids:
                ids = store.item_ids(con, only_idle=True, q=str(payload.get("q") or ""))
            accepted = manager.submit(ids)
            return {"accepted": accepted, "count": len(accepted)}
        finally:
            con.close()

    @app.post("/api/items/{item_id}/cancel")
    def api_cancel(item_id: int) -> dict:
        ok = manager.cancel(item_id)
        if not ok:
            con = store.connect()
            try:
                store.set_state(con, item_id, "canceled", error="已取消")
            finally:
                con.close()
        return {"ok": True}

    @app.post("/api/cancel_all")
    def api_cancel_all() -> dict:
        return {"canceled": manager.cancel_all()}

    # ------------------------------------------------------------------ 条目编辑
    @app.patch("/api/items/{item_id}")
    def api_patch(item_id: int, payload: dict = Body(default={})) -> dict:
        con = store.connect()
        try:
            if store.get_item(con, item_id) is None:
                raise HTTPException(404, "条目不存在")
            if "title" in payload:
                store.set_title(con, item_id, safe_name(str(payload["title"]), "video"))
            if "url" in payload and str(payload["url"]).strip():
                store.set_url(con, item_id, str(payload["url"]).strip())
                store.set_state(con, item_id, "idle", error="")
            if "ignored" in payload:
                store.set_ignored(con, item_id, bool(payload["ignored"]))
            if payload.get("retry"):
                store.set_state(con, item_id, "idle", error="")
            return {"ok": True}
        finally:
            con.close()

    @app.delete("/api/items/{item_id}")
    def api_delete(item_id: int, remove_file: bool = False) -> dict:
        con = store.connect()
        try:
            item = store.get_item(con, item_id)
            if item is None:
                raise HTTPException(404, "条目不存在")
            if remove_file and item["dl_path"]:
                p = Path(item["dl_path"])
                if p.exists() and p.is_file():
                    p.unlink()
            store.delete_item(con, item_id)
            return {"ok": True}
        finally:
            con.close()

    # ------------------------------------------------------------------ 手工添加
    @app.post("/api/cleanup/segments")
    def api_cleanup_segments(mode: str = "ignore") -> dict:
        """清理被误当成视频条目的 .ts 分片（mode=ignore 只忽略，delete 才真删）。"""
        con = store.connect()
        try:
            return {"affected": store.cleanup_segments(con, delete=mode == "delete"),
                    "mode": mode}
        finally:
            con.close()

    @app.post("/api/manual")
    def api_manual(payload: dict = Body(default={})) -> dict:
        raw = str(payload.get("url") or "").strip()
        title = str(payload.get("title") or "").strip()
        if not raw.startswith(("http://", "https://")):
            raise HTTPException(400, "请填写 http/https 开头的地址")
        headers = {"User-Agent": UA_FALLBACK}
        added: list[dict] = []
        con = store.connect()
        try:
            host = httpx.URL(raw).host
            headers = {**store.get_host_headers(con, host), **headers}
            kind = detect.classify(raw)
            text = ""
            if kind is None:  # 可能是接口地址，抓一下看里面有没有视频
                try:
                    r = httpx.get(raw, headers=headers, timeout=25, follow_redirects=True,
                                  trust_env=False, verify=ssl_context())
                    ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
                    kind = detect.classify(str(r.url), ct) or detect.classify(raw, ct)
                    if kind is None and len(r.content) < PARSE_BODY_LIMIT:
                        text = r.text
                except Exception as e:
                    raise HTTPException(400, f"取回失败：{e}")
            if kind:
                iid, created = store.upsert_media(con, url=raw, kind=kind, title=title, headers=headers)
                added.append({"id": iid, "url": raw, "created": created})
            for u, t in detect.urls_with_titles(text, base=raw):
                k = detect.classify(u)
                if not k:
                    continue
                iid, created = store.upsert_media(con, url=u, kind=k, title=title or (t or ""),
                                                  headers=headers)
                added.append({"id": iid, "url": u, "created": created})
            if not added:
                raise HTTPException(400, "没识别出视频地址：该地址不是媒体文件，返回内容里也没找到")
            return {"added": added}
        finally:
            con.close()

    # ------------------------------------------------------------------ 设置
    @app.get("/api/settings")
    def api_settings() -> dict:
        con = store.connect()
        try:
            return settings(con)
        finally:
            con.close()

    @app.post("/api/settings")
    def api_settings_set(payload: dict = Body(default={})) -> dict:
        con = store.connect()
        try:
            if "out_dir" in payload:
                p = Path(str(payload["out_dir"])).expanduser()
                p.mkdir(parents=True, exist_ok=True)
                store.set_setting(con, "out_dir", str(p))
            if "concurrency" in payload:
                store.set_setting(con, "concurrency", str(max(1, min(8, int(payload["concurrency"])))))
            cfg = settings(con)
        finally:
            con.close()
        manager.set_options(out_dir=Path(cfg["out_dir"]), concurrency=cfg["concurrency"])
        return cfg

    # ------------------------------------------------------------------ 代理 / 证书
    @app.post("/api/proxy")
    def api_proxy(payload: dict = Body(default={})) -> dict:
        con = store.connect()
        try:
            port = int(payload.get("port") or settings(con)["capture_port"])
            if payload.get("enable"):
                return proxy.enable_capture_proxy(con, port)
            return proxy.disable_capture_proxy(con)
        except Exception as e:
            raise HTTPException(400, str(e))
        finally:
            con.close()

    @app.post("/api/cert/install")
    def api_cert_install() -> dict:
        try:
            msg = proxy.cert_install()
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"message": msg, "cert": proxy.cert_status()}

    # ------------------------------------------------------------------ 文件
    @app.get("/api/reveal")
    def api_reveal(item_id: int | None = None) -> dict:
        con = store.connect()
        try:
            out_dir = Path(settings(con)["out_dir"])
            target = out_dir
            if item_id is not None:
                item = store.get_item(con, item_id)
                if item and item["dl_path"] and Path(item["dl_path"]).exists():
                    target = Path(item["dl_path"])
        finally:
            con.close()
        if sys.platform == "win32":
            if target.is_file():
                subprocess.Popen(["explorer", "/select,", str(target)])
            else:
                target.mkdir(parents=True, exist_ok=True)
                subprocess.Popen(["explorer", str(target)])
        return {"ok": True, "path": str(target)}

    @app.get("/files/{name}")
    def api_file(name: str):
        con = store.connect()
        try:
            out_dir = Path(settings(con)["out_dir"]).resolve()
        finally:
            con.close()
        target = (out_dir / name).resolve()
        if out_dir not in target.parents or not target.is_file():
            raise HTTPException(404, "文件不存在")
        return FileResponse(target)

    @app.get("/api/doctor")
    def api_doctor() -> dict:
        con = store.connect()
        try:
            cfg = settings(con)
            cert = proxy.cert_status()
            checks = [
                {"name": "ffmpeg", "ok": bool(_which(ffmpeg_path())), "detail": ffmpeg_path()},
                {"name": "mitmproxy CA 已生成", "ok": cert["exists"], "detail": cert["path"]},
                {"name": "CA 已装进系统根证书", "ok": cert["installed"], "detail": "点右侧按钮安装"},
                {"name": "抓包端口空闲或有服务", "ok": True,
                 "detail": f"{cfg['capture_port']} → " + ("已监听" if port_open(cfg["capture_port"]) else "未监听")},
            ]
            return {"checks": checks}
        finally:
            con.close()

    return app


def _which(exe: str) -> str | None:
    import shutil
    return shutil.which(exe)
