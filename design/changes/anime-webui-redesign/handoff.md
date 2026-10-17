# Handoff

<!-- DESIGN-PIPELINE:DESIGN-SYNTHESIS:START -->
## Requirements-Driven DESIGN.md Synthesis

- Manifest: `design/changes/anime-webui-redesign/design-synthesis.json`
- Status: ready-to-implement
- Stage: implementation
- Product design output: `DESIGN.md`
- Project motion foundation: `MOTION.md`
- Change design: `design/changes/anime-webui-redesign/design.md`
- Input mode: requirements-only
- Scope: 34/60 (fit)
- Next: Implement from DESIGN.md, change design.md, and tasks.md; then run normal design-pipeline QA.

Template and reference inputs are attributed evidence only. Product requirements and recorded
decisions determine the synthesized design.
<!-- DESIGN-PIPELINE:DESIGN-SYNTHESIS:END -->

## 交付状态（2026-10-16）

- 变更：`anime-webui-redesign`，`state.json` = `complete` / `phase: archive`，`events.jsonl` 与状态一致（seq 1–10）。
- 选的视觉方向：`poster-pop`（用户在 `direction-previews/index.html` 的三张同内容候选中选定；
  选择理由见 `direction-preview.json` 的 `decision.rationale`，落选理由见 `directions.md`）。
- 实现面：`static/index.html`（整页重写为海报波普，保留全部 DOM id/class 与 `/api/*` 契约）、
  `wxc/config.py`（`ART_FILE`，可用 `WXC_ART` 覆盖）、`wxc/webui.py`（只读路由 `GET /art/background`）。
- 界面身份：`DESIGN.md`（sha256 `406c9ee7b4f90339f1c32e101c5aa24b93c68491a82ec38b2c3177316cc9bc75`）。
- 动效语言：`MOTION.md`（sha256 `1e3945b3779e3f62874fdb7cc8945d961fdeaf5daf9479edd9f02f986c3dc034`）。
- 验证：`qa.md`（六档视口 + 真实数据 + 全状态覆盖 + 生命周期 API smoke + reduced-motion 计算样式）；
  截图在 `qa/screenshots/`。验证声明 = `unverified`（本变更无外部视觉参考可测量）。
- 门结果：`doctor` ready；`foundation check --kind all` ready；`direction check`（preview / selection）
  ready；`reconciliation check` ready（`applicable: false`）；`patterns audit` valid。
- 怎么用：`scripts\start.bat`（或 `.venv\Scripts\python.exe -m wxc.cli ui`）→ 浏览器开
  `http://127.0.0.1:8900`；四张号码牌会按 `/api/status` 自动点亮当前步。
- 未做（另开变更）：移动优先的触屏目标放大、读屏 `aria-live` 播报、深色变体。
