# CHANGELOG

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
