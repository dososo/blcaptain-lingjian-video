# AUDIT_READY

日期: 2026-07-02

## 置顶结论

本轮 iter_8 为收官审计就绪:

- 真实环境项: `V-REAL-01=PASS`,主 `verification/results.json` 为 52 PASS / 0 FAIL。
- 默认环境规格: macOS,默认 `/opt/homebrew/bin/ffmpeg` 已链接到 `ffmpeg-full`,继承 `claude_cli` LLM,本机 `macos_say` TTS。
- 发布视频抽验: `verification/evidence/V-REAL-01.log` 记录 ffmpeg 路径、版本配置、drawtext、OS 与 ffprobe;最终视频包含 `h264` 视频流与 `aac` 音频流。
- 离线回落项:隐藏 `claude/codex` 并清空 provider env 后,`verification/results.offline_fallback_20260702.json` 为 51 PASS / 1 BLOCKED_ENV / 0 FAIL。
- skill 交付项:根目录 `SKILL.md` 已落盘,README 顶部有对话式安装提示词,`scripts/install_skill_links.sh` 已验证可安装软链。

## 证据入口

- `verification/results.json`
- `verification/VERIFICATION_REPORT.md`
- `verification/FORBIDDEN_SCAN.md`
- `verification/evidence/*.log`
- `verification/results.real_pass_20260702.json`
- `verification/results.offline_fallback_20260702.json`
- `verification/evidence/V-REAL-01.real_pass_20260702.log`
- `verification/evidence/V-REAL-01.offline_fallback_20260702.log`
- `output/playwright/web-smoke.png`
- `docs/dev/11_REAL_VERIFY.md`
- `docs/dev/15_REAL_VERIFY_FIX.md`
- `docs/dev/16_CLOSING.md`

## results 对照表

| 文件 | 环境 | 复现命令 | 预期 |
| --- | --- | --- | --- |
| `verification/results.json` | 默认 PATH,`/opt/homebrew/bin/ffmpeg` 为 `ffmpeg-full`,可继承 `claude_cli`,TTS 为 `macos_say` | `uv run python scripts/ci/run_verification.py` | 52 PASS / 0 FAIL,`V-REAL-01=PASS` |
| `verification/results.real_pass_20260702.json` | 与主结果相同的真实环境快照 | 同上 | 52 PASS / 0 FAIL,保留真实 PASS 证据 |
| `verification/results.offline_fallback_20260702.json` | 临时 PATH 只暴露 `uv/node/pnpm`,隐藏 `claude/codex`,清空 provider env | `env -u ... PATH=<tmpbin>:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin uv run python scripts/ci/run_verification.py` | 51 PASS / 1 BLOCKED_ENV / 0 FAIL,`V-REAL-01` 阻塞于 `real_llm_provider` |

## R1-R10 精修落点

| 项 | 状态 | 落点 |
| --- | --- | --- |
| R1 preview/release 物理隔离 | PASS | `packages/core/rendering.py`, `packages/core/exporting.py`, `tests/test_batch2_release_export.py` |
| R2 extract provider 语义 | PASS | `apps/cli/lingjian_cli/main.py`, URL/OCR 分类型参数 |
| R3 artifact history | PASS | `packages/core/artifacts.py`, `history/<step>/` |
| R4 ffmpeg_card 可判定项 | PASS | CJK/layout、drawtext 探测、真实 ffprobe 视频/音频流均已测 |
| R5 provider 错误分类 | PASS | `packages/core/provider_errors.py`, `tests/test_batch2_text_provider.py` |
| R6 导出后回环 | PASS | artifact 改写会 stale,history 保留旧版 |
| R7 审批 provenance 入包 | PASS | `export_manifest.json.approvals` |
| R8 稀薄输入 warn | PASS | `packages/core/validation.py` |
| R9 中文字幕断行 | PASS | `engines/ffmpeg_card/text_layout.py` |
| R10 doctor 语义 | PASS | `packages/core/doctor.py`, `tests/test_doctor.py` |

## DoD 对照

| DoD | 状态 | 说明 |
| --- | --- | --- |
| 三批交付物实现 | PASS | CLI/core/Web/docs/verification 已落盘 |
| 所有验收命令通过 | PASS | 真实环境 52 PASS;离线回落 51 PASS / 1 BLOCKED_ENV |
| 6 个 Blocker 测试 | PASS | pytest 与静态扫描覆盖 |
| 12 个 High 有代码或测试 | PASS | 真实音视频检测已在 `ffmpeg-full` 环境补验 |
| Web 5 页主路径 | PASS | `/new`, `/script-review`, `/voice-review`, `/visuals-review`, `/export` |
| 文档完整中文优先 | PASS | README、安装、provider、license、troubleshooting 等 |
| release 包结构 | PASS | mock release 阻断;preview export 结构完整 |
| 无伪成功扫描项 | PASS | 13 项未发现 |
| Apache-2.0 边界 | PASS | LICENSE 与 license-notes 已写明 |

## 第二轮审计整改

- P0-1 已落地: `render --release` 无 FFmpeg/ffprobe 返回 `RELEASE_RENDER_REQUIRES_FFMPEG`;release QA 拒绝 stub 与不可验证视频。
- P1-2 已落地: `V-REAL-01` 先跑 doctor;doctor ready 时才执行真实 release 命令链,当前环境仍诚实 `BLOCKED_ENV`。
- P1-3 已落地: 审批签名 secret 改为项目随机密钥,已有 `.lingjian/approval_secret` 沿用。
- P1-4/P1-5 已落地: FS-02/03/09/10/13 改为 AST/行为扫描;FS-07 把 `PLATFORM_EXTRA_FILES` 作为静态 dict 受控例外。

## M2 落地状态

- M2-1 已落地: `llm_cli` / `tts_cli` 真实 CLI provider 与 `openai_compatible` / `openai_compatible_tts` API provider 已注册,配置后 `is_mock=False`,script/voice 会写入真实 provider 产物。
- M2-2 已落地: release `ffmpeg_card` 改为调用 FFmpeg 生成非 stub MP4;preview stub 不变。
- M2-3 已补验: 本机 `ffmpeg-full` + 继承 CLI provider 环境下,`V-REAL-01=PASS`。
- M2-4 已落地: ffprobe 增加 20 秒 timeout,超时进入 `RENDER_NOT_VERIFIABLE`。
- M2 详细说明: `docs/dev/10_M2.md`。

## 审计提醒

- `render_project` 仅 preview 可写 stub;release 无 FFmpeg/ffprobe 会硬失败。
- 真实发布前必须确保 FFmpeg/ffprobe 运行环境支持 `drawtext/libfreetype`,并具备真实 LLM/TTS provider。
- `doctor` 已把 CLI provider 与 API key provider 分层;CLI 可用时不强制 key。
- 本机 2026-07-02 终验探测结果:继承 LLM 与本机 TTS 已可用;普通 `ffmpeg` 缺 `drawtext` 会阻断;`ffmpeg-full` 优先 PATH 下已执行真实 PASS 分支。

## M3 前瞻加固

- M3-a 已落地:provider 输出增加 `LLM_OUTPUT_TOO_THIN` 与 `TTS_OUTPUT_INVALID` 健全性校验。
- M3-b 已落地:voice plan 的 `total_duration_sec` 驱动 release FFmpeg 输入时长,缺失时回落兜底。
- M3-c 已落地:`lj render --real` / `lj preview --real` 可 opt-in preview 真实 FFmpeg 渲染;默认 preview stub 不变,无 FFmpeg 时不硬失败。
- M3 详细说明: `docs/dev/12_M3.md`。

## Onboarding 能力层

- D1 已落地:`packages/core/capabilities.py` 按继承优先检测 LLM/TTS/渲染/字体;`providers/inherited_cli.py` 注册 `claude_cli`、`codex_cli`、`ollama_cli`、`llm_local_cli`、`macos_say`、`piper_cli`、`espeak_ng`。
- D2 已落地:`packages/core/credentials.py` 与 `lj credentials` 提供安全存储状态/撤销入口;默认只读 shell env,不落盘。
- D3 已落地:`docs/ONBOARDING.md` 写明预览档/发布档、先继承后 key、TTS/FFmpeg 诚实边界与安全承诺。
- D4 已落地:`lj setup` 输出当前可继承能力和缺失项最短开通步骤;`doctor` 只输出脱敏状态,不输出 key/base URL/model/完整命令。
- D5 已落地:`examples/providers/` 只演示 I/O 契约,显著标注禁止用于 release 冒充。
- 新增测试:`tests/test_capability_onboarding.py`;新增 license manifest 覆盖 `test_export_license_manifest_records_inherited_cli_provider_without_commands`。
- 详细说明: `docs/dev/14_ONBOARDING_CAPABILITY.md`。

## iter_7 修复项

- FIX-1 已落地:`packages/core/capabilities.py` 与 `packages/core/doctor.py` 增加 `ffmpeg_drawtext` 能力探测;无 `drawtext/libfreetype` 时 `doctor ready=false`。
- FIX-2 已落地:`packages/core/rendering.py` 的 FFmpeg 失败路径写入脱敏 stderr 摘要;缺滤镜返回 `FFMPEG_FILTER_UNAVAILABLE`。
- FIX-3 已落地:release 渲染合入真实 voice 音频并输出 AAC;`packages/core/qa.py` release 分支要求视频流与音频流同时可验证。
- FIX-4 已落地:已重新运行 `run_verification.py`,主 `results.json` 与当前代码保持一致。
- FIX-5 已落地:真实 PASS 与离线回落两份证据已归档。
- FIX-6 已落地:`docs/ONBOARDING.md` 补充 FFmpeg `drawtext/libfreetype` 与音频编码要求。

## 收官项

- P1-B1 已落地:根目录 `SKILL.md` 可用一句话触发灵剪主线,含适合/不适合、Guardrails、Honesty、已知边界。
- P1-B2 已落地:README 顶部嵌入对话式安装提示词;`scripts/install_skill_links.sh` 用 `ln -sfn` 安装到 `~/.codex/skills` 与 `~/.claude/skills`。
- P1-B3 已落地:本轮不实现 MCP,`packages/mcp_server/README.md` 与 `docs/skill-and-mcp.md` 均明确 MCP 为后续里程碑。
- P1-B4/B5 已落地:`lj setup` 文本模式明确预览档/发布档;README/SKILL.md 写清零 key 预览、隐私、安全、成熟度边界。
- P2-C1/C2 已落地:`lj run <project>` 默认在三审点暂停;显式 `--yes` 会写真实 approval 并完成预览 render -> qa -> export,不绕过审批门。
