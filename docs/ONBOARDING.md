# 灵剪 Onboarding:能力检测与继承优先

灵剪面向 Codex app 用户。第一步不是让你填 key,而是在 Codex app 里安装插件/skill 后,由 Codex 自动检测这台机器和当前会话已经具备什么能力,能继承就直接继承。

## 心智模型

- 预览档:可使用 mock、macOS say/espeak-ng 或 fallback_solid,用于离线体验、门禁验证和流程演示。
- 发布档:必须同时具备真实 LLM、Kokoro/云 TTS/用户录音、真实画面插件/每镜素材、FFmpeg/ffprobe/drawtext/AAC、中文字体和底部字幕安全区。`--strict --release` 下 say、espeak 与 fallback_solid 会阻断。

mock 永远不能用于正式 release。doctor 未 ready 时,真实终验必须停下,不得伪造 PASS。

能力分三层:

- 🟢 零 key 免费:继承 Claude/Codex CLI、HyperFrames 本地画面、Kokoro 中文 TTS、用户自备素材/录音、FFmpeg。
- 🟡 付费或需连接账号:火山豆包/OpenAI-compatible TTS、Fal/Picsart/HeyGen 数字人、商业素材库等。
- 🔴 发布需自建或人工:抖音/小红书/YouTube/TikTok 自动发布不在本仓库内,导出后人工上传或自建。

## 第一步:自动检测

Codex 对话里只需要说“先做灵剪能力门诊”。底层可用命令是 `uv run lj setup`;`uv run lj setup --json` 和 `uv run lj doctor --json` 只给 Codex/审计脚本使用,不要把原始 JSON 当作普通用户界面。

`lj setup` 会按优先级检测:

- LLM:先找 Claude Code 的 `claude`、Codex 的 `codex` 等官方订阅 CLI;再找 `ollama`、`llm`;最后才看 OpenAI-compatible key。
- TTS:先找用户录音、发布级云 TTS 或真实 TTS CLI;然后找 Kokoro 中文本地 TTS;再找用户自装 Piper;最后才使用 macOS `say`、espeak-ng 预览音,并在严格发布 QA 中阻断。
- 画面:优先检测 HyperFrames 零 key 动态画面;也可消费用户自带 `assets/scenes/` 素材或宿主 Remotion/imagegen 资产。都没有时才回落卡片,严格发布 QA 会阻断。
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

- 商用发布优选:用户录音、火山豆包、OpenAI-compatible TTS、自定义真实 TTS CLI。默认自动择优,有云 TTS 或录音就优先使用。
- 零 key 默认:Kokoro 中文本地 TTS。Apache-2.0 权重,可通过 `--strict` 发布门,但商用品质仍建议人工试听。
- 用户自装零 key:Piper 中文本地 TTS。Piper/模型涉及 GPL-3.0,只能由用户自装,灵剪只子进程调用,不进入核心依赖树。
- 预览级:macOS `say`、espeak-ng。零 key、可验证流程,但不是发布级;`--strict --release` 会因 `RELEASE_AUDIO_IS_PREVIEW_VOICE` 阻断。

先安装零 key 中文 Kokoro:

```bash
uv sync
npx hyperframes tts --list
uv run lj setup
```

`uv sync` 会安装灵剪的 Kokoro ONNX 运行包;`npx hyperframes tts --list` 用于确认 HyperFrames 的本地 Kokoro 资源可用。

只确认本机预览级是否可用:

```bash
say "灵剪语音检测"
uv run lj setup
```

macOS 的 `say` 不需要 key,但只用于预览。其他系统可安装 espeak-ng 预览音,或安装 Kokoro/Piper 作为本地 TTS。

如果你已经录好了口播音频,可以不用 TTS provider:

```bash
uv run lj voice ./projects/demo --provider auto --voice user --audio-file narration.m4a --json
# 或主线:
uv run lj run ./projects/demo --input-file input.txt --script-provider auto --voice-audio-file narration.m4a --json
```

这会写入 `provider_id=user_audio`,不标 mock,也不会把原始文件路径写进导出包。

Piper(GPL-3.0,用户自装):

```bash
pip install piper-tts
python3 -m piper.download_voices zh_CN-huayan-medium
uv run lj setup
```

Ubuntu/Debian 预览音:

```bash
sudo apt-get update && sudo apt-get install -y espeak-ng
uv run lj setup
```

Windows:

```powershell
winget install Gyan.FFmpeg
ffmpeg -filters | findstr drawtext
```

Windows 本机 TTS 当前建议通过 Piper、espeak-ng 或 OpenAI-compatible TTS 接入;macOS `say` 仅在 macOS 可用。

确实需要云 TTS 时再配置:

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

## 画面能力:HyperFrames 零 key 优先,自备素材稳态回落

灵剪核心不内置 Remotion/HyperFrames SDK。它会在 visuals 阶段生成每镜 storyboard,每镜包含:

- `generator`: `hyperframes`、`remotion`、`image-gen`、`user-asset` 或 `fallback_solid`。
- `visual_prompt`: 给 imagegen 的画面提示词。
- `motion_spec`: 给 HyperFrames/Remotion 的主运动结构描述。
- `brief`: 比例、安全区、禁项。
- `expected_asset_path`: 约定资产落点。
- `duration_sec`: 与配音时长对齐。

当前已验证的零 key 画面路径是检测到 `npx hyperframes` 后,用薄子进程适配器按镜头生成:

```text
project/assets/scenes/<scene_id>.mp4
```

你也可以直接提供每镜素材,这是稳定回落路径:

```text
project/assets/scenes/<scene_id>.mp4
project/assets/scenes/<scene_id>.png
```

Codex app 用户也可以在 Plugins / Add to Codex 中安装或启用更完整的宿主画面插件/skill。命令只是备用:

```bash
npx skills add heygen-com/hyperframes
npx skills add remotion-dev/skills
```

上面两个标识符分别来自 HyperFrames 与 Remotion 官方 skill 安装入口。注意:

- HyperFrames 需要 Node.js 22+ 与 FFmpeg,本地渲染零 key,已通过灵剪端到端 strict 验证。
- Remotion 需要 Node.js 与自动下载的 Chrome Headless;营利组织若超过 3 人使用,需核对 Remotion 商用 license。
- 若 skills CLI 或 Codex 插件市场发生变化,以官方文档和 Codex app 插件市场为准:

- HyperFrames: https://hyperframes.heygen.com/quickstart
- Remotion Agent Skills: https://www.remotion.dev/docs/ai/skills

安装后新开 Codex 会话,再跑 `uv run lj setup`。宿主 agent 或灵剪薄适配器使用已启用的 HyperFrames/Remotion/imagegen 产出:

```text
project/assets/scenes/<scene_id>.mp4
project/assets/scenes/<scene_id>.png
```

如果宿主没有这些能力,也没有用户自备素材,lj 会回落纯色卡片。普通 release 默认给 `RELEASE_VISUAL_IS_BLANK_CARD` warning;发布级验收请使用 `--strict`,此时会阻断。

这不是默认 release 硬门,是发布级质量门:没有真实画面仍可做低保真预览,但不能声称已经生成可发布动态画面。

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

当 Codex 确认能力门诊 ready 后,再执行真实终验:

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
