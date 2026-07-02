# 19 M2 真实画面生成与发布级配音

日期:2026-07-02

## 定位

本轮承接 M2 第 1 步的「画面消费」能力,补齐生成侧与配音分档:

> 最新口径更新:生态零 key 接入已在 `docs/dev/28_ECOSYSTEM_INTEGRATION.md` 落地。Kokoro 已成为默认零 key 中文 TTS;Piper 为用户自装 GPL 委托路径;say/espeak-ng 仍为预览级。HyperFrames 已通过 `npx hyperframes` 薄委托真机 strict 验证。

- visuals 产出每镜可执行生成规格,供宿主 imagegen/HyperFrames/Remotion 生成资产。
- render 前对缺失资产做 best-effort 宿主委托;不可用或失败时诚实回落,不伪造产物。
- TTS 分为发布级与预览级;火山豆包作为中文发布级 provider,本机 say/Piper/espeak-ng 降为预览音。

核心仍不 import、不 bundle Remotion/HyperFrames SDK,不新增用户命令,不降低 mock/stub/ffmpeg/审批 hard gate。

## 文件落点

- `apps/cli/lingjian_cli/main.py:651`: `visuals` 写入每镜 storyboard;新增 `visual_prompt`、`motion_spec`、`brief`、`expected_asset_path`、`duration_sec`。
- `packages/core/visual_generation.py:18`:新增 `ensure_scene_asset`,按 `generator` 委托宿主 CLI 生成缺失资产。
- `packages/core/rendering.py:313`:渲染每镜前调用 `ensure_scene_asset`;生成成功即消费 mp4/png,失败继续走原回落。
- `packages/core/capabilities.py:248`:TTS 能力增加 `quality_tier`,火山豆包/OpenAI-compatible/真实 TTS CLI 为 `publish`,say/Piper/espeak-ng 为 `preview`。
- `packages/core/capabilities.py:351`:视觉能力报告 host HyperFrames/Remotion/imagegen,包含 `LINGJIAN_HOST_IMAGEGEN_CLI` 等 CLI 探测。
- `providers/volcengine_tts.py:23`:新增火山豆包 TTS provider,只从环境读取 AppID/Access Token/Cluster。
- `providers/registry.py:23`:注册 `volcengine_tts`,并提供 `volcengine`、`doubao` 别名。
- `packages/core/qa.py:109`:release 音轨来自预览级 TTS 时给 `RELEASE_AUDIO_IS_PREVIEW_VOICE` warning。
- `providers/inherited_cli.py:116`:继承/本机 CLI 失败轻量重试一次,仍失败时返回稳定错误。
- `packages/core/exporting.py:61`:license manifest 记录火山豆包 provider 类型,不记录 token、AppID、cluster 或音色值。

## 生成委托契约

visual plan 每镜给宿主的最小契约:

```json
{
  "generator": "image-gen",
  "visual_prompt": "中文画面提示词",
  "motion_spec": {"type": "push_in", "intensity": "subtle"},
  "brief": {"ratio": "9:16", "safe_area": "center", "avoid": ["watermark"]},
  "expected_asset_path": "assets/scenes/s1.png",
  "duration_sec": 3.2
}
```

render 前委托层会把完整 JSON 发给可用命令:

- `LINGJIAN_HOST_IMAGEGEN_CLI` 或 `imagegen`
- `LINGJIAN_HOST_HYPERFRAMES_CLI` 或 `hyperframes`
- `LINGJIAN_HOST_REMOTION_CLI` 或 `remotion`

命令需要把产物写到 `expected_asset_path`,也可在 stdout 返回 `{"asset_path":"assets/scenes/s1.png"}`。命令不可用、超时、失败或未写产物时,scene 只记录 `generation_status`,render 按原逻辑回落,不会生成假文件。

## TTS 分档

- 发布级:`volcengine_tts`、`openai_compatible_tts`、`tts_cli`,doctor 中 `quality_tier=publish`。
- 预览级:`macos_say`、`piper_cli`、`espeak_ng`。

默认 `lj voice --provider auto` 与 `lj run` 会选择当前可用最高档 TTS。仅有预览级 TTS 时 release 可继续,但 QA warning:

- `RELEASE_AUDIO_IS_PREVIEW_VOICE`:release 音轨来自本机预览级 TTS;建议配置火山豆包等发布级 TTS。

火山豆包配置:

```bash
export VOLCENGINE_TTS_APP_ID=...
export VOLCENGINE_TTS_ACCESS_TOKEN=...
export VOLCENGINE_TTS_CLUSTER=...
export VOLCENGINE_TTS_VOICE_TYPE=...   # 可选
```

官方接口参考:

- 火山引擎「大模型HTTP非流式接口-V1--豆包语音」: https://www.volcengine.com/docs/6561/1257584
- 火山引擎「豆包语音-鉴权方法」: https://www.volcengine.com/docs/6561/1105162

## 新增测试

- `tests/test_m2_visual_generation_tts.py::test_visuals_writes_executable_generation_spec`
- `tests/test_m2_visual_generation_tts.py::test_render_delegates_missing_image_asset_to_host_cli_before_assembly`
- `tests/test_m2_visual_generation_tts.py::test_release_qa_warns_when_audio_uses_preview_tts`
- `tests/test_m2_visual_generation_tts.py::test_volcengine_tts_provider_uses_official_http_contract`
- `tests/test_m2_visual_generation_tts.py::test_inherited_cli_retries_once_after_transient_failure`
- `tests/test_m2_visual_generation_tts.py::test_setup_detects_host_imagegen_cli_as_static_visual_tier`
- `tests/test_m2_visual_generation_tts.py::test_setup_rejects_host_imagegen_cli_that_does_not_write_probe_asset`
- `tests/test_capability_onboarding.py::test_doctor_marks_volcengine_tts_as_publish_tier`
- `tests/test_batch2_release_export.py::test_export_license_manifest_records_volcengine_tts_without_secrets`

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

## 本轮验证结果

- `uv run pytest -q`:96 passed。
- `uv run ruff check .`:All checks passed。
- 5 个扫描器:全部 exit=0,`check_false_success.py` 13 项均 `ok=true`。
- `pnpm --dir apps/web lint`:通过,`tsc --noEmit`。
- `pnpm --dir apps/web build`:通过,Next.js 5 个主流程路由仍可静态构建。
- `uv run python scripts/ci/run_verification.py`:通过,`verification/results.json` 为 52 PASS / 0 FAIL。
- `verification/evidence/V-REAL-01.log`:doctor `ready=true`;TTS 方法含 `quality_tier=preview/publish`;QA warning 同时包含 `RELEASE_VISUAL_IS_BLANK_CARD` 与 `RELEASE_AUDIO_IS_PREVIEW_VOICE`;ffprobe 输出 `h264` 视频流与 `aac` 音频流。

## 诚实边界

- 宿主生成器不存在时,只允许回落并 warning,不能声称已生成真实画面。
- 火山豆包/OpenAI-compatible 等 key 只从环境读取,不进仓库、日志、manifest、results 或 release 包。
- say/Piper/espeak-ng 是真实非 mock TTS,但不是发布级音色;必须保留 `RELEASE_AUDIO_IS_PREVIEW_VOICE` warning。
- `V-REAL-01` 的 PASS 仍以 doctor ready、真实 ffmpeg/ffprobe、非 mock、非 stub、视频流和音频流为准。
