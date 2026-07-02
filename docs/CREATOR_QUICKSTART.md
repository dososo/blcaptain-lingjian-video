# 创作者快速开始

这份文档面向普通自媒体用户。主入口是在 Codex app 里对话,不是自己手敲完整 CLI。CLI 命令写在这里,是 Codex 代你执行和排错时的底层依据。

## 先做一次能力检测

```bash
uv sync
scripts/install_skill_links.sh
uv run lj setup
```

看 `lj setup` 的结论:

- LLM 已继承 Claude/Codex:可以用订阅能力写脚本,不需要 key。
- TTS 选中 Kokoro/火山/OpenAI-compatible/用户录音:可以进入发布链路;只有 macOS say/espeak-ng 时只能预览,严格发布会阻断。Piper 是用户自装的 GPL 零 key 本地 TTS,不进入灵剪依赖树。
- visuals 选中 host_hyperframes:可以走 HyperFrames 零 key 动态画面;如果仍是 fallback_solid,请安装/启用 HyperFrames 或提供每镜图片/视频。
- render OK:本机 FFmpeg/ffprobe/drawtext 已能出片。

## 你有一段文案

把文案保存成 `input.txt`,然后对 Codex 说:

```text
请使用 lingjian-video。先做灵剪能力门诊,用人话告诉我已继承、已具备、必须补齐、可选增强。然后把 input.txt 做成 45 秒抖音竖屏视频,脚本用 auto 继承当前 Codex/Claude 能力。配音优先用 Kokoro 中文本地 TTS,商用质量可用云 TTS 或我的录音;如果没有,请引导我安装 Kokoro、配置 TTS API 或提供口播音频。画面优先用 HyperFrames 零 key 动态画面;如果没有 HyperFrames/Remotion/imagegen,请引导我在 Codex app 插件市场安装/启用,或让我提供每镜素材;不要直接把 fallback 卡片说成真实画面。
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
2. 零 key 中文 TTS:安装 Kokoro。
3. 商用质量云 TTS:配置火山豆包或 OpenAI-compatible TTS。
4. 只想预览:用 macOS say/espeak-ng,但它们不是发布级;`--strict --release` 会因 `RELEASE_AUDIO_IS_PREVIEW_VOICE` 阻断。

Kokoro:

```bash
uv sync
npx hyperframes tts --list
uv run lj setup
```

Piper(GPL-3.0,用户自装,灵剪只子进程调用):

```bash
pip install piper-tts
python3 -m piper.download_voices zh_CN-huayan-medium
uv run lj setup
```

火山豆包:

```bash
export VOLCENGINE_TTS_APP_ID=...
export VOLCENGINE_TTS_ACCESS_TOKEN=...
export VOLCENGINE_TTS_CLUSTER=...
export VOLCENGINE_TTS_VOICE_TYPE=...
uv run lj doctor --json
```

## 你需要真实画面

灵剪不内置 Remotion/HyperFrames SDK。当前已验证的零 key 画面路径是:检测到 `npx hyperframes` 后,lj 会按 `visual_plan.json` 的 `expected_asset_path` 委托 HyperFrames 生成每镜 mp4,再统一组装。自备每镜 mp4/png 仍是最稳回落路径。

自备素材路径:

```text
projects/<项目>/assets/scenes/s1.mp4
projects/<项目>/assets/scenes/s2.png
```

如需让 Codex 宿主自动生成更丰富画面,优先在 Codex app 的 Plugins / Add to Codex 中安装或启用对应插件。命令只是备用:

```bash
npx skills add heygen-com/hyperframes
npx skills add remotion-dev/skills
```

上面两个标识符分别来自 HyperFrames 与 Remotion 的官方 skill 安装入口。HyperFrames 需要 Node.js 22+ 与 FFmpeg,本地渲染零 key;Remotion 需要 Node.js/Chrome Headless,营利组织超过 3 人使用需核对商用 license。若 skills CLI 或 Codex 插件市场发生变化,以官方文档为准:

- HyperFrames: https://hyperframes.heygen.com/quickstart
- Remotion Agent Skills: https://www.remotion.dev/docs/ai/skills

安装或启用后,新开 Codex 会话,再跑:

```bash
uv run lj setup
```

然后运行:

```bash
uv run lj visuals ./projects/my-video --engine ffmpeg_card --template product --json
uv run lj approve visuals ./projects/my-video --approved-by <你的名字> --json
uv run lj run ./projects/my-video --json
```

## 发布前检查

发布档必须同时满足:

- Codex 能力门诊确认发布级必需能力已补齐。
- QA 没有 hard failure。
- `uv run lj qa --release --strict --json` 没有 hard failure。
- 没有 `RELEASE_VISUAL_IS_BLANK_CARD`,否则说明全片还是回落卡片。
- 没有 `RELEASE_AUDIO_IS_PREVIEW_VOICE`,否则说明配音只是预览级。
- `ffprobe` 能看到 video 和 audio 流。
- 导出包里的 `license_manifest.md` 不含 key、base URL、完整命令或本机私密路径。

如果只想验证流程,可以使用 mock 预览档;但 mock 结果不能当发布级视频。
