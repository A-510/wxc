# Change Design — anime-webui-redesign

实现面：`static/index.html`（FastAPI 直接返回的单页界面）+ `wxc/config.py` 的 `ART_FILE` 与
`wxc/webui.py` 的只读路由 `GET /art/background`。界面身份 = 项目 `DESIGN.md`
（sha256 `406c9ee7b4f90339f1c32e101c5aa24b93c68491a82ec38b2c3177316cc9bc75`），动效语言 =
`MOTION.md`（sha256 `1e3945b3779e3f62874fdb7cc8945d961fdeaf5daf9479edd9f02f986c3dc034`）。

## Requirements Map

| 需求（来自 `brief.md` / `grill.md`） | 设计后果 |
| --- | --- |
| 一眼看懂主线：装 CA 证书 → 开系统代理 → 微信里播几秒 → 回来下载 | 四张**数据绑定**的印刷号码牌，直接吃 `/api/status` 的 `cert.installed` / `proxy.enabled` / `counts.total` / `counts.done`，当前步换成洋红底并在副标题写下一步动作 |
| 用户提供的 3840×2160 二次元插画必须用上 | 首屏顶部**海报条**：`center top / cover` 整幅构图 + 洋红罩 + 墨色标题带；不使用玻璃压暗插画 |
| 中文界面、桌面端 1366–2560 为主 | 系统 CJK 栈、14px 起正文、全角标点、零字距；容器 `max-width: 1440px` 居中，≤820 收口 |
| 无构建步骤、无外部字体/CDN/依赖 | 单文件 HTML/CSS/JS；插画走本机只读路由 `/art/background`；零 `http(s)://` 外链 |
| 不动 `/api/*` 契约、DOM id/class、1.5s 轮询与全部功能按钮 | 换皮不换骨架：JS 只增号码牌绑定、状态配色通道、Esc 取消改名、`aria-*`，其余逐字保留 |
| 抓包列表为空时不能像坏了 | 空态写成下一步动作（「先在微信里播放网课，或手动导入地址。」），并保留半调网点底 |
| 批量下载时盯住进度 / 失败 / 重试 | 行底状态色（完成绿 / 失败粉）+ 进度条 + 状态文字三通道；失败文案不截断、写成可执行动作 |
| 破坏性动作要挡一下 | 清理 TS 分片条目沿用原生 `confirm()`（键盘可读屏可达、零依赖） |

## Evidence Adoption Matrix

| Source | Observed property | Adopt / reject | Product-specific reason | Target |
| --- | --- | --- | --- | --- |
| `direction-previews/poster-pop.png`（用户选定） | 米黄纸 + 2px 墨线 + 硬投影 + 半调网点 + 青/洋红双色 | 采纳全部材料工艺 | 用户在三候选中选择它；插画以完整构图出现，正文落在纸上不受插画像素影响 | `static/index.html` 的全部 panel/sheet 规则 |
| `direction-previews/index.html` 的 `.c3` 段 | 顶栏 / 海报条 / 号码牌 / 工具栏 / 纸张面板的纵向顺序与尺寸 | 采纳顺序与比例，行内间距按真实数据微调 | 预览是用同一份真实内容与状态渲染并被批准的 | 同上 |
| 现有 `static/index.html` | DOM id/class 词表、`/api/*` 调用、轮询、`--warn`/`--err` 等被 JS 引用的变量名 | 采纳（不换骨架） | 换骨架会引入回归；契约优先级高于配色 | 全部 id/class 与 `<script>` |
| `design-pipeline/references/cjk-typography.md` | 系统 CJK 栈、14px 起、行高 1.5–1.75、零字距、全角标点 | 采纳 | Windows 目标机落到微软雅黑，无需下载字体 | `Typography` 段与 `--ui` 变量 |
| `MOTION.md` | minimal posture、`response.spring-settle`、`transform.orbit` | 采纳两个原语与其 reduced-motion 回退 | 需显式终止的循环动效只允许一个 | `.spin` / `.bar > i` / `button` |
| 半调网点、硬投影 | 公共印刷技法 | 采纳几何规律（内联 `radial-gradient` 重绘） | 与印刷海报语言一致，且零字节外部请求 | `.empty`、`html/body` 底 |

## Product Design Output

- 项目 `DESIGN.md`（sha256 见上）是**唯一**视觉真相：色板与实测对比度、字号、栅格、组件状态词表、
  Do/Don't、动效引用、素材许可与替换点。
- 变更实现落在 `static/index.html`：单文件、无构建，`DESIGN.md` 的 token 值逐条落到 CSS 变量，
  并把旧变量名（`--bg --panel --line --fg --muted --accent --ok --warn --err`）**映射**到新色板，
  因为页面内 JS 的模板字符串直接引用 `var(--warn)` / `var(--err)`。
- 组件映射：`pill`（状态胶囊）、`steps/.step`（四张号码牌）、`tools`（工具栏 ×2）、`panel`（纸张面板）、
  `tag`/`.q`（番札）、`bar`/`.spin`（进度）、`ops`（操作组）、`empty`（空态）、`.err-text`（失败文案）。
- 唯一新增后端面：只读路由 `GET /art/background`（`ART_FILE`，可用 `WXC_ART` 覆盖），
  不改任何 `/api/*` 语义。

## Spec Reconciliation

本变更**没有外部视觉参考**：`design-synthesis.json` 的 `inputs.mode = requirements-only`、
`inputs.references = []`，没有 `reference-evidence.json` / `reference.md`，
`website-cloning.json` 不存在。因此 `reconciliation check` 的 `applicable` 应为 `no`
（详见 `qa.md` 的 Spec Reconciliation 段）。

Graybox: 不适用（无可测量的参考栅格）
Reconciled: 2026-10-16T12:45:00Z

| Value | Specified | Implemented | Cause |
| --- | --- | --- | --- |

唯一按实测修正过的规范值（同一变更内、非参考对账）记录在 `qa.md` 的 Interface Discipline 段：
`DESIGN.md` 初稿写「行高约 34px」，实测为 41–55px（类型列带清晰度小字时更高），已按观测值改文档。
