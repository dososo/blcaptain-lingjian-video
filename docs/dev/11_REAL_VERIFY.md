# 11 真实环境 V-REAL-01 终验说明

日期: 2026-07-01

## 结论

本轮在当前机器无法把 `V-REAL-01` 跑成真实 PASS。

原因不是代码门禁失败,而是真实终验基础设施缺失:

- `ffmpeg`: 未安装或不在 PATH。
- `ffprobe`: 未安装或不在 PATH。
- 真实 LLM provider: 未配置 `LINGJIAN_LLM_CLI`,也未配置 `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL`。
- 真实 TTS provider: 未配置 `LINGJIAN_TTS_CLI`,也未配置 `OPENAI_TTS_BASE_URL` / `OPENAI_TTS_API_KEY` / `OPENAI_TTS_MODEL`。

本轮没有为了让 `V-REAL-01` PASS 而降低门禁,也没有使用 echo/cat/固定 JSON 桩冒充真实 provider。

## 当前机器规格

- 时间: 2026-07-01 22:10:31 CST。
- OS: macOS 26.5, build 25F71。
- Kernel: Darwin 25.5.0, arm64。
- `ffmpeg -version`: `command not found`。
- `ffprobe -version`: `command not found`。
- provider 类型: 未配置真实 CLI/API provider。

## 当前 doctor 证据

命令:

```bash
uv run lj doctor --json
```

结果:

- `ready=false`
- required 缺失项:
  - `ffmpeg`
  - `ffprobe`
  - `real_llm_provider`
  - `real_tts_provider`
- provider 状态已脱敏,见 `verification/evidence/V-REAL-01.log`。
- 离线态快照:
  - `verification/results_offline_blocked_20260701.json`
  - `verification/evidence/V-REAL-01-offline-blocked-20260701.log`

## 本轮离线回归结果

当前机器已完成的命令:

- `uv run python scripts/ci/run_verification.py`: 51 PASS / 1 BLOCKED_ENV / 0 FAIL,`V-REAL-01=BLOCKED_ENV`。
- `uv run pytest -q`: 56 passed。
- `uv run ruff check .`: 通过。
- `uv run python scripts/ci/check_false_success.py`: 通过,FS-01 到 FS-13 均无 findings。
- `uv run python scripts/ci/check_no_force.py`: 通过。
- `uv run python scripts/ci/check_forbidden_imports.py`: 通过。
- `uv run python scripts/ci/check_render_engine_m1.py`: 通过。
- `uv run python scripts/ci/check_ffmpeg_card_scope.py`: 通过。
- `pnpm --dir apps/web lint`: 通过。
- `pnpm --dir apps/web build`: 通过。
- `git diff --check`: 当前目录不是 git 仓库,该命令无法运行;已补充扫描代码、测试、文档、任务文件的冲突标记与尾随空白,未发现问题。

交付包:

- `lingjian_M1_codex_delivery_iter_4.zip`

## 真实环境终验 runbook

在具备真实环境的机器上执行以下步骤。

1. 安装并确认 FFmpeg/ffprobe:

```bash
ffmpeg -version
ffprobe -version
```

2. 配置真实 provider,二选一。

CLI provider:

```bash
export LINGJIAN_LLM_CLI=/path/to/real-llm
export LINGJIAN_TTS_CLI=/path/to/real-tts
```

CLI 契约:

- LLM CLI 从 stdin 读取 JSON,向 stdout 输出 JSON object,顶层包含非空 `scenes`。
- TTS CLI 从 stdin 读取 JSON,向 stdout 输出 JSON object,包含 `audio_base64` 与 `duration_sec`。
- 不得使用 echo/cat/固定 JSON 桩冒充真实 provider。

OpenAI-compatible API:

```bash
export OPENAI_BASE_URL=https://api.example.com/v1
export OPENAI_API_KEY=...
export OPENAI_MODEL=...
export OPENAI_TTS_BASE_URL=https://api.example.com/v1
export OPENAI_TTS_API_KEY=...
export OPENAI_TTS_MODEL=...
```

3. 确认 doctor ready:

```bash
uv run lj doctor --json
```

必须满足:

- `ready=true`
- `ffmpeg` / `ffprobe` 可用。
- LLM/TTS 至少各有一个 `safe_for_release=true` 的真实 provider。
- 输出只允许脱敏,不得打印 key。

4. 跑真实 V-REAL-01:

```bash
uv run python scripts/ci/run_verification.py
```

该命令在 doctor ready 后应真实执行:

```text
script -> voice -> visuals -> approve -> render --release -> qa --release -> export --release -> ffprobe
```

5. 人工抽验产物:

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=codec_type,codec_name -of json <release-video.mp4>
```

必须满足:

- `codec_type=video`
- `codec_name` 为真实视频编码,通常为 `h264`
- `video.mp4` 不是 17 字节 `LINGJIAN_STUB_MP4`
- `provider_manifest.json` 中 `release_allowed=true`
- `provider_manifest.json` 不含 mock provider
- `license_manifest.md` 不含 key、base URL、model、CLI 完整命令或 token
- `qa_report.json` 中 `release_ready=true`

6. 再跑离线态回归:

清空真实 provider 环境变量后重跑:

```bash
unset LINGJIAN_LLM_CLI
unset LINGJIAN_TTS_CLI
unset OPENAI_BASE_URL
unset OPENAI_API_KEY
unset OPENAI_MODEL
unset OPENAI_TTS_BASE_URL
unset OPENAI_TTS_API_KEY
unset OPENAI_TTS_MODEL
uv run python scripts/ci/run_verification.py
```

预期:

- `V-REAL-01=BLOCKED_ENV`
- `FAIL=0`
- 说明同一套代码在无真实 provider 环境下不会伪 PASS

## 应归档的真实 PASS 证据

真实环境补验成功后,需要归档:

- `verification/results.json`: `V-REAL-01=PASS`
- `verification/evidence/V-REAL-01.log`: 包含真实 release 命令链与 ffprobe 输出
- `ffmpeg -version` / `ffprobe -version` 首行
- provider 类型: CLI 命令名或 API 供应商,必须脱敏
- OS 版本
- 人工抽验的 ffprobe 文本
- 离线态回归的 `results.json`,证明 `V-REAL-01` 回落 `BLOCKED_ENV`

## M3 前瞻

以下项不阻塞本轮真实终验:

- M3-a: provider 输出健全性校验。对 CLI/API 返回的 scenes/audio 做最小结构、字数、时长校验,降低空壳 JSON 风险。
- M3-b: 真实 TTS 时长回填。`voice_plan.total_duration_sec` 由真实音频时长驱动 release 视频时长。
- M3-c: preview 真实渲染 opt-in。允许用户选择 preview 也走真实渲染,减少 preview/release 路径差异。
