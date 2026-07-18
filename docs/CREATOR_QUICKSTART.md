# 创作者快速开始

这份文档面向普通自媒体用户。主入口是在 Codex app 里对话,不是自己手敲完整 CLI。CLI 命令写在这里,是 Codex 代你执行和排错时的底层依据。

## 先做一次能力检测

```bash
uv sync
scripts/install_skill_links.sh
uv run lj setup
```

看 `lj setup` 的结论:

- LLM 已继承 Claude/Codex:可以用订阅能力写脚本,不需要 key。
- TTS 选中用户录音、火山豆包或 OpenAI-compatible:可以进入发布链路。Kokoro/Piper 只能做零 key 样片音;macOS say/espeak-ng 只能预览,严格发布会阻断。
- visuals 候选里出现 host_hyperframes:说明可以生成样片动效或委托宿主尝试;只有 `safe_for_release=true` 或用户已提供每镜真实视频素材时才算发布级视觉。若仍是 fallback_solid,请安装/启用真实画面插件或提供每镜视频素材。
- render OK:本机 FFmpeg/ffprobe/drawtext 已能出片。

## 第一次只要这样说

普通用户不需要先懂 CLI、provider 或 JSON。把下面这段改成自己的需求发给 Codex:

```text
我要做一条【平台】短视频,主题是【主题/产品/观点】。
内容依据是【一句话说明 / Markdown / 文档 / PDF / PPT / 网页链接 / GitHub 仓库 / 已有文案 / 其他素材】。
目标用户是【谁】。
希望观众看完后【下单/关注/咨询/理解某个观点】。
我现在有/没有现成视频素材。
我现在有/没有录好的口播音频。
```

如果你只给了主题,灵剪应该先问你“这条视频要基于哪份内容做?”。你可以直接拖入 Markdown、PDF、PPT、Word、已有脚本、产品介绍,也可以给网页或 GitHub 链接。只有你授权使用当前仓库/README/GitHub 页面时,Codex 才能把它作为脚本依据。

如果没有现成视频素材,灵剪必须先把脚本拆成“每镜需要什么真实动态视频素材/生成资产”的清单,再引导你提供素材或启用 Codex app 中的视频生成插件。不要直接把静态图片、单图循环、Ken Burns 或模板闪动当成发布级视频。

## 配音审核要先确认语气情绪

脚本批准后,不要直接生成全片配音。灵剪应该先给你一份“配音导演确认单”,让你确认这条视频听起来应该是什么感觉。

至少要说清:

- 整体口播定位:产品介绍、教程说明、带货转化、知识科普还是活动预告。
- 目标听感:亲和、清晰、可信、兴奋、沉稳、专业或生活化。
- 语速策略:开头抓人、中段说明、证明处放慢、CTA 稍有行动感。
- 情绪曲线:Hook、痛点、方案、证明、CTA 每一段的情绪变化。
- 停顿与重音:哪些词要强调,哪里需要短停顿,哪里不能连读。
- 分镜表达:每镜的语气、节奏、重读词、停顿点和结尾收束。
- 禁忌:不要广告腔、不要机器人腔、不要全程同一情绪、不要夸张吼叫。
- 试听策略:先试听短句或第一镜;满意后再生成全片。

用户确认这份配音导演稿后,Codex 才能调用火山豆包/OpenAI-compatible 等发布级 TTS 生成正式音轨。如果只是选了音色,但还没确认语气情绪,这一步不算完成。

正式音轨生成后,Codex 必须播放或指明试听文件,并给你明确反馈入口:

```text
如果满意,请说“批准配音”。
如果觉得太慢,请说“压到 45 秒”。
如果语气还不对,请直接说哪里不对,比如“更有激情一点 / 更像产品发布 / 更亲切 / CTA 更有号召力”。
```

你不需要学习参数名;只要按听感反馈,Codex 负责改口播导演稿、重配音或进入下一步。

## 画面三审要看什么

到 visuals 审核点时,不要只看“这一镜说什么”。灵剪应该给你一份导演分镜确认单,每一镜至少说清:

这份确认单应该**直接出现在 Codex 对话里**。`visual_plan.json` 链接只能作为补充,不能替代正文展示。如果 Codex 只给你文件路径、只让你自己打开 JSON、或只摘要成“画面/动效/转场/音效”,这一步不合格,你应该要求它重新展开完整导演分镜确认单。

- 这一镜的目标:Hook、痛点、方案、证明还是 CTA。
- 画面具体内容:主体、场景、产品/界面/数据/人物/素材。
- 素材策略:用用户视频、宿主生成视频、界面录屏、动态图形还是待补素材;图片只能作参考。
- 构图与焦点:主体放哪里、第一眼看哪里、底部字幕区和平台 UI 如何避让。
- 动效和关键帧:开场、中段、结尾分别发生什么,是否有镜头推进、横移、缩放、遮罩、视差、卡片展开、数据增长等真实变化。
- 转场:这一镜如何接上一镜和下一镜,不要无意义闪白或乱跳。
- 字幕策略:底部安全区、每行字数、拆句、字号、描边/底色/遮罩,并避让主体。
- 视觉元素:短标题、数据、图标、按钮、箭头、界面卡片、背景材质,以及禁止出现的装饰。
- 色彩与氛围:主色、辅助色、明暗、质感,全片风格要统一但镜头版式不能千篇一律。
- 音乐与音效:BGM 情绪、提示音/点击音/转场音,人声优先。

这一步参考的是视频制作里常见的 asset-first、layout-before-animation、beat planning 和 inspect/repair 工作法:先锁素材与构图,再设计运动;每镜至少有开场/中段/收束 3 个 beat;相邻镜头不能同模板换字;渲染后用抽帧和 QA 复核,不能用 LLM 自评替代真实检查。

Codex 给你展示画面三审时,必须完整列出上面这些项目。不能只摘要成“画面、动效、转场、音效”,也不能省略素材策略、构图焦点、关键帧、字幕策略、色彩氛围、禁止项和验收点。

技术上,这份确认单会写进 `artifacts/visual_plan.json` 的 `director_review_sheet_v2.scenes[]`。如果某一镜缺发布级动态素材,`asset_diagnosis_summary.single_next_action_zh` 会给出当前唯一最短动作,例如“请为这一镜提供 mp4/mov/m4v 视频素材,或启用 HyperFrames/Remotion 生成动态视频”。这一步的目标是让你先看懂缺什么,不要被一堆 provider、插件或 JSON 字段干扰。

批准前,Codex 必须给你明确反馈入口:

```text
如果满意,请说“批准画面分镜”。
如果某一镜不满意,请说“修改第 3 镜,画面更像真实 Codex 操作”。
如果你要补素材,请直接拖入对应镜头视频。
如果整体方向不对,请说“重做画面分镜”。
```

P1 起,同一个 `visual_plan.json` 还会写入 `director_knowledge_base_v1` 和 `director_router_summary`。你不需要自己选择 HyperFrames 还是 Remotion;Codex 会把每镜的 `route_reason` 翻译成人话,告诉你为什么这一镜适合用宿主动态视频、用户视频素材,或为什么还缺真实视频素材。对“灵剪是什么/开源项目介绍”这类视频,`asset_strategy_v2.required_evidence` 会优先要求 GitHub、README、Codex 操作、终端/QA 证据和导出包/Star CTA,避免全片只剩抽象模板。

## 你有一段文案

把文案保存成 `input.txt`,然后对 Codex 说:

```text
请使用 lingjian-video。先做灵剪能力门诊,用人话告诉我已继承、已具备、必须补齐、可选增强。然后把 input.txt 做成 45 秒抖音竖屏视频,脚本用 auto 继承当前 Codex/Claude 能力,默认 `--style clean_product --profile douyin_product`。配音优先使用我提供的口播音频,或引导我配置火山豆包/OpenAI-compatible 等自然中文 TTS;Kokoro 只能先出样片试听。画面优先使用我提供的每镜真实视频素材,或用 Codex app 中的 HyperFrames/Remotion/视频生成插件生成动态内容画面;imagegen 静图只能做参考图。不要把一张图片放几秒、Ken Burns、轻微缩放、内置模板或 fallback 卡片说成发布级视频。
```

对应命令:

```bash
uv run lj run ./projects/my-video \
  --name "我的视频" \
  --input-file input.txt \
  --script-provider auto \
  --voice-provider auto \
  --platform douyin \
  --ratio 9:16 \
  --style clean_product \
  --profile douyin_product \
  --json
```

默认会停在 script / voice / visuals 三次审核点。script 通过后,还必须先确认配音导演稿,再生成正式配音;voice 通过后才进入画面三审。

## 你已经录好了口播音频

如果你有 `narration.m4a`、`narration.wav` 或 `narration.mp3`,可以不用 TTS:

```bash
uv run lj run ./projects/my-video \
  --name "我的视频" \
  --input-file input.txt \
  --script-provider auto \
  --voice-audio-file narration.m4a \
  --platform douyin \
  --ratio 9:16 \
  --json
```

这条路径会把录音复制进项目 artifact,`provider_id=user_audio`,不标 mock,也不会把你的原始路径写进导出包。

## 你没有配音能力

按优先级选择:

1. 有录好的口播:用 `--voice-audio-file`。
2. 零 key 样片 TTS:安装 Kokoro,只用于先听节奏和流程。
3. 商用质量云 TTS:配置火山豆包或 OpenAI-compatible TTS。
4. 只想预览:用 Kokoro/Piper/macOS say/espeak-ng,但它们不是发布级;`--strict --release` 会因 `RELEASE_AUDIO_IS_PREVIEW_VOICE` 阻断。

Kokoro:

```bash
uv sync
npx hyperframes tts --list
uv run lj setup
```

Piper(GPL-3.0,用户自装,灵剪只子进程调用):

```bash
pip install piper-tts
python3 -m piper.download_voices zh_CN-huayan-medium
uv run lj setup
```

火山豆包:

先打开新版开通页 https://console.volcengine.com/speech/new/setting/activate?projectName=default 开通服务/领取活动,再打开 API Key 管理页 https://console.volcengine.com/speech/new/setting/apikeys?projectName=default 创建 API Key。

普通用户只需要复制 `API Key`。`Resource ID` 和 `Voice Type` 使用灵剪默认值;高级用户才覆盖。不要把完整 key 发给 Codex 聊天窗口,只在本机环境配置。

```bash
export VOLCENGINE_TTS_API_KEY=...
uv run lj doctor --json
```

有发布级 TTS 后,不要盲选隐藏默认音色。灵剪应先基于当前账号真实可用的音色生成最多 5 个短试听,让你选一个;如果火山列表接口暂不可用,只展示已实际合成通过的默认音色。不要把旧版或未验证的音色写成“热门前 5”。

底层命令是:

```bash
uv run lj voice-options ./projects/my-video --provider volcengine_tts --json
```

它会生成 `artifacts/voice_options.json` 和 `artifacts/voice_options/option_*.wav`。你只需要试听后告诉 Codex 选第几个音色;Codex 会带着对应 `voice_id` 继续正式配音。

音色选好后,灵剪还必须先展示配音导演确认单。比如产品介绍视频应默认是“清晰、亲和、可信、有产品发布感”,但每镜的语气、停顿和重音仍要给你确认;确认后才正式消耗 TTS 调用生成全片音轨。

正式音轨生成后,不要让用户猜下一步。必须明确告诉用户可以“批准配音”、“压到 45 秒”或直接描述语气问题。

## 你需要真实画面

灵剪不内置 Remotion/HyperFrames SDK。检测到 `npx hyperframes` 后,lj 可按 `visual_plan.json` 的 `expected_asset_path` 生成样片动效 mp4,再统一组装。它能证明流程,但如果画面只是一张图/模板闪几秒,不算发布级视频。发布级路径必须是自备每镜真实 mp4/mov/m4v,或宿主插件生成的动态内容视频。

自备素材路径:

```text
projects/<项目>/assets/scenes/s1.mp4
projects/<项目>/assets/scenes/s2.mp4
```

`.png/.jpg` 只能做样片或视觉参考。即使加 Ken Burns/zoompan,`--strict --release` 也会阻断。

如需让 Codex 宿主自动生成更丰富画面,优先在 Codex app 的 Plugins / Add to Codex 中安装或启用对应插件。命令只是备用:

```bash
npx skills add heygen-com/hyperframes
npx skills add remotion-dev/skills
```

上面两个标识符分别来自 HyperFrames 与 Remotion 的官方 skill 安装入口。HyperFrames 需要 Node.js 22+ 与 FFmpeg,本地渲染零 key;Remotion 需要 Node.js/Chrome Headless,营利组织超过 3 人使用需核对商用 license。若 skills CLI 或 Codex 插件市场发生变化,以官方文档为准:

- HyperFrames: https://hyperframes.heygen.com/quickstart
- Remotion Agent Skills: https://www.remotion.dev/docs/ai/skills

安装或启用后,新开 Codex 会话,再跑:

```bash
uv run lj setup
```

然后运行:

```bash
uv run lj visuals ./projects/my-video --engine ffmpeg_card --template product --style clean_product --profile douyin_product --json
uv run lj approve visuals ./projects/my-video --approved-by '你的名字' --json
uv run lj run ./projects/my-video --json
```

可选收敛参数只保留两个:

- `--style`: `clean_product`、`bold_news`、`warm_lifestyle`、`tech_minimal`。
- `--profile`: `product_intro`、`open_source_project_intro`、`tutorial_guide`、`review_comparison`、`ecommerce_sales`、`knowledge_explainer`、`douyin_product`、`xiaohongshu_life`、`shipinhao_knowledge`。

它们会写入导演契约层,统一配色/光影/运动语言/底部安全区/叙事节奏,但不承诺爆款。

## 发布前检查

发布档必须同时满足:

- Codex 能力门诊确认发布级必需能力已补齐。
- QA 没有 hard failure。
- `uv run lj qa --release --strict --json` 没有 hard failure。
- 没有 `RELEASE_VISUAL_IS_BLANK_CARD` / `RELEASE_VISUAL_IS_TEMPLATE_LOOP` / `RELEASE_VISUAL_REUSES_SINGLE_ASSET` / `RELEASE_VISUAL_CONTAINS_STATIC_IMAGE`,否则说明画面仍是占位、样片模板、单素材循环或静态图片。
- 没有 `RELEASE_AUDIO_IS_PREVIEW_VOICE`,否则说明配音只是样片/预览级。
- `ffprobe` 能看到 video 和 audio 流。
- 导出包里的 `license_manifest.md` 不含 key、base URL、完整命令或本机私密路径。

如果只想验证流程,可以使用 mock 预览档;但 mock 结果不能当发布级视频。
