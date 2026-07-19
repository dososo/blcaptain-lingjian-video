---
name: lingjian-video
description: 用对话式一句话触发"灵剪(lingjian)"短视频生产主干:从文本/链接/图片参考素材出发,经脚本→配音→画面三道人工审批门,产出可预览或可发布的竖屏短视频,并导出分发包。全流程可复跑、门禁可审计。当用户说"帮我做一条短视频""把这段文案/这个链接做成视频""生成抖音/小红书/YouTube 竖屏视频""跑灵剪主线""lj 脚本/配音/渲染/导出"等时使用。
keywords: [灵剪, lingjian, lj, 短视频, 竖屏视频, 抖音, douyin, 小红书, youtube, 文案转视频, 链接转视频, 脚本配音渲染, 三审, 视频导出]
---

# 灵剪 (lingjian-video) 通用 Agent 发布级短视频 Skill

灵剪是一个通用的发布级中文短视频生产 Skill,可在任意能跑命令的 AI Agent 里运行(经 `lj` CLI)。用户只说目标、给文案/素材/录音或授权,宿主 agent 负责安装依赖、检测并继承能力、引导补齐发布级 TTS 与画面能力,再编排"素材 → 脚本 → 配音 → 画面 → 底部字幕 → 渲染 → QA → 导出"。CLI 是底层执行引擎,不是普通用户主入口。

> 诚实前提:灵剪只保证流程可复跑、门禁可审计,不承诺成片质量或"爆款"。

## 灵剪的独家差异化(命根子,别丢)

市面 AI 视频"一句话出片"是黑箱:骰子摇一次,吐一条,你没法改。灵剪反过来 —— 一句话进,脚本 / 分镜 / 配音 / 画面 / 配乐 / 字幕 / 音效全自动,**但每一关,都能审**。五条差异化,任何一条丢了灵剪就退化成又一个黑箱:

1. **蓝图先行**:一部片由一张贯穿全片的蓝图统领(能量曲线 + 母题 + 每关产物与门禁),不是逐镜各自为政。(注:从流水线产物自动生成整片能量曲线仍在接入主线,当前 CLI 尚不自动产出,别对用户宣称已全自动生成。)
2. **本地导演控制台(director-board)**:每一关在本机 `localhost` 打开一个可读、可交互的导演板,把这一关的候选逐项摆给用户看。见下节红线。
3. **调研贯穿始终**:调研不是只在开头,而是每一关持续 —— 吸收顶级证据 → 内化基线 → 牵引产出;失败要补不凑。
4. **关卡确认,给候选不给 yes/no**:每一关不是问"行不行",而是给出候选让用户挑、让用户改,用户点头才进下一关。
5. **可审计**:每一关的产物、门禁、证据都可追溯复核(results.json + 报告 + evidence 日志);门禁绑 artifact,内容变更自动失效。

## 本地导演控制台(director-board)· 硬规则

- **控制台 = 本机服务,永不远程。** 每关的导演板只在 `localhost` / 本地静态服务打开(仓库 `director-board/` 内 `render.js` + `board.schema.json` + `standalone.html`)。**绝不**把任何云端 / 部署 / 隧道 / 开发调试地址(vercel、trycloudflare、ngrok、作者私有预览页等)当作用户控制台展示,也绝不写进任何面向用户或对外发布的产物。用户走的每一步,右侧打开的都是他自己机器上的页面。
- **数据契约**:每关产出符合 `board.schema.json` 的 `board.json`(meta + shots[],每镜 energy/script/signature/beats/transitions),渲染器逐镜展示 + 逐镜"确认"按钮;`handle.allConfirmed()` 全绿才允许进下一关。
- **同一渲染器横切每关**:风格关 / 脚本关 / 配音关 / 画面关只换 `meta` 文案与卡片字段复用,不为每关重写。
- **确定性**:禁 `Date.now` / 未播种 `random`,导演板可复现;纯原生 JS + SVG,无第三方库、无网络请求(读本地数据除外)。

## 普通用户工作流纲领(最高优先级)

- 不把 CLI、provider 矩阵、JSON、环境变量块甩给普通用户。宿主 agent 负责安装、检测、运行命令和解释结果;用户只需要说目标、确认内容、拖入素材/录音或授权。
- 每次只让用户做一个最短动作。不要同时给一堆选择;先按默认优先级自动继承和检测,缺什么再问什么。
- 发布级最短路径固定为:安装/初始化 → 能力门诊 → 补齐必需资源 → 脚本审阅 → 音色试听/选择 → 配音导演确认 → 配音试听审阅 → 画面审阅 → 渲染 → QA → 导出。
- 能自动继承的能力直接用;不能继承时,先问用户是否有现成资源。配音先要用户录好的口播音频;没有录音时才引导开通一个推荐 TTS。画面先要每镜真实视频素材或真正视频生成插件;不要把图片、模板动效、单图循环当发布级画面。
- 缺发布级能力时必须停下,用一句人话说明缺什么和下一步要用户提供什么。不要继续生成低质量 release,不要把样片说成可发布成片。
- 面向用户说“请拖入口播音频”“请拖入每镜视频素材”“我来帮你检查宿主插件是否可用”这类动作;不要让用户自己理解 `doctor --json`、`export VOLCENGINE_...` 或 provider 配置细节。
- 面向用户展示本地文件、审核 artifact、音频、视频、截图、导出包或证据日志时,必须使用可点击 Markdown 文件链接,并使用绝对路径;必要时带行号。不要只给相对路径或纯文本路径。示例:`[voice_plan.json](/Users/.../artifacts/voice_plan.json)`、`[full.wav](/Users/.../artifacts/voice_segments/full.wav)`。
- 用户没有录音时,默认只引导一个中文发布级 TTS 路径:打开火山豆包新版控制台开通页 https://console.volcengine.com/speech/new/setting/activate?projectName=default 开通服务/领取活动,再打开 API Key 管理页 https://console.volcengine.com/speech/new/setting/apikeys?projectName=default 创建 API Key。普通用户只需要 API Key;Resource ID 与 Voice Type 用灵剪默认值,不要让用户找旧版 APP ID、Access Token、Cluster ID、Voice Type。
- 用户拿到 API Key 后,按其系统给一条标准保存命令(`docs/ONBOARDING.md` 是唯一标准,逐字照搬):macOS 用 `security` 存进 Keychain、Linux 用 `secret-tool` 存进 Secret Service(两者 **service = account = `lingjian:<NAME>`**,前缀不能少,否则灵剪读不到)、Windows 用**用户环境变量**(`SetEnvironmentVariable(...,"User")` 或当前会话 `$env:`)。存后灵剪启动自动注入(`inject_stored_credentials` 读回),无需每次手动 export。命令用**单次** `stty -echo`+`IFS= read -r` 读入(不用 `security -w` 两次确认,长 key 粘两遍必报 `passwords don't match`),粘贴时不回显要明说“看不到字符是正常的”。必须说明“直接粘贴原文,不要加双引号,不要发到聊天里”;key 只进本机安全存储,不上传、不联网。
- 用户侧入口只暴露一句中文和两个可选收敛参数:`--style` 控制统一风格,`--profile` 控制平台+受众预设。不要让用户堆一堆比例、节奏、字幕、BGM flag;缺省用 `--style clean_product --profile douyin_product`。
- 可用 style:**4 套已实现风格库**(完整方法论见 `styles/<key>.md`)——`vox_cut`(Vox 编辑剪影·橙黑半调)、`dark_keynote`(暗场发布·史诗)、`cinematic`(写实电影感·国风人文)、`neue_sachlichkeit`(新客观主义·实物档案);另有通用收敛预设 `clean_product`、`bold_news`、`warm_lifestyle`、`tech_minimal`。**选风格后,必须读 `styles/<key>.md` 用它的色板/字体/质感/动画/prompt 约束去指导 Seedance/生图**,别只当标签。换风格 = 复用横切能力换皮重排,不重做。可用 profile: `product_intro`、`open_source_project_intro`、`tutorial_guide`、`review_comparison`、`ecommerce_sales`、`knowledge_explainer`、`douyin_product`、`xiaohongshu_life`、`shipinhao_knowledge`。这些只收敛导演契约和提示,不承诺爆款。
- 内容类型 Profile 的 `required_evidence` 必须进入每镜导演分镜确认单、`visual_plan.json`、`render_manifest.json` 和 QA;不能只停留在提示词或文档里。`--release --strict` 下,Profile 要求的素材/证据没有进入每镜 `expected_real_evidence` / `asset_strategy_v2` 时必须阻断。

## 视频需求澄清阶段(必须先做)

普通用户第一次触发灵剪时,先用人话收集最小需求,不要直接进入 provider、CLI、JSON 或环境变量说明。必须确认以下 7 项:

```text
我要做一条【平台】短视频,主题是【主题/产品/观点】。
画幅比例选择【9:16 / 16:9 / 3:4 / 4:3 / 1:1】,如果不确定,我会按平台推荐默认值。
内容依据是【一句话说明 / Markdown / 文档 / PDF / PPT / 网页链接 / GitHub 仓库 / 已有文案 / 其他素材】。
目标用户是【谁】。
希望观众看完后【下单/关注/咨询/理解某个观点】。
我现在有/没有现成视频素材。
我现在有/没有录好的口播音频。
```

执行规则:
- 用户已经给齐这些信息时,不要重复提问;先复述成一段清楚的制作目标,再进入能力门诊。
- 用户只给平台时,不能静默把抖音/小红书默认推断成 9:16 并继续。必须先让用户选择画幅比例:9:16、16:9、3:4、4:3、1:1;可以说明平台推荐默认值,用户不选时才采用默认值并在目标确认里明说。
- 用户只给主题、没有给内容依据时,不要直接编完整脚本。必须先问用户“这条视频要基于哪份内容做?”并让用户提供最方便的一种:一句话说明、Markdown、PDF、PPT、Word、网页链接、GitHub 仓库、产品介绍文案、已有脚本或截图。用户授权使用当前仓库/README/GitHub 链接时,才可把它作为内容依据。
- 用户确认内容依据后,先 ingest/extract 或读取该内容,再进入脚本生成。不能凭模型常识替用户编产品细节、功能边界、价格、授权或效果承诺。
- 用户缺视频素材时,不能直接跑发布级生成。必须先基于脚本拆出“每镜需要什么真实动态视频素材/生成资产”的清单,再让用户提供素材、授权宿主 agent 代采目标对象截图/录屏、或启用宿主 agent 中真正的视频生成插件。截图/录屏必须只采集目标对象内容,例如当前项目 README、Skill、CLI、QA、导出包、Codex 操作或终端输出;涉及当前屏幕时必须先确认隐私安全,用户不授权时只能给手动导入 mp4 的兜底。
- 开源项目介绍需要终端/QA/导出包证据时,宿主 agent 可以代跑 `lj ingest command --command ...` 把命令输出保存为项目内终端文本证据;这只是终端回放素材,不是屏幕录制。若用户/宿主已配置 `LINGJIAN_TERMINAL_RECORD_CLI`,可加 `--record` 采集真实终端录屏;未配置或失败时必须如实提示,不得伪造录屏。Codex 操作录屏可用 `lj ingest codex --scene-id ...`;默认只登记录屏任务,不会录当前屏幕。只有用户确认当前屏幕可录且无隐私内容后,才可加 `--allow-screen-recording` 触发 macOS `screencapture` 或 `LINGJIAN_CODEX_RECORD_CLI`;录屏失败或不可验证仍不能伪造成 captured。
- 用户缺口播音频时,先检查是否已有发布级 TTS key;没有才引导一个推荐路径。不要同时给多家 TTS 选择。
- 已有发布级 TTS key 时,不要隐藏使用哪个音色。先基于 provider 真实可用音色生成 5 个短试听,默认优先覆盖 2 个女声 + 3 个男声,让用户选一个;无法拉到列表或账号权限不足时只展示真实合成通过的音色,不要编造“热门前 5”或不可播放选项。如果当前账号只实际合成通过 1 个音色,必须明确说“当前账号只验证到 1 个可用音色”,并展示音色名称、`voice_id` 和试听文件。
- 用户选定音色或确认使用录音前,必须展示“配音导演确认单”,让用户确认语气、情绪、语速、停顿、重音和每镜表达方式。用户批准前,不要正式调用付费/发布级 TTS 生成全片配音。
- 每次只让用户补一个最短动作。例如先解决配音,再解决画面,不要把所有缺口一次性压给用户。

内容输入引导话术:

```text
接下来先确定内容依据。你可以直接给我:
1. 一段文字/Markdown;
2. 一个网页或 GitHub 链接;
3. PDF、PPT、Word 文档;
4. 已有脚本/产品介绍/截图。

如果你只是给了主题,我会先问你是否允许我使用当前仓库 README / GitHub 页面作为依据,确认后再写脚本。
```

## 配音三审必须包含语气情绪确认单

配音不是“选一个音色后直接生成”。脚本批准后、正式调用发布级 TTS 或接入用户录音前,必须先给用户看“配音导演确认单”。这一步是必经环节,不能省略。

每条视频至少确认:

```text
整体口播定位:产品介绍 / 教程说明 / 带货转化 / 知识科普 / 活动预告等。
目标听感:亲和、清晰、可信、兴奋、沉稳、专业或生活化。
语速策略:开头抓人、中段说明、证明处放慢、CTA 稍有行动感。
情绪曲线:每镜从 Hook、痛点、方案、证明到 CTA 的情绪变化。
停顿与重音:哪些词要强调,哪里需要短停顿,哪里不能连读。
分镜表达:每镜的语气、节奏、重读词、停顿点和结尾收束。
禁忌:不要广告腔、不要机器人腔、不要全程同一情绪、不要夸张吼叫。
试听策略:先用短句或第一镜试听;用户满意后再生成全片。
验收点:用户听完应觉得自然、像产品介绍、能听清价值和行动号召。
```

执行规则:

- 有用户录音时,先确认录音是否满足目标听感;不合适时提醒用户重录或改用发布级 TTS,不要静默继续。
- 使用火山豆包/OpenAI-compatible 等发布级 TTS 时,先展示配音导演确认单,得到用户确认后再生成正式音轨。调用付费 TTS 前仍要遵守成本/账号提示。
- 能用 provider 官方“语音指令/标签/SSML”时,只按官方文档已确认字段接入;字段未确认时,不要凭空编 API 参数。可先通过口播稿改写、标点、停顿和分镜逐段合成提升自然度。
- 对产品介绍视频,默认口径是“清晰、亲和、可信、有产品发布感”;开头略有悬念,痛点处更有共情,方案处稳定清楚,证明处放慢,CTA 处更有行动感。
- 配音生成后,仍要试听并让用户批准 `voice_plan.json` 或试听音频;用户说“不自然/情绪不对/声音变了”时,先调整配音导演稿或固定同一音色参数,不要直接进入画面。
- 配音试听后,必须给用户明确的反馈入口,例如:“如果满意,请说‘批准配音’;如果觉得太慢,请说‘压到 45 秒’;如果语气不对,请直接说‘更有激情一点 / 更像产品发布 / 更亲切 / CTA 更有号召力’。”不要只问“可以吗”。

## 画面三审必须是导演分镜确认单

画面三审不是让用户确认“旁白对应一个镜头”,而是确认“这一镜到底会看到什么、怎么动、怎么转场、字幕如何避让、声音如何配合”。没有导演分镜确认单,不要进入画面生成或批准 visuals。

出现位置:

- `visual_plan.json` 生成后、调用 `lj approve visuals` 前,必须立刻在对话里完整展开导演分镜确认单。
- 可以同时给 `[visual_plan.json](绝对路径)` 可点击链接,但链接只能作为补充,不能替代正文展示。
- 不能只给镜头文件路径、不能只说“请打开 visual_plan.json 查看”、不能只摘要成“画面/动效/转场/音效”。如果没有在聊天里完整展示确认单,就不得询问或执行“批准画面分镜”。
- 如果用户直接说“批准画面分镜”,但此前本轮还没有展示完整确认单,必须先停下补展示,再让用户确认一次;不能把这句话直接当作有效审批。
- 普通用户界面里默认展示“压缩但具体”的分镜确认单,不要只让用户打开 `director_review_sheet.md`。每次先展示全片风格锁:整体色调、主色/辅助色/背景色、字体/材质、明暗与运动气质。每镜至少展示:镜头目标/口播、画面会看到什么、素材策略与状态、构图、动效关键帧、转场、字幕、音效、批准前要看什么。完整长版仍保留在 `director_review_sheet.md` 和 `visual_plan.json` 里,链接只能作补充。
- 对话展示可以比完整 Markdown 短,但不能空泛。不要只写“动态图形 + 转场 + 字幕”,也不能把素材、构图、转场、音效压到文档里不展示;不要把 13 个字段逐字堆满屏。目标是让普通用户不打开文件也能判断每一镜是否拍对、是否需要补素材、是否可以批准。

参考 HyperFrames / motion-graphics 的成熟做法,灵剪画面三审必须遵守:

- Asset-first:先判断这一镜需要真实素材、界面录屏、动态图形、数据可视化、产品画面还是抽象动效;没有素材时先说明要生成/补齐什么,不能用静态图片或模板闪动凑数。
- Layout before animation:先锁主体区、文字区、底部字幕安全区、平台 UI 避让区、视觉焦点,再决定动画;主体、CTA 和字幕不能互相遮挡。
- Beat planning:每镜至少有开场 / 中段 / 收束 3 个视觉 beat,标清大致时间点和变化,不能入场后冻结。
- Motion variety:相邻镜头不得同版式、同运动、同节奏;全片要在统一风格下切换 kinetic title、界面滑入、数据聚焦、分屏对比、卡片展开、深度推近等不同视觉蓝图。
- Reuse-first, not template-loop:可复用 HyperFrames/Remotion 的成熟 block、caption、chart、callout、transition 能力,但不能只换文字循环同一个模板。
- Design system lock:色彩、字体语气、光影、描边、圆角、材质、空间留白必须统一;“酷炫”来自运动设计和视觉层次,不是随机闪光、图标堆砌和无意义特效。
- Keyframe evidence:每镜生成规格要能落到关键帧/状态变化,例如 0.0s 主体出现、1.2s 数据增长、3.0s 卡片翻转、结尾留 CTA;不能只写“动态展示”。
- Audio-aware motion:转场不要切在词中;BGM 比人声低 16dB;必要时标注点击音、提示音、数据增长音、转场 whoosh,但音效不能抢口播。
- Inspect and repair:渲染后要用 ffprobe、抽帧和 render_manifest 检查真实运动、字幕安全区、对比度、模板复用和静态图;不达标先修,不能用 LLM 自评放行。

每一镜给用户看的“导演分镜确认单”至少包含:

```text
镜头目标:这一镜承担 Hook / 痛点 / 方案 / 证明 / CTA 哪个叙事功能。
画面内容:具体出现什么主体、场景、产品/界面/数据/人物/素材。
素材策略:使用用户视频、宿主生成视频、界面录屏、动态图形或待补素材;图片只能作参考。
构图与焦点:主体位置、视觉焦点、前中后景、底部字幕和平台 UI 避让。
视觉元素:短标题、数据、图标、按钮、箭头、界面卡片、背景材质;哪些必须出现,哪些禁止。
动效与镜头运动:主运动、次运动、镜头推进/横移/缩放/遮罩/视差/卡片展开等。
关键帧节奏:按时间点列开场、中段、结尾状态,确保全时长都有发展。
转场设计:入场、出场、与前后镜头衔接方式,避免无意义闪白和乱跳。
字幕策略:底部安全区、每行字数、拆句、字号、描边/底色/遮罩、主体避让。
颜色与氛围:主色、辅助色、明暗、质感、统一 style_lock。
音乐与音效:BGM 情绪、提示音/点击音/转场音、音量关系。
禁止项:静态图放几秒、Ken Burns 冒充视频、模板循环、大段文字复读旁白、中心字幕遮挡主体。
验收点:用户看这一镜时应该能判断哪些东西必须生成出来。
```

这份确认单要用人话展示给用户,不要直接甩 JSON。展示给用户时必须完整列出上述所有核心项,不得简化成“画面/动效/转场/音效”等少数摘要项,也不得省略素材策略、构图焦点、关键帧、字幕策略、色彩氛围、禁止项和验收点。用户批准后,同一内容再写入 `visual_plan.json` 的结构化字段,供 HyperFrames/Remotion/外部生成器执行与 QA 复核。

展示格式要求:

- 每镜都要单独编号,并完整列出:镜头目标、画面内容、素材策略、构图与焦点、视觉元素、动效与镜头运动、关键帧节奏、转场设计、字幕策略、颜色与氛围、音乐与音效、禁止项、验收点。
- 每镜下面必须给一个清晰的“这一镜批准前你要看什么”结论。
- 最后再给用户反馈入口:“批准画面分镜 / 修改某一镜 / 补充素材 / 重做分镜”。不要只问“可以吗”。
- 对话里的普通用户展示版可以合并字段,推荐先给 4-6 行全片风格锁,再每镜 5-7 行:目标与口播、画面与构图、素材策略与状态、动效关键帧、转场/字幕/音效、批准前检查。若用户要求“展开/更细”,再按镜头补齐完整字段;若用户只想快速审阅,不要把完整长版硬塞到对话里。

`visual_plan.json` 中的权威用户审阅入口是 `director_review_sheet_v2.scenes[]`。每镜还必须包含 `asset_diagnosis`,明确素材状态、是否可作为发布级动态视频、下一步补齐动作。若 `asset_diagnosis_summary.non_publish_grade_count > 0`,给用户只展示 `asset_diagnosis_summary.single_next_action_zh` 作为当前最短动作,不要同时抛出一堆插件/key/素材选项。

P1 起,`visual_plan.json` 还必须包含 `director_knowledge_base_v1` 与 `director_router_summary`。每镜要展示 `engine_policy`、`route_reason`、`asset_strategy_v2`、`expected_real_evidence`、`director_knowledge_refs` 和 `caption_contract`,让用户能看懂这一镜为什么用 HyperFrames/Remotion/用户视频/待补素材,以及需要哪些真实证据画面。普通用户不需要手选引擎;宿主 agent 只把路由理由和缺口动作讲清楚。

Director Router 不能只写好看的解释字段。每镜 `engine_policy.generator`、`engine_policy.selected_engine` 必须和实际 `generator`/素材类型一致:HyperFrames 镜头就是 `hyperframes`,Remotion 镜头就是 `remotion`,用户动态视频就是 `user_video`,图片/缺素材就是 `needs_video_asset` 或参考素材。不要为了通过审核把 Router 文案改成发布级,但实际仍走图片、fallback 或其它生成器;`--release --strict` 会阻断这种不一致。

如果某镜路由到 Remotion,必须先向用户说明 Node/Chrome Headless 与 Remotion 商用 license 边界,并在用户确认后把 `engine_policy.license_confirmation.status=confirmed` 或等价确认字段写入产物。只写”Remotion 需要 license”不够;`--release --strict` 会阻断未确认 license 的 Remotion 镜头。

## 视频生产硬约束(测量不假设 · 每关可审)

踩坑固化的硬规则,违反即返工。核心一句:**别把”我设了这个值”当成”这件事发生了”。**

### 测量,不假设
- 一切时间点从素材测出来,不许估:配音停顿用 `silencedetect` 测、卡点用 whisper 逐字对齐测、音效接触点从源片逐帧测。字数估切点必错。
- 量的必须是”最终信号”,不是中间量:音效响不响,按成片真实增益后量(不是量原始文件);响度按成片 `loudnorm` 复测。
- 别用同义反复验证自己:在 T 放一个事件、又去 T 查它,永远通过——这不是验证。检查器和修复器不能共用同一个判断;换一把尺子,或直接读产物确认。
- 别给没想清楚的概念硬造数字当门禁:只有用户耳朵/眼睛验过的判据才配当硬门;自造指标先降级成提示,不许拦路一部要发布的片子。

### 改一半 = 没改
- 改了引用的一处,必须改另一处:改了片段名要改音效映射表、改了裁切要改文件名。”改了一半,另一半留在原地,然后拿着'我改过了'的印象往下走”是反复翻车的根因。
- 用对账门(断言)锁死:产物里每个镜头都要在映射表里、每个裁切窗口里必须真有声音、一个事件不许被两张表重复上声。断言失败即停,不放行。

### 音频
- 配音整段一次连贯合成,禁逐句拼接:逐句独立合成 + 逐句变速再拼 = 割裂变调;节奏靠文本 + 自然语调 + 画面卡点,时长用 `silencedetect` 反测。
- 无旁白模式(新客观主义等「作者退场、让对象自己说话」的片):`lj run/voice --no-voiceover` —— 不合成配音,文字卡(`on_screen_text`)代旁白承担叙事,镜时长按文字卡阅读时长定,音频 = BGM + SFX(都无则纯静音基轨)。QA 认 `voiceover=false` 不强制真实配音、字幕认文字卡。适合实物档案 / 蓝晒这类「演示不讲道理」的风格,别硬塞旁白。
- 音色必须用全文试听筛,不能用两句短句外推。AI 听不见,没资格替用户筛音色。
- 字幕 = 配音原文逐字,一字不省,且不带任何标点(用空格断);画面要呼应旁白提到的物件。
- 音效库文件常”一个文件塞十几记独立事件”,别当一段连续音裁;裁切窗口里出现”响—静—响”就是裁到了两记,返工。没合适的不硬放(宁缺毋滥)。
- BGM 固定低音量垫底,忌 ducking 抽拉造成忽大忽小;和音效共存靠挖频段坑,不是一个给另一个让路。末级不做动态压缩(会把顶高的瞬态压回去)。
- 成片响度硬标准:**总响度 −14 LUFS、真峰 ≤ −1 dBTP**(抖音 / B站 / YouTube 通用);对白是主体、规范到 −14~−16 LUFS,有人声时 BGM(music bed)压到**比对白低约 15–20dB**(人声不费力、音乐可感知但不掩盖字)。
- **★连贯硬规则(音乐 + 配音,一动就割裂):音乐全程固定音量、固定节奏,绝不跟情绪 / 段落改音量或改节奏——不 sidechain、不 ducking、不「呼吸」、不中途变速换曲。情绪匹配只靠「选一条情绪合适的曲 + 让它自身的高潮对齐画面高潮(时间对齐)」,不靠动音量动节奏。配音同理:整段一次合成、固定基准语速、自然语调,绝不逐句变速 / 逐句调。片头尾无人声时音乐自然更清楚,是固定垫底的自然结果,不主动抬压。**
- 配乐/音效来源:免版税 BGM/SFX 从 Pixabay(音效免署名)获取 —— Pixabay 无公开音乐/音效 API,由宿主 agent 用浏览器能力(Chrome use / computer use)按情绪搜并下载,或用户自带音频。拿到文件后经 `lj ingest audio --kind bgm`(或 `--kind sfx`)挂载,渲染自动混音(BGM 默认比人声低 16dB)。BGM 气质靠用户试听选,不擅自定。

### 画面(视频优先,不是网页/PPT)
- Seedance 首帧定成败:动作能不能做完由首帧几何决定——首帧把必经的物理约束摆死(如刀刃垂直穿过要剪的东西),模型就没有编造余地;光靠 prompt 写狠没用。
- 真视频为主 + 代码图形叠加:该用 Seedance 生真视频的地方不要用单图动效凑;文字/精确图形用代码,生命力/氛围交给视频生成。
- 每镜视频必须 ≥ 配音时长,不够用尾帧定格补(`tpad`),别用 `-shortest` 截掉音频尾。
- 现成真实素材优先搜真实源下载并标来源(logo/产品/史料),别 AI 凭空生成;真找不到才生图补。别过度版权焦虑(公开品牌资产标来源即用)。
- 生图能力在 Codex(内置 Image gen),灵剪本身不生图、只消费产出的 PNG 当参考/样片。跨 agent 调用范式:**Codex 宿主**直接用内置生图;**非 Codex 宿主(Claude / Gemini / Cursor 等)经 CLI 调 Codex 生图** —— `codex exec -s workspace-write --skip-git-repo-check "用生图能力生成<画面描述>,保存为 <路径>.png"`(本项目样片的图都是这样在 Claude 里生的)。环境预检查 codex CLI 可用(`lj setup` 已检测 codex_cli);中国题材锁东亚面孔 + 严格年代,封面/关键帧留白放标题、按目标比例构图。
- 手不是禁区:需要人的动作就正面清楚地拍手;唯一红线是别让”没有身子的手”凭空飘进画面。
- 审美克制,别画蛇添足:发光/光晕/粒子等外挂特效默认不加,惊艳靠构图光影节奏质感本身;图形标注只标可查证的真事实,不标”看起来很技术”的乱码(假装有文献感,和刀刃对不上断口是同一种病)。
- **渲染引擎分工(各发挥长处,不是二选一)**:**HyperFrames 是画面执行主力**(HTML+CSS+GSAP,agent 生成友好、Apache-2.0 任意规模免费、覆盖排版/字幕/图形/大字/3D(Three.js)/GPU(TypeGPU)/Lottie/数据驱动批量/云渲染);**Remotion 发挥它独有的长处**——`<Player>` 网页内实时调参预览(喂灵剪「控制台实时展示」)、成熟 AWS Lambda 规模化云渲染、React 数据驱动个性化批量。**Remotion 是 source-available、>3 人营利须付费**:路由到 Remotion 的镜必先过 license 确认门(见主线工作流,`--release --strict` 阻断未确认),合规方式(≤3人免费 / 授权核验 / 当独立管线产物当素材)由用户定。
- **交付坑(必守)**:内嵌浏览器 **block video**(autoplay / 多 `<video>` 切换都失败)→ **成片必须 `ffmpeg` 服务端合成单个 mp4** 才能内嵌播放,别把多个 video 标签丢给前端。

### 固化能力 = 硬约束(必调用 `capabilities/`,不是参考摆设)
灵剪的差异化内核在 `capabilities/`,宿主 agent 走每一步**必须调用**它们,不是可选参考——否则就退化成又一个「一键黑箱」:
- **音效** 必按 `capabilities/sfx-strategy/SFX_STRATEGY.md` 五铁律 + 21 动作→音效映射表:每记音效对应一个明确画面动作(motivated),找不到对应画面的**删**;快节奏截短去拖尾、高潮留余韵、**舒缓收尾不用低频拖尾**;跟念轻音不抢人声;音量靠**固定增益**分层(不 sidechain / 不 ducking);时间用 cadence 精确卡点。★音效 mp3 库不随发布仓打包(来自 hyperframes-media skill),用户需自备免版权 mp3,或用 `sfx_mix.py <full.mp4> <hits.json> <out.mp4> <你的音效目录>`(第 4 个位置参数指定音效目录),见 `SFX_STRATEGY.md`「库来源」。
- **转场** 必过 `capabilities/transition-library` 内容匹配器(`match.js`:按相邻镜能量差 ΔE + 语义 + 母题 + 风格荐转场)+ **稀缺守卫**(强转场全片默认 ≤3,超配额自动降级为隐形硬切/匹配剪辑);反廉价护栏(90% 隐形硬切、闪白/闪黑任一秒 ≤3 次)。默认硬切,强转场只压 2–3 个能量拐点。
- **卡点** 画面砸词/揭示/音效必用 `capabilities/cadence/cadence.py`(silencedetect 测配音停顿→语音段起点,`noise=-30dB d=0.05`):画面事件 start **绝不早于**对应词起点(可 −0.05~0.1s 让加速段提前、峰值正压词)。主线 `voice_plan.voice_cadence` 已按同一逻辑自动测。
- **版式** 字幕/大字排版按 `capabilities/layout-safety/TYPOGRAPHY_RULES.md`,防大字压标签、越界等 inspect 查不出的字形级溢出。
- **控制台** 每关候选用 **`lj console <项目> [--gate auto/voice/script/board] --json`** 起本机导演板:它按当前关自动生成候选页(配音关=音色卡+播放器;脚本/分镜关=`render.js` 能量曲线板+每镜确认),打印 `http://127.0.0.1:<port>/`,宿主 agent 在右侧浏览器打开、用户逐项确认(写回 `console_state.json`)。**别再把候选当文件甩进对话** —— 用控制台(见上文红线)。
这些能力全比例、全风格通用:换比例/换风格是**复用它们换皮重排,不重做**。

### 通则
- 别把一次事故概括成永久禁令:模型在进步,写死的能力假设会过期(例:早期”AI 生手会崩”→ 现在不是问题,再”禁手”反而是错的)。红线要窄、对准真正的失败模式。

## 何时用 / 何时不适用
适合:给了文案/链接/图片想做竖屏短视频;想走可审计流程并逐步过审;先出预览档(零配置)或具备真实能力后出发布档;导出分发包。
不适合/先澄清:要复杂动效/timeline/模板市场/AI 生图生视频/数字人(均不在 M1);要"保证上热门"(不承诺);只想聊运营选题(非主线核心,只能作明确标注的可选后续)。

## 能力前置与自检(先跑,别假设)

普通用户路径从与宿主 agent 对话开始:先运行 `lj setup` 并用人话说明"已继承 / 已具备 / 必须补齐 / 可选增强"。`doctor --json` 只给宿主 agent/审计脚本内部判断,不要让普通用户直接解读 JSON。

```bash
uv sync
uv run lj setup          # 能力仪表盘:优先继承已登录 CLI / 本机能力
uv run lj doctor --json  # 逐项体检;required 缺失时 exit code 非 0
```
- lj setup 优先继承已登录官方 CLI(claude/codex 作 LLM)。发布级 TTS 默认优先用户录音/云 TTS;Kokoro/Piper 中文本地 TTS 只算零 key 样片音,macOS say 与 espeak-ng 只算预览级,都不能默认冒充发布级配音。Piper 是用户自装 GPL 本地 TTS,灵剪只子进程调用。
- doctor 未 ready 时不要继续 release。
- 普通创作者路径见 `docs/CREATOR_QUICKSTART.md`;能力边界见 `docs/CAPABILITY_MATRIX.md`。

画面能力:
- visuals 会按场景生成 storyboard,字段包含 generator、visual_prompt、motion_spec、brief、expected_asset_path、duration_sec、asset_path、subtitle_burn。
- 发布级 generator 优先级:hyperframes/remotion/外部视频生成器 -> user-asset 视频 -> fallback_solid。image-gen 只产静态参考图,不能作为发布级视频能力。
- 当前已验证的零 key 视觉样片路径是 HyperFrames:检测到 `npx hyperframes` 时,lj 通过薄子进程适配器按镜生成 mp4 到 `expected_asset_path`;这只能证明动态样片流程,不能自动算发布级视觉。发布级必须使用用户每镜真实视频素材,或显式验证过能生成内容相关动态视频资产的宿主插件/外部生成器。lj 不 import、不 bundle Remotion/HyperFrames SDK,只委托 CLI 或消费落盘资产并用 FFmpeg 组装。
- 宿主 agent 用户若已安装/启用 HyperFrames/Remotion 或其他视频生成插件/skill,宿主 agent 可按 storyboard 的 `visual_prompt` 与 `motion_spec` 渲染更丰富的每镜视频产物到 `expected_asset_path`;自备每镜 mp4/mov/m4v 是发布级稳态回落。imagegen/图片只可做样片/参考。缺插件时要先引导用户在宿主 agent 的插件/skill 安装入口安装/启用,或让用户提供视频素材;仍缺失才回落 fallback_solid,且只能称为预览/占位。
- Remotion 只能作为 opt-in 精密执行器;启用前必须让用户确认 license,并把确认写入 `engine_policy`。未确认时不能继续发布级 strict 导出。

两档模式:
- 预览档(零配置):--provider mock 出脚本/配音,render 默认 preview。mock 产物仅预览,禁止当发布质量。
- 发布档(需最小集合齐备):① 真实 LLM(继承 claude/codex,或 OpenAI-compatible/key/CLI);② 用户录好的口播、云 TTS 或经用户确认自然的真实 TTS CLI;③ 真实动态视频画面(HyperFrames/Remotion/外部生成器输出的视频资产,或用户每镜 mp4/mov/m4v);④ FFmpeg/ffprobe 且支持 drawtext/libfreetype/AAC;⑤ 中文字幕在底部安全区。Kokoro/Piper/say/espeak-ng、静态图片、imagegen PNG、fallback_solid 与内置样片模板只能预览/样片,`--strict --release` 会阻断。

真实 provider 环境变量(仅从环境读取,不写入 artifact/日志/release 包):
```bash
export LINGJIAN_LLM_CLI=your-llm-command
export LINGJIAN_TTS_CLI=your-tts-command
export OPENAI_BASE_URL=... OPENAI_API_KEY=... OPENAI_MODEL=...
export OPENAI_TTS_BASE_URL=... OPENAI_TTS_API_KEY=... OPENAI_TTS_MODEL=...
export VOLCENGINE_TTS_API_KEY=...
```

## ★脚本/内容生成:宿主 agent 自产优先(别 fork 外部 CLI)

灵剪是 **agent 通用 skill**,宿主 agent(Claude / Codex / Gemini / Cursor…)**本身就是那个 LLM**。脚本、旁白、分镜文案这类「需要智能创作」的内容,**第一优先级是宿主 agent 直接产出**,再交给 `lj` 做结构化 / 校验 / 门禁 —— **不要**用 `--script-provider auto/claude/codex` 去 shell 调一个外部 `claude -p` / `codex exec` 子进程。你在 Claude 里跑,再 fork 一个无头 `claude` 是南辕北辙:多一层、易超时、常因未登录而失败。

**LLM 宿主(你自己就是 LLM)默认走这条:**

```bash
# 1) 导出创作契约(钩子库 / 风格锁 / 素材摘要),你按它创作,才对得上风格
uv run lj script ./projects/demo --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --style vox_cut --profile product_intro --emit-contract --json
#    读 artifacts/script_contract.json → 你(宿主 agent)按顶级脚本方法论 + 契约,直接创作脚本
#    写成 {"scenes":[{"id":"s1","narration_text":"…"}, …]} 存成 authored.json
# 2) 回填(provider 记为 host_authored,非 mock)
uv run lj script ./projects/demo --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --style vox_cut --profile product_intro --from-file authored.json --json
```

聚合命令同理:`lj run ... --script-provider host` 到脚本关会**导出契约并暂停**(`status: awaiting_host_authoring`),等你自产脚本 `--from-file` 回填后再继续 `lj run`。

**`--script-provider auto/claude/codex/openai` 只留给「宿主不是 LLM」的场景**:纯自动化 / CI / 被非智能程序驱动、或宿主 agent 无创作能力时,才委托外部 LLM CLI 或 OpenAI-compatible API 兜底。`mock` 只出占位骨架,仅预览、禁当发布质量。

## 主线工作流(按真实命令)
> 当前 CLI 支持 `lj run` 聚合命令。默认会在 script / voice / visuals 三审点停下;显式 `--yes` 仅用于 CI 或用户明确授权的自动审批。所有命令加 --json;前缀统一 uv run lj;⏸ 为三审暂停点,必须停下等用户确认再 approve。**脚本关:LLM 宿主走上一节「宿主自产」(`--script-provider host` 或 `lj script --emit-contract`/`--from-file`),不要 fork 外部 CLI。**

每个暂停点给用户展示 artifact 时,必须同时给可点击文件链接。比如脚本审阅给 `[script.json](绝对路径)`,配音审阅给 `[voice_plan.json](绝对路径)` 与 `[full.wav](绝对路径)`,画面审阅给 `[visual_plan.json](绝对路径)`,导出后给 `[video.mp4](绝对路径)` 和导出包目录链接。

```bash
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --script-provider host --voice-provider auto --json
# ⏸ 审阅 artifacts/script.json 后:
uv run lj approve script ./projects/demo --approved-by '你的名字' --json
# ⏸ 先展示配音导演确认单:整体口播定位、语气情绪、语速、停顿、重音、每镜表达。用户确认后才生成正式配音。
uv run lj run ./projects/demo --json
# ⏸ 审阅 artifacts/voice_plan.json 后:
#   必须给用户三个反馈入口:批准配音 / 压到目标时长 / 调整语气情绪。
uv run lj approve voice ./projects/demo --approved-by '你的名字' --json
uv run lj run ./projects/demo --json
# ⏸ 审阅 artifacts/visual_plan.json 后:
uv run lj approve visuals ./projects/demo --approved-by '你的名字' --json
uv run lj run ./projects/demo --json
```

真做内容时,脚本关走**宿主自身 LLM 自产**(`--script-provider host`,见上「宿主自产」节),不要默认 mock、也不要 fork 外部 claude/codex CLI:

```bash
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --script-provider host --voice-provider auto --json
```

如果使用火山豆包 TTS 且用户还没选音色,`lj run` 必须先停在 `voice_options` 阶段,生成 `artifacts/voice_options.json` 与默认 5 个试听音频,优先为 2 个女声 + 3 个男声。用户试听后再用选中的 `voice_id` 继续正式配音;不要默认隐藏音色直接合成。如果实际少于 5 个可用试听,就明确告诉用户当前账号只验证到这些可用音色,不要表现成系统遗漏了其他音色。

音色选定后,不要立刻生成全片配音。必须先按脚本生成配音导演确认单,用人话列出整体口播定位、每镜语气情绪、语速、停顿、重音和 CTA 表达;用户批准后再调用正式 TTS。若用户要求“产品介绍感”,默认采用清晰、亲和、可信、有产品发布感的表达,但仍要展示给用户确认。

已有录好的口播音频时:

```bash
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --script-provider host --voice-audio-file narration.m4a --json
```

逐条命令备选:
```bash
uv run lj setup && uv run lj doctor --json
uv run lj init ./projects/demo --name "演示项目" --json
uv run lj ingest text  ./projects/demo --file examples/product_intro_zh.txt --json
#   或 ingest url  ./projects/demo --url '粘贴网页链接' --screenshot --json
#   或 ingest command ./projects/demo --command "uv run lj doctor --json" --role terminal --json
#   或 ingest codex ./projects/demo --task "展示 lingjian-video 进入分镜三审" --json
#      默认只登记 Codex 操作录屏任务。确认当前屏幕可录且无隐私内容后,
#      才可加 --allow-screen-recording 触发 macOS screencapture 默认适配器或
#      LINGJIAN_CODEX_RECORD_CLI;也可手动拖入 mp4。只有 ffprobe 确认视频流后,
#      才会成为 Codex 操作录屏证据。失败时只记录任务,不伪造录屏。
#   或 ingest image ./projects/demo --file '图片文件路径' --role cover --json
uv run lj extract ./projects/demo --json
# LLM 宿主:--emit-contract 拿契约 → 自产 → --from-file 回填(见上「宿主自产」节);下行 mock 仅零配置预览
uv run lj script ./projects/demo --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj approve script ./projects/demo --approved-by '你的名字' --json
uv run lj voice ./projects/demo --provider mock --voice test-voice --json
# 或者用用户录好的口播音频:
uv run lj voice ./projects/demo --provider auto --voice user --audio-file narration.m4a --json
uv run lj approve voice ./projects/demo --approved-by '你的名字' --json
uv run lj visuals ./projects/demo --engine ffmpeg_card --template product --json
# 审阅 artifacts/visual_plan.json:确认每镜 generator、visual_prompt、motion_spec、expected_asset_path。
# 宿主启用了 HyperFrames/Remotion/imagegen 时,按 expected_asset_path 生成 mp4 等动态视频资产;图片只可做样片/参考。缺宿主能力时先引导安装/启用插件或 skill,允许用户放自有视频素材,最后才回落卡片。
uv run lj approve visuals ./projects/demo --approved-by '你的名字' --json
uv run lj render ./projects/demo --platform douyin --language zh-CN --ratio 9:16 --json   # 发布档追加 --release
uv run lj qa ./projects/demo --json                                                       # 发布前:qa --release --platform douyin
uv run lj export ./projects/demo --platform douyin --language zh-CN --ratio 9:16 --json   # 全平台:--all-platforms;发布包:--release
```
辅助:uv run lj status|reindex ./projects/demo --json;uv run lj credentials status|forget <name> --json。
> 平台参数(诚实):--platform 为自由字符串。M1 中 youtube 会额外产出缩略图/描述/章节等附加文件;其余平台按通用结构导出。竖屏常用 --ratio 9:16。

## Guardrails(硬规则,不可绕过)
- 不绕审批门:三审必须先 approve 才能 render;到暂停点停下、请用户确认,不替用户批准。
- mock 不可 release:mock 产物仅预览;--release 必须真实 LLM+真实 TTS 且 doctor ready。
- 缺能力就诚实停:doctor 未 ready(FFmpeg 无 drawtext、无真实 TTS/LLM 等)时不硬凑、不写假产物,告知缺什么再停。
- 绝不把真实 key 写进仓库/日志/导出包;doctor 只输出脱敏状态;不在对话回显完整 key。
- 发布前先 QA:qa --release 有 hard_failures 时不导出发布包。
- 不假装动态画面:宿主生成器失败、产物不存在、同一资产反复循环或只使用内置样片模板时,必须告诉用户这不是发布级真实视频;严格发布用 `--strict` 阻断。
- 不假装发布级配音:Kokoro/Piper/say/espeak-ng 是样片/预览级真实语音;严格发布用 `--strict` 阻断并报告 `RELEASE_AUDIO_IS_PREVIEW_VOICE`。商用发布优先使用用户录音或自然中文云 TTS。
- 配音缺失时不硬闯:先引导用户提供已录好的口播音频并用 `--voice-audio-file` 接入;没有录音时再引导配置发布级 TTS API。Kokoro 只能用于免费样片试听。
- 不跳过配音导演确认:脚本批准后、正式 TTS 生成前必须确认语气情绪、语速、停顿、重音和每镜表达;不要让用户只选音色就直接花费 TTS 额度生成全片。
- 火山豆包 TTS 引导要给新版直接入口:先打开 https://console.volcengine.com/speech/new/setting/activate?projectName=default 开通服务/领取活动,再打开 https://console.volcengine.com/speech/new/setting/apikeys?projectName=default 创建 API Key。提醒用户不要在聊天里发送完整 key;只在本机环境配置 `VOLCENGINE_TTS_API_KEY`。
- Seedance 文生视频(用户无每镜视频素材、又想要 AI 动态画面时)引导:先打开火山方舟「开通管理」 https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement 只勾所需 Seedance 模型(别点全选);**Seedance 2.0 系列开通硬门槛=账户余额 > 200 元**(官方,余额不够报 `BalanceNotEnough`),门槛是预留不是扣费、开通后按量后付费。再打开「API Key 管理」 https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey 创建 Key(ARK key 是 UUID 形态、实测长 46、无 sk-/ak- 前缀)。拿到后按 `docs/ONBOARDING.md` 的标准命令存进安全存储(service=account=`lingjian:VOLCENGINE_ARK_API_KEY`)。禁真人脸参考图;认火山方舟官方入口,别下蹭名仓库。
- 火山音色选择要诚实:用实际合成探测(逐音色试合成)得到当前账号可用音色,最多给 5 个试听;不要把旧版/不可用音色写成可选项,也不要声称“官方热门”除非有官方排行依据。
- 配置 key 按 `docs/ONBOARDING.md` 的三平台标准命令(service=account=`lingjian:<NAME>`,前缀不能少):macOS `printf`+`stty -echo`+`IFS= read -r`+`security`(不用 `read -s -p`、不用 `-w` 两次确认),Linux `secret-tool store`,Windows 用户环境变量/`$env:`。存后灵剪启动自动注入,无需再手动 export。
- 给 HyperFrames/Remotion 的生成指令必须包含确定性规则:禁 `Date.now`、未播种 `random`、用 `setTimeout` 做渲染时序、渲染期网络请求、`repeat:-1` 无限循环;使用帧驱动或 paused master timeline;固定 width/height/fps;字幕最后叠加且位于底部安全区;剪切点 30ms 淡入淡出,不在词中切;BGM 比人声低 16dB。

## Honesty(必须遵守)
- 绝不编造产物/统计/成功结果:没真跑出来的不许写"已完成"。
- 跑真命令验证,而非看文件存在:以命令 --json 返回(ok/status/release_ready/exit code)为准。
- 不承诺成片质量、不承诺爆款:只保证流程可复跑、门禁可审计。
- 能力以 doctor 为准:是否可发布唯一权威是 doctor 的 ready 与各项状态。
- 不夸大未实现的部分(见下)。

## Do-NOT
- 不静默降级为纯色卡片、静态图片、Ken Burns、单图循环或内置样片模板后继续称为发布级。
- 不静默把零 key 引擎切换成付费引擎;调用火山、fal、picsart 等付费/账号能力前,先说明成本/账号前提并取得用户确认。
- 不把 LLM 自评当质量门。发布质量结论必须来自真实命令、render_manifest、ffprobe/抽帧与 QA hard gate。
- 不把 say、fallback_solid、imagegen PNG、静态图片或 Kokoro/Piper 样片音说成商业发布级效果。
- 不绕过三审,不替用户批准脚本/配音/画面。

## Should / ShouldNot 触发样例
- Should: “用灵剪帮我把这段文案做成 45 秒抖音带货短视频,风格清爽产品说明。”
- Should: “跑 lingjian-video,我有口播音频和每镜视频素材,请帮我审稿、配字幕、QA 后导出。”
- Should: “用 `--style tech_minimal --profile shipinhao_knowledge` 做一个知识类竖屏视频。”
- ShouldNot: “随便给我生成一条能发的视频,缺素材就用一张图动一动。”这必须先解释发布级画面要求。
- ShouldNot: “不用我确认,直接帮我开通付费生成。”这必须停下让用户确认账号和费用。

## 已知边界(如实告知用户)
- mock 仅预览,非发布质量。
- HyperFrames/Remotion/imagegen 由宿主 agent 或本机 CLI 委托提供;灵剪核心不内置、不 bundle、不 import SDK。
- 宿主 agent 用户可以安装/启用 HyperFrames/Remotion/imagegen 插件或 skill;缺失时应先引导安装,不是直接把 fallback 当真实画面。
- ffmpeg_card/fallback_solid 是回落卡片路径,不是动态画面质量承诺。
- 订阅通常不含 TTS;LLM 可继承 claude/codex,TTS 一般需本机或单独配置。
- 中文商用发布 TTS 首选用户录音或火山豆包,次选 OpenAI-compatible/其他云 TTS;Kokoro 是零 key 中文默认,不承诺音色质量。Piper 为 GPL 用户自装路径。
- say 仅 macOS;espeak-ng 属预览级本机 TTS,不属于发布级最小集合。
- 默认 Homebrew FFmpeg 可能缺 drawtext;render --release 会硬失败,以 doctor 为准。
- 本地导演控制台:**`lj console <项目>` 已实现(v1.1.0)** —— 起本机 `localhost` 服务 + 按当前关自动生成候选页(配音关=音色卡+内联播放器;脚本/分镜关=`render.js` 能量曲线导演板 + 每镜「确认」)+ `/confirm` 写回 `artifacts/console_state.json`;宿主 agent 把打印的 URL 在右侧浏览器打开、用户逐项确认。渲染器 `render.js` + 契约 `board.schema.json` 随仓库发布。**仍在推进(别宣称已做)**:画面关(`visual_plan.json`)专用视图、确认写回自动转 `lj approve`、`lj run` 自动在每关调起 console。`apps/web`(Next.js)仍是骨架,非当前控制台路径。
- MCP 尚未实现(packages/mcp_server 仅有 README),不能对外宣称 MCP 可用。
- 平台知识包/爆款算法非核心,只能作明确标注的可选后续。
