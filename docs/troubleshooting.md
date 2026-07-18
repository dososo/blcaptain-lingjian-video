# 故障排查

## doctor 不 ready

先看 `required`:

- 缺 FFmpeg/ffprobe: 安装 FFmpeg。
- 缺 `ffmpeg_drawtext`: 当前 FFmpeg 不支持 `drawtext/libfreetype`;先跑 `ffmpeg -hide_banner -h filter=drawtext` 自检。
- 缺中文字体: 安装 PingFang/STHeiti 或配置 Noto Sans SC。
- 缺真实 LLM/TTS: 配置 CLI provider 或 API provider。
- 缺发布级 TTS:配置火山/OpenAI-compatible TTS,或使用 `--audio-file` / `--voice-audio-file` 提供已录好的口播音频。
- visuals 只有 fallback:安装/启用 Codex 桌面版 HyperFrames、Remotion 或其他视频生成插件/skill,安装后新开会话再跑 `uv run lj setup`;imagegen 只能做静态参考图。发布级也可把每镜 mp4/mov/m4v 放进 `project/assets/scenes/`。
- CLI provider 已设置但仍缺失: 确认 `LINGJIAN_LLM_CLI` / `LINGJIAN_TTS_CLI` 指向可执行命令,且命令可从 stdin 读 JSON、向 stdout 写 JSON。

## render 返回 `APPROVAL_REQUIRED`

说明文案、语音或画面至少一个 artifact 未审批。依次执行:

```bash
uv run lj approve script <project> --approved-by <name> --json
uv run lj approve voice <project> --approved-by <name> --json
uv run lj approve visuals <project> --approved-by <name> --json
```

## render 返回 `APPROVAL_STALE`

说明审批后 artifact 内容变了。重新审核当前 artifact 后再渲染。

## release 导出失败

- `RELEASE_RENDER_REQUIRES_FFMPEG`: `render --release` 需要同时找到 FFmpeg 和 ffprobe。安装后先跑 `uv run lj doctor --json`。
- `FFMPEG_FILTER_UNAVAILABLE`: 当前 FFmpeg 缺少 `drawtext/libfreetype`,请安装带 freetype 的 FFmpeg 后重试。
- `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`: 当前链路含 mock provider,不能 release。
- `PREVIEW_ARTIFACT_NOT_RELEASABLE`: 正在引用 preview 产物,需要 release render。
- `RELEASE_VIDEO_IS_STUB`: release QA 检测到视频仍是离线 stub,不得发布。
- `RENDER_NOT_VERIFIABLE`: release QA 无法用 ffprobe 确认有效视频流。
- `RELEASE_AUDIO_MISSING`: release 视频缺少可验证音频流,请重新生成真实 voice 并重新 release render。
- `RELEASE_AUDIO_IS_PREVIEW_VOICE`: 当前音轨来自 Kokoro/Piper/say/espeak-ng 等样片/预览级 TTS,请改用已录好的口播音频或配置火山豆包/OpenAI-compatible 等自然中文 TTS。
- `RELEASE_VISUAL_IS_BLANK_CARD`: 当前画面全部是回落卡片,请安装/启用真实画面插件,或按 `visual_plan.json` 放置每镜 mp4/mov/m4v。
- `RELEASE_VISUAL_IS_TEMPLATE_LOOP`: 当前画面来自灵剪内置 HyperFrames 样片模板,可能只是短循环/闪动,不能作为发布级真实视频。
- `RELEASE_VISUAL_REUSES_SINGLE_ASSET`: 多镜头复用了同一个素材,更像一张图反复闪几秒,请为每镜提供不同的真实视频资产。
- `RELEASE_VISUAL_CONTAINS_STATIC_IMAGE`: 当前 release 含静态图片镜头;一张图片放几秒、Ken Burns 或轻微缩放都不算发布级视频,请提供真实视频素材或动态生成资产。
- `QA_BLOCKING`: QA hard failure 未修复。

## CLI provider 失败

- `PROVIDER_TIMEOUT`: CLI provider 60 秒内没有返回。
- `PROVIDER_CLI_FAILED`: CLI provider 退出码非 0。
- `LLM_INVALID_JSON`: CLI stdout 不是合法 JSON object。
- `LLM_OUTPUT_TOO_THIN`: LLM CLI 返回空 scenes 或 narration_text 过少。
- `TTS_OUTPUT_INVALID`: TTS CLI 返回空音频、非法 base64 或非正数 duration。

## OpenAI-compatible API provider 失败

- `PROVIDER_AUTH_FAILED`: key 或模型权限无效。
- `LLM_RATE_LIMITED`: API 返回限流。
- `PROVIDER_QUOTA_EXCEEDED`: API 返回额度不足。
- `PROVIDER_API_FAILED`: base URL、endpoint 或网络请求失败。
- `LLM_INVALID_JSON`: LLM 没有返回包含 `scenes` 的 JSON object。
- `LLM_OUTPUT_TOO_THIN`: LLM 返回空 scenes 或 narration_text 过少。
- `TTS_OUTPUT_INVALID`: TTS endpoint 没有返回有效音频字节。

## Web build 有 sharp 审批问题

根 `pnpm-workspace.yaml` 已允许 `sharp` 构建。若本地仍失败,执行:

```bash
pnpm rebuild sharp
pnpm install
```
