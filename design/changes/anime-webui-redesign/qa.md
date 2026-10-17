# QA — anime-webui-redesign

实现面：`static/index.html`（单页界面）、`wxc/config.py`（`ART_FILE`）、`wxc/webui.py`（只读路由 `GET /art/background`）。
证据目录：`design/changes/anime-webui-redesign/qa/screenshots/`、`direction-previews/`。

## Self-Check

- Command: `node design-pipeline/scripts/designer-pipeline.cjs doctor --project-root .`
- Result: `ready`（node 24.9.0，`nodeSupported: true`，`missing: []`；mengto / shadcnio / prism 快照校验 `ready`）
- Missing required skills: 无（本变更不需要额外的 companion skill）
- Missing enhancement skills: 无
- Missing optional skills: 无
- Fallbacks used: 无（`interface-discipline.md` 的内置快照即为回退源，本次未触发）

## Static Checks

- Lint: 不适用（本仓库无 lint 配置；单文件 HTML/CSS/JS，无构建步骤）
- Typecheck: 不适用（无 TS/类型检查器）
- Tests: 不适用（仓库无测试套件）；本变更以**真实服务 + 真实数据库**的运行验证代替（见 Browser / manual QA）
- Build: 不适用（FastAPI 直接返回 `static/index.html`，无构建）

## Control Plane Checks

- `designer-pipeline doctor`: `ready`（exit 0）
- `designer-pipeline status`: `implementing` / `phase: implementation` → 迁移后 `stateSchema: design-pipeline.state.v2`，`migrationRequired: false`
- State schema / phase registry: `design-pipeline.state.v2` / `design-pipeline.phases.v2`
- State SHA-256 before mutation: `0fb32ca14af439ceb031e0a241fa3b872bfcbccb6b57588d9991773e98aa88ce`（v1）
- State/event consistency: `event-ahead` → `change repair` → `consistent`
- Migration or repair performed? evidence: `change migrate --write --expected-sha256 …` → `migrated`（`5f2e30cc…`）；`events.jsonl` 由 v1 事件逐条改写为 `design-pipeline.event.v2`（5 条，seq 1–5）；`change repair` → `repaired`（`previousConsistency: event-ahead`）
- Unknown future schema/registry fail-closed check: 未触发（本变更 schema 均在注册表内；`fail` 路径未走到）
- CLI exit code recorded as returned, not as assumed:
  `doctor` 0 / `status` 0 / `change migrate` 0 / `change repair` 0 / `foundation check --kind all` 0 /
  `direction check`（preview 与 selection）0 / `reconciliation check` 0 / `next` 0 / `decide` 0
- Any kernel failure reported by its own code rather than as success: 无。过程中出现过一次
  `LOCKED`（遗留 `state.json.lock`，exit 1，非内核失败）：按 `change repair --unlock --minimum-age-ms 0`
  记录的路径清除后重试成功；另有一次 `EXPECTED_HASH_REQUIRED`（exit 1），补 `--expected-sha256` 后成功。

## Browser / Visual Checks

统一夹具 `direction-previews/content-fixture.json` 的同构状态（真实条目字段 + 全部状态），视口逐档截图：

| 视口 | 截图 | 实测（同一夹具） |
| --- | --- | --- |
| 375×812 | `qa/screenshots/ui-states-375x812.png` | 横向溢出 0 · 文本重叠 0 · 裁切文本 0 · 表格同屏 6 行 · 海报条 130px · 整页滚动（表格给 56vh） |
| 768×1024 | `qa/screenshots/ui-states-768x1024.png` | 横向溢出 0 · 重叠 0 · 裁切 0 · 表格同屏 8 行 · 海报条 140px |
| 820×700 | `qa/screenshots/ui-states-820x700.png` | 横向溢出 0 · 表格横向滚动兜底 · 同屏 3 行 · 号码牌仍一行 4 张 |
| 900×800 | `qa/screenshots/ui-states-760x700.png` 档同族 | 大小列隐藏 · 同屏 6 行（760×700 档） |
| 1024×768 | `qa/screenshots/ui-states-1024x768.png` | 主机列隐藏 · 同屏 5 行 |
| 1280×800 | `qa/screenshots/ui-states-1280x800.png` | 主机/大小列同屏可见 · 同屏 5 行 |
| 1440×900（基准） | `qa/screenshots/ui-states-1440x900.png` | 7 列齐 · 同屏 6 行 · 海报条 171px · 页高不滚（`body overflow: hidden`） |
| 1920×1080 | `qa/screenshots/ui-states-1920x1080.png` | 同屏 9 行 · 纸张居中留白 |
| 真实数据（无夹具） | `qa/screenshots/ui-live-1440x900.png` | 真实 8 条（完成 2）· 号码牌 `1 done / 2 cur(关闭) / 3 done / 4 done` |
| 减弱动效 | `qa/screenshots/ui-reduced-motion.png` | 弧段静止，文字仍报「下载中 · 12.4 MB」 |
| 进度/旋转弧特写 | `qa/screenshots/ui-bars.png` | 确定条 100×8px（填充 18.1×6px）· 旋转弧 14×14px |

Check:

- No overlapping text or controls: 实测文本/控件包围盒两两重叠数 = 0（375 / 768 / 820 / 1440 / 1920 五档）
- No clipped labels: 实测 `scrollWidth > clientWidth` 的文本节点数 = 0（同上五档）
- Primary workflow is visible without explanation text: 首屏四张号码牌直接写「安装 CA 证书 / 开启系统代理 / 微信里播放网课 / 下载到本地」，当前步洋红底并在副标题写下一步动作
- Empty, loading, error, disabled, hover, focus, and active states exist where relevant: 空态（半调网点 + 下一步动作）、失败行（粉底 + 红字 + 不截断）、排队中、已取消、已忽略过滤、下载中（有/无比例）、TS 分片「下载整节课」、未知大小 `—`、`:hover`（色变）、`:focus-visible`（3px 外描边）、`:active`（下沉 1.5px + 撤掉硬投影）、禁用（`button:disabled`）
- Palette is not one-note: 米黄纸 + 墨 + 青 + 洋红 + 绿/黄/红三状态色，另有 4 种行底
- Typography fits the surface and density: 13.5px 正文/表格、12px 表头、等宽数字、单行省略 + `title` 全量、错误文案不截断

## Plain-Language Checks

- First useful sentence states the exact consequence or available action: 空态「先在微信里播放网课，或手动导入地址。」；步骤 3 未达时副标题「在微信 PC 端播放几秒」；页脚「代理开着会一直抓包，**下完记得点「关闭系统代理」**」
- Actor, event, scope/count, uncertainty, time/limit, exclusions, and unchanged state preserved: 清理分片确认写清范围（「把列表里所有「TS 片」条目删掉？它们只是视频分片，真正要下的是 HLS 条目。」），失败文案写清恢复动作（「回微信重新播放该课时，刷新后重下。」）
- Title names the smallest accurate problem or outcome: `wxc · 网课下载器`；页头胶囊写「名称：状态」而非泛泛的「正常/异常」
- Buttons and recovery guidance correspond to actions the interface actually provides: 全部按钮与 `/api/*` 一一对应；无「重试全部」等不存在的能力
- Internal causes and jargon removed unless they change the reader's decision: 失败行不写堆栈，技术细节（URL）放 `title`
- High-impact old/proposed comparison and selected version: 旧版「深色灰板 + 单一说明卡」→ 新版「海报条 + 数据绑定号码牌 + 纸张表格」，差异与理由见 `directions.md`
- Directness introduced no broader or stronger claim: 页脚只说「代理开着会一直抓包」，未声称「下载更快/更安全」

## Direction Preview Checks

- `direction-preview.json` applicability: **required**；reason: `visual-redesign`
- `direction check --stage preview` status and exit code: `ready`，exit 0（判据：3 候选、同视口 1440×900、同夹具哈希、13 项状态覆盖、每候选一张已哈希截图）
- Candidate IDs, shared viewport, content fixture hash, and state coverage: `sky-glass` / `dusk-ink` / `poster-pop`；1440×900；夹具 `80d6534a…`；13 项状态覆盖
- Pairwise axis differences; luminance or era difference retained: 明度 light / dark / 亮纸+重墨；年代 2020s 玻璃 / 2010s-2020s 深色控制台 / 1970s-1990s 复古印刷
- `index.html` and one screenshot per candidate exist with matching hashes: 3 张 PNG 与 `direction-preview.json` 内的 sha256 一致（`direction check` 逐张复核通过）
- Preview shell and candidates usable at desktop and narrow widths: 预览壳在 1440/1000px 下均可读（比较外壳 1000px 居中、候选 60% 缩放）
- Selection source: **user**（三张同内容截图中由用户选定 `poster-pop`）
- `direction check --stage selection` status and selected-direction rationale: `ready`，exit 0；理由写在 `direction-preview.json` 的 `decision.rationale`（产品适配 + 已知风险）
- `directions.md` was written only after the selection gate passed: 是（selection 门通过后写入）

## CJK Typography Checks

- Resolved system/project font stack and real available weights: `system-ui, -apple-system, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif`；Windows 目标机落到微软雅黑，实际只有 400/600（无 500，不假装）
- Body size, line height, measure, tracking, and overflow behavior: 正文 14px/1.6、表格 13.5px/1.5、`letter-spacing: 0`、`line-break: strict`、`word-break: normal`、标题单行省略、错误文案 `overflow-wrap: anywhere`
- Full-width punctuation and mixed-script convention checked with real strings: 真实标题「高等数学（上）· 第3章 第2节 导数的定义」、错误文案「链接带时效签名已失效：回微信重新播放该课时，刷新后重下。」全角标点无两侧空格，中数之间不手工加空格
- No synthesized italic CJK or negative CJK body tracking: 未使用斜体；无负字距（`letter-spacing: 0`）
- Decorative font scope, subset glyphs, WOFF2/hosted bytes, license, and fallback: 不适用（不使用装饰字体、不含 `@font-face`、零字节字体下载）
- Font-loaded and font-failure captures: 不适用（系统栈，无加载过程）；改字体栈即改回退，无 FOUT 风险
- Desktop/mobile, light/dark, and 200% zoom evidence: 桌面 375→1920 六档截图；无深色变体（海报波普为亮纸单一主题，明暗由系统 CSS 决定，不提供切换）；200% 缩放实测横向溢出 0、元素纵向序不变、无重叠

## Contextual Anti-Slop Review

- Evidence file: `DESIGN.md` 的 `Anti-template Decisions` 段 + `design/changes/anime-webui-redesign/directions.md`
- Command: 不适用（本技能包未提供 anti-slop CLI；`evaluateAntiSlop` 未暴露为命令）
- Report: 人工对照 `references/anti-slop-review.md` 的四项（cohesion / product-grounded signature / specificity / template-pattern density）逐项检查
- Status: **pass**
- Hard blockers: 无（内容可见、控件可操作、可读性达标、响应式完整、reduced-motion 有效、参考来源已记录）
- Contextual warnings: 顶部海报条占首屏高度（已知取舍，用户选定方向时已明示）；纸感在长时间密集扫读下略累
- Accepted contextual decisions: 硬投影与番札旋转属于印刷语言而非「AI 语法」，保留
- Preference information reviewed: 无（用户未提供审美偏好清单）
- `Anti-template Decisions` recorded in `design.md` or project `DESIGN.md`: 两处都有（刻意避免 / 保留的通用模式 / 产品特定理由 / 冲突优先级）
- Upstream rubric source/hash reviewed: `references/anti-slop-rubric.json`（随技能包快照）

## Motion Foundation Checks

- Project `MOTION.md` exists: 是
- `check-motion-foundation.cjs` status: `ready`（`foundation check --kind all` 内，exit 0）
- Normalized foundation model matches `motion-foundation.schema.json`: 是
- Foundation schema: `design-pipeline.motion-foundation.v0.1`
- Foundation SHA-256: `1e3945b3779e3f62874fdb7cc8945d961fdeaf5daf9479edd9f02f986c3dc034`
- Foundation posture: `minimal`
- Required headings use one language consistently: 是（英文标题 + 中文内容，全篇一致）
- Primitive registry schema: `design-pipeline.motion-primitives.v1`
- Selected primitive IDs resolve: `response.spring-settle`、`transform.orbit`（均在注册表内）
- Missing or orphan primitive IDs: 无
- Change `motion.md` foundation hash matches: 是（同 `1e3945b3…`）
- Runtime capability is supported / degraded / unsupported: CSS transitions/keyframes = supported；WAAPI = degraded（未使用）；Anime.js / GSAP / Canvas / WebGL / 滤镜 = unsupported（未引入）
- Degradation is documented: 是（`MOTION.md` 的 `Runtime Policy` 与 `Reduced Motion` 两表）
- Procedural equations are declarative: 不适用（generator count 0，无程序化路径）
- Procedural seeds and sampling are deterministic: 不适用
- Source provenance is measured / instrumented / inferred / authored: **authored**（本变更无可测量的参考运动；`MOTION.md` 的来源决策保持概念级采纳）
- External adopted and rejected properties recorded: 是（`MOTION.md` 的 `Source Decisions`）

## Change Motion Checks

- `motion.md` required? yes/no: **yes**（状态切换、进度推进、hover/focus 反馈、不确定指示）
- `motion.md` created? yes/no: **yes**（`design/changes/anime-webui-redesign/motion.md`）
- Foundation link and hash recorded: 是（`1e3945b3…`）
- Selected primitive IDs recorded: 是（两个）
- Scene, stage, camera, and layer ownership: 不适用（无场景运行时）
- Track and timeline IDs: 不适用（无时间轴编排）
- State machine and interruption behavior: 状态替换即终态；新状态直接接管旧过渡，不留排队（CSS 属性过渡天然满足）
- Procedural generators and parameter bounds: 无
- Runtime adapter bindings: 纯 CSS（无库、无构建）
- Implementation matches `motion.md`: 是（120ms 颜色、240ms 线性宽度、900ms 顺时针弧、按下 1.5px 离散下沉）
- Library choice matches `motion.md`: 是（无第三方库）
- `prefers-reduced-motion`: 实测 `animation-name: none` / `transition-property: none`（弧段静止、宽度瞬到、颜色瞬换），关闭后恢复 `orbit` / `width` / `background-color`
- Fast repeated clicks: 按钮无排队动效（离散状态替换），连点只重复同一状态；进度过渡被新值直接接管
- Route/page transition interruption: 不适用（单页、无路由）
- Scroll animation performance: 不适用（无滚动联动；表格内滚动不触发动效）
- Focus and hover motion: 焦点环无过渡（立即出现）；hover 仅颜色 120ms，不触发布局
- Animation purpose: 只表达「机器正在做事」与「状态刚改变」两类事实
- Duration/easing: 120ms（颜色）/ 240ms `linear`（进度）/ 900ms `linear`（弧）/ 离散（按下）
- Timeline/stagger behavior: 无
- Cleanup on unmount: 无生命周期组件；`.spin` 随状态节点移除即终止，setInterval 在页面卸载时随文档销毁
- Evidence: screenshot / video / trace / manual notes: 截图 `qa/screenshots/ui-reduced-motion.png`、`ui-bars.png` + 计算样式实测（见上）

## Reference And Spatial Routing

- `reference.md` source inventory and provenance: **不适用**（本变更无外部视觉参考：`design-synthesis.json` 的 `inputs.mode = requirements-only`、`inputs.references = []`，无 `reference-evidence.json` / `reference.md` / `website-cloning.json`）
- Source availability: 不适用
- Pending reason, requested from, and unlock action reported to the user: 不适用
- Observable spatial evidence for and against 3D: 不适用（无 3D；无 canvas/WebGL）
- 其余各项（per-region 结构表、uniformity、composition、schema era、route、fidelity invariants、required artifacts、`reference check` 状态、verification claim 推导）: 不适用
- Verification claim（独立一行）: **unverified**
- 理由：本变更没有 `reconstruction.json` / `reference-evidence.json` 可跑 `reconstruction check --stage final`，因此按契约记 `unverified`（不是从某个 `ready` 阶段推断出来的）。本文件与 `design.md`、最终答复均不把本变更描述为 verified / exact / identical / 1:1 / pixel-perfect / faithful / complete。

## Graybox Gate

- 不适用：本变更没有 `reference-evidence.json`（无可测量的参考栅格，无 `graybox.png`）
- `reconstruction check --stage graybox`: 不适用（无可运行的 reconstruction 文档）

## Spec Reconciliation

- `Spec Reconciliation` section present in `design.md`: 是（第 44 行起）
- Cited graybox capture exists on disk: 不适用 → 门以 `applicable: false` + 警告 `reconciliation-capture-missing` 记录，非阻断
- Reconciled timestamp: `2026-10-16T12:45:00Z`
- Rows: specified value / implemented value / observed cause: 空表（`specDrift.changedValues = 0`，空表为合法结果）
- Every `Cause` describes an observation, not an intention: 不适用（空表）；文内另有一条同变更内的实测修正记录（行高 34px → 实测 41–55px）
- Empty table is a valid result; absent section is `blocked`: 空表已确认合法
- `reconciliation check` 单独运行的 status: `ready`（`applicable: false`，`warnings: [reconciliation-capture-missing]`，exit 0）；`reference check` 未单独运行（无参考可查）
- `reference check` exit code: 不适用（本变更无参考）；`reconciliation check` exit 0
- `referenceSignals` reported by the gate: `[]`
- `applicable`: **no**（`design-synthesis.json` 判定非参考驱动），因此未填充的 stub 只作警告
- Manifest present and readable: `design-synthesis.json` 可读，`inputs.mode = requirements-only`、`inputs.references = []`，两者一致（无 `reconciliation-manifest-*` 故障）

## Scene And Runtime Checks

- 不适用：无 `scene.json`，无 canvas/WebGL/WebGPU、无相机、无渲染循环、无持久空间状态。

## Evidence Receipt Checks

- 不适用（未使用 evidence adapter / receipt；证据为浏览器实测截图与计算样式读数，路径见上）

## Motion And Component Evidence

- `verify motion` result and receipt: 不适用（未生成 receipt；本变更动效为纯 CSS，逐条落到 `motion.md` 并实测计算样式）
- Deterministic capture ID / seed: 无（无程序化生成器）
- Duration tolerance and long-frame budget: 单位过渡 120/240/900ms，无长帧风险（仅 transform/opacity/width，无逐帧脚本）
- Interruption/reversal behavior: 新状态直接接管（CSS 属性过渡），弧段随节点移除终止
- Reduced-motion substitute: 弧段静止 + 文字照常更新（实测）
- `verify components` matrix: 不适用（无组件库）
- Hover / focus / pressed / disabled / loading / empty / error states: 全部覆盖（见 Browser / Visual Checks）
- Keyboard / touch / mobile / desktop coverage: 键盘（Tab 顺序、`:focus-visible`、Enter/Esc 改名、原生 confirm）、触屏未专测（桌面优先）、移动宽度 375 已截图

## Interoperability And Benchmark

- Design tokens schema/provenance: 无独立 tokens 文件；token 落在 `static/index.html` 的 `:root` 并在 `DESIGN.md` 的 `Colors` 段逐条给出值与实测对比度（零外部依赖，无构建步骤）。`tokens check` 需要 `--artifact <tokens 文件>`，本仓库不存在该工件 → 不适用（exit 1，`OPTION_REQUIRED`）
- UI IR schema and catalog component IDs: 不适用（单文件页面，无组件目录）。`ui-ir check` 需要 `--artifact <ui-ir 文件>` → 不适用（exit 1，`OPTION_REQUIRED`）
- Design-to-code source/token mappings: `DESIGN.md` → CSS 变量逐条映射（含旧变量名保留/映射理由）
- Pattern catalog audit/search evidence: `patterns audit` → `status: valid`，`total: 7`，coverage = `data-table` / `dialog` / `combobox`（generic-workflow）+ `button` / `tabs` / `dialogue-box` / `hud`（native），无 unsupported、无 out-of-scope。job plan 里的 `design-system` 检索为 secondary，`admission: reference-only`，未成为第二主路径
- Benchmark manifest and measurements: 不适用
- All required dimensions represented: 不适用
- Required failures/unknowns preserved (not averaged away): 不适用
- Local feedback observation recorded when reusable: 无（本次无跨项目可复用的适配规则；未提 `adaptation propose`）

## Adapter Governance

- 不适用（本变更不安装/引入任何 adapter、库或图形目录路由）

## Accessibility Checks

- Keyboard tab order: 顶栏 → 号码牌（非交互）→ 工具栏 → 导入/搜索 → 面板工具条 → 表格（勾选 → 标题改名 → 操作按钮），与视觉顺序一致
- Focus ring: `:focus-visible` 3px `--cyan-deep` 外描边 + `outline-offset: 1px`，无过渡、立即出现；输入框额外换边框色
- ARIA labels / names: 勾选框 `aria-label="选择：<标题>"`、搜索框 `aria-label`、顶栏胶囊为文本内容、当前步 `aria-current="step"`、进度 `role="progressbar"` + `aria-valuemin/max/now`、旋转弧 `aria-hidden="true"`
- Contrast: 正文 16.6:1、次级 10.1:1、说明 6.4:1、完成绿 7.3:1、失败红 6.8:1、番札 6.5:1、主按钮（纸色字/青底）4.6:1 —— 全部 ≥ 4.5:1
- Touch targets: 主要控件高 30px、行内按钮高 ~26px（桌面优先；375 档未做触屏目标放大）
- Form errors: 无表单校验错误面；失败文案即恢复指引，不截断
- Screen reader announcements where relevant: 状态面板与计数为文本；轮询更新不打断读屏（无 `aria-live`，有意保持安静）

## Engineering Fit

- Uses existing components/tokens: 复用既有 DOM 骨架、id/class、`/api/*`、1.5s 轮询；新增仅只读路由 `/art/background`
- Avoids unnecessary dependencies: 零新增依赖、零外部字体/CDN/框架/构建
- Does not create parallel OpenSpec/GBrain source of truth: 是（OpenSpec/GBrain 均未检测到）
- React/Next conventions checked when applicable: 不适用
- Animation library choice justified: 无库；`MOTION.md` 已把 Anime.js / GSAP 记为 unsupported

## Agent-Readable State

- `state.json` exists: 是
- `state.json.status`: `implementing` → `verifying` → `complete`（随 advance 推进；v2 schema）
- `state.json.phase`: `implementation` → `gate-review` → `verification` → `release-readiness` → `archive`
- `state.json.nextActions` current: 是（随每次 advance 更新）
- `events.jsonl` exists: 是（v2，seq 连续）
- Last event matches current phase: 是（`change repair` 后 `consistency: consistent`）
- `handoff.md` exists: 是
- `handoff.md` agrees with `state.json`: 是（都指向「实现 → QA → 交付」这条链）
- Evidence paths in state/events exist: 是（`qa/screenshots/`、`direction-previews/`、`DESIGN.md`、`MOTION.md`）
- Another agent can resume from these files without conversation history: 是

## Package And Release Reproducibility

- 不适用（未发布 design-pipeline 本身）

## Interface Discipline

- Mode: **full**（六域：accessibility / layout / typography / color / UI polish / writing）
- Diff scope: `static/index.html`（整页换皮 + 状态三通道 + a11y 增强）、`wxc/config.py`（新增 `ART_FILE`）、`wxc/webui.py`（新增只读路由）
- Consumer expansion: 页面内 JS 模板字符串（引用 `var(--warn)` / `var(--err)`，故旧变量名必须保留）、浏览器作为唯一 `/api/*` 消费方、`GET /art/background` 的 CSS 消费方
- Removed-signal inspection: 旧 `--bg/--panel/--line/--fg/--muted/--accent/--ok/--warn/--err` **未删**（映射到新色板）；`@keyframes slide`（`translateX` 不确定条）被 `@keyframes orbit` 取代；`.indet` 被 `.spin` 取代；旧说明卡 `.hint` 被四张号码牌与页脚取代；旧的 `tr.done/tr.error` 底色语义保留但换色
- Findings（每条带状态与严重度）：

| # | Finding | Domain | Status | Severity | Repair |
| --- | --- | --- | --- | --- | --- |
| 1 | 顶栏 `.bar` 与进度条 `.bar` 类名冲突，进度条被撑成 16px、填充高度塌到 0，顶栏高度被压 | UI polish / layout | **Introduced** | 高（功能性外观缺陷） | 顶栏改名 `.topbar`；实测进度条恢复 8px、填充 6px、顶栏 38.4px |
| 2 | 820–760 宽度下操作列换行导致行高 175px、同屏仅 2 行 | layout / responsive | **Introduced** | 中 | ≤820 操作列 `flex-wrap: nowrap` + 表格 `min-width: 860px` 横向滚动兜底；行高回到 55.4px |
| 3 | 375 宽度下面板被压成 0 高度，表格不可达 | layout / responsive | **Introduced** | 高（内容不可达） | ≤760 顶栏换行 + 整页滚动 + 表格固定 `56vh`；实测同屏 6 行、无裁切 |
| 4 | 长标题只有 URL 在 `title` 里，看不到全名 | writing / accessibility | **Introduced** | 低 | `title` 改为「全名 — 地址」 |
| 5 | `DESIGN.md` 初稿写「行高约 34px」，与实测 41–55px 不符 | writing（文档准确性） | **Introduced** | 低 | 按实测改文档并写明同屏行数 |
| 6 | 旧版 `.err-text` 用 `word-break: break-all`，中文错误文案会被硬断 | typography | **Pre-existing** | 低 | 本次改为 `overflow-wrap: anywhere`（在本次换皮范围内顺带修掉） |
| 7 | 表格行 hover 只靠颜色，灰度下不易区分 | color / accessibility | **Pre-existing** | 低 | 未修（行状态另有文字与形状通道，非阻断）；保留为已知项 |
| 8 | 触屏目标未放大（行内按钮 ~26px） | accessibility | **Pre-existing** | 低 | 未修（桌面优先、移动端为兜底；如需移动优先需另开变更） |

- Remaining pre-existing items: #7、#8（均非阻断，已记录）
- Final verdict: **pass**（阻断项 0；非阻断 2 项）

## Scorecard

| Dimension | Score | Notes |
| --- | ---: | --- |
| Visual taste | 5 | 插画以完整构图成为海报，印刷材料语言统一；无渐变光球/玻璃/emoji 等模板语法 |
| UX clarity | 5 | 四步号码牌吃真实状态并给下一步动作；失败文案即可执行动作；破坏性动作二次确认 |
| Accessibility | 4 | 对比度全部 ≥4.5:1、焦点环即时、ARIA 完整；扣分在触屏目标与无 `aria-live`（有意安静） |
| Responsiveness | 4 | 375→1920 六档无溢出/重叠/裁切；扣分在 820 档需要横向滚动、375 档顶栏变高 |
| Motion quality | 5 | 只有一类循环动效且表达「机器正在做事」，中断/回退明确，reduced-motion 实测生效 |
| Engineering fit | 5 | 零新增依赖、零构建、契约不变、只加一条只读路由 |
| Performance risk | 5 | 单文件、静态位图背景、纯 CSS 动效，无逐帧脚本；轮询 1.5s 与旧版一致 |

## Decision Audit

| Decision | Principle | Result | Risk |
| --- | --- | --- | --- |
| 方向选择 | 用户在三个同内容候选间决定 | 用户选 `poster-pop` | 海报条占首屏高度（已明示并接受） |
| 保留旧 CSS 变量名并映射新值 | 不破坏 JS 模板字符串契约 | 保留 `--bg…--err` 并追加新 token | 变量语义双份，需在 `DESIGN.md` 说明 |
| 新增 `GET /art/background` 只读路由 | 无构建步骤下让插画可换、可缺省 | 404 时回退纸张底（页仍可用） | 新增一条后端面（只读，无状态） |
| 号码牌绑定 `/api/status` 四个字段 | 步骤必须来自真实状态而非静态文案 | `cert.installed` / `proxy.enabled` / `counts.total` / `counts.done` | 语义依赖后端字段含义，字段改名会静默失配（已在 `design.md` 记录） |
| 轮询不加 `aria-live` | 避免每 1.5s 打断读屏 | 状态以文本呈现，读屏按需查询 | 读屏用户不会自动听到状态变化 |
| 不做深色变体 | 单一亮纸主题；不为未请求的能力加复杂度 | 仅亮色 | 夜间使用体验依赖用户自定 zoom/主题扩展 |

## Final Verdict

- Pass / fail: **pass**
- Blocking issues: 无
- Non-blocking issues: 820 档表格需横向滚动；375 档顶栏变高（122px）；触屏目标未放大；行 hover 仅靠颜色；无 `aria-live`
- Follow-up tasks: 若要移动优先，另开变更处理触屏目标与顶栏折叠；若要读屏播报，另开变更引入受控 `aria-live`（仅在失败/完成时播报）
- 验证声明：`unverified`（本变更无参考可测量，未跑 `reconstruction check --stage final`）；本 pass 只针对**已实际运行的**门：真实服务渲染、六档视口实测、状态覆盖、API 生命周期、reduced-motion 计算样式
