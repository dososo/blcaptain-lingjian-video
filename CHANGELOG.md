# CHANGELOG

## v0.2.0 - Codex 发布级 Skill 封版

日期:2026-07-03

### 已完成

- Codex Plugin 化:新增官方 plugin manifest、marketplace 元数据与 `~/.agents/skills` 安装路径,支持 Codex app 里一句话触发灵剪主线。
- 零 key 画面:接入 HyperFrames 宿主委托路径,按 visual plan 逐镜生成/消费真实 mp4;核心不 import、不 bundle HyperFrames 或 Remotion SDK。
- 画面打磨:HyperFrames 场景适配器支持 `hook/pain/solution/proof/cta` 多版式蓝图,相邻镜头可呈现不同结构与运动;画面只放短视觉关键词,口播全文由底部字幕承载。
- 零 key 中文配音:接入 Kokoro 中文本地 TTS 作为默认零 key 基线;继续支持用户录音、火山豆包与 OpenAI-compatible TTS。
- 发布硬门:新增/完善 `--strict`,严格发布时纯色回落画面与预览级音轨会阻断 export;mock/stub、缺视频流、缺音频流与不可 ffprobe 验证仍为 hard gate。
- 字幕安全区:release 字幕烧录固定在画面底部安全区,避免遮挡主体内容。
- 诚实能力分层:README、SKILL、ONBOARDING 与能力矩阵统一说明「零 key 免费 / 付费需连接账号 / 发布需自建」,并标清 Kokoro Apache、Piper GPL、Remotion 商用 license。
- cosmetic 清理:HyperFrames HTML 不再把 `motion_spec.main` 的原始基元名作为可见或可检索文字写出。

### 已知边界

- 发布级画面质量取决于宿主 HyperFrames/Remotion/imagegen 能力或用户自备素材;灵剪只负责编排、三审、组装、QA 与导出。
- Kokoro 是零 key 中文基线,适合开箱发布链路验收;商用品质仍建议使用云 TTS 或用户录音。
- Remotion 作为可选画面路径时需用户自行遵守其商用 license;Piper 为 GPL-3.0,仅作为用户自装的子进程路径。
- Web 控制台仍是静态骨架,MCP server 仍为后续里程碑。

### 验证

- `uv run pytest -q`
- `uv run ruff check .`
- `uv run python scripts/ci/check_false_success.py`
- `uv run python scripts/ci/check_no_force.py`
- `uv run python scripts/ci/check_forbidden_imports.py`
- `uv run python scripts/ci/check_render_engine_m1.py`
- `uv run python scripts/ci/check_ffmpeg_card_scope.py`
- `pnpm --dir apps/web build`
- `uv run python scripts/ci/run_verification.py`
- `lj run --release --strict` 真机复现 HyperFrames + Kokoro 发布级成片

## v0.1.0 - M1 封版

日期:2026-07-02

### 已完成

- CLI 主线:支持 `lj run` 引导素材导入、脚本、配音、画面、渲染、QA、导出,默认在 script / voice / visuals 三审点暂停。
- 审批门禁:三审未通过不得渲染;mock provider 不得用于正式 release;doctor 未 ready 时真实发布链路保持 `BLOCKED_ENV`。
- 能力检测:优先继承已登录的 Claude Code/Codex CLI 作为 LLM,优先检测 macOS `say`、Piper、espeak-ng 等本机 TTS。
- 真实渲染:release 模式要求 FFmpeg/ffprobe 且支持 `drawtext/libfreetype`;发布视频必须含真实视频流与音频流。
- QA 与导出:release QA 拒绝 stub 视频、不可 ffprobe 验证的视频、缺音频的视频和 mock provider。
- Onboarding:新增 `SKILL.md`、`docs/ONBOARDING.md`、README 对话式安装提示词和 `scripts/install_skill_links.sh`。
- 证据归档:默认真实环境 `verification/results.json` 为 52 PASS / 0 FAIL;离线回落快照为 51 PASS / 1 BLOCKED_ENV / 0 FAIL。

### 已知边界

- Web 控制台仍是静态骨架,尚未接后端 API。
- MCP server 尚未实现,`packages/mcp_server/README.md` 仅记录边界。
- `ffmpeg_card` 是最小卡片渲染引擎,不包含复杂 timeline、Remotion、HyperFrames 或模板市场。
- M1 不承诺成片质量或平台爆款效果,只保证流程可复跑、门禁可审计。

### 验证

- `uv run python scripts/ci/run_verification.py`
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run python scripts/ci/check_false_success.py`
- `uv run python scripts/ci/check_no_force.py`
- `uv run python scripts/ci/check_forbidden_imports.py`
- `uv run python scripts/ci/check_render_engine_m1.py`
- `uv run python scripts/ci/check_ffmpeg_card_scope.py`
- `pnpm --dir apps/web lint`
- `pnpm --dir apps/web build`
