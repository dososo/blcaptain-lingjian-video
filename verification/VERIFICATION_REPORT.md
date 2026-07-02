# 验证报告

日期: 2026-07-02

## 置顶结论

- `V-REAL-01`: `PASS`
- 真实环境: 默认 `/opt/homebrew/bin/ffmpeg` 已链接到 `ffmpeg-full`,支持 `drawtext/libfreetype`;LLM 继承 `claude_cli`,TTS 使用 macOS `say`。
- 真实终验证据:`verification/evidence/V-REAL-01.log`。
- 离线回落证据:`verification/results.offline_fallback_20260702.json` 与 `verification/evidence/V-REAL-01.offline_fallback_20260702.log`。
- 诚实边界:隐藏 `claude/codex` 且清空 provider env 后,`V-REAL-01` 回落 `BLOCKED_ENV(real_llm_provider)`,FAIL=0。

## 汇总

- 总项数: 52
- PASS: 52
- FAIL: 0
- BLOCKED_ENV: 0
- 结果文件: `verification/results.json`
- 真实 PASS 快照: `verification/results.real_pass_20260702.json`
- 离线回落快照: `verification/results.offline_fallback_20260702.json`
- 命令日志: `verification/evidence/*.log`

## 已验证主项

- 基础质量: `uv sync`、`uv run pytest`、`uv run ruff check .`。
- doctor: required 缺失时退出码非 0,并输出脱敏 provider 状态。
- M2 provider: fake CLI 与 fake OpenAI-compatible API 离线测试证明 `llm_cli`/`tts_cli`/`openai_compatible`/`openai_compatible_tts` 配置后可解析为 `is_mock=false`,script/voice artifact 正确落 provider 信息。
- M3 provider 健全性:CLI/API provider 空 scenes 或空音频会返回 `LLM_OUTPUT_TOO_THIN` / `TTS_OUTPUT_INVALID`。
- M3 TTS 时长:OpenAI-compatible TTS 对 WAV 响应使用帧数/采样率计算 duration,不依赖 FFmpeg。
- M3 preview real:默认 preview 仍为 stub;`--real` opt-in 在无 FFmpeg 时回落 stub,有 FFmpeg 时走 ffmpeg_card 路径。
- M3 release 时长:release FFmpeg 输入时长读取 `voice_plan.total_duration_sec`,缺失时继续兜底。
- Onboarding 能力层:`lj setup` 会先继承订阅/本机 CLI 能力;`resolve_provider("auto", kind)` 可解析到当前最优真实 provider。
- M2 画面委托:`visual_plan.json` 可按镜记录 host/user/fallback generator、`visual_prompt`、`motion_spec` 与 `expected_asset_path`;release/real-preview 会先委托可用宿主 CLI 生成缺失资产,再消费每镜 mp4/png 产物并组装;缺产物回落 `fallback_solid` 且 QA 给 `RELEASE_VISUAL_IS_BLANK_CARD` warning。
- M2 宿主能力分档:`lj setup --json` 输出 `capabilities.visuals`;HyperFrames/Remotion/imagegen 为宿主委托能力,不作为 release 硬门。
- M2 发布级配音分档:`capabilities.tts` 记录 `quality_tier`;火山豆包/OpenAI-compatible/真实 TTS CLI 为 release tier,say/Piper/espeak-ng 为 preview tier。
- Web: `pnpm --dir apps/web lint` 与 `pnpm --dir apps/web build`;build 输出包含 5 个主流程路由。
- Web smoke: Playwright 打开 `/` 与 `/export`,截图写入 `output/playwright/web-smoke.png`。
- 审批门禁: 未审 render 返回 `APPROVAL_REQUIRED`;改稿后 render 返回 `APPROVAL_STALE`;三审后 preview render 成功。
- release 边界: mock release 返回 `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`。
- release 视频本体验证: stub 哨兵返回 `RELEASE_VIDEO_IS_STUB`;ffprobe 不可验证返回 `RENDER_NOT_VERIFIABLE`;缺音频流返回 `RELEASE_AUDIO_MISSING`。
- release render 环境门禁: 无 FFmpeg/ffprobe 时返回 `RELEASE_RENDER_REQUIRES_FFMPEG`,不写 stub;有 FFmpeg 但无 `drawtext/libfreetype` 时 doctor 不 ready,render 失败返回 `FFMPEG_FILTER_UNAVAILABLE` 与 stderr 摘要。
- release 真出片: `ffmpeg_card` 生成 H.264/yuv420p MP4,并合入 TTS 音频为 AAC 音轨。
- release 画面质量提示:当前机器未检测到宿主 HyperFrames/Remotion/imagegen,`V-REAL-01` 使用回落卡片并给 warning;这不影响非 stub、视频流、音频流和真实 provider hard gate。
- release 配音质量提示:当前机器使用 macOS `say` 时,QA 会给 `RELEASE_AUDIO_IS_PREVIEW_VOICE` warning;这不影响真实非 mock 音轨与 AAC hard gate。
- ffprobe timeout: 子进程 20 秒超时会进入 `RENDER_NOT_VERIFIABLE`。
- export: canonical 包结构、YouTube 附加文件、多平台导出均通过。
- license: `license_manifest.md` 记录用户自带 CLI/API provider 类型,不记录 key/base URL/model/命令值。
- reindex: SQLite 派生索引可重建,status 可读。
- 中文路径: 中文项目路径可执行 init/script。
- URL 合规: URL 输入标记为不可信输入,默认不下载视频。
- 伪成功扫描: 13 项扫描全部 PASS;FS-02/03/09/10/13 已改为 AST/行为绑定,FS-07 覆盖静态 dict 例外。

## 不能宣称的内容

- mock preview 只证明离线门禁、导出结构和审计链路,不代表正式可发布质量。
- 继承 CLI 可用于本机真实终验,但不代表任何云 API key 已配置或可用。
- 普通 `ffmpeg` 二进制存在不等于 release 可用;必须通过 `drawtext/libfreetype` 探测。

## 真实终验复核

2026-07-02 当前机器探测:

- OS: macOS 26.5, Darwin 25.5.0, arm64。
- `/opt/homebrew/bin/ffmpeg`: version 8.1.2,配置含 `--enable-libfreetype`;`ffmpeg -hide_banner -h filter=drawtext` 返回 `Draw text on top of video frames using libfreetype library`。
- `ffprobe`: version 8.1.2。
- LLM:检测到 `claude_cli` 与 `codex_cli`,可继承当前 CLI 登录能力。
- TTS:检测到 `macos_say`,本机零 key TTS 可用,质量分档为 preview。
- OpenAI-compatible LLM/TTS env:未配置,但当前不是阻塞项。
- `V-REAL-01.log` 最终 ffprobe:
  - `codec_name=h264`, `codec_type=video`
  - `codec_name=aac`, `codec_type=audio`

因此本机真实终验已通过;离线回落快照证明缺真实 LLM 时不会伪 PASS。
