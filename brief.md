# Brief（当前任务：出场动画）

> 上一任务（界面皮肤重做，ui/standard・poster-pop）已归档于 `design/changes/anime-webui-redesign/brief.md`；
> 本文件是**当前 web/standard 任务**（出场动画）的 intake 记录，对应 `decide --stage intake` 的答复。

1. **product**：wxc —— 微信小程序网课下载器的**本地单页界面**（FastAPI 托管的 `static/index.html`，无构建步骤，`http://127.0.0.1:8900`）。
   本次交付的是这一页的**出场（入场）动画**：首屏从"开始绘制"到"可操作终态"之间那 1 秒多钟里发生什么。
   页面主线不变：**① 安装 CA 证书 → ② 开启系统代理 → ③ 在微信 PC 端播放几秒网课 → ④ 回到本页下载**。
2. **audience**：学生本人在自己的 Windows 电脑上、用桌面浏览器看 `127.0.0.1:8900`（1366–2560 宽）；
   同一个会话里会反复刷新（下载进度要看），所以出场动画必须**短、可跳过、不重复挡路**。
3. **duration**：入场 **≤1.2 秒**（最长不超过 1.8 秒）；任意按键 / 点击 / 滚轮**立即收敛到终态**；
   每个浏览器会话只播一次（`sessionStorage` 标记）；`prefers-reduced-motion: reduce` 下直接显示终态，不播。
   判据：首屏在**零网络往返**下就能看出四步流程；出场动画不得推迟第一次可交互。
4. **assets**：**零外部素材**。全部由 CSS / 内联 SVG 现场生成（角括、发丝线、色块、字标、网点）；
   不引入外部字体、图标库、CDN、动效库（Anime.js/GSAP 均不引入）。
   沿用既有素材：页面唯一外部位图仍是用户自有的 `背景.jpg`（经只读路由 `GET /art/background`，非商用、仅本机个人使用、不再分发）。
   参考样本（Hypergryph 官网）**只作观察样本**：不抄其代码、素材、字标或文案。
5. **风格**：用户指定「明日方舟」风格。落到可执行语言 = `design-pipeline/references/visual-style-signals.json`
   的 `industrial-tactical` 信号（高对比操作层级、结构线与裁切几何、等宽遥测数字、状态遥测），
   而不是复刻任何一款游戏的画面。
6. **功能边界**：只加出场层与入场时序；不改 `/api/*` 契约、不改 `wxc/` 既有逻辑、
   不改既有 DOM id / class 名（页面内 JS 直接引用）、不引入构建步骤。
