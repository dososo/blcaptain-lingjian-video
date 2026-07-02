# Codex Plugin 发布级主线重定位说明

日期:2026-07-02

## 结论

本轮只修正产品形态与发布级主线表达,不重写工程底座。灵剪从“开发者 CLI-first 项目”调整为“Codex app 里一句话触发的发布级中文短视频 Skill/Plugin”。CLI 继续作为底层执行引擎,普通用户主路径改为 Codex app 安装、能力门诊、三审确认和严格发布 QA。

## 改动清单

| 项 | 文件 | 改法 |
| --- | --- | --- |
| Codex Plugin 分发 | `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `skills/lingjian-video/SKILL.md` | 新增 plugin manifest、repo marketplace 与 plugin skill 目录;符合 Codex 官方 `.codex-plugin/plugin.json` 与 `$REPO_ROOT/.agents/plugins/marketplace.json` 结构。 |
| 官方 skill 目录 | `scripts/install_skill_links.sh` | Codex 软链从旧 `~/.codex/skills` 改为官方 `~/.agents/skills`;Claude Code 仍写 `~/.claude/skills`。 |
| 普通用户入口 | `README.md`, `SKILL.md`, `docs/ONBOARDING.md`, `docs/CREATOR_QUICKSTART.md`, `docs/CAPABILITY_MATRIX.md` | 统一为 Codex app prompt-first;`doctor --json` 只作为 Codex/审计内部判断,不作为普通用户 UI。 |
| 发布级最小能力 | 同上, `packages/core/capabilities.py` | 明确发布级需要真实 LLM、发布级 TTS 或用户录音、真实画面插件或每镜素材、FFmpeg/ffprobe/drawtext/AAC、CJK 字体和底部字幕。 |
| 字幕底部安全区 | `packages/core/rendering.py`, `tests/test_batch2_release_export.py` | `drawtext` 的 y 坐标从画面中部改到底部安全区;测试断言命令不再使用 `(h/2)`。 |
| 严格发布门 | `packages/core/qa.py`, `packages/core/exporting.py`, `apps/cli/lingjian_cli/main.py` | 新增 `--strict`;严格模式把 `RELEASE_AUDIO_IS_PREVIEW_VOICE` 与 `RELEASE_VISUAL_IS_BLANK_CARD` 升为 hard failure 并阻断 release export。默认非 strict 行为不变。 |
| 测试覆盖 | `tests/test_batch2_release_export.py`, `tests/test_m2_visual_generation_tts.py`, `tests/test_cli_contract.py`, `tests/test_skill_packaging.py` | 覆盖 strict 行为、底部字幕、plugin manifest/marketplace、官方 skill 软链目录与 CLI strict 入口。 |

## 发布级口径

- `macOS say`、Piper、espeak-ng:预览级真实语音,不属于发布级最小集合。
- `fallback_solid`:纯色回落卡片,不属于发布级真实画面。
- mock/stub:开发验证路径,不可 release。
- 普通 release 为兼容旧验证保留 warning;发布级验收必须使用 `--strict --release`。
- HyperFrames/Remotion/imagegen 不由灵剪内置或 bundle;灵剪只生成规格、委托宿主或消费用户素材、组装、QA 与导出。

## 官方机制依据

- Codex Plugins 使用 `.codex-plugin/plugin.json` 作为插件 manifest。
- Repo marketplace 使用 `$REPO_ROOT/.agents/plugins/marketplace.json`。
- Codex app 主路径是 Plugins / Add to Codex;CLI `codex plugin marketplace add owner/repo` 是备用安装路径。
- 散装 skill 的官方用户目录是 `~/.agents/skills`,不是旧的 `~/.codex/skills`。

## 待真机继续验证

- 宿主 HyperFrames/Remotion/imagegen 自动生成动态画面的端到端发布片仍需真实 Codex app 环境留证。
- 当前已验证的发布级视觉首选路径仍是按 `visual_plan.json` 自备每镜 mp4/png。
- Remotion 商用 license 与 HyperFrames Node.js 22+ 前置已在用户文档中提示,但不作为灵剪核心依赖。

## 验收命令

```bash
uv run pytest -q
uv run ruff check .
uv run python scripts/ci/check_false_success.py
uv run python scripts/ci/check_no_force.py
uv run python scripts/ci/check_forbidden_imports.py
uv run python scripts/ci/check_render_engine_m1.py
uv run python scripts/ci/check_ffmpeg_card_scope.py
pnpm --dir apps/web lint
pnpm --dir apps/web build
uv run python scripts/ci/run_verification.py
```

## 不做边界

- 不实现完整 Web 控制台作主线。
- 不 import、不 bundle Remotion/HyperFrames SDK。
- 不做爆款算法、平台知识包、声音克隆、ASR、默认视频下载。
- 不把 say/mock/fallback_solid 说成发布级。
- 不削弱 mock/stub/ffprobe/三审/key 脱敏/user_audio 路径不泄漏等既有门禁。
