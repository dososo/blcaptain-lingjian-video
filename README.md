# 灵剪 Video Studio M1

## 30 秒上手:对话式安装提示词

把下面这段复制给 Codex 或 Claude Code。如你使用自建或 fork 仓库,请把命令里的仓库地址替换为你自己的仓库。

```text
请帮我安装并启用「灵剪 lingjian-video」短视频生产 skill。请一步步来,每步都用真实命令验证是否成功(不要只看文件是否存在),需要我提供东西时再停下问我:

1. 把仓库 clone 到一个稳定目录:git clone https://github.com/dososo/blcaptain-lingjian-video.git ~/Developer/lingjian-video
2. 安装依赖:cd ~/Developer/lingjian-video && uv sync
3. 注册 skill:用 ln -sfn 把仓库里 SKILL.md 所在目录整个软链进你的 skills 目录(Claude Code 用 ~/.claude/skills/,Codex 用 ~/.codex/skills/);必须软链整个目录,保证 SKILL.md 和它的同级文件在一起。
4. 能力自检:运行 uv run lj setup 和 uv run lj doctor --json,然后把结果分两栏告诉我 ——"已继承、可直接用的能力"(比如 claude/codex 作 LLM、macOS say 作 TTS)和"还缺、需要我处理的能力"(比如 ffmpeg 是否支持 drawtext、是否缺真实 TTS)。
5. 我是订阅用户:LLM 尽量继承我已登录的 Codex/Claude,不要默认向我要 API key;只有当某项能力确实缺失、且只能靠我提供 key 或安装工具时,才用一句话告诉我要装什么/配什么(优先零 key 的本机或继承方案)。
6. 装完做一次最小验证:优先用 --script-provider auto --voice-provider auto 跑一条 demo 到 render 预览,确认第一条命令就能产出可打开视频;如果只是验证流程,可以显式使用 mock,但要说明 mock 产物不是发布级。

请注意:所有 key 只从我的当前环境读取,绝不要写进仓库、日志或任何导出文件;也不要在回复里回显我的完整 key。
```

本仓库本地安装可直接运行:

```bash
uv sync
scripts/install_skill_links.sh
uv run lj setup
uv run lj doctor --json
```

若后续接入 skills.sh 生态,发布后可提供:

```bash
npx skills add https://github.com/dososo/blcaptain-lingjian-video.git --skill lingjian-video
```

灵剪 M1/M2 是一个可审核、可复跑、可归档的短视频生产主干。当前实现覆盖 CLI、核心状态机、mock 预览链路、宿主画面生成委托与产物消费、审批门禁、QA、导出包、Next.js Web 控制台与离线验证脚本。Web 控制台当前为静态骨架,不能替代 CLI 审批流,详见 [`docs/CAPABILITY_MATRIX.md`](docs/CAPABILITY_MATRIX.md)。

普通创作者先看:

- [`docs/CREATOR_QUICKSTART.md`](docs/CREATOR_QUICKSTART.md):按“有文案 / 有录音 / 有画面素材 / 要发布”选择路径。
- [`docs/CAPABILITY_MATRIX.md`](docs/CAPABILITY_MATRIX.md):Skill、CLI、MCP、插件、TTS、FFmpeg 分别是什么状态。

## 当前边界

- mock provider 只允许预览和离线测试,不能用于正式 release。
- 正式 release 必须配置真实 LLM 与真实 TTS provider。`doctor` 未 ready 时,验收项 `V-REAL-01` 标记为 `BLOCKED_ENV`。
- `render --release` 必须具备 FFmpeg/ffprobe,且 FFmpeg 支持 `drawtext/libfreetype`;缺失时硬失败,不会写离线 stub。
- 能提供本机 CLI provider 时,不强制提供 API key。必须使用 key 时,doctor 只输出脱敏状态,不会把 key 写入日志、artifact 或导出包。
- 新用户先跑 `lj setup`,系统会优先继承已登录的官方 CLI 或本机能力,缺失时才引导提供 key。
- M2 不 bundle HyperFrames/Remotion,`visuals` 会产出每镜可执行生成规格;当前已验证的发布级视觉路径是把每镜 mp4/png 放入 `project/assets/scenes/`,再由 lj 用 FFmpeg 统一组装。
- Codex 桌面版用户可安装/启用 HyperFrames、Remotion、imagegen 插件或 skill,由宿主按 `visual_plan.json` 生成每镜资产;这条自动生成路径是可选进阶,生成器不可用或失败时可消费用户自带素材,否则回落 `fallback_solid` 卡片并在 QA 中 warning。
- 配音缺失时不要硬闯:优先配置发布级 TTS API;如果用户已有录好的口播,可用 `--voice-audio-file` 或 `lj voice --audio-file` 接入。

## 隐私与安全

- 数据默认留在本机:项目文件、artifact、渲染产物和导出包都写入你指定的本地目录。
- key 默认不落盘:真实 provider 的 key 只从当前 shell 环境读取,不会写入仓库、日志、manifest、`results.json` 或 release 包。
- 能继承就不问 key:已登录的 Claude Code/Codex CLI 只通过官方命令行调用,不会读取 OAuth token、cookie、Keychain 内部文件或私密凭据文件。
- 导出包不夹带本地凭据:`projects/`、`exports/`、`.env*`、`.venv/`、`node_modules/` 已在 `.gitignore` 中排除。
- 发布前可选做依赖审计:Python 侧可接 `pip-audit` 或 `uv export` 后审计;Node 侧可用 `pnpm audit`、Socket 或 Snyk。M1 不把这些云审计服务作为必需依赖。

## 跨平台能力说明

FFmpeg 是 release 硬门,且必须支持 `drawtext/libfreetype` 与 AAC 音频编码。

macOS:

```bash
brew install ffmpeg
ffmpeg -hide_banner -h filter=drawtext
```

如果 Homebrew 默认包缺 `drawtext`,可切到 `ffmpeg-full`:

```bash
brew install ffmpeg-full
brew unlink ffmpeg && brew link ffmpeg-full
ffmpeg -filters | grep drawtext
```

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg espeak-ng
ffmpeg -filters | grep drawtext
```

Windows:

```powershell
winget install Gyan.FFmpeg
ffmpeg -filters | findstr drawtext
```

TTS 分两档:火山豆包、OpenAI-compatible TTS 或自定义真实 TTS CLI 属发布级;macOS `say`、Piper、espeak-ng 属预览级零 key 语音。只有预览级 TTS 时 release 不阻断,但 QA 会给 `RELEASE_AUDIO_IS_PREVIEW_VOICE` warning。ChatGPT/Claude 订阅通常只覆盖 LLM,不等于包含 TTS。

## 快速开始

推荐先用 `lj run` 走引导主线。默认会在 script / voice / visuals 三审点暂停;只有显式传 `--yes` 才会自动写入审批记录。

```bash
uv sync
uv run lj setup
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --script-provider auto --voice-provider auto --json
```

如果只想验证流程,可以显式使用 mock;mock 产物只证明门禁和流程,不是发布级视频:

```bash
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --script-provider mock --voice-provider mock --json
```

已有录好的口播音频时:

```bash
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --script-provider auto --voice-audio-file narration.m4a --json
```

逐条命令备选:

```bash
uv sync
uv run lj setup
uv run lj doctor --json
uv run lj init ./projects/demo --name "演示项目" --json
uv run lj ingest text ./projects/demo --file examples/product_intro_zh.txt --json
uv run lj extract ./projects/demo --json
# 真内容推荐 auto,继承当前 Claude/Codex CLI:
uv run lj script ./projects/demo --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider auto --json
# 仅验证流程时才显式使用 mock:
uv run lj script ./projects/demo --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj approve script ./projects/demo --approved-by tester --json
uv run lj voice ./projects/demo --provider mock --voice test-voice --json
# 或者使用已经录好的口播音频:
uv run lj voice ./projects/demo --provider auto --voice user --audio-file narration.m4a --json
uv run lj approve voice ./projects/demo --approved-by tester --json
uv run lj visuals ./projects/demo --engine ffmpeg_card --template product --json
# visuals 会生成每镜 storyboard:包含 generator、visual_prompt、motion_spec、brief、expected_asset_path 与 duration_sec。
# render 前会按 generator 委托宿主 HyperFrames/Remotion/imagegen CLI 写入 assets/scenes/<scene_id>.mp4|png;缺宿主能力时先引导安装/启用插件或 skill,允许用户放自有素材,最后才 fallback_solid。
uv run lj approve visuals ./projects/demo --approved-by tester --json
uv run lj render ./projects/demo --platform douyin --language zh-CN --ratio 9:16 --json
uv run lj qa ./projects/demo --json
uv run lj export ./projects/demo --platform douyin --language zh-CN --ratio 9:16 --json
```

完整 onboarding 向导见 [`docs/ONBOARDING.md`](docs/ONBOARDING.md)。

Web 控制台:

当前 Web 控制台为静态骨架,不能替代 CLI 审批流;完整主线仍以 `uv run lj ...` 为准。能力状态见 [`docs/CAPABILITY_MATRIX.md`](docs/CAPABILITY_MATRIX.md)。

```bash
pnpm install
pnpm --dir apps/web build
pnpm --dir apps/web dev
```

## 真实 provider 配置

能力继承优先:

```bash
uv run lj setup
```

若已登录 Claude Code `claude` 或 Codex `codex` CLI,灵剪会优先继承 LLM 能力,无需 key。TTS 通常不包含在订阅内;默认自动选择当前最高档 TTS,有发布级云 TTS 时优先云 TTS,否则回落 macOS `say`、Piper、espeak-ng 等预览级本机 TTS。

自定义 CLI provider:

```bash
export LINGJIAN_LLM_CLI=your-llm-command
export LINGJIAN_TTS_CLI=your-tts-command
```

CLI provider 从 stdin 读取 JSON,向 stdout 输出 JSON。LLM CLI 返回 `scenes`;TTS CLI 返回 `audio_base64` 与 `duration_sec`。CLI 命令、key 和环境变量值不会写入 release 包。

OpenAI-compatible API:

```bash
export OPENAI_BASE_URL=https://api.example.com/v1
export OPENAI_API_KEY=...
export OPENAI_MODEL=...
export OPENAI_TTS_BASE_URL=https://api.example.com/v1
export OPENAI_TTS_API_KEY=...
export OPENAI_TTS_MODEL=...
```

LLM provider ID 为 `openai_compatible`;TTS provider ID 为 `openai_compatible_tts`。API key、base URL、model 值只从环境读取,不会写入 artifact、日志或 release 包。

火山豆包 TTS:

```bash
export VOLCENGINE_TTS_APP_ID=...
export VOLCENGINE_TTS_ACCESS_TOKEN=...
export VOLCENGINE_TTS_CLUSTER=...
export VOLCENGINE_TTS_VOICE_TYPE=...   # 可选
```

TTS provider ID 为 `volcengine_tts`,也可用别名 `volcengine` 或 `doubao`。Access Token 只从环境读取,不会写入 artifact、日志或 release 包。

已有录音可不用 TTS:

```bash
uv run lj voice ./projects/demo --provider auto --voice user --audio-file narration.m4a --json
```

该路径会写 `provider_id=user_audio`,不会标 mock,也不会把原始文件路径写入导出包。

配置后先跑 `uv run lj doctor --json`。required 缺失时 exit code 非 0,不得继续 release。

## 验证

```bash
uv run pytest
uv run ruff check .
uv run python scripts/ci/check_false_success.py
pnpm --dir apps/web lint
pnpm --dir apps/web build
```

完整证据见 `verification/` 与 `docs/dev/AUDIT_READY.md`。
