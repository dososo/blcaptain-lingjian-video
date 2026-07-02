# 08 总结

日期: 2026-07-01

## 本轮结论

M2 代码落地已完成,等待真实环境补验。

- 离线验证: 51 PASS / 0 FAIL。
- 真实环境: `V-REAL-01 BLOCKED_ENV`。
- 阻塞原因: 当前环境缺 FFmpeg、ffprobe、真实 LLM provider、真实 TTS provider。

## 主要交付

- Python core/CLI/provider/mock/doctor/approval/reindex/export/QA。
- Next.js Web 控制台与 5 个主流程路由。
- 文档: README、安装、provider、render engine、platform preset、MCP 边界、license、troubleshooting。
- 证据: `verification/results.json`, `verification/evidence/*.log`, `FORBIDDEN_SCAN.md`, `AUDIT_READY.md`。
- 打包脚本由最终 zip 命令生成。

## M2 交付

- CLI provider: `llm_cli` / `tts_cli` 支持用户本机命令,配置后 `is_mock=false`。
- OpenAI-compatible API provider: `openai_compatible` / `openai_compatible_tts` 支持显式 opt-in 的 LLM/TTS 真实接入,缺 key 时不算 ready。
- release 渲染: FFmpeg 生成非 stub MP4,CJK 字幕通过 `drawtext` 烧录,preview stub 不变。
- QA: ffprobe 增加 20 秒 timeout,超时仍 hard failure。
- license: `license_manifest.md` 记录用户自带 CLI/API provider 类型,不记录 key/base URL/model/命令值。
- 详细说明: `docs/dev/10_M2.md`。

## M3 交付

- provider 健全性:新增 `LLM_OUTPUT_TOO_THIN` 与 `TTS_OUTPUT_INVALID`。
- release 时长:继续由 `voice_plan.total_duration_sec` 驱动,缺失时兜底。
- preview 真实渲染 opt-in:`lj render --real` / `lj preview --real`,默认 stub 不变。
- 详细说明: `docs/dev/12_M3.md`。

## 第二轮整改摘要

- release render 缺 FFmpeg/ffprobe 时返回 `RELEASE_RENDER_REQUIRES_FFMPEG`,不再写 release stub。
- release QA 新增视频本体验证:`RELEASE_VIDEO_IS_STUB` 与 `RENDER_NOT_VERIFIABLE` 均为 hard failure。
- `V-REAL-01` 改为 doctor 探测;ready 时执行真实 release 命令链,当前环境仍为 `BLOCKED_ENV`。
- 审批签名 secret 改为项目随机密钥并设 `0600`,已有 secret 沿用。
- FS-02/03/09/10/13 升级为 AST/行为扫描;FS-07 明确静态 dict 受控例外。

## 待终审补验

1. 安装 FFmpeg/ffprobe。
2. 配置真实 LLM/TTS CLI provider 或 OpenAI-compatible API key。
3. 重跑 `uv run lj doctor --json`,确认 required 清空。
4. 跑 `uv run python scripts/ci/run_verification.py`,确认 `V-REAL-01=PASS`、`provider_manifest.json` 不含 mock 且 `qa_report.json.release_ready=true`。

真实终验 runbook 与当前阻塞证据见 `docs/dev/11_REAL_VERIFY.md`。
