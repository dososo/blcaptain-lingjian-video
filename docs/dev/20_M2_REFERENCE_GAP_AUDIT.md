# 20 M2 对标差距审计与补充

日期:2026-07-02

## 对标依据

- 用户附件:`/Users/manxiaochu/.codex/attachments/a7064e46-b4ba-4441-92e7-51da9049822e/pasted-text.txt`
- 仓库参考包:`lingjian_M1_FINAL_after_claude_final_audit/reference/final-audit/00_EXECUTIVE_SUMMARY.md`
- 仓库参考包:`lingjian_M1_FINAL_after_claude_final_audit/reference/final-audit/03_BEST_PRACTICES.md`
- 仓库参考包:`lingjian_M1_FINAL_after_claude_final_audit/reference/final-audit/07_GOAL_PATCH_SUGGESTIONS.md`

## 已对齐项

- `visual_plan.json` 已按镜记录 `generator`、`visual_prompt`、`motion_spec`、`brief`、`expected_asset_path`、`duration_sec`。
- `render` 已消费宿主/用户 mp4/png;视频镜头规范化,图片镜头走 Ken Burns/zoompan,缺资产回落 `fallback_solid`。
- `render_manifest.json` 已记录 `visual_real_count`、`visual_total` 与每镜 `render_source`。
- release QA 已对全回落画面给 `RELEASE_VISUAL_IS_BLANK_CARD` warning。
- TTS 已分为发布级与预览级;发布级 provider 为火山豆包、OpenAI-compatible TTS、自定义真实 TTS CLI;预览级 provider 为 macOS say/Piper/espeak-ng。
- release QA 已对预览级音轨给 `RELEASE_AUDIO_IS_PREVIEW_VOICE` warning。
- 仍保持 core/providers 不 import、不 bundle Remotion/HyperFrames/Playwright SDK。

## 本轮补齐的差距

### 1. 发布级 TTS 分档字段

差距:最新封版 runbook 期望 doctor 中发布级 TTS 显示 `quality_tier=publish`,此前代码使用 `release`。

补充:

- `packages/core/capabilities.py`:火山豆包、OpenAI-compatible TTS、自定义 TTS CLI 的 `quality_tier` 改为 `publish`。
- `packages/core/doctor.py`:preview TTS notice 判断改为寻找 `quality_tier=publish`。
- `tests/test_capability_onboarding.py::test_doctor_marks_volcengine_tts_as_publish_tier`:新增单测,确认火山豆包配置后不再出现 preview TTS warning,且 token 不泄漏。

### 2. 宿主画面 CLI 能力探测

差距:M2 最终版强调“探测真实能出图/出片才标可用”。此前 `LINGJIAN_HOST_IMAGEGEN_CLI` 只要指向可执行文件就会被视为可用。

补充:

- `packages/core/capabilities.py`:新增行为级 probe。候选宿主 CLI 必须接收 storyboard JSON,并在临时 `expected_asset_path` 写出非空 png/mp4,才会被标为可用。
- `tests/test_m2_visual_generation_tts.py::test_setup_detects_host_imagegen_cli_as_static_visual_tier`:证明能写资产的 fake CLI 才显示 `host_imagegen`。
- `tests/test_m2_visual_generation_tts.py::test_setup_rejects_host_imagegen_cli_that_does_not_write_probe_asset`:证明只会 `exit 0` 的空 CLI 会被降为 `fallback_solid`。

## 仍未补、且本轮不补的边界

- 不自研 Remotion/HyperFrames 引擎。
- 不在 `packages/core`、`providers`、`engines` 中 import/bundle Remotion/HyperFrames SDK。
- 不新增用户命令;继续走 `lj run` 与 `visuals` 三审。
- 不把 FFmpeg fallback 升级成复杂动画引擎;Ken Burns/zoompan 只属于 lj 组装层,不进入 `engines/ffmpeg_card`。
- 不默认下载他人视频,不引入 yt-dlp/youtube-dl 主路径。
- 不引入平台知识包、爆款算法、声音克隆、ASR/WhisperX、本地权重。
- 不承诺成片质量或爆款;只能承诺流程可复跑、门禁可审计。
- 不把内置 Codex `image_gen` 伪装成 CLI 能力。内置 imagegen 仍由宿主 agent 按 SKILL 编排生成资产后落盘;CLI 自动委托只认真实可执行命令。

## 当前环境差距

当前机器在正确 PATH 下:

- LLM 可继承 `claude_cli` / `codex_cli`。
- FFmpeg/ffprobe/drawtext 可用。
- TTS 只有 `macos_say`,仍是 `quality_tier=preview`。
- visuals 仍为 `fallback_solid`,未检测到可行为探测通过的宿主 CLI。

因此当前不能宣称“发布级画面 + 发布级配音封版通过”。需要用户先在本机提供发布级 TTS 环境变量,并由宿主 agent 或真实 CLI 写出每镜资产后再跑全质量验收。

## 本轮验证

- `uv run pytest -q`:96 passed。
- `uv run ruff check .`:All checks passed。
- 5 个扫描器: `check_false_success.py` / `check_no_force.py` / `check_forbidden_imports.py` / `check_render_engine_m1.py` / `check_ffmpeg_card_scope.py` 均 exit=0。
- `pnpm --dir apps/web lint`:通过。
- `pnpm --dir apps/web build`:通过。
- `uv run python scripts/ci/run_verification.py`:通过,`verification/results.json` 为 52 PASS / 0 FAIL。
- `git diff --check`:通过。
