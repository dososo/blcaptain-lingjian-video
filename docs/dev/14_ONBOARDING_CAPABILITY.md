# 14 Onboarding 能力检测与继承层

日期:2026-07-02

## 目标

本轮在 M1/M2/M3 已达标的基础上,补齐用户安装后的第一步体验:先检测并继承当前环境已有能力,能用订阅/本机 CLI 就不要求 key;缺失时再给最短开通路径。此层不得削弱 mock/release/stub/审批门禁。

## 实现落点

- `packages/core/capabilities.py:74`:新增 `detect_capabilities`,统一检测 LLM/TTS/渲染/字体。
- `packages/core/capabilities.py:159`:LLM 优先级为 `claude_cli`、`codex_cli`、`llm_cli`、`ollama_cli`、`llm_local_cli`、`openai_compatible`、missing。
- `packages/core/capabilities.py:242`:TTS 优先级为 `tts_cli`、`macos_say`、`piper_cli`、`espeak_ng`、`openai_compatible_tts`、missing。
- `packages/core/capabilities.py:313`:渲染能力不只认本机 `ffmpeg` + `ffprobe`,还会探测 `drawtext/libfreetype`;缺失时仍阻塞 release。
- `packages/core/capabilities.py:459`:新增 `ffmpeg_drawtext_available`,优先执行 `ffmpeg -hide_banner -h filter=drawtext`,失败时回退 `ffmpeg -hide_banner -filters`。
- `packages/core/capabilities.py:351`:字体能力检测 macOS PingFang/STHeiti 与 `~/.cache/lingjian/fonts/NotoSansSC-Regular.otf`。
- `packages/core/doctor.py:24`:doctor method 增加 `source_type` 与 `label_zh`,保持旧字段不改名。
- `packages/core/doctor.py:52`:doctor 脱敏扩展到 `base_url`、`model`、`command` 等配置字段。
- `packages/core/doctor.py:154`:doctor 默认接入能力检测,但证据 JSON 只保留状态摘要,不开通命令。
- `packages/core/doctor.py:180`:当 FFmpeg/ffprobe 存在但缺少 `drawtext/libfreetype` 时,doctor 追加 `ffmpeg_drawtext` 必需项并返回 `ready=false`。
- `packages/core/rendering.py:76`:release 渲染读取 voice plan 中的真实音频文件;缺失时返回 `RELEASE_AUDIO_MISSING`。
- `packages/core/rendering.py:153`:release `ffmpeg_card` 合入音频输入,使用 `-c:a aac` 输出带音轨 MP4;preview 保持可无音轨。
- `packages/core/rendering.py:148`:FFmpeg 失败时保留 stderr 末尾摘要并脱敏项目路径;缺 `drawtext` 时返回 `FFMPEG_FILTER_UNAVAILABLE`。
- `packages/core/qa.py:43`:release QA 用 ffprobe 同时确认视频流与音频流;缺音频返回 `RELEASE_AUDIO_MISSING`。
- `providers/inherited_cli.py:18`:新增官方/本机 LLM CLI 适配器,只调用命令,不读取凭据文件。
- `providers/inherited_cli.py:63`:新增本机 TTS 适配器,覆盖 `say`、`piper`、`espeak-ng`。
- `providers/registry.py:11`:注册继承/本机 provider;`resolve_provider("auto", kind)` 按检测结果选当前最优 provider。
- `apps/cli/lingjian_cli/main.py:215`:新增 `lj setup`,输出可继承能力与缺失项下一步。
- `apps/cli/lingjian_cli/main.py:235`:新增 `lj credentials status/forget`,用于查看安全存储状态和撤销凭据。
- `packages/core/credentials.py:23`:检测 macOS Keychain、Linux Secret Service、Windows Credential Manager;默认模式仍为 ephemeral env。
- `packages/core/exporting.py:61`:license manifest 登记继承 CLI 与本机 TTS provider,不写命令、key、base URL 或 model。
- `scripts/ci/run_verification.py:231`:真实终验先记录 ffmpeg 路径、版本、drawtext 与 OS provenance。
- `scripts/ci/run_verification.py:329`:真实终验最终 ffprobe 输出 `codec_type/codec_name` 全部 stream,证据可复核视频与音频流。
- `docs/ONBOARDING.md`:新增用户向导,说明预览档/发布档、继承优先、TTS/FFmpeg 边界和安全承诺。
- `examples/providers/`:新增 I/O 契约示例骨架,顶部标注非真实、禁止用于 release 冒充。

## 安全边界

- 继承订阅能力只通过官方 CLI 命令,不读取 OAuth token、cookie、Keychain 内部文件或私密凭据文件。
- 默认只读取当前 shell 环境变量,不落盘。
- doctor 作为证据输出只保留状态和脱敏配置摘要;具体配置步骤放在 `lj setup` 与 `docs/ONBOARDING.md`。
- release 包、manifest、日志不记录 key/token/base URL/model/完整命令。
- 示例 provider 文件仅演示契约,禁止用于 release 冒充真实模型或语音引擎。

## 新增测试

- `tests/test_capability_onboarding.py::test_capability_detection_prefers_inherited_llm_cli_and_local_tts`
- `tests/test_capability_onboarding.py::test_doctor_uses_inherited_capabilities_without_api_key`
- `tests/test_capability_onboarding.py::test_doctor_requires_ffmpeg_drawtext_for_release_ready`
- `tests/test_capability_onboarding.py::test_doctor_accepts_ffmpeg_with_drawtext_filter`
- `tests/test_capability_onboarding.py::test_doctor_accepts_ffmpeg_drawtext_filter_help`
- `tests/test_capability_onboarding.py::test_resolve_auto_provider_runs_inherited_cli_adapters`
- `tests/test_capability_onboarding.py::test_setup_reports_missing_short_commands_without_leaking_keys`
- `tests/test_capability_onboarding.py::test_credentials_status_and_forget_are_safe_without_secret_store`
- `tests/test_batch2_release_export.py::test_release_render_uses_ffmpeg_and_writes_non_stub_video`
- `tests/test_batch2_release_export.py::test_release_render_reports_ffmpeg_filter_error_with_stderr`
- `tests/test_batch2_release_export.py::test_release_qa_rejects_release_without_audio_stream`
- `tests/test_batch2_release_export.py::test_release_qa_accepts_when_ffprobe_confirms_video_and_audio`
- `tests/test_batch2_release_export.py::test_export_license_manifest_records_inherited_cli_provider_without_commands`

## 验收命令与结果

- `uv run lj doctor --json`:通过,`ready=true`;检测到继承 LLM(`claude_cli`/`codex_cli`)、本机 TTS(`macos_say`)、默认 FFmpeg/ffprobe/drawtext 与中文字体。
- `ffmpeg -hide_banner -filters | grep drawtext`:通过,默认 `/opt/homebrew/bin/ffmpeg` 已链接到 `ffmpeg-full`。
- `uv run python scripts/ci/run_verification.py`:通过,`verification/results.json` 为 52 PASS / 0 FAIL;`V-REAL-01=PASS`。
- `verification/evidence/V-REAL-01.log`:真实链路执行 script -> voice -> visuals -> approve -> render --release -> qa --release -> export --release -> ffprobe;ffprobe 输出包含 `h264` 视频流与 `aac` 音频流。
- `verification/results.real_pass_20260702.json`:真实 PASS 快照。
- `verification/results.offline_fallback_20260702.json`:隐藏 `claude/codex` 且清空 provider env 后回落快照,51 PASS / 1 BLOCKED_ENV / 0 FAIL,`V-REAL-01` 阻塞原因为 `real_llm_provider`。
- `uv run python scripts/ci/check_false_success.py`:通过,13 项均未发现。
- `uv run python scripts/ci/check_no_force.py`:通过。
- `uv run python scripts/ci/check_forbidden_imports.py`:通过。
- `uv run python scripts/ci/check_render_engine_m1.py`:通过。
- `uv run python scripts/ci/check_ffmpeg_card_scope.py`:通过。
- `uv run pytest -q`:78 passed。
- `uv run ruff check .`:All checks passed。
- `pnpm --dir apps/web lint`:通过,`tsc --noEmit`。
- `pnpm --dir apps/web build`:通过,Next.js build 成功。
- `unzip -t lingjian_M1_codex_delivery_iter_8.zip`:通过,压缩包数据无错误。

## 当前环境说明

本机已安装 FFmpeg/ffprobe,并已通过 Homebrew link 让默认 `/opt/homebrew/bin/ffmpeg` 指向带 `drawtext/libfreetype` 的 `ffmpeg-full`;doctor 常态 `ready=true`,真实 `V-REAL-01` 已通过。使用临时 PATH 隐藏 `claude/codex` 并清空 provider env 后,同一套代码会回落 `BLOCKED_ENV`,证明没有伪 PASS。
