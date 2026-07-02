# 创作者快速开始

这份文档面向普通自媒体用户。你不需要先理解全部 CLI,只要按素材类型选择一条路径。

## 先做一次能力检测

```bash
uv sync
scripts/install_skill_links.sh
uv run lj setup
uv run lj doctor --json
```

看 `lj setup` 的结论:

- LLM 已继承 Claude/Codex:可以用订阅能力写脚本,不需要 key。
- TTS 只有 macOS say/Piper/espeak-ng:能听预览,但不是发布级配音。
- visuals 是 fallback_solid:还没有真实画面生成能力,需要安装/启用 Codex 里的 HyperFrames、Remotion、imagegen,或自己提供每镜素材。
- render OK:本机 FFmpeg/ffprobe/drawtext 已能出片。

## 你有一段文案

把文案保存成 `input.txt`,然后对 Codex 说:

```text
请使用 lingjian-video。先运行 uv run lj setup,告诉我已继承和缺失的能力。然后把 input.txt 做成 45 秒抖音竖屏视频,脚本用 auto 继承当前 Codex/Claude 能力,配音优先用发布级 TTS;如果没有发布级 TTS,请引导我配置 TTS API 或让我提供已录好的口播音频。画面阶段如果没有 HyperFrames/Remotion/imagegen,请引导我安装插件/skill,不要直接把 fallback 卡片说成真实画面。
```

对应命令:

```bash
uv run lj run ./projects/my-video \
  --name "我的视频" \
  --input-file input.txt \
  --script-provider auto \
  --voice-provider auto \
  --platform douyin \
  --ratio 9:16 \
  --json
```

默认会停在 script / voice / visuals 三次审核点。你看完 artifact 后再批准。

## 你已经录好了口播音频

如果你有 `narration.m4a`、`narration.wav` 或 `narration.mp3`,可以不用 TTS:

```bash
uv run lj run ./projects/my-video \
  --name "我的视频" \
  --input-file input.txt \
  --script-provider auto \
  --voice-audio-file narration.m4a \
  --platform douyin \
  --ratio 9:16 \
  --json
```

这条路径会把录音复制进项目 artifact,`provider_id=user_audio`,不标 mock,也不会把你的原始路径写进导出包。

## 你没有配音能力

按优先级选择:

1. 有录好的口播:用 `--voice-audio-file`。
2. 中文发布级 TTS:配置火山豆包。
3. OpenAI-compatible TTS:配置 `OPENAI_TTS_*`。
4. 只想预览:用 macOS say/Piper/espeak-ng,但 release QA 会提示 `RELEASE_AUDIO_IS_PREVIEW_VOICE`。

火山豆包:

```bash
export VOLCENGINE_TTS_APP_ID=...
export VOLCENGINE_TTS_ACCESS_TOKEN=...
export VOLCENGINE_TTS_CLUSTER=...
export VOLCENGINE_TTS_VOICE_TYPE=...
uv run lj doctor --json
```

## 你需要真实画面

灵剪不内置 Remotion/HyperFrames。Codex 桌面版用户应先安装或启用相关插件/skill,让宿主生成每镜资产,再交给 lj 组装。

可尝试:

```bash
npx skills add heygen-com/hyperframes
npx skills add remotion-dev/skills
```

上面两个标识符分别来自 HyperFrames 与 Remotion 的官方 skill 安装入口。若 skills CLI 或 Codex 插件市场发生变化,以官方文档为准:

- HyperFrames: https://hyperframes.heygen.com/quickstart
- Remotion Agent Skills: https://www.remotion.dev/docs/ai/skills

安装或启用后,新开 Codex 会话,再跑:

```bash
uv run lj setup
```

如果 `visuals` 仍是 fallback,也可以手动把素材放到:

```text
projects/<项目>/assets/scenes/s1.mp4
projects/<项目>/assets/scenes/s2.png
```

然后运行:

```bash
uv run lj visuals ./projects/my-video --engine ffmpeg_card --template product --json
uv run lj approve visuals ./projects/my-video --approved-by <你的名字> --json
uv run lj run ./projects/my-video --json
```

## 发布前检查

发布档必须同时满足:

- `uv run lj doctor --json` 中 `ready=true`。
- QA 没有 hard failure。
- 没有 `RELEASE_VISUAL_IS_BLANK_CARD`,否则说明全片还是回落卡片。
- 没有 `RELEASE_AUDIO_IS_PREVIEW_VOICE`,否则说明配音只是预览级。
- `ffprobe` 能看到 video 和 audio 流。
- 导出包里的 `license_manifest.md` 不含 key、base URL、完整命令或本机私密路径。

如果只想验证流程,可以使用 mock 预览档;但 mock 结果不能当发布级视频。
