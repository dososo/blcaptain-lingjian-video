# 灵剪 · 视频转场动效库 v1.1（42 转场）

> **转场是灵剪的固化能力，不是临时挑的花活。** 分镜关按内容从本库选配 → 在**分帧动效导演板**明示给用户 → 用户逐镜确认。机读版见 `transitions.json`，内容匹配器见 `match.js`。

## 三条铁律（写进匹配器）

1. **稀缺**：强转场（energy≥4）全片 **≤2–3 个**，只压能量曲线拐点；其余用隐形接续（A 象限，≈90%）。**均匀撒花哨转场 = AI 味头号来源。**
2. **motivated**：每个转场必有动机——运动方向、情绪断点、或母题承接。不为炫技而切。
3. **母题**：相邻镜有共同视觉元素时，优先用匹配剪辑（match-cut）承接母题，隐形而有力。

## 四象限谱系

| 象限 | 定位 | 能量档 | 占比 | 收录转场（v1.1 共 42：A8 / B11 / C9 / D14） |
|---|---|---|---|---|
| **A · 隐形接续** | 看不见的剪辑，叙事连续 | 0–1 | ≈90% | 硬切 · 匹配剪辑 · 动作匹配 · J/L Cut · 强切 · 隐形无缝切 · 插入切 · 平行交叉剪 |
| **B · 动势甩带** | 用运动方向把两镜甩/推在一起 | 2–5 | 稀缺 | 甩镜 · 推 · 拉 · 急推 · 滑移 · 旋切 · 滚切 · 变焦冲模糊 · 方向扭曲甩 · 覆盖揭示 · 空间交换 |
| **C · 时间冲击** | 用闪/停制造顿挫与反差 | 3–5 | 极稀缺 | 闪白 · 闪黑 · 定格 · 跳切 · 频闪 · 数字故障 · RGB 错位 · 抖动切 · 速度斜坡 |
| **D · 材质装饰** | 用墨/光/网点做风格化过渡 | 1–3 | 稀缺 | 水墨擦除 · 遮罩擦除 · 溶解 · 漏光 · 像素化 · 烧胶片 · 撕纸揭页 · 颗粒溶解 · 水痕扭曲 · 万花筒 · 排线擦除 · 网点绽放 · 数据摩什 · 虹膜开合 |

### A · 隐形接续（默认主力）

| 转场 | e | feel | 何时用 | 实现要点（HF/GSAP） | 廉价陷阱 |
|---|---|---|---|---|---|
| 硬切 Hard Cut | 0 | 无过渡直切 | ΔE 小、无需强调（默认） | 两 clip 首尾相接，靠构图/节奏承接 | 该给情绪断点也硬切=平 |
| 匹配剪辑 Match Cut | 1 | 形似而意转 | 母题承接、首尾呼应 | 入镜元素落在出镜同一屏幕位置/尺寸，切点对齐 | 构图没真对齐=普通硬切 |
| 动作匹配 Match on Action | 1 | 动作跨镜连续 | 同主体连续动作 | 切点在动作中段，入镜接下一姿态 | 切点没卡动作=跳 |
| J/L Cut | 1 | 声先/后于画 | 配音驱动的平滑接续 | 音轨比画面提前(J)/延后(L) 0.3–0.8s | 错位过长=声画脱节 |

### B · 动势甩带

| 转场 | e | feel | 何时用 | 实现要点（HF/GSAP） | 廉价陷阱 |
|---|---|---|---|---|---|
| 甩镜 Whip Pan | 5 | 急速横甩+运动模糊 | 能量升、语义转折、大跳 | 出镜 translateX 加速+blur，入镜反向减速入，峰值 motion-blur；12–16 帧 | 不加运动模糊=廉价滑动 |
| 推 Push | 3 | 新镜推出旧镜 | 叙事递进、引入新层级 | 入/出镜同向 translate 等速联动 | 无缓动匀速推=PPT |
| 拉 Pull | 3 | 后拉交代语境 | 从局部抽离到全局 | 出镜 scale down+后移，入镜从后景升起 | 动机不明=莫名后退 |
| 急推 Zoom Punch | 5 | 猛推进高潮（全片最猛） | 冲向能量顶峰 | 出镜 scale 快拉大+轻 blur，入镜从大回落到 1；8–10 帧 | 每镜都急推=麻木，须稀缺 |
| 滑移 Slide | 2 | 整屏平移 | 并列内容横向切换 | 整屏 translate，长尾缓动(power2/3) | 无缓动=幻灯 |

### C · 时间冲击（极稀缺，压拐点）

| 转场 | e | feel | 何时用 | 实现要点（HF/GSAP） | 廉价陷阱 |
|---|---|---|---|---|---|
| 闪白 Flash White | 4 | 过曝白闪盖切点 | 情绪爆点、时空跳跃 | 切点插 2–4 帧白 overlay 0→1→0 | 闪太久=晃眼（违反无障碍） |
| 闪黑 Flash Black | 5 | 切黑再起，压成静 | 顶峰跌落、章节断点 | 切点插 2–5 帧黑 overlay，配音断 | 黑太久=像卡顿 |
| 定格 Freeze Frame | 3 | 骤停一拍 | 强调瞬间/数据 | 末帧静止 ≥0.4s（合法拍） | 无强调对象=像卡死 |
| 跳切 Jump Cut | 3 | 同机位省略跳跃 | 压缩重复、节奏/幽默 | 同构图删中段帧，保留起止 | 无节奏支撑=像丢帧 |

### D · 材质装饰（风格化，稀缺点）

| 转场 | e | feel | 何时用 | 实现要点（HF/GSAP） | 廉价陷阱 |
|---|---|---|---|---|---|
| 水墨擦除 Ink Wipe | 2 | 墨迹晕染擦过 | 收束、东方母题 | 墨形 luma mask 从一点晕开做遮罩 | 墨形太规则=像圆形擦除 |
| 遮罩擦除 Luma Wipe | 2 | 灰度图形遮罩擦入 | 几何/图形母题 | clip-path / SVG mask 按形状展开 | 形状与内容无关=噪音 |
| 溶解 Dissolve | 1 | 交叠淡化，时间流逝 | 舒缓、抒情、回忆 | 出镜 opacity→0 同入镜 0→1，交叠 8–16 帧 | **快节奏产品介绍滥用=拖、廉价** |
| 漏光 Light Leak | 2 | 胶片漏光扫过 | 复古/胶片风 | 漏光素材 screen/add 混合扫切点 | 套预设=一眼模板 |
| 像素化 Pixelize | 3 | 块化再还原 | 数字/故障母题 | 切点 mosaic 升峰再回落 | 与气质不符=为效果而效果 |

## 内容匹配规则（`match.js` 人读版）

上游按「相邻镜能量差 ΔE + 语义关系 + 母题 + 风格」荐转场：

| 条件 | 荐转场 | 理由 |
|---|---|---|
| 进入顶峰镜（e≥5）且上升 | **急推 Zoom Punch** | 冲进能量顶峰 |
| 语义=转折 / 大幅升(ΔE≥3) | **甩镜 Whip Pan** | 转折甩带 |
| 顶峰跌落（ΔE≤−3 且前镜 e≥4） | **闪黑 Flash Black** | 反差喘息 |
| 语义=收束 / 东方风 | **水墨擦除 Ink Wipe** | 收束晕染 |
| 有母题承接 | **匹配剪辑 Match Cut** | 隐形而有力 |
| 语义=递进 | **推 Push** | 推进层级 |
| 并列 / 其余 | **硬切 Hard Cut** | 隐形默认 |

**稀缺守卫**：以上若荐出强转场（e≥4）但超过全片配额（默认 3），自动降级为隐形（有母题→match-cut，否则→hard-cut），并在导演板标注「降级」。→ 见 `test/match.test.js`，喂本片能量+语义可重现下方编排。

## 反廉价护栏（护住不出 AI 味）

- 均匀给每个镜间撒转场 → **改**：90% 隐形硬切/匹配，强转场只压 2–3 个拐点。
- 滑/推无长尾缓动 → PPT 幻灯感；一律带 power2/3 缓动。
- 快节奏 Profile（产品介绍）滥用溶解/淡入淡出 → 拖沓廉价；溶解仅留给抒情慢段。
- 材质转场（漏光/水墨）套现成预设 → 一眼模板；须与母题/风格绑定，稀缺点用。
- 闪白/闪黑频率：任一秒 ≤3 次（无障碍硬线），黑白帧 ≤5 帧。

## 实现映射（可选后端，**须核**）

灵剪主引擎 = **HyperFrames + GSAP**（上表「实现要点」即此）。若走 ffmpeg / gl-transitions 后端，`transitions.json` 的 `ffmpeg`/`gl` 字段给了近似项，**但标『待核』者必须对照官方核实**（`ffmpeg -h filter=xfade` 的真实 transition 名单、gl-transitions 库现有 shader），勿直接采信——水墨/甩镜等多数无通用 xfade 现成项，需自定义 luma matte 或自建。

## 本片编排（已用 match.test 验证重现）

| 拐点 | 转场 | 能量 | motivated |
|---|---|---|---|
| 钩子→转折 | 甩镜 Whip Pan | ●●●●● | 混乱一把甩到理顺 |
| 转折→是什么 | 匹配剪辑 Match Cut | ● | 场记板→模板，构图对齐 |
| 是什么→流程 | 推 Push | ●●● | 流程线顺势推成流水线 |
| 流程→三道闸 | 急推 Zoom Punch | ●●●●● | 全片最猛，冲进顶峰 |
| 三道闸→诚实 | 闪黑 Flash Black | ●●●●● | 顶峰猛切到静，反差 |
| 诚实→收尾 | 水墨擦除 Ink Wipe | ●● | 东方晕染，翻墨黑首尾呼应 |

强转场只在 pipeline→gates→honesty 两个拐点（能量峰），其余隐形——稀缺律落地。

> **状态诚实说明**：本库 42 个转场（v1.1；ffmpeg xfade 58 项、gl-transitions 125 shader 均官方核实过）的 HyperFrames/GSAP 跨镜实现均为 `spec`（已规格化、可实现），跨镜成片实现随主线画面执行集成;默认以硬切 concat 兜底,强转场按能量差稀缺使用。匹配逻辑已用 node 测试验证自洽。4 个转场（whip-pan/ink-wipe/paper-tear/halftone-bloom）的 gl 无现成 shader，标「待核」需自建。

---

## v1.1 扩充速查（+24 项，B/C/D 为主 · 官方名单核实）

> ffmpeg xfade **58 个**具名 transition（`ffmpeg -h filter=xfade` 官方核实，v8.1.2）；gl-transitions **125 个** shader（GitHub `gl-transitions/gl-transitions` 目录核实）。以下 `ffmpeg`/`gl` 列均为真实项，「无直接项/待核」为诚实缺口非编造。

| 转场 | 象限 | e | 何时用 | ffmpeg（真实项） | gl（真实 shader） |
|---|---|---|---|---|---|
| 强切 Smash Cut | A | 2 | 强反差断点/喜剧 | concat 硬切 | — |
| 隐形无缝切 Invisible Cut | A | 0 | 伪长镜/无缝换景 | concat 硬切 | — |
| 插入切 Cutaway | A | 1 | 掩盖跳剪/补细节 | concat 硬切×2 | — |
| 平行交叉剪 Cross Cut | A | 1 | 并置/悬念 | concat 交替硬切 | — |
| 旋切 Spin | B | 4 | 情绪翻转（稀缺） | 无直接项 | RotateScaleVanish / Swirl |
| 滚切 Roll | B | 3 | 卷轴母题 | 无直接项 | Rolls |
| 变焦冲模糊 Zoom Blur | B | 4 | 冲焦点（稀缺） | 近似 zoomin + hblur | CrossZoom / DreamyZoom |
| 方向扭曲甩 Directional Warp | B | 4 | 方向转折（稀缺） | 无直接项（近 smoothleft/right） | directionalwarp / crosswarp |
| 覆盖揭示 Cover/Reveal | B | 2 | 层级切换 | coverleft… / revealleft… | — |
| 空间交换 Swap | B | 3 | 并列对比 | 无直接项 | swap |
| 频闪 Strobe | C | 4 | 卡点爆发（极稀缺） | fadewhite/fadeblack 多段序列 | — |
| 数字故障 Glitch | C | 4 | 数字母题（稀缺） | 无直接项 | GlitchMemories / GlitchDisplace |
| 通道错位 RGB Split | C | 4 | 震动/科技（稀缺） | 无直接项 | GlitchDisplace |
| 抖动切 Shake Cut | C | 3 | 撞击重音（稀缺） | concat 硬切 + 抖动 | — |
| 速度斜坡 Speed Ramp | C | 4 | 蓄力释放（稀缺） | setpts + minterpolate | — |
| 烧胶片 Film Burn | D | 3 | 复古/胶片（稀缺） | 无直接项 | FilmBurn / undulatingBurnOut |
| 撕纸揭页 Paper Tear | D | 2 | 东方/册页（稀缺） | 无直接项 | 待核（近 InvertedPageCurl） |
| 颗粒溶解 Grain Dissolve | D | 2 | 回忆/抒情（稀缺） | dissolve | dissolve / luminance_melt |
| 水痕扭曲 Liquid Warp | D | 3 | 水/梦境（稀缺） | 无直接项 | WaterDrop / ripple / crosswarp |
| 万花筒团花 Kaleidoscope | D | 3 | 纹样/华彩（极稀缺） | 无直接项 | kaleidoscope / powerKaleido |
| 排线擦除 Crosshatch | D | 2 | 版画/线稿（稀缺） | 无直接项 | crosshatch |
| 网点绽放 Halftone Bloom | D | 2 | 印刷/波普（稀缺） | 无直接项 | 待核（近 PolkaDotsCurtain） |
| 数据摩什 Datamosh | D | 3 | 数字/实验（极稀缺） | 无直接项 | StripDatamoshGlitch |
| 虹膜开合 Iris | D | 2 | 聚焦/默片（稀缺） | circleopen/circleclose/circlecrop | circleopen / CircleCrop |

> 全部 24 项 `status="spec"`、`inFilm=null`；完整字段（feel/motivated/impl/cheapTrap）见 `transitions.json`。ffmpeg xfade 全名单与 gl 来源见 `_expansion_draft.md`。
