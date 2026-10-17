#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""概念预览构建器（概念阶段工具，不进产品）。

把 static/index.html 原样读入，注入「出场动效 + 固定内容夹具 + 关键帧冻结钩子」，
输出 design/changes/arknights-entrance-motion/preview/c<N>.html。
产品代码一行不改；关键帧因此是真实页面在真实入场中的样子。

用法：
  python tools/preview.py            # 生成 c1/c2/c3 预览页
"""
from __future__ import annotations

import argparse
import pathlib
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[4]          # 仓库根
HERE = pathlib.Path(__file__).resolve().parents[1]          # design/changes/arknights-entrance-motion
PAGE = ROOT / "static" / "index.html"
ART = ROOT / "背景.jpg"
OUT = HERE / "preview"
CONCEPTS = ("c1", "c2", "c3")

# 海报条素材地址：默认指向本机文件（file:// 预览用）；经 http 预览时传 --art "/<encoded>"
ART_URL = "file:///" + urllib.parse.quote(ART.as_posix())

SKIP_AND_FREEZE = """
<script>
/* 入场收尾 + 关键帧钩子。
   任意输入立即收敛到终态；否则到入场时长后也摘掉 `entering`——
   摘掉的原因见 c3.css 顶部：页面每 1500ms 重写 #rows，挂在 tbody tr 上的入场动画会被轮询反复重启。 */
(function () {
  var html = document.documentElement;
  var t = new URLSearchParams(location.search).get('t');
  var done = false;
  function settle(user) {
    if (done) return;
    done = true;
    html.classList.remove('entering');
    /* 只有用户打断时才用 wxc-skip 把整页直接压到终态；
       自然播完时各动画自己的 fill 已到终态，不额外冻结页面上其它 CSS。 */
    if (user) html.classList.add('wxc-skip');
  }
  if (t == null) {
    ['keydown', 'pointerdown', 'touchstart', 'wheel'].forEach(function (k) {
      addEventListener(k, function () { settle(true); }, { passive: true });
    });
    setTimeout(function () { settle(false); }, __ENTRANCE_MS__);
  } else {
    setTimeout(function () {
      document.getAnimations().forEach(function (a) { a.pause(); a.currentTime = Number(t); });
      html.setAttribute('data-frozen', t);
    }, 120);
  }
})();
</script>
</body>
"""


# 入场时长（ms）：settle 用；与 concepts/c<N>.css 里的时间线一致
ENTRANCE_MS = {"c1": 1360, "c2": 1340, "c3": 900}


def build(cid: str) -> pathlib.Path:
    html = PAGE.read_text(encoding="utf-8")

    art_url = ART_URL
    css = "\n".join([
        (HERE / "concepts" / "shared.css").read_text(encoding="utf-8"),
        (HERE / "concepts" / f"{cid}.css").read_text(encoding="utf-8"),
        f"/* 预览专用：把 /art/background 指向本机素材（产品里由 FastAPI 只读路由提供） */\n"
        f".poster{{background-image:url(\"{art_url}\")}}",
    ])
    fixture = (HERE / "concepts" / "fixture.js").read_text(encoding="utf-8")
    gate_file = HERE / "concepts" / f"{cid}.gate.html"
    gate = gate_file.read_text(encoding="utf-8") if gate_file.exists() else ""

    html = html.replace('<html lang="zh-CN">', f'<html lang="zh-CN" class="{cid} entering">', 1)
    html = html.replace(
        "</head>",
        f"<style>\n{css}\n</style>\n</head>",
        1,
    )
    html = html.replace(
        '<div class="wrap">',
        f'<div class="wrap">\n{gate}',
        1,
    )
    html = html.replace(
        "<script>\nconst $ = s => document.querySelector(s);",
        f"<script>\n{fixture}\n</script>\n<script>\nconst $ = s => document.querySelector(s);",
        1,
    )
    html = html.replace("</body>", SKIP_AND_FREEZE.replace("__ENTRANCE_MS__", str(ENTRANCE_MS[cid])), 1)

    for marker in (f'class="{cid} entering"', "wxc-skip", "getAnimations",
                   f"settle(false); }}, {ENTRANCE_MS[cid]})"):
        assert marker in html, f"{cid}: 注入失败（缺少 {marker}）"

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{cid}.html"
    target.write_text(html, encoding="utf-8")
    return target


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--art", default=None,
                    help='海报条素材 URL；经 http 预览时传 "/<percent-encoded 背景.jpg>"')
    args = ap.parse_args()
    if args.art:
        ART_URL = args.art
    for cid in CONCEPTS:
        print(build(cid))
