# 灵剪 Onboarding:能力检测与继承优先

灵剪面向公开开源用户,默认认为你可能正在 Codex 桌面版、Claude Code、本机模型或普通 shell 中使用。第一步不是让你填 key,而是先检测这台机器已经具备什么能力,能继承就直接继承。

## 心智模型

- 预览档:零配置使用 mock provider,用于离线体验、门禁验证和流程演示。
- 发布档:必须同时具备真实 LLM、真实非 mock TTS、FFmpeg/ffprobe、中文字体。缺一项都不能 release;只有本机预览级 TTS 时可出 release,但 QA 会提示建议升级发布级 TTS。

mock 永远不能用于正式 release。doctor 未 ready 时,真实终验必须停下,不得伪造 PASS。

## 第一步:自动检测

```bash
uv run lj setup
uv run lj setup --json
uv run lj doctor --json
```

`lj setup` 会按优先级检测:

- LLM:先找 Claude Code 的 `claude`、Codex 的 `codex` 等官方订阅 CLI;再找 `ollama`、`llm`;最后才看 OpenAI-compatible key。
- TTS:先找发布级云 TTS 或真实 TTS CLI;没有时使用本机预览级 TTS,如 macOS `say`、Piper、espeak-ng,并在发布 QA 中 warning。
- 画面:当前已验证的发布级视觉首选路径是消费用户自带 `assets/scenes/` 素材;宿主 HyperFrames/Remotion/imagegen 自动生成属于可选进阶。两者都没有时才回落卡片并在 QA warning。
- 渲染:检查本机 `ffmpeg`、`ffprobe`,并确认 `ffmpeg` 支持 `drawtext/libfreetype`。
- 字体:macOS 用 PingFang;其他系统可放 `~/.cache/lingjian/fonts/NotoSansSC-Regular.otf`。

命中可继承能力时,灵剪会显示「无需 key」。只对缺失项给下一条命令。

## LLM:先继承,后 key

如果你已经登录 Claude Code 或 Codex CLI:

```bash
claude --version
codex --version
uv run lj setup
```

灵剪只调用官方 CLI 命令,不读取、不复制、不搬运 OAuth token 或凭据文件。

如果没有订阅 CLI,可以使用本机模型:

```bash
ollama --version
llm --version
uv run lj setup
```

如果以上都没有,再配置 OpenAI-compatible 三件套:

```bash
export OPENAI_BASE_URL=https://api.example.com/v1
export OPENAI_API_KEY=...
export OPENAI_MODEL=...
uv run lj doctor --json
```

## TTS:订阅通常不包含

ChatGPT/Claude 订阅通常只提供 LLM,不代表 TTS 也可用。TTS 分两档:

- 发布级:火山豆包、OpenAI-compatible TTS、自定义真实 TTS CLI。默认自动择优,有发布级就优先发布级。
- 预览级:macOS `say`、Piper、espeak-ng。零 key、可验证流程,但 release QA 会给 `RELEASE_AUDIO_IS_PREVIEW_VOICE` warning。

先确认本机预览级是否可用:

```bash
say "灵剪语音检测"
uv run lj setup
```

macOS 的 `say` 不需要 key。其他系统可安装 Piper 或 espeak-ng。

如果你已经录好了口播音频,可以不用 TTS provider:

```bash
uv run lj voice ./projects/demo --provider auto --voice user --audio-file narration.m4a --json
# 或主线:
uv run lj run ./projects/demo --input-file input.txt --script-provider auto --voice-audio-file narration.m4a --json
```

这会写入 `provider_id=user_audio`,不标 mock,也不会把原始文件路径写进导出包。

确实需要云 TTS 时再配置:

Ubuntu/Debian:

```bash
sudo apt-get update && sudo apt-get install -y espeak-ng
uv run lj setup
```

Piper 可作为更自然的本机 TTS,请按发行版安装官方包或二进制后确保 `piper` 在 `PATH` 中:

```bash
piper --version
uv run lj setup
```

Windows:

```powershell
winget install Gyan.FFmpeg
ffmpeg -filters | findstr drawtext
```

Windows 本机 TTS 当前建议通过 Piper、espeak-ng 或 OpenAI-compatible TTS 接入;macOS `say` 仅在 macOS 可用。

中文发布级 TTS 首选火山豆包:

```bash
export VOLCENGINE_TTS_APP_ID=...
export VOLCENGINE_TTS_ACCESS_TOKEN=...
export VOLCENGINE_TTS_CLUSTER=...
export VOLCENGINE_TTS_VOICE_TYPE=...   # 可选
uv run lj doctor --json
```

也可以使用 OpenAI-compatible TTS:

```bash
export OPENAI_TTS_BASE_URL=https://api.example.com/v1
export OPENAI_TTS_API_KEY=...
export OPENAI_TTS_MODEL=...
uv run lj doctor --json
```

## FFmpeg 与字体

release 渲染必须本机安装 FFmpeg/ffprobe,并且 FFmpeg 必须支持:

- `drawtext/libfreetype`:用于烧录中文字幕。
- AAC 音频编码:用于把真实 TTS 配音合入发布视频。

只安装到二进制还不够;`lj doctor` 会实际探测这些能力,缺失时保持 `ready=false`。

macOS:

```bash
brew install ffmpeg
ffmpeg -hide_banner -h filter=drawtext
```

如果 `drawtext` 不存在,请安装或切换到带 freetype 的 FFmpeg,例如:

```bash
brew reinstall ffmpeg
brew install ffmpeg-full
brew unlink ffmpeg && brew link ffmpeg-full
ffmpeg -filters | grep drawtext
```

Ubuntu/Debian:

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
ffmpeg -filters | grep drawtext
```

Windows:

```powershell
winget install Gyan.FFmpeg
ffmpeg -filters | findstr drawtext
```

字体:

- macOS 默认使用 PingFang。
- 其他系统缺字体时,放置 `~/.cache/lingjian/fonts/NotoSansSC-Regular.otf`。

## 画面能力:自备素材优先,宿主委托进阶

灵剪核心不内置 Remotion/HyperFrames。它会在 visuals 阶段生成每镜 storyboard,每镜包含:

- `generator`: `hyperframes`、`remotion`、`image-gen`、`user-asset` 或 `fallback_solid`。
- `visual_prompt`: 给 imagegen 的画面提示词。
- `motion_spec`: 给 HyperFrames/Remotion 的主运动结构描述。
- `brief`: 比例、安全区、禁项。
- `expected_asset_path`: 约定资产落点。
- `duration_sec`: 与配音时长对齐。

当前已验证的发布级视觉路径是把每镜 mp4/png 放到:

```text
project/assets/scenes/<scene_id>.mp4
project/assets/scenes/<scene_id>.png
```

Codex 桌面版用户也可以安装或启用宿主画面插件/skill,让宿主自动生成这些资产。可尝试:

```bash
npx skills add heygen-com/hyperframes
npx skills add remotion-dev/skills
```

上面两个标识符分别来自 HyperFrames 与 Remotion 官方 skill 安装入口。若 skills CLI 或 Codex 插件市场发生变化,以官方文档为准:

- HyperFrames: https://hyperframes.heygen.com/quickstart
- Remotion Agent Skills: https://www.remotion.dev/docs/ai/skills

安装后新开 Codex 会话,再跑 `uv run lj setup`。宿主 agent 使用已启用的 HyperFrames/Remotion/imagegen 产出:

```text
project/assets/scenes/<scene_id>.mp4
project/assets/scenes/<scene_id>.png
```

如果宿主没有这些能力,也没有用户自备素材,lj 会回落纯色卡片并在 release QA 中给 `RELEASE_VISUAL_IS_BLANK_CARD` warning。

这不是 release 硬门:没有宿主画面能力仍可出片,但不能声称已经生成动态画面。

CLI 委托入口可选:

```bash
export LINGJIAN_HOST_IMAGEGEN_CLI=/path/to/real-imagegen
export LINGJIAN_HOST_HYPERFRAMES_CLI=/path/to/hyperframes
export LINGJIAN_HOST_REMOTION_CLI=/path/to/remotion
```

这些命令只接收 storyboard JSON 并把资产写到 `expected_asset_path`;灵剪不会读取它们的凭据文件。

## 安全承诺

我郑重承诺:

- 默认只读取当前 shell 环境变量,不把 key 写入仓库、日志、manifest、release 包或 stdout。
- 能继承 CLI 能力时,不会要求你提供 key。
- 继承订阅只调用厂商官方 CLI,不读取 OAuth token、cookie、Keychain 内部文件或私密凭据文件。
- 需要持久化凭据时,优先使用 OS 安全存储:macOS Keychain、Linux Secret Service、Windows Credential Manager。
- 没有安全存储时,只有在你明确同意后才允许使用 `0600` 权限本地配置文件。
- `lj credentials status --json` 只显示是否存在,不显示值。
- `lj credentials forget NAME --json` 可撤销已存凭据;当前 shell 里的变量仍需你自己 `unset`。

## 真实终验

当 `uv run lj doctor --json` 返回 `ready=true` 后,再执行:

```bash
uv run python scripts/ci/run_verification.py
```

此时 `V-REAL-01` 才会真实执行 script -> voice -> visuals -> approve -> render --release -> qa --release -> export --release -> ffprobe。

人工抽验发布视频时,应看到至少一个视频流和一个音频流:

```bash
ffprobe -v error -show_entries stream=codec_type,codec_name -of json <release-video.mp4>
```

真实环境终验 runbook 见 `docs/dev/11_REAL_VERIFY.md`。

## 用户、Codex、Claude 分工

- 用户:提供本机已登录 CLI、真实 provider key 或安装 FFmpeg 等外部条件。
- Codex:改代码、跑命令、生成证据、打包交付。
- Claude Code:拆需求、做架构规划与第 7 步审计复核。

任何前置不满足时,流程必须停下并说明缺什么。不能用 echo、固定 JSON、假 CLI 冒充真实 provider。
