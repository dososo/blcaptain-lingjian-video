# 21 开源首用路径与创作者工作流补强

日期:2026-07-02

## 背景

本轮目标不是扩功能,而是把普通开源用户拿到仓库后的第一条可用路径讲清楚。用户特别纠正了一个关键点:

- 灵剪核心不内置 Remotion/HyperFrames,但 Codex 桌面版用户可以安装/启用这些插件或 skill。
- 缺失时应该由 onboarding 引导安装/启用,而不是把“不内置”写成“用户自己解决”。
- 配音缺失时,除了 TTS API,还必须支持用户已录好的口播音频。

## 对标参考

- `video-use`:第一屏强调“把素材放进文件夹,让 agent 操作,输出 final.mp4”,并用 setup prompt 让 agent 安装 skill、检查 FFmpeg/key。
- `OpenMontage`:README 第一屏列 prerequisite、zero-key 能力、provider menu 与 self-review,让用户知道当前机器能做到什么。
- `codex-storyboard`:强调安装后需重启/新开会话加载 MCP/插件能力,并把用户动作藏到自然语言工作流后面。
- `hyperframes-motion-director`:采用“brief/proposal 先确认,再生成资产,再 review report”的两阶段方式,与灵剪三审一致。

## 本轮改动

- `apps/cli/lingjian_cli/main.py`:新增 `lj voice --audio-file` 与 `lj run --voice-audio-file`。录音会复制进项目 artifact,写入 `provider_id=user_audio`、`provider_is_mock=false`。
- `packages/core/exporting.py`:license manifest 对 `user_audio` 只记录 “User supplied recorded narration”,不记录原始路径。
- `packages/core/capabilities.py`:visual fallback 的 next step 明确引导 Codex 桌面版安装/启用 HyperFrames、Remotion、imagegen 插件或 skill,安装后新开会话再跑 `lj setup`。
- `docs/CREATOR_QUICKSTART.md`:新增普通创作者路径,覆盖“有文案 / 有录音 / 缺 TTS / 缺画面插件 / 发布前检查”。
- `docs/CAPABILITY_MATRIX.md`:新增 Skill、CLI、MCP、插件、TTS、FFmpeg 能力矩阵。
- `README.md`、`SKILL.md`、`docs/ONBOARDING.md`、`docs/providers.md`、`docs/troubleshooting.md`、`docs/skill-and-mcp.md`:同步主线说明。
- README Web 段已就地标明“静态骨架,不能替代 CLI 审批流”。
- HyperFrames/Remotion skill 安装标识符已补官方入口链接;若入口变化,以官方文档和 Codex 插件市场为准。
- `tests/test_cli_contract.py`:覆盖用户录音入口。
- `tests/test_skill_packaging.py`、`tests/test_capability_onboarding.py`:覆盖创作者文档、插件安装提示与 setup next step。

## 保持的边界

- 不在灵剪核心中 import/bundle Remotion/HyperFrames SDK。
- 不新增 MCP server,不宣称 MCP 可用。
- 不把 Web 静态骨架宣称为完整审批控制台。
- 不做平台知识包、爆款算法、声音克隆、ASR/WhisperX、本地权重或默认视频下载。
- 不把 fallback_solid 或预览级 say/Piper/espeak-ng 伪装成发布级质量。
- 用户录音只作为本地输入,不上传、不泄漏原始路径、不写 key。

## 验收

- `uv run pytest -q`:99 passed。
- `uv run ruff check .`:All checks passed。
- 5 个扫描器:`check_false_success.py` / `check_no_force.py` / `check_forbidden_imports.py` / `check_render_engine_m1.py` / `check_ffmpeg_card_scope.py` 均 exit=0。
- `pnpm --dir apps/web lint`:通过。
- `pnpm --dir apps/web build`:通过。
- `uv run python scripts/ci/run_verification.py`:通过,`verification/results.json` 为 52 PASS / 0 FAIL。
