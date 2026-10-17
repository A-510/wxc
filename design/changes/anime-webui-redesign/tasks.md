# Tasks — anime-webui-redesign

实现面：`static/index.html`（+ `wxc/config.py` 的 `ART_FILE`、`wxc/webui.py` 的 `/art/background`）。

## Tokens / theme

- [x] `:root` 落 `DESIGN.md` 的海报波普色板（纸/墨/青/洋红/状态三色），并按最坏背景实测对比度
- [x] 保留旧变量名 `--bg --panel --line --fg --muted --accent --ok --warn --err` 并映射到新值（JS 模板直接引用）
- [x] 8px 基准间距、3–4px 硬边圆角、无模糊硬投影（2/3/4/6px 四档）

## Layout

- [x] `100dvh` 三档层级 + 竖向结构：顶栏 → 海报条 → 四张号码牌 → 工具栏 ×2 → 表格面板 → 页脚带，间距 10px
- [x] 海报条 `center top / cover` + `clamp(118px,19vh,172px)`，底部墨色标题带
- [x] 表格容器内滚动、表头吸顶（`position: sticky` + `inset` 墨线，避免 `border-collapse` 吃掉描边）
- [x] 响应式：≤1180 隐藏主机列；≤900 隐藏大小列并降海报条；≤760 号码牌折 2×2；≤820 工具栏换行 + 表格横向滚动兜底；≤高度 640/560 收海报条 / 允许整页滚动

## Components

- [x] 状态胶囊 `pill`（默认 / `.ok` / `.bad`）
- [x] 四张号码牌 `steps/.step`（未达 / 当前 / 已达，`aria-current="step"`）
- [x] 工具栏 `tools`（配置行、导入/搜索行）
- [x] 纸张面板 + 页脚带（下载目录、并发、关闭代理提醒）
- [x] 番札 `tag` / `.q`、进度 `bar` / `.spin`、操作组 `ops`、空态 `empty`、失败文案 `.err-text`
- [x] 输入/按钮 30px 高、`:focus-visible` 3px 外描边

## States

- [x] 列表状态词表：未下载 / 排队中 / 下载中 / 完成 / 失败 / 已取消 / 已忽略
- [x] 三通道：文字 + 颜色（`--ok`/`--err`/`--muted`）+ 形状（进度条 / 旋转弧 / 番札边框）
- [x] 进度：确定条（`role="progressbar"` + `aria-valuenow`，240ms 线性）；不确定 → `.spin` 旋转弧
- [x] TS 分片行换成「下载整节课」；失败行不截断并写成下一步动作；未知大小 `—`
- [x] 空态、已忽略过滤、搜索空结果三个空面
- [x] 抓包状态 → 顶栏胶囊 + 号码牌同步点亮

## Playground

- [x] 不适用：`playground.json` 不存在，本变更无交互式 Playground 需求（记为支持的豁免，见 `qa.md`）

## Motion

- [x] 动画机会筛选：四步/胶囊/失败文案按状态替换处理，只保留下载中不确定指示（记录在 `motion.md`）
- [x] 词汇、曲线、运行时、reduced-motion：`motion.md`（CSS transitions，无库）
- [x] 动效审查与证据：实测 `prefers-reduced-motion: reduce` 下 `animation-name: none`（见 `qa.md`）

## Scene / runtime

- [x] 不适用：无 canvas/WebGL/WebGPU、无相机、无持久空间状态

## Accessibility

- [x] Tab 顺序 = 视觉顺序；全部交互元素是真 `<button>` / `<input>` / `contenteditable`
- [x] `:focus-visible` 3px `--cyan-deep` 外描边，立即出现（不靠过渡）
- [x] 复选框 `aria-label="选择：<标题>"`；搜索框 `aria-label`
- [x] 进度条 `role="progressbar"` + `aria-valuemin/max/now`；旋转弧 `aria-hidden="true"`（文字承载语义）
- [x] 当前步 `aria-current="step"`；改名 Enter 提交、Esc 取消（还原）
- [x] 对比度实测：正文 16.6:1、次级 10.1:1、说明 6.4:1，最小文本对（主按钮纸色字）4.6:1，全部 ≥ 4.5:1
- [x] 破坏性动作二次确认；插画为 CSS 背景（装饰），标题带文字可读

## Responsive QA

- [x] 1440×900（基准，同屏 6 行）、1920×1080（9 行）、1280×800、1024×768、900×800、820×700、760×700 逐档实测
- [x] 无横向溢出、无重叠、无裁切（含 200% 缩放）
- [x] 截图见 `design/changes/anime-webui-redesign/evidence/`

## Browser / manual QA

- [x] 真实服务（`python -m wxc.cli ui --no-capture`，`127.0.0.1:8900`）+ 真实数据库渲染
- [x] 无外部请求（全部请求 host = `127.0.0.1`）、控制台零错误
- [x] 全状态覆盖渲染（含 `running` 有/无比例、`queued`、`error`、`ts`、`canceled`、`ignored`、超长标题、未知大小、含 HTML 的标题转义）
- [x] 功能路径：手动导入 → 改名 → 忽略 → 取消忽略 → 取消下载 → 删除（实测 200，数据库回到原状）
- [x] 搜索过滤、全选、显示已忽略、空态

## Interface discipline（review scope: full）

- [x] 六域检查：accessibility / layout / typography / color / UI polish / writing
- [x] Diff 范围：`static/index.html`（整页换皮 + 少量 a11y/状态通道增强）、`wxc/config.py`、`wxc/webui.py`
- [x] 消费者扩展：页面内 JS 模板字符串（`var(--warn)`/`var(--err)`）、`/api/*` 调用方（浏览器）、`/art/background`
- [x] 删除信号检查：`--bg/--panel/...` 旧变量名保留（未删）、`slide` 关键帧被 `orbit` 取代、`.indet` 被 `.spin` 取代、`.hint` 卡片被号码牌与页脚取代
- [x] 每条发现带 `Introduced` / `Regression` / `Pre-existing` 状态（见 `qa.md`）
