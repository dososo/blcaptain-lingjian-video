# LingJian Video Studio M1 Codex 执行 TODO

日期: 2026-07-01

## 前提与假设

- 当前目录是最终需求资产包,不是已有代码仓库;无 `.git`、无 `pyproject.toml`、无 `package.json`。
- 实现唯一依据按优先级执行: `02_PRD_GOAL_REFINEMENTS.md` > `base/LINGJIAN_M1_GOAL_ACCEPTED_BASE.md` > `base/LINGJIAN_M1_PRD_ACCEPTED_BASE.md` > `00/01` 产品与 UX 定义 > `reference/final-audit/*`。
- 根目录 5 个最终文档与 `lingjian_M1_FINAL_after_claude_final_audit/` 下同名文件 hash 一致;已按重复副本处理。
- 真实 LLM/TTS 的 release 验收需要真实 key;若当前环境无 key,`V-REAL-01` 必须置顶标 `BLOCKED_ENV`,不得算通过。
- 用户安装后的初始化体验必须主动检查 MCP/CLI/provider/key 能力。能用 CLI provider 的场景不强制 key;必须 key 时要引导配置并声明脱敏、安全与不写入 release 包。
- `base/` 与 `reference/` 作为只读依据保留,不回写。

## 成功标准

- DoD §20 全满足。
- 10 项精修 R1-R10 全部有代码、测试与证据落点。
- GOAL §19 验收命令全集逐条真跑,`verification/results.json` 与 `verification/evidence/*.log` 可复核。
- 13 条伪成功扫描在代码上真跑并全部未发现;如发现,必须修复后重跑。
- 离线 CI 绿;真实 provider 项无 key 时仅允许 `BLOCKED_ENV` 置顶。
- 产出 `docs/dev/AUDIT_READY.md`、`verification/VERIFICATION_REPORT.md`、`verification/FORBIDDEN_SCAN.md`、`docs/dev/08_SUMMARY.md` 与交付 zip。

## 8 步执行清单

- [x] ① 调研:完整阅读项目资产、确认文件地图、hash 重复关系、实现依据与验收闸门。
- [x] ① 调研:产出 `docs/dev/01_RESEARCH.md`,列模块、依赖、license、环境需求与合规清单。
- [x] ② 分析:产出 `docs/dev/02_ANALYSIS.md`,列架构边界、数据流、R1-R10 落点与风险表。
- [x] ③ 计划:产出 `docs/dev/03_PLAN.md`,按 Batch 1→2→3 写明开发顺序、验收命令与证据产物。
- [x] 杰哥已确认计划后进入实现代码开发。
- [x] ④ 开发 Batch 1:核心 schema/core/CLI/API/mock provider/doctor/provider 配置检查/approval hash/history/reindex/import guard。
- [x] ⑤ 验证 Batch 1:门禁、stale、doctor、reindex、无 force/import guard 证据。
- [x] ⑥ 测试 Batch 1:离线 pytest/ruff/CLI golden/provider 契约/静态扫描。
- [x] ④ 开发 Batch 2:provider 契约、ffmpeg_card、QA、export、preview/release 物理隔离、CJK 断行。
- [x] ⑤ 验证 Batch 2:mock preview 可出片、release 禁 mock、canonical export、QA、稀薄输入、preview 不可 release。
- [x] ⑥ 测试 Batch 2:离线 QA、provider 错误分类、preset 无平台名 if、伪成功扫描。
- [x] ④ 开发 Batch 3:Next.js 5 页 Web 控制台、provider 配置说明、文档、跨平台 polish。
- [x] ⑤ 验证 Batch 3:pnpm lint/build、Web smoke、中文路径、文档/许可证检查。
- [x] ⑥ 测试全集:GOAL §19 + 精修新增 V 项 + 默认离线 CI。
- [x] ⑦ 审计验收准备:产出 `AUDIT_READY.md`、`VERIFICATION_REPORT.md`、`FORBIDDEN_SCAN.md`。
- [x] ⑧ 总结打包:产出 `08_SUMMARY.md` 与 `lingjian_M1_codex_delivery_iter_1.zip`。

## Review

- 离线验证结果: 51 PASS / 0 FAIL / 1 BLOCKED_ENV。
- 置顶阻塞:当前环境缺 FFmpeg/ffprobe,且没有真实 LLM/TTS API key 或业务 CLI provider;`V-REAL-01` 按要求标 `BLOCKED_ENV`。
- 证据路径:`verification/results.json`, `verification/evidence/*.log`, `verification/VERIFICATION_REPORT.md`, `verification/FORBIDDEN_SCAN.md`, `docs/dev/AUDIT_READY.md`。
- 不宣称真实 release 已通过;终审需在有 FFmpeg/ffprobe 与真实 provider 的环境补验。

## 第二轮审计整改清单

- [x] P0-1: release render 缺 FFmpeg/ffprobe 必须硬失败;release QA 必须识别 stub 与不可验证视频。
- [x] P1-2: `V-REAL-01` 从无条件 `BLOCKED_ENV` 改为 doctor ready 时真跑真实 release 分支,当前环境仍 `BLOCKED_ENV`。
- [x] P1-3: 审批签名密钥改为项目随机密钥,兼容已有 `.lingjian/approval_secret`。
- [x] P1-4: FS-02/03/09/10/13 从死字符串扫描升级为 AST/行为绑定扫描。
- [x] P1-5: FS-07 明确 `PLATFORM_EXTRA_FILES` 是静态数据驱动白名单,扫描覆盖该例外。
- [x] 重跑 verification、5 个扫描器、pytest、ruff、Web lint/build。
- [x] 更新 `AUDIT_READY.md`、`VERIFICATION_REPORT.md`、`FORBIDDEN_SCAN.md`、`08_SUMMARY.md` 与错误码说明。
- [x] 重新打包 `lingjian_M1_codex_delivery_iter_2.zip` 并产出整改说明。

## 第二轮整改 Review

- P0-1: `packages/core/rendering.py` 对 release 缺 FFmpeg/ffprobe 抛 `RELEASE_RENDER_REQUIRES_FFMPEG`,不写 stub;`packages/core/qa.py` 对 release stub 抛 `RELEASE_VIDEO_IS_STUB`,ffprobe 不可验证抛 `RENDER_NOT_VERIFIABLE`。
- P1-2: `scripts/ci/run_verification.py` 的 `V-REAL-01` 改为先跑 doctor;ready 时真执行 release 命令链,当前环境仍 `BLOCKED_ENV`。
- P1-3: `.lingjian/approval_secret` 改为随机生成并设 `0600`,已有 secret 沿用;篡改审批字段会 stale。
- P1-4/P1-5: `check_false_success.py` 升级 AST/行为扫描,并把 `PLATFORM_EXTRA_FILES` 作为静态 dict 受控例外。
- 验证结果: `uv run python scripts/ci/run_verification.py` 通过,`verification/results.json` 为 51 PASS / 1 BLOCKED_ENV / 0 FAIL;`uv run pytest -q` 为 45 passed;`uv run ruff check .`、5 个扫描器、`pnpm --dir apps/web lint`、`pnpm --dir apps/web build` 均通过。
- 证据入口: `docs/dev/09_REMEDIATION.md`, `verification/results.json`, `verification/evidence/V-REAL-01.log`, `verification/false_success_scan.json`, `verification/FORBIDDEN_SCAN.md`。

## M2 真实 provider/渲染落地清单

- [x] M2-1: 实现 CLI 与 OpenAI-compatible LLM/TTS provider,配置后 `resolve_provider` 可返回 `is_mock=False`,script/voice 正确写真实 provider 产物。
- [x] M2-2: release `ffmpeg_card` 使用 FFmpeg 生成可 ffprobe 验证的非 stub MP4;preview/stub 路径保持不变。
- [ ] M2-3: `V-REAL-01` 在真实环境走 ready 分支;当前无 ffmpeg/provider 环境保留 `BLOCKED_ENV` 并记录阻塞。
- [x] M2-4: `_video_stream_is_verifiable` 添加 timeout,超时判 `RENDER_NOT_VERIFIABLE`。
- [x] 新增 provider/渲染/timeout 离线测试,并先验证失败再实现。
- [x] 重跑 `run_verification.py`、5 个扫描器、pytest、ruff、Web lint/build。
- [x] 更新 M2 文档、license/provider/render 说明与打包 `lingjian_M1_codex_delivery_iter_3.zip`。

## M2 Review

- M2-1: `providers/cli.py` 新增真实 CLI provider;`providers/openai_compatible.py` 新增 API provider;`providers/registry.py` 注册 `llm_cli`/`tts_cli`/`openai_compatible`/`openai_compatible_tts`;`apps/cli/lingjian_cli/main.py` 的 script/voice 已接线。
- M2-2: `packages/core/rendering.py` release 路径改为 FFmpeg 真出片,preview stub 不变,release stub 哨兵仍被拒绝。
- M2-3: 当前机器缺 FFmpeg、ffprobe、真实 LLM/TTS provider,`V-REAL-01` 仍为 `BLOCKED_ENV`;未伪装 PASS。
- M2-4: `packages/core/qa.py` ffprobe 增加 20 秒 timeout,超时进入 `RENDER_NOT_VERIFIABLE`。
- 新增测试: CLI/API provider resolve、script/voice fake CLI、script/voice fake API、API HTTP 错误映射、release ffmpeg fake run、ffprobe timeout、license manifest 记录 CLI/API provider。
- 当前验证: `uv run python scripts/ci/run_verification.py` failures=0;`uv run pytest -q` 56 passed;`uv run ruff check .`、5 个扫描器、`pnpm --dir apps/web lint`、`pnpm --dir apps/web build` 均通过。
- M2 说明: `docs/dev/10_M2.md`。

## 真实环境 V-REAL-01 终验清单

- [x] 探测当前机器 FFmpeg/ffprobe:均缺失,无法进入真实 release 终验。
- [x] 探测当前 provider env:CLI 与 OpenAI-compatible API 均未配置,未打印 key。
- [x] 运行 `uv run lj doctor --json`:返回 `ready=false`,缺 `ffmpeg`、`ffprobe`、`real_llm_provider`、`real_tts_provider`。
- [x] 保持 `V-REAL-01=BLOCKED_ENV`,未用假 CLI/固定 JSON 桩冒充真实 provider。
- [x] 新增 `docs/dev/11_REAL_VERIFY.md`,记录真实环境 runbook、当前阻塞证据、离线回归要求与 M3 前瞻。
- [ ] 在具备 FFmpeg/ffprobe + 真实 provider 的机器上补跑 `uv run python scripts/ci/run_verification.py`,使 `V-REAL-01=PASS`。
- [ ] 归档真实 PASS 的 ffprobe 输出、provider 类型、OS/FFmpeg 版本与离线回归 results。

## 真实终验 Review

- 当前机器规格:macOS 26.5, Darwin 25.5.0, arm64。
- 当前阻塞:`ffmpeg` 与 `ffprobe` command not found;`LINGJIAN_LLM_CLI`、`LINGJIAN_TTS_CLI`、OpenAI-compatible LLM/TTS env 全缺失。
- 当前结论:本机只能完成离线态回归与 runbook 交付,不能宣称真实 V-REAL-01 PASS。
- 离线回归:`uv run python scripts/ci/run_verification.py` 为 51 PASS / 1 BLOCKED_ENV / 0 FAIL;`uv run pytest -q` 为 56 passed;ruff、5 个扫描器、Web lint/build 均通过。
- 交付包:`lingjian_M1_codex_delivery_iter_4.zip`。
- 真实终验说明:`docs/dev/11_REAL_VERIFY.md`。

- [x] M3-a: provider 输出健全性校验。LLM scenes 必须非空且 narration_text 有足够内容;TTS audio 必须非空且 duration_sec>0,不合格抛稳定错误码。
- [x] M3-b: 真实 TTS 时长回填驱动 release 视频时长。确认 voice 产物写入 `total_duration_sec`,release 渲染读取该值;缺失时继续兜底。
- [x] M3-c: preview 真实渲染 opt-in。新增显式开关,默认 preview 仍写 stub;开关打开但无 FFmpeg 时仍回落 stub 且不抛错。
- [x] 新增离线单测并按 TDD 先红后绿。
- [x] 重跑 `run_verification.py`、5 个扫描器、pytest、ruff、Web lint/build。
- [x] 更新 `docs/dev/12_M3.md`、`docs/dev/AUDIT_READY.md` 与交付说明。
- [x] 打包 `lingjian_M1_codex_delivery_iter_5.zip`。

## M3 Review

- M3-a: `providers/validation.py` 新增脚本/语音健全性校验;CLI/API provider 均已接入;CLI 命令执行期错误会输出稳定 JSON。
- M3-b: `apps/cli/lingjian_cli/main.py` 继续写入 provider 返回 duration 到 voice plan;`packages/core/rendering.py` release 时长读取 `voice_plan.total_duration_sec`。
- M3-c: `lj render --real` 与 `lj preview --real` 已接入 `real_preview`;默认 preview stub 不变,无 FFmpeg 时回落 stub。
- 新增测试:CLI thin scenes、CLI empty audio、OpenAI-compatible thin scenes、OpenAI-compatible empty audio、release duration 读取与兜底、preview real 无 FFmpeg 回落、preview real 有 FFmpeg 走渲染。
- 局部验证:`uv run pytest ...` M3 测试先红后绿;最终 `uv run python scripts/ci/run_verification.py` 为 51 PASS / 1 BLOCKED_ENV / 0 FAIL;`uv run pytest -q` 为 65 passed;`uv run ruff check .`、5 个扫描器、Web lint/build 均通过。
- 交付包:`lingjian_M1_codex_delivery_iter_5.zip`,排除 `.venv`、`node_modules`、构建缓存、`projects`、`exports` 与旧 zip。
- M3 说明:`docs/dev/12_M3.md`。

## Onboarding 能力检测与继承清单

- [x] D1: 新增能力检测器,按 LLM/TTS/渲染/字体优先级链输出结构化能力清单。
- [x] D1: 新增订阅/本机 CLI 适配器,将 claude/codex/ollama/say/piper/espeak-ng 翻译为现有 provider 契约。
- [x] D1: `doctor` 与 `resolve_provider("auto", kind)` 接入继承优先的真实 provider。
- [x] D2: 增加安全凭据状态/撤销入口,默认只读 shell env,可选持久化说明走 OS 安全存储。
- [x] D3: 新增 `docs/ONBOARDING.md`,README 增加入口,交叉引用真实终验 runbook。
- [x] D4: 新增 `lj setup`,文本/JSON 模式只对缺失项给最短开通命令。
- [x] D5: 新增 `examples/providers/` 示例骨架,显著标注仅演示契约、禁止冒充 release。
- [x] 验证:新增离线测试覆盖 fake CLI 检测、auto provider、doctor、setup 脱敏、credentials。
- [x] 验证:重跑 run_verification、5 扫描器、pytest、ruff、pnpm lint/build。
- [x] 文档与交付:更新 `docs/dev/AUDIT_READY.md`,新增 `docs/dev/14_ONBOARDING_CAPABILITY.md`,打包 `lingjian_M1_codex_delivery_iter_6.zip`。

## Onboarding 能力层 Review

- D1: `packages/core/capabilities.py` 已实现继承优先检测;`providers/inherited_cli.py` 与 `providers/registry.py` 已接入 `claude_cli`、`codex_cli`、`ollama_cli`、`llm_local_cli`、`macos_say`、`piper_cli`、`espeak_ng`;`resolve_provider("auto", kind)` 可按当前最优能力解析。
- D2: `packages/core/credentials.py` 与 `lj credentials status/forget` 已实现安全存储状态/撤销入口;默认只读 shell env,不落盘。
- D3/D4: `docs/ONBOARDING.md`、README 与 `lj setup` 已说明先继承、后 key,TTS/FFmpeg 的诚实边界和安全承诺。
- D5: `examples/providers/` 已新增契约示例,显著标注非真实、禁止用于 release 冒充。
- 新增测试: `tests/test_capability_onboarding.py` 5 条;`tests/test_batch2_release_export.py::test_export_license_manifest_records_inherited_cli_provider_without_commands`。
- 当前验证: `uv run python scripts/ci/run_verification.py` 为 51 PASS / 1 BLOCKED_ENV / 0 FAIL;`uv run pytest` 为 71 passed;ruff、5 个扫描器、Web lint/build 均通过。
- 当前真实终验状态:检测到 `claude/codex` 可继承 LLM,检测到 macOS `say` 可作为 TTS,但仍缺 FFmpeg/ffprobe,因此 `V-REAL-01` 继续诚实 `BLOCKED_ENV`。
- 交付包:`lingjian_M1_codex_delivery_iter_6.zip`。

## 真实终验缺陷修复清单

- [x] FIX-1: render 能力检测必须验证 ffmpeg `drawtext`/libfreetype 能力;无 drawtext 时 doctor ready=false。
- [x] FIX-2: release FFmpeg 失败返回可诊断 stderr 摘要;滤镜缺失给稳定错误码。
- [x] FIX-3: release 视频合入 voice 音轨;QA release 增加音频流 hard fail。
- [x] FIX-4: 修复后重跑 `run_verification.py`,确保 results/evidence 与当前代码一致。
- [x] FIX-5: 真实终验 PASS 与离线回落 BLOCKED_ENV 两份证据归档。
- [x] FIX-6: 文档补充 ffmpeg drawtext/libfreetype 与音频编码要求。
- [x] 收尾:5 扫描器、pytest、ruff、pnpm lint/build 全绿,打包 `lingjian_M1_codex_delivery_iter_7.zip`。

## 真实终验缺陷修复 Review

- FIX-1: `packages/core/capabilities.py` 新增 `ffmpeg_drawtext_available`,优先跑 `ffmpeg -hide_banner -h filter=drawtext`,回退 `-filters`;`packages/core/doctor.py` 在 FFmpeg/ffprobe 存在但缺 drawtext 时返回 `ffmpeg_drawtext` required,ready=false。
- FIX-2: `packages/core/rendering.py` 的 FFmpeg 失败路径写入脱敏 stderr 摘要;缺 `drawtext` 返回 `FFMPEG_FILTER_UNAVAILABLE`,普通失败仍为 `RENDER_FAILED`。
- FIX-3: release 渲染读取 voice plan 音频并用 `-c:a aac` 合入音轨;`packages/core/qa.py` release 分支要求 ffprobe 同时确认 video/audio,缺音频返回 `RELEASE_AUDIO_MISSING`。
- FIX-4/FIX-5: 真实环境 `V-REAL-01=PASS`,ffprobe 证据包含 h264 视频流与 aac 音频流;隐藏 `claude/codex` 并清空 provider env 后,离线回落为 51 PASS / 1 BLOCKED_ENV / 0 FAIL。
- FIX-6: `docs/ONBOARDING.md`、`docs/dev/AUDIT_READY.md`、`docs/dev/14_ONBOARDING_CAPABILITY.md`、`verification/VERIFICATION_REPORT.md`、`verification/FORBIDDEN_SCAN.md` 已同步 drawtext、音轨和双证据说明。
- 新增/覆盖测试: `test_doctor_requires_ffmpeg_drawtext_for_release_ready`, `test_doctor_accepts_ffmpeg_with_drawtext_filter`, `test_doctor_accepts_ffmpeg_drawtext_filter_help`, `test_release_render_reports_ffmpeg_filter_error_with_stderr`, `test_release_qa_rejects_release_without_audio_stream`, `test_release_qa_accepts_when_ffprobe_confirms_video_and_audio`。
- 验证结果: `uv run pytest -q` 为 78 passed;`uv run ruff check .`、5 个扫描器、`pnpm --dir apps/web lint`、`pnpm --dir apps/web build` 均通过;最终证据见 `verification/results.json`、`verification/results.real_pass_20260702.json`、`verification/results.offline_fallback_20260702.json` 与 `verification/evidence/V-REAL-01*.log`。

## 收官一键执行包清单

- [x] P0-A1: 默认 PATH 重跑 `run_verification.py`,主 `verification/results.json` 与 `lj doctor --json` 常态一致。
- [x] P0-A2: 持久 drawtext 能力可复现;做不到则文档诚实说明 BLOCKED_ENV。
- [x] P0-A3: `V-REAL-01` 证据补 ffmpeg 路径、版本首行、drawtext、OS、h264+aac ffprobe provenance。
- [x] P0-A4: `AUDIT_READY.md` 用表说明默认/real_pass/offline_fallback 三份 results 的环境与复现方式。
- [x] P1-B1: 根目录落盘 `SKILL.md`,frontmatter 含触发词。
- [x] P1-B2: README 顶部嵌入对话式安装提示词,并提供 clone+软链安装脚本;skills.sh 路径按发布状态诚实说明。
- [x] P1-B3: MCP 表述二选一诚实;本轮不实现 MCP,明确后续里程碑。
- [x] P1-B4/B5: README/SKILL.md 写清零 key 预览、能力仪表盘、适合/不适合、Honesty、隐私与成熟度边界。
- [x] P2-C1: 新增 `lj run <project>` 引导主线,默认停在三审点,`--yes` 仅用于显式 CI 自动审批。
- [x] P2-C2: `lj run` render 后自动跑 QA 摘要,再导出。
- [x] 收尾:重跑 verification、5 扫描器、pytest、ruff、pnpm lint/build,更新审计文档并打包 `iter_8.zip`。

## 收官执行包 Review

- P0: 已 `brew unlink ffmpeg && brew link ffmpeg-full`,默认 `/opt/homebrew/bin/ffmpeg` 支持 `drawtext/libfreetype`;`uv run lj doctor --json` 常态 `ready=true`;`V-REAL-01.log` 已记录 ffmpeg 路径、版本配置、drawtext、OS 与 h264+aac ffprobe。
- P1: 根目录新增 `SKILL.md`;README 顶部嵌入对话式安装提示词;新增 `scripts/install_skill_links.sh` 并已运行,软链到 `~/.codex/skills/lingjian-video` 与 `~/.claude/skills/lingjian-video`;MCP 文档明确后续里程碑。
- P2: `apps/cli/lingjian_cli/main.py` 新增 `lj run`;默认在三审点返回 `awaiting_approval`,显式 `--yes` 写真实 approvals 并完成 preview render -> qa -> export;release 模式先验 doctor。
- 新增测试: `test_lj_run_pauses_at_script_review_without_yes`, `test_lj_run_yes_completes_preview_flow_with_real_approvals`, `test_skill_file_and_readme_install_prompt_are_packaged`, `test_install_skill_script_and_mcp_boundary_are_honest`, `test_setup_text_names_preview_and_release_modes`;`test_real_release_verification_runs_release_chain_when_ready` 增加 provenance 断言。
- 证据: `verification/results.json` 为默认真实环境 52 PASS / 0 FAIL;`verification/results.real_pass_20260702.json` 为真实 PASS 快照;`verification/results.offline_fallback_20260702.json` 为 51 PASS / 1 BLOCKED_ENV / 0 FAIL。
- 文档: `docs/dev/AUDIT_READY.md`、`docs/dev/14_ONBOARDING_CAPABILITY.md`、`docs/dev/15_REAL_VERIFY_FIX.md`、`docs/dev/16_CLOSING.md`、`verification/VERIFICATION_REPORT.md`、README 与 `docs/ONBOARDING.md` 已同步。

## M1 封版与开源发布准备清单

- [x] 仓库与版本:确认 git 状态,对齐 `pyproject.toml`、`package.json`、`apps/web/package.json` 的 `0.1.0`,准备 `v0.1.0` tag。
- [x] 发布文档:新增 `CHANGELOG.md`、`ROADMAP.md`,README 补隐私、安全与跨平台开通说明。
- [ ] 占位替换:将 README/ONBOARDING/SKILL 中的 `<REPO_URL>` 替换为真实开源仓库地址;本地无 remote 时标为阻塞并等待用户提供。
- [x] 首用自检:在干净 clone 中按 README 顶部流程跑到预览档出片,留存 doctor 与预览证据。
- [x] 验证与打包:重跑 run_verification、pytest、ruff、5 扫描器、pnpm lint/build,打包 `iter_9` 并记录发布准备说明。

## M1 封版与开源发布准备 Review

- 已完成:版本对齐为 `0.1.0`;新增 `CHANGELOG.md`、`ROADMAP.md`、`docs/dev/17_RELEASE_PREP.md`;README 补隐私、安全、可选依赖审计与跨平台 FFmpeg/TTS;`.gitignore` 补 `.env*` 与 `.lingjian/`。
- 首用自检:本地 clean clone 运行 `uv sync`、`scripts/install_skill_links.sh`、`uv run lj setup`、`uv run lj doctor --json`、`lj run --yes` 预览档、QA、export,证据在 `verification/release_prep/`。
- 验证结果:`run_verification.py` 为 52 PASS / 0 FAIL;`uv run pytest -q` 为 83 passed;ruff、5 个扫描器、Web lint/build 均通过。
- 交付包:`lingjian_M1_codex_delivery_iter_9.zip`,已通过 `unzip -t`,并排除 `.git`、`.venv`、`node_modules`、`projects`、`exports` 与旧 zip。
- 当前阻塞:本地无 `git remote`,无法确认真实开源仓库地址;`README.md` 中 `<REPO_URL>` 未替换,最终 `v0.1.0` tag 暂不创建。

## M2 画面委托主轨清单

- [x] RED:新增测试覆盖 visual_plan 每镜 generator 字段、宿主视频资产消费、静态图 zoompan、缺资产 fallback_solid、render_manifest 反 PPT 统计、QA warning、capability 画面分档。
- [x] GREEN:实现 visuals artifact 生成 storyboard 字段,按 hyperframes/remotion/image-gen/user-asset/fallback_solid 消费资产并用 FFmpeg 组装。
- [x] GREEN:doctor/setup 增加视觉能力分档,只报告可用性,不把宿主插件缺失当 release 硬门。
- [x] 扫描语义:保持 core/providers 禁 import remotion/hyperframes/playwright;更新扫描文档说明“委托宿主产物消费”被允许。
- [x] 文档与证据:更新 SKILL/README/AUDIT_READY/FORBIDDEN_SCAN,新增 `docs/dev/18_M2_VISUAL_DELEGATION.md`,重跑验证并打包。

## M2 画面委托主轨 Review

- 已完成:visuals 生成每镜 storyboard;release/real-preview 可消费宿主或用户 mp4/png,图片走 zoompan,缺资产走 `fallback_solid`;render_manifest 写 `visual_real_count/visual_total/scenes`。
- QA:新增 `RELEASE_VISUAL_IS_BLANK_CARD` warning,当前不作为 hard failure;release 原有 mock/stub/ffprobe/audio hard gate 未削弱。
- 能力检测:`lj setup --json` 新增 `capabilities.visuals`;宿主 HyperFrames/Remotion/imagegen 可通过环境显式声明或 CLI probe 识别,缺失时报告回落卡片。
- 扫描纪律:未在 core/providers import Remotion/HyperFrames/Playwright;FORBIDDEN_SCAN 记录“宿主产物消费允许,SDK bundle 禁止”。
- 验证结果:`uv run pytest -q` 为 87 passed;`uv run python scripts/ci/run_verification.py` 为 52 PASS / 0 FAIL;ruff、5 扫描器、Web lint/build 均通过。
- 交付包:`lingjian_M2_visual_delegation_iter_1.zip`,已通过 `unzip -t`,并排除 `.git`、`.venv`、`node_modules`、`projects`、`exports` 与旧 zip。

## M2 第2步 真实画面生成与发布级配音清单

- [x] RED:测试 visual_plan 生成规格包含 `visual_prompt`、`motion_spec`、`expected_asset_path`,并用假生成器 CLI 写入资产。
- [x] RED:测试渲染前会对缺失资产执行生成委托,成功后 `visual_real_count>0` 且无 blank-card warning;生成失败时诚实回落。
- [x] RED:测试 TTS 分档,火山豆包 TTS provider 用脱敏 env 配置并返回音频;本机 say/piper/espeak release QA 给预览音 warning。
- [x] GREEN:实现宿主生成委托层、火山 TTS provider、TTS 分档与自动择优;外部 CLI 失败增加一次轻量重试和清晰错误。
- [x] 文档与证据:更新 README/SKILL/ONBOARDING/FORBIDDEN_SCAN/AUDIT_READY,新增 `docs/dev/19_M2_VISUAL_GEN_AND_TTS.md`,重跑验证并打包 iter_10。

### Review: M2 第2步

- 已完成:visuals 每镜写入可执行生成规格;render 前按 `LINGJIAN_HOST_IMAGEGEN_CLI`、`LINGJIAN_HOST_HYPERFRAMES_CLI`、`LINGJIAN_HOST_REMOTION_CLI` 或同名 CLI 做 best-effort 委托,失败不伪造产物。
- 已完成:新增火山豆包 TTS provider;TTS 能力有 `quality_tier`,发布级为 `publish`,本机 say/Piper/espeak-ng 保持真实可用但 release QA warning。
- 已完成:继承/本机 CLI 失败轻量重试一次;doctor JSON 保持脱敏,不输出 key 值或完整命令。
- 验证: `uv run pytest -q` 94 passed;`uv run ruff check .` 通过;5 个扫描器 exit=0;`pnpm --dir apps/web lint` 与 `build` 通过;`run_verification.py` 52 PASS / 0 FAIL,V-REAL-01=PASS。
- 证据: `verification/evidence/V-REAL-01.log` 含 `RELEASE_AUDIO_IS_PREVIEW_VOICE` 与 `RELEASE_VISUAL_IS_BLANK_CARD` warnings,最终 ffprobe 含 h264 视频流与 aac 音频流。

## M2 对标差距补充清单

- [x] 对标 `a7064e46.../pasted-text.txt` 的 M2 最终版,梳理已落地、仍缺和不做边界。
- [x] 将发布级 TTS `quality_tier` 口径调整为 `publish`,并补 doctor 单测。
- [x] 将宿主画面 CLI capability 从“命令存在”升级为“探测命令能写出临时资产”。
- [x] 新增对标说明文档,明确不做自研引擎、不 import/bundle Remotion/HyperFrames、不加新用户命令、不做爆款算法/平台知识包。

### Review: M2 对标差距补充

- 对标依据:用户 M2 最终版附件与 `reference/final-audit/00_EXECUTIVE_SUMMARY.md`、`03_BEST_PRACTICES.md`、`07_GOAL_PATCH_SUGGESTIONS.md`。
- 补齐项:发布级 TTS 对外字段统一为 `quality_tier=publish`;宿主画面 CLI capability 改为行为探测,必须写出临时资产才标可用。
- 不做边界:不自研/不 bundle Remotion/HyperFrames,不新增用户命令,不做平台知识包、爆款算法、声音克隆、ASR、本地权重或默认视频下载。
- 验证: `uv run pytest -q` 96 passed;`uv run ruff check .` 通过;5 个扫描器 exit=0;`pnpm --dir apps/web lint` 与 `build` 通过;`run_verification.py` 52 PASS / 0 FAIL;`git diff --check` 通过。
- 证据文档:`docs/dev/20_M2_REFERENCE_GAP_AUDIT.md`。

## 开源首用路径补强清单

- [x] 明确 Codex 桌面版完整工作流:灵剪核心不内置 Remotion/HyperFrames,但用户可安装/启用宿主插件或 skill,再由灵剪消费资产。
- [x] 补齐缺画面能力时的引导:推荐 HyperFrames/Remotion/imagegen,安装后新开会话并重跑 `lj setup`。
- [x] 补齐缺配音能力时的路径:TTS API 或用户已录好的口播音频,新增 `--audio-file` / `--voice-audio-file` 接入口。
- [x] 新增创作者向文档 `docs/CREATOR_QUICKSTART.md` 与能力矩阵 `docs/CAPABILITY_MATRIX.md`。
- [x] 更新 README、SKILL、ONBOARDING、providers、troubleshooting、skill-and-mcp 的主线说明。
- [x] 重跑 pytest、ruff、5 扫描器、Web lint/build 与 verification。
- [x] 产出 Claude 对抗式审查移交文档,系统对标行业并列出可挑战问题。

### Review: 开源首用路径补强

- 实现: `apps/cli/lingjian_cli/main.py` 支持 `lj voice --audio-file` 与 `lj run --voice-audio-file`,写入 `provider_id=user_audio`、`provider_is_mock=false`,复制音频到项目 artifact。
- 文档:普通用户入口拆为创作者快速开始与能力矩阵;明确插件/skill 不是灵剪内置,但 Codex 桌面版用户应被引导安装/启用。
- 安全边界:用户录音只进入本地项目 artifact,导出 manifest 只写来源类型,不记录原始路径;Remotion/HyperFrames 仍不 import、不 bundle。
- 验证:`uv run pytest -q` 为 99 passed;ruff、5 扫描器、Web lint/build 均通过;`run_verification.py` 为 52 PASS / 0 FAIL。
- 对抗审查移交:`docs/dev/22_CLAUDE_ADVERSARIAL_REVIEW_HANDOFF.md`。

## 开源发布收尾整改清单

- [x] P0-1: 使用真实仓库 `https://github.com/dososo/blcaptain-lingjian-video.git` 替换用户面 `<REPO_URL>`,配置 remote。
- [x] P1-1: 校准 HyperFrames/Remotion skill 安装标识符,保留已由官方入口确认的标识符并补官方文档链接。
- [x] P2-1: README Web 段就地补“静态骨架,不能替代 CLI 审批流”免责。
- [ ] P2-2: `--strict` 为可选增强,本轮未动;如需改变 QA/export 行为需用户确认。
- [x] 产出发布收尾说明 `docs/dev/23_RELEASE_CLOSING.md`。
- [x] P0 完成后重跑全量验收命令。
- [x] 干净 clone 首用自检通过,证据归档到 `verification/release_closing/`。
- [ ] 提交自检证据,更新 `v0.1.0` tag 并 push。

### Review: 开源发布收尾整改

- P1-1 依据:HyperFrames 官方 quickstart/GitHub 均确认 `npx skills add heygen-com/hyperframes`;Remotion Agent Skills 官方文档确认 `npx skills add remotion-dev/skills`。
- P2-1 已落地:README 顶部能力说明和 Web 控制台段均标明 Web 当前为静态骨架,完整主线以 CLI 为准。
- 当前状态:真实开源仓库已创建并配置 remote;全量验收与干净 clone 自检通过,等待提交自检证据、更新 tag、push。
