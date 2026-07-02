# 15 真实终验缺陷修复说明

日期:2026-07-02

## 结论

本轮修复真实终验暴露的三类问题:doctor 只看 FFmpeg 二进制导致误报 ready、release 视频缺音轨、V-REAL-01 证据不够完整。修复后:

- `verification/results.json`:52 PASS / 0 FAIL,`V-REAL-01=PASS`。
- `verification/results.offline_fallback_20260702.json`:51 PASS / 1 BLOCKED_ENV / 0 FAIL,缺真实 LLM 时不伪 PASS。
- `verification/evidence/V-REAL-01.log`:真实链路执行前记录 ffmpeg 路径、版本、drawtext 与 OS provenance;最终 ffprobe 输出包含 `h264` 视频流与 `aac` 音频流。

## 改动落点

- `packages/core/capabilities.py:313`:render 能力从“ffmpeg/ffprobe 存在”升级为“ffmpeg/ffprobe 存在且 FFmpeg 支持 drawtext/libfreetype”。
- `packages/core/capabilities.py:459`:新增 `ffmpeg_drawtext_available`,优先跑 `ffmpeg -hide_banner -h filter=drawtext`,失败时回退 `ffmpeg -hide_banner -filters`。
- `packages/core/doctor.py:180`:FFmpeg/ffprobe 存在但缺 drawtext 时,doctor 追加 `ffmpeg_drawtext` required 并返回 `ready=false`。
- `packages/core/rendering.py:76`:release 渲染读取 voice plan 中的真实音频文件;缺失时返回 `RELEASE_AUDIO_MISSING`。
- `packages/core/rendering.py:153`:release `ffmpeg_card` 合入音频输入,输出 `-c:a aac`;preview 仍可无音轨。
- `packages/core/rendering.py:148`:FFmpeg 失败时保留脱敏 stderr tail;缺 drawtext 时返回 `FFMPEG_FILTER_UNAVAILABLE`。
- `packages/core/qa.py:43`:release QA 用 ffprobe 同时确认 video/audio;缺音频返回 `RELEASE_AUDIO_MISSING`。
- `scripts/ci/run_verification.py:231`:真实终验先记录 ffmpeg 路径、版本、drawtext 与 OS provenance。
- `scripts/ci/run_verification.py:329`:真实终验最终 ffprobe 输出所有 stream 的 `codec_type/codec_name`,不再只选 `v:0`。

## 新增测试

- `tests/test_capability_onboarding.py::test_doctor_requires_ffmpeg_drawtext_for_release_ready`
- `tests/test_capability_onboarding.py::test_doctor_accepts_ffmpeg_with_drawtext_filter`
- `tests/test_capability_onboarding.py::test_doctor_accepts_ffmpeg_drawtext_filter_help`
- `tests/test_batch2_release_export.py::test_release_render_reports_ffmpeg_filter_error_with_stderr`
- `tests/test_batch2_release_export.py::test_release_qa_rejects_release_without_audio_stream`
- `tests/test_batch2_release_export.py::test_release_qa_accepts_when_ffprobe_confirms_video_and_audio`

## 验收结果

- 默认 FFmpeg 路径:`/opt/homebrew/bin/ffmpeg` 已链接到 `ffmpeg-full`,`uv run lj doctor --json` 返回 `ready=true`。
- `ffmpeg -hide_banner -filters | grep drawtext`:返回 `drawtext ... using libfreetype library`。
- 真实终验:`uv run python scripts/ci/run_verification.py` 返回 `failures=0`,主结果为 52 PASS。
- 人工 ffprobe:`ffprobe -v error -show_entries stream=codec_type,codec_name -of json <video.mp4>` 确认 `h264` 视频流与 `aac` 音频流。
- 离线回落:临时 PATH 只暴露 `uv/node/pnpm`,隐藏 `claude/codex` 并清空 provider env 后,`run_verification.py` 返回 `failures=0`,V-REAL-01 回落 `BLOCKED_ENV(real_llm_provider)`。
- `uv run pytest -q`:78 passed。
- `uv run ruff check .`:All checks passed。
- 5 个扫描器:`check_false_success.py`、`check_no_force.py`、`check_forbidden_imports.py`、`check_render_engine_m1.py`、`check_ffmpeg_card_scope.py` 均 exit=0。
- `pnpm --dir apps/web lint`:通过。
- `pnpm --dir apps/web build`:通过。
- `git diff --check`:无输出。
- `unzip -t lingjian_M1_codex_delivery_iter_8.zip`:No errors detected。

## 证据文件

- `verification/results.json`
- `verification/results.real_pass_20260702.json`
- `verification/results.offline_fallback_20260702.json`
- `verification/evidence/V-REAL-01.log`
- `verification/evidence/V-REAL-01.real_pass_20260702.log`
- `verification/evidence/V-REAL-01.offline_fallback_20260702.log`
- `docs/dev/AUDIT_READY.md`
- `docs/dev/14_ONBOARDING_CAPABILITY.md`
