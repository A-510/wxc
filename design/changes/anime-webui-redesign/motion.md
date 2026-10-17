<!-- DESIGN-PIPELINE:MOTION:START -->
# Motion — anime-webui-redesign

- 项目动效基础：`MOTION.md`，sha256 `1e3945b3779e3f62874fdb7cc8945d961fdeaf5daf9479edd9f02f986c3dc034`（posture `minimal`）
- 选中原语：`primitive: response.spring-settle`（响应/收敛）、`primitive: transform.orbit`（不确定进度旋转弧）
- 原语注册表：`design-pipeline.motion-primitives.v1`（两个 ID 均在该注册表中解析）
- 来源：本变更的运动均为**作者设计**（authored），无可测量的参考运动证据；未采用程序化生成器（generator count 0）
- 运行时能力：CSS transitions / keyframes = supported；WAAPI = degraded（本变更未使用）；Anime.js / GSAP /
  Canvas / WebGL / SVG 滤镜 = unsupported（本变更未引入）；无降级缺失
- 实现库：无（纯 CSS，无第三方动效库，符合「无构建步骤、无外部依赖」）
- 渲染面白名单为空：无 canvas / WebGL / WebGPU

## 逐项落点（本变更真实出现的位置）

| 交互 | 触发 | 目的 | 时长 / 缓动 | 中断行为 | 性能预算 | reduced-motion 回退 |
| --- | --- | --- | --- | --- | --- | --- |
| 按钮 / 输入 / 行的 hover | 指针进入 | 说明可点与当前行 | 背景色 120ms（颜色属性，无过渡的几何） | 立即被新状态替换 | 仅颜色，不触发布局 | 取消过渡，颜色瞬时切换 |
| 按钮按下 | `:active` | 印刷「压下去」的物理确认 | 无过渡（离散替换）：下沉 1.5px + 撤掉硬投影 | 抬起即恢复 | 仅 transform + box-shadow | 同一瞬时状态，不依赖过渡 |
| 键盘焦点 | `:focus-visible` | 键盘可达 | 无过渡（3px `--cyan-deep` 外描边立即出现，绝不由动效延迟） | — | — | 不适用（本就瞬时） |
| 确定性进度条 | `/api/items` 的 `progress` 变化 | 进度是数据，不是演出 | 宽度 240ms `linear`；`role="progressbar"` + `aria-valuenow` | 新值直接接管，不排队 | 宽度过渡只读一次布局 | 取消过渡，宽度瞬时到位，百分比文字照常更新 |
| 不确定进度旋转弧 `.spin` | 下载中且服务端未报比例 | 唯一的循环动效：机器正在做事 | 900ms `linear` 顺时针（`transform.orbit`） | 状态离开「下载中」即随节点移除终止，不留后台循环 | 合成层 transform 动画，单条 ≤1 个实例 | 弧段静止（授权静止相位）+ 中文状态文字「下载中 · 已收 12.4 MB」 |
| 状态胶囊 / 号码牌状态切换 | 轮询回填 | 同一帧内替换文案与配色 | 缩放 0.96→1 由 `response.spring-settle` 承担；本实现只用颜色/底色的直接属性过渡（120ms），不使用缩放通道 | 立即收敛到最新真实状态 | — | 瞬时替换 |
| 原生 `confirm()` 对话框 | 清理 TS 分片 | 破坏性动作二次确认 | 浏览器原生（`response.spring-settle` 的 0.98→1 缩放不适用：不引入自绘模态） | 原生 | — | 原生 |

## 审查结论

- 动画机会筛选：本变更没有新增「值得做动效」的地方——四步号码牌、状态胶囊、失败文案都是**状态替换**，
  用颜色与文字表达即足够；唯一保留下来的时间驱动动效是下载中的不确定指示（机器正在做事）。
- 未引入滚动触发、入场编排、逐帧渲染或库级时间轴（与 `MOTION.md` 的 Rejected 列表一致）。
- 实机验证：`prefers-reduced-motion: reduce` 下 `.spin` 的 `animation-name` 为 `none`、
  进度条与按钮 `transition-property` 为 `none`（Chrome `Emulation.setEmulatedMedia` + 计算样式实测），
  关闭减弱动效后恢复 `orbit` / `width` / `background-color`。
<!-- DESIGN-PIPELINE:MOTION:END -->
