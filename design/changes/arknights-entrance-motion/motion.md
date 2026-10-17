# motion.md · 变更 `arknights-entrance-motion`（出场动效）实现与证据

本文件是**本次变更**的实施计划与证据记录；项目级动效语言仍以根目录 `MOTION.md` 为准，本文件只做选择与特化，不重新定义。

## Foundation Link

- Project foundation: `MOTION.md`
- Foundation schema: `design-pipeline.motion-foundation.v0.1`
- Foundation SHA-256: `8f2c53fb7e5e9c5a898e84388dd2a02b4103c6872f916762ac4a1226f71d09b5`
- Foundation posture: `minimal`
- Primitive registry: `design-pipeline.motion-primitives.v1`
- Selected primitive IDs: `response.spring-settle`、`transform.orbit`（既有）、`reveal.trim-line`（本次新增选中）
- Any authored extension and why the registry is insufficient: **`reveal.mask-wipe`** —— 注册表里唯一的 reveal 原语是路径可见长度（`reveal.trim-line`，渲染面 svg / canvas）；本次出场的四条内容带是**矩形裁切窗口**在已排版盒子上移动，语义不同，硬套会篡改原语语义，故按注册表纪律登记自撰扩展（字段见下）。
- `foundation check --kind motion` 结果：`ready`，`selectedPrimitives: [response.spring-settle, transform.orbit, reveal.trim-line]`（自撰扩展不作为注册表 id 参与校验）。

## Authored extension `reveal.mask-wipe`

| Field | Value |
| --- | --- |
| intent | 用一个直边矩形裁切窗口扫过已排版的盒子来揭示它（不改变盒子自身的布局占位） |
| channels | `clip.inset`、`position.x`、`position.y` |
| parameters / units / defaults | `direction` 左→右（默认）；`from` `inset(0 100% 0 0)`；`to` `inset(0 0 0 0)`；`distance` 5px 上落（默认）；`duration` 300ms（默认）／220ms（自检行实例）；`stagger` 100ms（默认，带与带之间）／140ms（自检行之间） |
| drivers | time、state |
| render surface | CSS（`clip-path` + `transform`）；不要求 svg / canvas / WebGL |
| runtime capability | css `supported`；waapi `supported`（等价终态）；animejs / gsap `unsupported`（本项目不引入库） |
| reduced-motion substitute | 取消窗口：内容以终态直接出现（无裁切、无位移）；出场整体不播 |
| accessibility | 只作用于装饰带与已经排版的容器；不改变可读内容、不改变焦点可见性、不改变布局占位；信息不依赖"是否被擦出来" |
| provenance | authored（项目自撰）；`codeCopied: false`；无外部来源 |

## Summary

- Change id: `arknights-entrance-motion`
- Surfaces: `static/index.html`（单页界面）的出场层与四条内容带
- Motion owner: 项目自身（单文件内联 CSS + 2 段内联脚本，无库）
- Motion risk: low（一次性的 CSS 动画，无逐帧渲染面、无后台循环、无外部请求）
- Implementation target: **CSS keyframes + clip-path / transform / 离散 visibility**；另加 head 内一次同步判定与 body 末一次 `setTimeout` 收尾

## Motion Principles

- Purpose: 每会话第一次打开时，用"本机工具正在自检"这件事交代四步主线（证书 → 代理 → 抓包 → 下载引擎）确实在工作；之后不再播。
- Product feeling: 工业战术（结构线、裁切几何、等宽遥测数字），冷、快、硬边；不热闹、不弹跳。
- What motion must never do: 不重播、不循环、不遮挡可读内容超过 1.4 秒、不推迟第一次可交互（任意输入即刻收敛）、不携带只有动效才知道的信息、不做纯透明度入场、不引入外部素材或库。
- Reduced-motion principle: 不播（头脚本在首帧前就决定），页面首帧即终态。
- Maximum time before the user can interact: **0ms**——键盘与指针在任何时刻都能终止出场；被出场层挡住的那一次点击被用作"跳过"（与所观察的参考站点一致），落地时如需可把该次点击转发给底层元素。

## Scene And Layer Model

| Scene id | Stage / viewport | Camera | Layers | Entry | Exit | Interruption |
| --- | --- | --- | --- | --- | --- | --- |
| entrance（出场罩） | 首屏，1440×900 基准，1366–2560 宽 | 无（平面，无 3D 相机） | 两个：`exit-gate`（罩，z 99）与 `content-bands`（页面自身的带，z ≤ 2） | 首帧即已遮盖（`display:grid`），角括与字标自外向内落位 | 1360ms 单帧硬切（`visibility` 终值），收尾再摘类名 | 任意输入即刻终止；`prefers-reduced-motion` 下不建立 |

- Layer `exit-gate`：语义所有者 = 出场罩；渲染面 = DOM + CSS；坐标空间 = 视口固定（`position:fixed; inset:0`）；遮罩关系 = 覆盖全屏但 `aria-hidden`、不参与布局；Z = 99；必须保持可读/可操作的内容 = 无（罩内只有装饰与遥测文本，页面在它下面完整存在）。
- Layer `content-bands`：语义所有者 = 页面自身的五条带（顶栏 / 海报条 / 号码牌 / 工具条 ×2 / 表格面板）；渲染面 = DOM + CSS；坐标空间 = 页面流；遮罩关系 = 自身被 `clip-path` 由右向左揭示；Z = 1–2（不变）；必须保持可读/可操作 = 可读性在入场结束后完全恢复（收尾摘掉类名）。

## Interaction Inventory

| Trigger | Target | Primitive / effect | Purpose | Start state | End state | Repeat behavior |
| --- | --- | --- | --- | --- | --- | --- |
| 会话内首次页面加载 | `html` | 挂 `wxc-boot` 类名（建立入场） | 交代"本机工具正在自检" | 无类名（终态页面） | `wxc-boot` + 首帧遮盖 | 每会话一次（`sessionStorage` 标记）；不重复 |
| 加载后 0–300ms | 角括 / 发丝框 / 字标 | `primitive: response.spring-settle` | 结构先就位 | 罩内元素未落位 | 各元素到静止值 | 不重复（随入场整体结束） |
| 加载后 300ms 起 | 中央发丝进度线 | `primitive: reveal.trim-line`（css degraded） | 遥测：自检在推进 | 可见长度 0 | 可见长度 100% | 不重复、不循环 |
| 加载后 340ms 起（四行） | 四条自检行 + 方块指示 | `authored: reveal.mask-wipe` | 逐条交代四步主线 | 裁切 100% / 方块空 | 裁切 0 / 方块实心（单帧 step-end） | 不重复 |
| 加载后 560/660/780/900(980)/1060ms | 五条内容带 | `authored: reveal.mask-wipe` | 依序揭示已排版的页面 | `inset(0 100% 0 0)` + 上落 5px | `inset(0 0 0 0)` + 归位 | 不重复 |
| 加载后 1360ms（自然结束） | 罩 | 离散状态替换（不使用原语） | 硬切退场，不留过场 | 罩可见 | 罩不可见；类名被摘掉 | 一次性 |
| 任意输入（键 / 指针 / 触摸 / 滚轮） | 罩 + 五条内容带 | 离散状态替换（跳过的统一收敛） | 用户不必看完 | 入场进行中 | `wxc-boot` 摘掉 + `wxc-skip` 加上 → 全页终态 | 首次输入即触发，之后无动画 |
| 轮询（每 1500ms 重写 `#rows`） | 表格行 | 不使用原语（入场不参与） | 数据更新不得重启入场 | 终态行 | 终态行 | 行入场只在 `wxc-boot` 存在时定义；收尾后重建的行无动画（实测：4.2s 后无裁切残留） |
| hover / focus / 按下 / 进度推进 | 行、按钮、进度条 | 既有 `response.spring-settle` 等 | 既有交互反馈 | —— | —— | 不受入场影响 |

## Tracks And Timeline

| Track id | Scene / target | Channel | Start | Duration | Delay | Easing | Stagger | Driver |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| `boot-frame` | 罩 / 发丝框 | scale | 0 | 300ms | 0 | cubic-bezier(.16,1,.3,1) | — | time |
| `boot-corner` | 罩 / 四个角括 | position.x, position.y | 0 | 300ms | 0 / 40 / 80 / 120ms | cubic-bezier(.16,1,.3,1) | 40ms | time |
| `boot-mark` | 罩 / 自绘字标 | scale | 60ms | 340ms | — | cubic-bezier(.16,1,.3,1) | — | time |
| `boot-bar` | 罩 / 发丝进度线 | path.progress | 300ms | 900ms | — | cubic-bezier(.55,0,.45,1)（S 形，对齐实测） | — | time |
| `boot-line` | 罩 / 四条自检行 | clip.inset, position.y | 340/480/620/760ms | 220ms | 见左列 | cubic-bezier(.16,1,.3,1) | 140ms | time |
| `boot-sq` | 罩 / 四个方块指示 | background-color | 510/650/790/930ms | 1ms | — | step-end | — | state |
| `boot-band` | 页面 / 五条内容带 | clip.inset, position.y | 560/660/780/900(980)/1060ms | 300ms | 见左列 | cubic-bezier(.16,1,.3,1) | 100ms | time |
| `boot-cut` | 罩 / 整体 | visibility（离散） | 1360ms | 1ms | — | step-start | — | state |
| `boot-settle` | `html` / 类名 | —（脚本） | 1360ms | — | — | — | — | time（一次 `setTimeout`） |

Rules 落实情况：时间单位毫秒；delay 与 stagger 分开给出；时间轴所有者是 CSS 引擎（唯一例外是收尾的那一次 `setTimeout`）；track 之间是重叠的（各带在自检行之后 20ms 起步）；重放不存在（每会话一次）、倒放不适用、seek 不适用；取消 = 任意输入；快速连点 = 第一次输入即收敛，之后无动画可触发。无滚动驱动轨道。

## Procedural Generators

无。generator count 0；不在运行时求值任何表达式，不逐帧执行脚本，不引入外部动画求解器。

## State Machine And Interruption

| State | Event | Guard | Next state | Running tracks cancelled / preserved | Focus behavior |
| --- | --- | --- | --- | --- | --- |
| `absent`（未挂类名） | 首次加载 | 未被 `sessionStorage` 标记 且 非 reduced-motion | `playing` | —— | 不变 |
| `absent` | 首次加载 | 已标记 或 reduced-motion | `absent` | —— | 不变 |
| `playing` | 任意输入 | —— | `skipped` | 全部取消（摘类名） | 焦点不延迟，第一次输入同时充当跳过 |
| `playing` | 1360ms 到点 | —— | `done` | 全部结束（各动画 fill 已到终态），摘类名 | 不变 |
| `skipped` | 之后的轮询 / 数据更新 | —— | `skipped` | 无入场动画可重启（类名已摘） | 不变 |
| `done` | 之后的轮询 / 数据更新 | —— | `done` | 同上 | 不变 |

- 入场期间连点：第一次输入即收敛，后续输入正常作用于页面。
- 路由变化：本项目是单页无路由；若将来加路由，入场只在文档首次加载建立，不随路由重播。
- 滚动反向：无滚动驱动轨道，不适用。
- **视口 resize**：入场只做位移/裁切，重排由浏览器按既有响应式规则一次完成；不逐帧推进布局。
- 组件卸载：不适用（无组件框架）；收尾摘类名等价于"卸载入场层"。
- 加载成功/失败与动效同时发生：入场不依赖 `/api/*`（失败只影响表格内容，不影响出场）。
- 清理：无 rAF 循环、无 observer、无定时器常驻（只有一次 `setTimeout`）、无 WebGL / Canvas 上下文、无监听器泄漏（4 个被动监听器随页面生命周期，一次性使用）。

## Easing And Spatial Behavior

| Motion type | Easing | Origin / direction | Distance / scale | Opacity / filter | Why |
| --- | --- | --- | --- | --- | --- |
| Small UI feedback | 120ms 直接属性过渡 | —— | ≤2% 缩放 | 无 | 既有纪律，未改动 |
| Enter / reveal（自检行、内容带） | cubic-bezier(.16,1,.3,1) | 自右向左揭示 + 5px 上落 | 100% 宽度 | 不用透明度承载 | 硬边擦除是几何事件；透明度不参与 |
| Enter / settle（角括、发丝框、字标） | cubic-bezier(.16,1,.3,1) | 自外向内 | 12px / ≤3.5% 缩放 | 伴随（不承载） | 结构先就位，无过冲 |
| Telemetry（发丝进度线） | cubic-bezier(.55,0,.45,1) | 自左向右 | 可见长度 0 → 100% | 无 | 对齐参考站点实测的 S 形填充 |
| Exit / dismiss（罩） | 单帧 step-start | —— | —— | 无淡出 | 参考站点的交场是硬切（实测两处场景切换间隔约 200ms，本项目取更干脆的单帧） |
| Route transition | 不适用 | —— | —— | —— | 单页无路由 |
| Scroll-linked motion | 不适用 | —— | —— | —— | 未选中任何滚动驱动原语 |

只用 `transform` / `clip-path` / 离散 `visibility`；无布局属性推进、无模糊、无滤镜、无 mask 链。

## Runtime Binding

| Primitive / track | Adapter | Capability | Degradation | Cleanup owner |
| --- | --- | --- | --- | --- |
| `primitive: response.spring-settle`（入场落位） | CSS | supported | 无（减弱动效下整体不播） | CSS（摘类名即失效） |
| `primitive: reveal.trim-line`（发丝线） | CSS | degraded（宽度轴缩放近似路径可见长度） | 语义保留：单调、不循环、可静止 | CSS |
| `authored: reveal.mask-wipe` | CSS | supported | 减弱动效下取消窗口 | CSS |
| 收尾（摘类名） | 内联脚本（一次 `setTimeout`） | supported | 不适用 | 页面自身（一次性） |

不新增任何动画运行时；WAAPI 未使用（CSS 已足够，且同一语义不应有两个所有者）。

## Accessibility And Reduced Motion

- `prefers-reduced-motion` 替代：头脚本读到 reduce 就**不挂** `wxc-boot`——首帧即终态，零遮挡；同时 CSS 侧再兜一层 `display:none` 与 `animation:none`。
- 键盘焦点在动效期间：入场层不含可聚焦元素，`aria-hidden="true"`；第一次按键即跳过；焦点环由样式直接给出，不依赖过渡。
- 屏幕阅读器影响：出场罩 `aria-hidden`；四条自检行是**装饰性遥测文本**，真实状态由顶栏胶囊与号码牌（DOM 常驻、可读）给出；因此入场不播也不丢信息。
- Pause / stop / skip：任意输入跳过；无暂停（时长上限 1.4s，短到不需要暂停）。
- Touch-target 稳定性：入场层覆盖期间不改变任何控件的尺寸与位置（终态布局在入场开始前就已确定）。
- 非运动等价物：入场携带的信息（四步主线）在页面里由顶栏胶囊、四张号码牌与脚注常驻给出。
- 闪烁 / 视差 / 前庭风险：无全屏闪烁（罩底色恒定、无闪白）、无视差、无循环动效；唯一的循环动效仍是既有下载旋转弧。

## Performance Budget

- Target frame rate: 60fps（视觉目标 16.7ms/帧）
- Main-thread budget: 入场期间无脚本运行（纯 CSS 动画）；仅两次一次性脚本（head 判定、收尾定时器）
- Particle / element ceiling: 同时运动的元素 ≤ 16（4 角括 + 1 发丝框 + 1 字标 + 1 发丝线 + 4 自检行 + 4 方块 + 5 内容带）
- Properties allowed: `transform`、`clip-path`、`background-color`（单帧 step-end）、`visibility`（单帧）
- Properties avoided: 布局属性（width/height/top/left 推进）、`filter`、`backdrop-filter`、`box-shadow` 动画（入场不使用）、`mask-image` 链
- Filter / Canvas / WebGL budget: 0
- Scroll observer refresh: 不适用
- Heavy asset strategy: 零图片、零字体、零外部请求；角括/斜线束/字标为内联 SVG 与 CSS 几何
- Low-end mobile fallback: 不做移动端优先；≤820 的响应式规则沿用既有页面；减弱动效即终态
- Deterministic sampling seed: 不适用（无生成器）
- Renderer preference and fallback: 浏览器默认合成路径（transform / clip-path 走合成器；clip-path 会触发重绘，但只作用于 5 条带、单次 300ms）
- Ticker / manual loop owner: 无（无 rAF 循环）
- Draw-call, texture-memory, and DPR ceiling: 0 / 0 / 不适用

## Evidence And Provenance

| Evidence id | Fact | Classification | Source | Confidence | Artifact |
| --- | --- | --- | --- | ---: | --- |
| `ref-ak-progress` | 官网发丝进度线占宽 51%、S 形填充（x 567@1.20s → 1365@2.20s）、场景切换 2.933s/3.133s | measured | 录像逐帧像素（30fps，`crop` + rawvideo） | high | `evidence/ref-ak/entry.webm`、`sheet-1fps.png`、`sheet-cut.png` |
| `ref-ak-anims` | 官网交场后页内 CSS 动画仅 5 个、缓动全为 `linear` | measured | `document.getAnimations()` 清单 | high | `evidence/ref-ak/anim-inventory.json` |
| `ref-endfield-wipe` | 满屏强调色块前缘 x=60@400ms → x=1560@667ms，整次扫清 ≈0.95s；黄实测 rgb(249,240,51) | measured | 60fps 逐帧像素采样 | high | `evidence/ref-endfield/entry.webm` |
| `entrance-timeline` | 真实 `static/index.html` 上：首帧即 `wxc-boot` + 罩 `grid/visible`；内容带裁切在 809ms 处于中间态；1393ms 起类名摘除、罩 `display:none`、裁切 `none` | measured | 页面内 rAF 采样（1440×900，267 帧） | high | `qa/entrance-verify.json` |
| `entrance-session-once` | 同会话第二次加载：无类名、罩 `display:none`、标记 `1` | measured | 同上 | high | `qa/entrance-verify.json` |
| `entrance-skip` | 350ms 按键：类名变 `wxc-skip`、罩 `display:none`、海报条与面板裁切 `none` | measured | 同上 | high | `qa/entrance-verify.json` |
| `entrance-reduced` | reduced-motion 下不挂类名、罩 `display:none`，且不消耗会话标记 | measured | 同上（CDP 媒体特性模拟） | high | `qa/entrance-verify.json` |
| `interaction-gate` | 真实点击（1440×900）驱动：84 帧内目标盒子收敛，input 后 7ms 静止，无 finding | instrumented | `verify interaction`（Chrome + puppeteer-core，探针 `.gate`） | high | `qa/interaction/interaction.json` |
| `entrance-design` | 角括 / 发丝框 / 字标 / 发丝线 / 自检行 / 内容带 / 硬切的时间轴与缓动取值 | authored | 本变更设计（用户从三个候选方案中选定方案 1） | high | 本文件、`concepts/c1.css`、`preview/c1-key-780ms.png` |
| `motion-md-update` | 项目动效基础新增"每会话一次的入场"结果、`reveal.trim-line` 选中与 `reveal.mask-wipe` 自撰扩展 | authored | 本变更（`MOTION.md` sha 已更新进 `DESIGN.md`） | high | `MOTION.md`、`DESIGN.md` |

未产出（如实声明，不用猜测替代）：`motion-observation.json` / temporal trace JSON / frame sequence WebM / `motion-ir.json` / `motion-verification.json` —— 本项目没有对应的采集与编译工具；本变更以 rAF 采样 JSON、逐帧录像与交互门禁作为等价证据。

## QA Scenarios

| Scenario | Expected result | Evidence |
| --- | --- | --- |
| Repeated rapid interaction | 第一次输入即收敛到终态，后续输入正常落到页面控件 | `qa/entrance-verify.json`（skip 用例：350ms 按键后类名 `wxc-skip`、裁切全 `none`） |
| Keyboard navigation | 第一次按键跳过出场；Tab 顺序与焦点环不受影响（罩内无可聚焦元素） | 同上（`keydown` 走同一条收敛路径） |
| Reduced motion | 首帧即终态页面，无罩、无裁切，且不消耗会话标记 | `qa/entrance-verify.json`（reducedMotion 用例） |
| Mobile viewport | 非目标；≤820 响应式规则沿用既有页面，入场只做裁切/位移，不改变断点行为 | 概念阶段 1440/1600 视口实测 + 响应式规则未改动 |
| Slow device / network | 入场是纯 CSS，不依赖网络；`/api/*` 失败只影响表格内容 | `qa/screenshots/final-1440x900.png`（接口正常时的终态）＋ file:// 下无接口时入场仍完整（`qa/file-url-check.json`） |
| Route interruption | 不适用（单页无路由） | —— |
| Scroll up/down repeatedly | 无滚动驱动轨道 | —— |
| Resize during motion | 不逐帧推进布局；重排由既有响应式规则一次完成 | 设计约束（入场只用 transform / clip-path） |
| Renderer init or asset failure | 无 Canvas / WebGL / 外部素材可失败；内联 SVG 与 CSS 几何不依赖网络 | 同上 |
| Tab hide, route exit, and remount | 无后台循环；`setTimeout` 一次即完成，摘类名后无动画残留 | `qa/entrance-verify.json`（2093ms 采样：类名 `(none)`、裁切 `none`、无 running 动画） |
| 轮询重启（本项目特有） | 每 1500ms 重写 `#rows` 不得重启入场 | 三方案预览实测（`preview/_smoke.json`）：播完后等到 4.2s（≥2 次轮询）行仍无裁切残留 |

## Pipeline note（web/standard 的路径偏差，如实记录）

`web` 子工作流的 build 阶段以**项目根目录的 `index.html`** 作为交付页判定（`workflows/web.cjs` 的 `exists(root, "index.html")`）。
本仓库的页面是 `static/index.html`（FastAPI 在 `/` 提供，README / PLAN / DESIGN 三处都以此为准），
为了满足工具的路径假设去改仓库结构属于超范围改动，故**在原地构建**，并直接运行其余阶段对应的命令：

- build：改 `static/index.html`（出场层 CSS + 罩标记 + 两段内联脚本）。
- probe：`interaction.json`（根目录）+ `verify interaction` → `passed`，门禁已写回 `.design-pipeline/state.json`。
- review / deliver：由用户决定，用 `decide --stage review|deliver` 记录。

因此 `designer-pipeline next --project-root .` 会一直停在第 4 步 `build (4/7)`——这是路径假设不匹配，不是未完成的工作。

## Final Motion Score

| Dimension | Score | Notes |
| --- | ---: | --- |
| Purpose | 5 | 入场只交代"本机工具在自检"，且四条自检行就是产品四步主线；不承载只有动效才知道的信息 |
| Timing | 4 | 1360ms 入场 + 单帧硬切；扣 1 分是因为上限 1.4s 对"反复刷新的本地工具"仍偏长，靠"任意输入即刻收敛 + 每会话一次"兜住 |
| Easing | 5 | 全为单段 ease（无弹跳、无过冲），发丝线用与实测一致的 S 形；硬切是离散替换而非伪过渡 |
| Choreography | 4 | 四条自检行与四条内容带一一对应，节奏清楚；扣 1 分是内容带比自检行多一条（两条工具栏共享一次揭示），映射不是严格 1:1 |
| Interruption | 5 | 任意输入即收敛，实测 input 后 7ms 静止（`interaction-gate`） |
| Responsiveness | 4 | 入场期间无脚本运行、无 rAF 循环；扣 1 分是 `clip-path` 会触发 5 条带的重绘（单次 300ms，实测无掉帧证据也没做逐帧性能采样） |
| Accessibility | 5 | 罩 `aria-hidden`；减弱动效下不播且不闪；信息在非运动通道完整存在 |
| Performance | 4 | 同时运动元素 ≤16、无滤镜/画布/外部请求；扣 1 分是未采集主线程逐帧 trace |
| Foundation fit | 5 | `foundation check --kind motion` = ready；新增的入场结果、`reveal.trim-line` 选中与自撰扩展均已写回 `MOTION.md` |
| Implementation fit | 5 | 单文件、零依赖、零构建；`verify interaction` 通过；`static/index.html` 之外未改动产品代码 |
