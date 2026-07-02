# 灵剪 Onboarding:能力检测与继承优先

灵剪面向公开开源用户,默认认为你可能正在 Codex 桌面版、Claude Code、本机模型或普通 shell 中使用。第一步不是让你填 key,而是先检测这台机器已经具备什么能力,能继承就直接继承。

## 心智模型

- 预览档:零配置使用 mock provider,用于离线体验、门禁验证和流程演示。
- 发布档:必须同时具备真实 LLM、真实 TTS、FFmpeg/ffprobe、中文字体。缺一项都不能 release。

mock 永远不能用于正式 release。doctor 未 ready 时,真实终验必须停下,不得伪造 PASS。

## 第一步:自动检测

```bash
uv run lj setup
uv run lj setup --json
uv run lj doctor --json
```

`lj setup` 会按优先级检测:

- LLM:先找 Claude Code 的 `claude`、Codex 的 `codex` 等官方订阅 CLI;再找 `ollama`、`llm`;最后才看 OpenAI-compatible key。
- TTS:先找本机 TTS,如 macOS `say`、Piper、espeak-ng;再看 TTS API key。
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

ChatGPT/Claude 订阅通常只提供 LLM,不代表 TTS 也可用。TTS 优先走本机:

```bash
say "灵剪语音检测"
uv run lj setup
```

macOS 的 `say` 不需要 key。其他系统可安装 Piper 或 espeak-ng。确实需要云 TTS 时再配置:

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
