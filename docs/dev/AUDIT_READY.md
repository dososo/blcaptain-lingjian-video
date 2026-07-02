# AUDIT_READY

日期: 2026-07-02

## 置顶结论

本轮在 M2 底座上补做「Codex Plugin 发布级主线重定位」:工程底座保持可复现,产品入口从开发者 CLI-first 调整为 Codex app Plugin/Skill prompt-first。

- 真实环境项: `V-REAL-01=PASS`,主 `verification/results.json` 为 52 PASS / 0 FAIL。
- 默认环境规格: macOS,默认 `/opt/homebrew/bin/ffmpeg` 已链接到 `ffmpeg-full`,继承 `claude_cli` LLM,检测到 `npx hyperframes` 与 Kokoro 中文本地 TTS。
- 发布视频抽验: `verification/evidence/V-REAL-01.log` 记录 ffmpeg 路径、版本配置、drawtext、OS 与 ffprobe;最终视频包含 `h264` 视频流与 `aac` 音频流。
- 离线回落项:隐藏 `claude/codex` 并清空 provider env 后,`verification/results.offline_fallback_20260702.json` 为 51 PASS / 1 BLOCKED_ENV / 0 FAIL。
- skill 交付项:根目录 `SKILL.md` 已落盘,README 顶部有对话式安装提示词,`scripts/install_skill_links.sh` 已验证可安装软链。
- 发布准备项:`CHANGELOG.md`、`ROADMAP.md`、隐私/安全说明、跨平台 FFmpeg/TTS 指南、干净 clone 首用自检证据已落盘。
- M2 画面委托项:visuals 生成每镜可执行规格,render 前可委托宿主 imagegen/HyperFrames/Remotion CLI 生成 mp4/png 并组装;缺产物回落卡片且 QA warning,不削弱 release hard gate。
- 生态零 key 项:HyperFrames 已作为首选零 key 画面引擎接入薄子进程委托;Kokoro 中文 TTS 已作为默认零 key 配音 provider 接入;Piper 保留为用户自装 GPL 委托路径。
- M2 配音分档项:用户录音、火山豆包/OpenAI-compatible/真实 TTS CLI 为商用发布优选;Kokoro/Piper 为零 key 本地 TTS;macOS say/espeak-ng 为预览级,`--strict --release` 阻断预览音。
- Codex Plugin 项:新增 `.codex-plugin/plugin.json`、`.agents/plugins/marketplace.json` 与 `skills/lingjian-video/SKILL.md`;安装脚本改用 Codex 官方 `~/.agents/skills`。
- 发布级视觉项:`fallback_solid` 普通 release 默认 warning,`--strict --release` 阻断;HyperFrames 零 key 自动生成已真机通过,自备每镜 mp4/png 仍是稳定回落路径。

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
- `docs/dev/17_RELEASE_PREP.md`
- `docs/dev/18_M2_VISUAL_DELEGATION.md`
- `docs/dev/19_M2_VISUAL_GEN_AND_TTS.md`
- `docs/dev/20_M2_REFERENCE_GAP_AUDIT.md`
- `docs/dev/26_CODEX_PLUGIN_REPOSITIONING.md`
- `docs/dev/28_ECOSYSTEM_INTEGRATION.md`
- `verification/release_prep/*`

## results 对照表

| 文件 | 环境 | 复现命令 | 预期 |
| --- | --- | --- | --- |
| `verification/results.json` | 默认 PATH,`/opt/homebrew/bin/ffmpeg` 为 `ffmpeg-full`,可继承 `claude_cli`,TTS 为 `kokoro_zh_tts`,视觉为 HyperFrames 委托产物 | `uv run python scripts/ci/run_verification.py` | 52 PASS / 0 FAIL,`V-REAL-01=PASS` |
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
- P1-B2 已更新:README 顶部嵌入 Codex app 对话式安装提示词;`scripts/install_skill_links.sh` 用 `ln -sfn` 安装到 Codex 官方 `~/.agents/skills` 与 Claude Code `~/.claude/skills`。
- P1-B3 已落地:本轮不实现 MCP,`packages/mcp_server/README.md` 与 `docs/skill-and-mcp.md` 均明确 MCP 为后续里程碑。
- P1-B4/B5 已落地:`lj setup` 文本模式明确预览档/发布档;README/SKILL.md 写清零 key 预览、隐私、安全、成熟度边界。
- P2-C1/C2 已落地:`lj run <project>` 默认在三审点暂停;显式 `--yes` 会写真实 approval 并完成预览 render -> qa -> export,不绕过审批门。

## 发布准备项

- 版本已对齐:`pyproject.toml`、`package.json`、`apps/web/package.json` 均为 `0.1.0`。
- 变更与路线图已落盘:`CHANGELOG.md` 与 `ROADMAP.md`。
- README 已补隐私、安全、可选依赖审计、macOS/Linux/Windows FFmpeg 与 TTS 路径。
- `.gitignore` 已排除 `.env*`、`.lingjian/`、`projects/`、`exports/`、`.venv/`、`node_modules/` 与构建缓存。
- 干净 clone 首用自检已完成:见 `verification/release_prep/setup.txt`、`doctor.json`、`preview_run.json`、`preview_qa.json`、`preview_export.json`。
- 发布地址已确认:`https://github.com/dososo/blcaptain-lingjian-video.git`;用户面安装命令已替换真实地址,`v0.1.0` tag 在最终发布提交后更新。

## M2 画面委托项

- `apps/cli/lingjian_cli/main.py` 已让 visuals 产物写入每镜 generator/asset/motion/subtitle/brief。
- `packages/core/rendering.py` 已按 visual_plan 消费宿主视频、静态图或用户素材;缺资产时 `fallback_solid` 回落。
- `packages/core/qa.py` 已新增 `RELEASE_VISUAL_IS_BLANK_CARD`;默认 warning,`--strict` 下为 hard failure。
- `packages/core/capabilities.py` 已新增 `capabilities.visuals`,报告 HyperFrames/Remotion/imagegen 或回落卡片。
- 扫描语义不回退:仍禁止 core/providers import Remotion/HyperFrames/Playwright;只允许 generator 字符串和宿主产物消费。

## M2 第2步 生成侧与发布级配音

- `apps/cli/lingjian_cli/main.py` 已让 `visuals` 每镜写入 `visual_prompt`、`motion_spec`、`brief`、`expected_asset_path` 与 `duration_sec`,作为宿主生成契约。
- `packages/core/visual_generation.py` 新增宿主委托层,按 `LINGJIAN_HOST_IMAGEGEN_CLI`、`LINGJIAN_HOST_HYPERFRAMES_CLI`、`LINGJIAN_HOST_REMOTION_CLI` 或同名 CLI 生成缺失资产;失败只记录状态并回落,不伪造产物。
- `providers/volcengine_tts.py` 已注册火山豆包 TTS provider,配置 `VOLCENGINE_TTS_APP_ID`、`VOLCENGINE_TTS_ACCESS_TOKEN`、`VOLCENGINE_TTS_CLUSTER` 后作为发布级中文 TTS。
- `packages/core/qa.py` 已新增 `RELEASE_AUDIO_IS_PREVIEW_VOICE`;默认 warning,`--strict` 下为 hard failure;不削弱非 mock、音频流、ffprobe 等 hard gate。
- `providers/inherited_cli.py` 已给继承/本机 CLI 调用增加一次轻量重试;失败错误保持稳定并标明外部 CLI 调用失败。
- 详细说明: `docs/dev/19_M2_VISUAL_GEN_AND_TTS.md`。

## M2 对标补充项

- 已对标用户 M2 最终版附件与 `lingjian_M1_FINAL_after_claude_final_audit/reference/final-audit/*`。
- 发布级 TTS 字段已统一为 `quality_tier=publish`,preview 本机 TTS 保持 `quality_tier=preview`。
- 宿主画面 CLI 能力检测已从“命令存在”升级为“probe 能写出临时资产”;只 `exit 0` 的空 CLI 不再标为可用。
- 不做边界已明确:不自研/不 bundle Remotion/HyperFrames,不新增用户命令,不做平台知识包/爆款算法/声音克隆/ASR/默认下载视频。
- 对标补充验证: `uv run pytest -q` 为 96 passed;ruff、5 个扫描器、Web lint/build、`run_verification.py` 与 `git diff --check` 均通过。
- 详细说明: `docs/dev/20_M2_REFERENCE_GAP_AUDIT.md`。

## 开源首用路径补强

- 已明确 Codex 桌面版完整工作流:灵剪核心不内置 Remotion/HyperFrames,但用户可安装/启用 HyperFrames、Remotion、imagegen 插件或 skill,由宿主生成资产后交给 lj 组装。
- `lj setup` 缺画面能力时会给出插件/skill 安装和新开会话提示;仍缺失时才允许用户素材或 fallback。
- 已新增用户录音入口:`lj voice --audio-file` 与 `lj run --voice-audio-file`,写入 `provider_id=user_audio`、`provider_is_mock=false`。
- 新增创作者文档:`docs/CREATOR_QUICKSTART.md` 与 `docs/CAPABILITY_MATRIX.md`。
- 保持边界:不实现 MCP、不宣称 Web 完整可用、不 import/bundle Remotion/HyperFrames、不做平台知识包/爆款算法/声音克隆/ASR/默认下载视频。
- 验证:`uv run pytest -q` 为 99 passed;ruff、5 个扫描器、Web lint/build 均通过;`run_verification.py` 为 52 PASS / 0 FAIL。
- 详细说明: `docs/dev/21_OPEN_SOURCE_USABILITY.md`。
- Claude 对抗式审查移交:`docs/dev/22_CLAUDE_ADVERSARIAL_REVIEW_HANDOFF.md`。

## 开源发布收尾

- GitHub 仓库已创建:`https://github.com/dososo/blcaptain-lingjian-video`。
- 仓库可见性已按用户要求改为 `PRIVATE`;公开发布前需再切回 public 或确认仅授权用户分发。
- README 用户面安装命令已替换真实仓库地址;fork 用户说明已保留。
- README Web 段已就地标明“静态骨架,不能替代 CLI 审批流”。
- HyperFrames/Remotion skill 安装标识符已补官方入口链接;若入口变化,以官方文档或 Codex 插件市场为准。
- `--strict` 已在本轮落地为发布级质量门;默认非 strict 保持旧 QA/export 行为。
- 发布收尾验收:`pytest` 99 passed;ruff、5 扫描器、Web lint/build、`run_verification.py` 均通过;`results.json` 为 52 PASS / 0 FAIL。
- 干净 clone 首用自检已通过,证据见 `verification/release_closing/`。
- 详细说明:`docs/dev/23_RELEASE_CLOSING.md`。

## 真实用户体验审查后补强

- README / SKILL 第一条主线命令已改为 `--script-provider auto --voice-provider auto`;mock 仅作为显式流程验证选项。
- HyperFrames/Remotion `npx skills add` 标识符已用临时环境验证可解析安装;但它们是 agent skill 能力,不等于 `lj setup` 可探测的 CLI。
- 历史补强当时把自备每镜 mp4/png 作为发布级视觉首选;本轮生态接入后,最新首选为 HyperFrames 零 key 自动生成,自备素材保留为稳定回落。
- 自备图片 release 链路已真跑,未出现 `RELEASE_VISUAL_IS_BLANK_CARD`,ffprobe 确认 h264+aac;证据见 `verification/release_visual_user_assets/`。
- 详细说明:`docs/dev/24_REAL_USER_EXPERIENCE_NOTES.md`。

## 真实用户现场体验

- 已按用户视角从 setup/doctor 跑到 script/voice/visuals 三审,再由 Codex 宿主 `imagegen` 生成 6 张每镜图片放入 `assets/scenes/`。
- 重跑 `lj visuals` 后 `visual_real_count=6/6`,6 个 scene 均为 `user-asset`;release render/QA/export/ffprobe 通过。
- QA `hard_failures=[]`,未出现 `RELEASE_VISUAL_IS_BLANK_CARD`;仍保留 `RELEASE_AUDIO_IS_PREVIEW_VOICE`,因为当前音轨来自 macOS say 预览级 TTS。
- 视频:`exports/user_experience_live_20260702T081937Z/douyin/zh-CN/9x16/video.mp4`。
- 现场证据:`verification/user_experience_live_user_experience_live_20260702T081937Z/`。
- 详细说明:`docs/dev/25_USER_EXPERIENCE_LIVE_RUN.md`。

## Codex Plugin 发布级主线重定位

- 分发形态:新增 Codex plugin manifest 与 repo marketplace,官方依据为 Codex Plugins 文档的 `.codex-plugin/plugin.json` 与 `$REPO_ROOT/.agents/plugins/marketplace.json`。
- 用户入口:README/SKILL/ONBOARDING/CREATOR_QUICKSTART/CAPABILITY_MATRIX 均改为 Codex app prompt-first;CLI 保留为底层执行和开发备用。
- 发布级最小集合:LLM、发布级 TTS 或用户录音、真实画面插件或每镜素材、FFmpeg/ffprobe/drawtext/AAC、CJK 字体、底部字幕。
- 严格发布:新增 `--strict`,将 `RELEASE_AUDIO_IS_PREVIEW_VOICE` 与 `RELEASE_VISUAL_IS_BLANK_CARD` 从 warning 升为 hard failure 并阻断 release export;默认非 strict 行为不变。
- 字幕位置:`packages/core/rendering.py` 的 drawtext y 坐标改到底部安全区,避免居中遮挡主画面。
- 详细说明:`docs/dev/26_CODEX_PLUGIN_REPOSITIONING.md`。

## Phase 2+3 真机验证

- Codex Plugin 本地官方链路已验证:`codex plugin marketplace add /Users/manxiaochu/Documents/Codex/lingjian-video --json` 与 `codex plugin add lingjian-video@blcaptain-lingjian-video --json` 均成功,plugin 在 `codex plugin list --json` 中为 installed/enabled。

## 生态零 key 引擎接入

- `packages/core/capabilities.py` 已把 `npx hyperframes` 探测为 `host_hyperframes`,setup/doctor 显示 HyperFrames 零 key 动态画面。
- `packages/core/visual_generation.py` 已在没有自定义 `LINGJIAN_HOST_HYPERFRAMES_CLI` 时调用 `scripts/providers/hyperframes_scene_cli.py`,由 `npx hyperframes render` 生成每镜 mp4。
- `providers/local_zero_key_tts.py` 与 `scripts/providers/kokoro_zh_tts.py` 已接入 Kokoro 中文本地 TTS,`provider_id=kokoro_zh_tts`,不 import Kokoro SDK 到核心 provider 主路径。
- `scripts/providers/piper_cli.py` 保留 Piper 用户自装 GPL 委托路径,不进入核心依赖树。
- 真机验收:`uv run lj run ./projects/eco_publish --script-provider auto --voice-provider auto --release --strict --yes --json` 成功导出,QA `hard_failures=[]`,`warnings=[]`,`release_ready=true`。
- 抽验证据:`exports/eco_publish/douyin/zh-CN/9x16/video.mp4` 为 `h264` + `aac`;`render_manifest.json` 显示 `visual_real_count=6/visual_total=6`,6 镜均为 `generator=hyperframes`;抽帧见 `verification/eco_publish_frames/`。
- 详细说明:`docs/dev/28_ECOSYSTEM_INTEGRATION.md`。
- 一句话触发已验证:新 Codex 线程 `019f22b6-2091-7722-83d5-885c3e772757` 对“用 lingjian-video 帮我做一条抖音短视频”返回 `lingjian-video:lingjian-video;下一步进入视频需求澄清阶段`。
- HyperFrames 真机渲染已验证:`npx hyperframes init`、`npm run check`、`npm run render` 成功,输出 `/tmp/lingjian-hyperframes-verify/scene.mp4`,ffprobe 为 h264 1080x1920。
- 灵剪消费 HyperFrames mp4 已验证:项目 `projects/publish_real_phase23` 的 6 个场景均消费 `assets/scenes/*.mp4`,render manifest 为 `visual_real_count=6/6`,QA 不再出现 `RELEASE_VISUAL_IS_BLANK_CARD`。
- 严格发布已用免费本地 Kokoro 补验通过:先确认 `macOS say` 会被 `--strict` 正确阻断,再用 Kokoro `zf_xiaobei` 生成中文口播 wav,通过 `--voice-audio-file` 作为本地音频 artifact 接入项目 `publish_real_kokoro`;`lj qa --release --strict` 为 `hard_failures=[]`,`warnings=[]`,`release_ready=true`,`lj export --release --strict` 成功。
- 免费口播成片:`exports/publish_real_kokoro/douyin/zh-CN/9x16/video.mp4`,ffprobe 为 h264 1080x1920 + aac 24kHz mono;provider manifest 为 `claude_cli` + `user_audio` + `delegated_scene_assembly`,无 mock。
- 详细说明:`docs/dev/27_PHASE23_REAL_VERIFY.md`;抽帧证据:`verification/phase23_frames/`。
