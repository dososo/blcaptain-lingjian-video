---
name: lingjian-video
description: 用对话式一句话触发"灵剪(lingjian)"短视频生产主干:从文本/链接/图片素材出发,经脚本→配音→画面三道人工审批门,产出可预览或可发布的竖屏短视频,并导出分发包。全流程可复跑、门禁可审计。当用户说"帮我做一条短视频""把这段文案/这个链接做成视频""生成抖音/小红书/YouTube 竖屏视频""跑灵剪主线""lj 脚本/配音/渲染/导出"等时使用。
keywords: [灵剪, lingjian, lj, 短视频, 竖屏视频, 抖音, douyin, 小红书, youtube, 文案转视频, 链接转视频, 脚本配音渲染, 三审, 视频导出]
---

# 灵剪 (lingjian-video) 短视频生产主干

灵剪 M1 是一个 CLI + Web 的短视频生产主干:把"素材 → 脚本 → 配音 → 画面 → 渲染 → 质检 → 导出"做成可审核、可复跑、可归档的命令链,并在 script / voice / visuals 三处设人在环审批门。面向 Codex / Claude 订阅用户:宿主 agent 提供 LLM(订阅继承),ffmpeg 与 TTS 按需准备。

> 诚实前提:灵剪只保证流程可复跑、门禁可审计,不承诺成片质量或"爆款"。

## 何时用 / 何时不适用
适合:给了文案/链接/图片想做竖屏短视频;想走可审计流程并逐步过审;先出预览档(零配置)或具备真实能力后出发布档;导出分发包。
不适合/先澄清:要复杂动效/timeline/模板市场/AI 生图生视频/数字人(均不在 M1);要"保证上热门"(不承诺);只想聊运营选题(非主线核心,只能作明确标注的可选后续)。

## 能力前置与自检(先跑,别假设)
```bash
uv sync
uv run lj setup          # 能力仪表盘:优先继承已登录 CLI / 本机能力
uv run lj doctor --json  # 逐项体检;required 缺失时 exit code 非 0
```
- lj setup 优先继承已登录官方 CLI(claude/codex 作 LLM)与本机 TTS(macOS say / Piper / espeak-ng),尽量零 key。
- doctor 未 ready 时不要继续 release。

两档模式:
- 预览档(零配置):--provider mock 出脚本/配音,render 默认 preview。mock 产物仅预览,禁止当发布质量。
- 发布档(需三项齐备才可 --release):① 真实 LLM(继承 claude/codex,或 OpenAI-compatible 需 key,或 LINGJIAN_LLM_CLI);② 真实 TTS(订阅通常不含;优先 say[仅 macOS]/Piper/espeak-ng,或 OpenAI-compatible TTS,或 LINGJIAN_TTS_CLI);③ FFmpeg/ffprobe 且支持 drawtext/libfreetype(默认 Homebrew 精简版可能无 —— 以 doctor 的 ready 为准,缺失硬失败不写 stub)。

真实 provider 环境变量(仅从环境读取,不写入 artifact/日志/release 包):
```bash
export LINGJIAN_LLM_CLI=your-llm-command
export LINGJIAN_TTS_CLI=your-tts-command
export OPENAI_BASE_URL=... OPENAI_API_KEY=... OPENAI_MODEL=...
export OPENAI_TTS_BASE_URL=... OPENAI_TTS_API_KEY=... OPENAI_TTS_MODEL=...
```

## 主线工作流(按真实命令)
> 当前 CLI 支持 `lj run` 聚合命令。默认会在 script / voice / visuals 三审点停下;显式 `--yes` 仅用于 CI 或用户明确授权的自动审批。所有命令加 --json;前缀统一 uv run lj;⏸ 为三审暂停点,必须停下等用户确认再 approve。

```bash
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --json
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
uv run lj approve voice ./projects/demo --approved-by <用户> --json
uv run lj visuals ./projects/demo --engine ffmpeg_card --template product --json
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

## Honesty(必须遵守)
- 绝不编造产物/统计/成功结果:没真跑出来的不许写"已完成"。
- 跑真命令验证,而非看文件存在:以命令 --json 返回(ok/status/release_ready/exit code)为准。
- 不承诺成片质量、不承诺爆款:只保证流程可复跑、门禁可审计。
- 能力以 doctor 为准:是否可发布唯一权威是 doctor 的 ready 与各项状态。
- 不夸大未实现的部分(见下)。

## 已知边界(如实告知用户)
- mock 仅预览,非发布质量。
- ffmpeg_card 是最小卡片(纯色底+字幕+配音),无高级动效/timeline/HyperFrames/Remotion/插件市场。
- 订阅通常不含 TTS;LLM 可继承 claude/codex,TTS 一般需本机或单独配置。
- say 仅 macOS;其他系统用 Piper/espeak-ng 或 OpenAI-compatible TTS。
- 默认 Homebrew FFmpeg 可能缺 drawtext;render --release 会硬失败,以 doctor 为准。
- Web 控制台目前为静态骨架(未接后端 API),不能宣称它已能驱动完整审批流。
- MCP 尚未实现(packages/mcp_server 仅有 README),不能对外宣称 MCP 可用。
- 平台知识包/爆款算法非核心,只能作明确标注的可选后续。
