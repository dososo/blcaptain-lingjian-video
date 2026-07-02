# 第二轮审计整改说明

日期: 2026-07-01

## 结论

本轮整改已完成,当前离线基线仍为 51 PASS / 1 BLOCKED_ENV / 0 FAIL。`V-REAL-01` 在当前无 FFmpeg、ffprobe、真实 LLM provider、真实 TTS provider 的环境下保持 `BLOCKED_ENV`,没有伪装为 PASS。

## 整改落点

### P0-1 release 视频本体门禁

- `packages/core/rendering.py:15-16`: 提取 `STUB_VIDEO_BYTES = b"LINGJIAN_STUB_MP4"`。
- `packages/core/rendering.py:78-83`: `render_project(mode="release")` 缺 FFmpeg/ffprobe 时抛 `RELEASE_RENDER_REQUIRES_FFMPEG`,不写 stub。
- `packages/core/qa.py:41-67`: release QA 用 ffprobe 校验有效视频流。
- `packages/core/qa.py:70-84`: release QA 拒绝 stub 哨兵并返回 `RELEASE_VIDEO_IS_STUB`;不可验证返回 `RENDER_NOT_VERIFIABLE`。
- `apps/cli/lingjian_cli/main.py:393-400`: `lj qa` 新增 `--release` 与 `--platform`,供真实 release 验证链路调用。

新增测试:

- `tests/test_batch2_release_export.py:148`: `test_release_render_requires_ffmpeg_before_writing_stub`
- `tests/test_batch2_release_export.py:174`: `test_release_qa_rejects_stub_and_unverifiable_video`
- `tests/test_batch2_release_export.py:206`: `test_release_qa_accepts_non_stub_when_ffprobe_confirms_video`

### P1-2 V-REAL-01 环境探测

- `scripts/ci/run_verification.py:145-160`: 先执行 doctor 并解析 required 缺口。
- `scripts/ci/run_verification.py:171-335`: doctor ready 时执行真实 release 命令链,包括 `render --release`、`qa --release`、`export --release` 和 ffprobe;未 ready 时保留 `BLOCKED_ENV`。
- `verification/results.json`: 当前仍为 `51 PASS / 1 BLOCKED_ENV / 0 FAIL`,且 `V-REAL-01` 置顶。
- `verification/evidence/V-REAL-01.log`: 记录 doctor 输出与缺失项。

新增测试:

- `tests/test_run_verification.py:16`: `test_real_release_verification_blocks_when_doctor_not_ready`
- `tests/test_run_verification.py:41`: `test_real_release_verification_runs_release_chain_when_ready`

### P1-3 审批签名密钥去路径化

- `packages/core/project.py:59-76`: 项目初始化时生成随机 `.lingjian/approval_secret`,权限 `0600`;已存在则沿用。
- `packages/core/approvals.py:31-37`: 审批签名读取项目 secret,缺失时随机生成并设 `0600`,不再使用项目路径 hash。

新增测试:

- `tests/test_core_gate.py:39`: `test_init_project_creates_random_private_approval_secret`
- `tests/test_core_gate.py:49`: `test_existing_approval_secret_is_reused`
- `tests/test_core_gate.py:60`: `test_tampered_approval_signature_marks_stale`

### P1-4/P1-5 伪成功扫描行为化

- `scripts/ci/check_false_success.py:50-60`: FS-02/03 必须找到 `raise LingjianError(<error_code>)`。
- `scripts/ci/check_false_success.py:81-112`: FS-09/10 绑定 `_write_index`、`reindex_project` 与测试函数调用结构。
- `scripts/ci/check_false_success.py:115-153`: FS-13 绑定 doctor 的 `DoctorItem` 与 `safe_for_release` 流。
- `scripts/ci/check_false_success.py:168-225`: FS-07 扫平台控制流,并校验 `PLATFORM_EXTRA_FILES` 仅为静态字符串 dict。
- `verification/FORBIDDEN_SCAN.md`: 明确静态 dict 是受控数据例外。

新增测试:

- `tests/test_static_guards.py:32`: `test_false_success_scan_rejects_dead_error_code_string`
- `tests/test_static_guards.py:58`: `test_platform_extra_files_whitelist_requires_static_strings`

## 验收命令

全部命令已在 2026-07-01 重跑:

- `uv run python scripts/ci/run_verification.py`: 通过,`failures=0`。
- `uv run python scripts/ci/check_false_success.py`: 通过,13 项全部未发现。
- `uv run python scripts/ci/check_no_force.py`: 通过。
- `uv run python scripts/ci/check_forbidden_imports.py`: 通过。
- `uv run python scripts/ci/check_render_engine_m1.py`: 通过。
- `uv run python scripts/ci/check_ffmpeg_card_scope.py`: 通过。
- `uv run pytest -q`: 通过,45 passed。
- `uv run ruff check .`: 通过。
- `pnpm --dir apps/web lint`: 通过。
- `pnpm --dir apps/web build`: 通过。

## 范围说明

- 未削弱 mock 三层 release 门禁。
- 未改 `packages/core/exporting.py` 主 release 逻辑。
- 未新增网络请求或真实 key 依赖。
- 未把 yt-dlp、youtube-dl、Remotion、HyperFrames、Playwright 引入 core/providers/engines 主路径。

## 后续 M2

M2 真实 CLI/API provider、release FFmpeg 出片、ffprobe timeout 与真实终验状态见 `docs/dev/10_M2.md`。
