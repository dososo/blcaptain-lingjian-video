---
name: lingjian-video
description: 用对话式一句话触发"灵剪(lingjian)"短视频生产主干:从文本/链接/图片素材出发,经脚本→配音→画面三道人工审批门,产出可预览或可发布的竖屏短视频,并导出分发包。全流程可复跑、门禁可审计。当用户说"帮我做一条短视频""把这段文案/这个链接做成视频""生成抖音/小红书/YouTube 竖屏视频""跑灵剪主线""lj 脚本/配音/渲染/导出"等时使用。
keywords: [灵剪, lingjian, lj, 短视频, 竖屏视频, 抖音, douyin, 小红书, youtube, 文案转视频, 链接转视频, 脚本配音渲染, 三审, 视频导出]
---

# 灵剪 (lingjian-video) Codex 发布级短视频 Skill

灵剪是 Codex app 里的发布级中文短视频 Skill/Plugin:用户只说目标、给文案/素材/录音或授权,Codex 负责安装依赖、检测并继承能力、引导补齐发布级 TTS 与画面能力,再编排"素材 → 脚本 → 配音 → 画面 → 底部字幕 → 渲染 → QA → 导出"。CLI 是底层执行引擎,不是普通用户主入口。

> 诚实前提:灵剪只保证流程可复跑、门禁可审计,不承诺成片质量或"爆款"。

## 何时用 / 何时不适用
适合:给了文案/链接/图片想做竖屏短视频;想走可审计流程并逐步过审;先出预览档(零配置)或具备真实能力后出发布档;导出分发包。
不适合/先澄清:要复杂动效/timeline/模板市场/AI 生图生视频/数字人(均不在 M1);要"保证上热门"(不承诺);只想聊运营选题(非主线核心,只能作明确标注的可选后续)。

## 能力前置与自检(先跑,别假设)

普通用户路径从 Codex app 对话开始:先运行 `lj setup` 并用人话说明"已继承 / 已具备 / 必须补齐 / 可选增强"。`doctor --json` 只给 Codex/审计脚本内部判断,不要让普通用户直接解读 JSON。

```bash
uv sync
uv run lj setup          # 能力仪表盘:优先继承已登录 CLI / 本机能力
uv run lj doctor --json  # 逐项体检;required 缺失时 exit code 非 0
```
- lj setup 优先继承已登录官方 CLI(claude/codex 作 LLM)。TTS 默认优先用户录音/云 TTS/Kokoro 中文本地 TTS;macOS say 与 espeak-ng 只算预览级,不是发布级配音。Piper 是用户自装 GPL 本地 TTS,灵剪只子进程调用。
- doctor 未 ready 时不要继续 release。
- 普通创作者路径见 `docs/CREATOR_QUICKSTART.md`;能力边界见 `docs/CAPABILITY_MATRIX.md`。

画面能力:
- visuals 会按场景生成 storyboard,字段包含 generator、visual_prompt、motion_spec、brief、expected_asset_path、duration_sec、asset_path、subtitle_burn。
- generator 优先级:hyperframes -> remotion -> image-gen -> user-asset -> fallback_solid。
- 当前已验证的零 key 发布视觉路径是 HyperFrames:检测到 `npx hyperframes` 时,lj 通过薄子进程适配器按镜生成 mp4 到 `expected_asset_path`;lj 不 import、不 bundle Remotion/HyperFrames SDK,只委托 CLI 或消费落盘资产并用 FFmpeg 组装。
- Codex app 用户若已安装/启用 HyperFrames/Remotion/imagegen 插件或 skill,宿主 agent 可按 storyboard 的 `visual_prompt` 与 `motion_spec` 渲染更丰富的每镜产物到 `expected_asset_path`;自备每镜 mp4/png 仍是稳态回落。缺插件时要先引导用户在 Codex 插件市场安装/启用,或让用户提供素材;仍缺失才回落 fallback_solid,且只能称为预览/占位。

两档模式:
- 预览档(零配置):--provider mock 出脚本/配音,render 默认 preview。mock 产物仅预览,禁止当发布质量。
- 发布档(需最小集合齐备):① 真实 LLM(继承 claude/codex,或 OpenAI-compatible/key/CLI);② Kokoro/云 TTS/真实 TTS CLI 或用户录好的口播;③ 真实画面(HyperFrames/Remotion/imagegen 生成资产,或用户每镜 mp4/png);④ FFmpeg/ffprobe 且支持 drawtext/libfreetype/AAC;⑤ 中文字幕在底部安全区。say/espeak-ng 与 fallback_solid 只能预览,`--strict --release` 会阻断。

真实 provider 环境变量(仅从环境读取,不写入 artifact/日志/release 包):
```bash
export LINGJIAN_LLM_CLI=your-llm-command
export LINGJIAN_TTS_CLI=your-tts-command
export OPENAI_BASE_URL=... OPENAI_API_KEY=... OPENAI_MODEL=...
export OPENAI_TTS_BASE_URL=... OPENAI_TTS_API_KEY=... OPENAI_TTS_MODEL=...
export VOLCENGINE_TTS_APP_ID=... VOLCENGINE_TTS_ACCESS_TOKEN=... VOLCENGINE_TTS_CLUSTER=...
```

## 主线工作流(按真实命令)
> 当前 CLI 支持 `lj run` 聚合命令。默认会在 script / voice / visuals 三审点停下;显式 `--yes` 仅用于 CI 或用户明确授权的自动审批。所有命令加 --json;前缀统一 uv run lj;⏸ 为三审暂停点,必须停下等用户确认再 approve。

```bash
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --script-provider auto --voice-provider auto --json
# ⏸ 审阅 artifacts/script.json 后:
uv run lj approve script ./projects/demo --approved-by <用户> --json
uv run lj run ./projects/demo --json
# ⏸ 审阅 artifacts/voice_plan.json 后:
uv run lj approve voice ./projects/demo --approved-by <用户> --json
uv run lj run ./projects/demo --json
# ⏸ 审阅 artifacts/visual_plan.json 后:
uv run lj approve visuals ./projects/demo --approved-by <用户> --json
uv run lj run ./projects/demo --json
```

真做内容时优先继承当前订阅 CLI,不要默认用 mock:

```bash
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --script-provider auto --voice-provider auto --json
```

已有录好的口播音频时:

```bash
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --script-provider auto --voice-audio-file narration.m4a --json
```

逐条命令备选:
```bash
uv run lj setup && uv run lj doctor --json
uv run lj init ./projects/demo --name "演示项目" --json
uv run lj ingest text  ./projects/demo --file examples/product_intro_zh.txt --json
#   或 ingest url  ./projects/demo --url <链接> --screenshot --json
#   或 ingest image ./projects/demo --file <图片> --role cover --json
uv run lj extract ./projects/demo --json
uv run lj script ./projects/demo --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj approve script ./projects/demo --approved-by <用户> --json
uv run lj voice ./projects/demo --provider mock --voice test-voice --json
# 或者用用户录好的口播音频:
uv run lj voice ./projects/demo --provider auto --voice user --audio-file narration.m4a --json
uv run lj approve voice ./projects/demo --approved-by <用户> --json
uv run lj visuals ./projects/demo --engine ffmpeg_card --template product --json
# 审阅 artifacts/visual_plan.json:确认每镜 generator、visual_prompt、motion_spec、expected_asset_path。
# 宿主启用了 HyperFrames/Remotion/imagegen 时,按 expected_asset_path 生成 mp4/png;检测到 npx hyperframes 时 lj 可薄委托生成 mp4。缺宿主能力时先引导安装/启用插件或 skill,允许用户放自有素材,最后才回落卡片。
uv run lj approve visuals ./projects/demo --approved-by <用户> --json
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
- 不假装动态画面:宿主生成器失败或产物不存在时只能回落 fallback_solid,必须告诉用户这不是发布级真实画面;严格发布用 `--strict` 阻断。
- 不假装发布级配音:say/espeak-ng 是预览级真实语音;严格发布用 `--strict` 阻断并报告 `RELEASE_AUDIO_IS_PREVIEW_VOICE`。Kokoro 是零 key 中文默认,商用发布仍建议试听或使用用户录音/云 TTS。
- 配音缺失时不硬闯:先引导用户安装 Kokoro,再引导配置发布级 TTS API,或让用户提供已录好的口播音频并用 `--voice-audio-file` 接入。

## Honesty(必须遵守)
- 绝不编造产物/统计/成功结果:没真跑出来的不许写"已完成"。
- 跑真命令验证,而非看文件存在:以命令 --json 返回(ok/status/release_ready/exit code)为准。
- 不承诺成片质量、不承诺爆款:只保证流程可复跑、门禁可审计。
- 能力以 doctor 为准:是否可发布唯一权威是 doctor 的 ready 与各项状态。
- 不夸大未实现的部分(见下)。

## 已知边界(如实告知用户)
- mock 仅预览,非发布质量。
- HyperFrames/Remotion/imagegen 由宿主 agent 或本机 CLI 委托提供;灵剪核心不内置、不 bundle、不 import SDK。
- Codex app 用户可以安装/启用 HyperFrames/Remotion/imagegen 插件或 skill;缺失时应先引导安装,不是直接把 fallback 当真实画面。
- ffmpeg_card/fallback_solid 是回落卡片路径,不是动态画面质量承诺。
- 订阅通常不含 TTS;LLM 可继承 claude/codex,TTS 一般需本机或单独配置。
- 中文商用发布 TTS 首选用户录音或火山豆包,次选 OpenAI-compatible/其他云 TTS;Kokoro 是零 key 中文默认,不承诺音色质量。Piper 为 GPL 用户自装路径。
- say 仅 macOS;espeak-ng 属预览级本机 TTS,不属于发布级最小集合。
- 默认 Homebrew FFmpeg 可能缺 drawtext;render --release 会硬失败,以 doctor 为准。
- Web 控制台目前为静态骨架(未接后端 API),不能宣称它已能驱动完整审批流。
- MCP 尚未实现(packages/mcp_server 仅有 README),不能对外宣称 MCP 可用。
- 平台知识包/爆款算法非核心,只能作明确标注的可选后续。
