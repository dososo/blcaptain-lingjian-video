# 灵剪 Video Studio M1

## 30 秒上手:对话式安装提示词

把下面这段复制给 Codex 或 Claude Code。发布后请把 `<REPO_URL>` 替换为真实仓库地址。

```text
请帮我安装并启用「灵剪 lingjian-video」短视频生产 skill。请一步步来,每步都用真实命令验证是否成功(不要只看文件是否存在),需要我提供东西时再停下问我:

1. 把仓库 clone 到一个稳定目录:git clone <REPO_URL> ~/Developer/lingjian-video
2. 安装依赖:cd ~/Developer/lingjian-video && uv sync
3. 注册 skill:用 ln -sfn 把仓库里 SKILL.md 所在目录整个软链进你的 skills 目录(Claude Code 用 ~/.claude/skills/,Codex 用 ~/.codex/skills/);必须软链整个目录,保证 SKILL.md 和它的同级文件在一起。
4. 能力自检:运行 uv run lj setup 和 uv run lj doctor --json,然后把结果分两栏告诉我 ——"已继承、可直接用的能力"(比如 claude/codex 作 LLM、macOS say 作 TTS)和"还缺、需要我处理的能力"(比如 ffmpeg 是否支持 drawtext、是否缺真实 TTS)。
5. 我是订阅用户:LLM 尽量继承我已登录的 Codex/Claude,不要默认向我要 API key;只有当某项能力确实缺失、且只能靠我提供 key 或安装工具时,才用一句话告诉我要装什么/配什么(优先零 key 的本机或继承方案)。
6. 装完做一次最小验证:用预览档(--provider mock)跑一条 demo 到 render 预览,确认整条流程可复跑,再把结论告诉我。

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
npx skills add <REPO_URL> --skill lingjian-video
```

灵剪 M1 是一个可审核、可复跑、可归档的短视频生产主干。当前实现覆盖 CLI、核心状态机、mock 预览链路、审批门禁、QA、导出包、Next.js Web 控制台与离线验证脚本。

## 当前边界

- mock provider 只允许预览和离线测试,不能用于正式 release。
- 正式 release 必须配置真实 LLM 与真实 TTS provider。`doctor` 未 ready 时,验收项 `V-REAL-01` 标记为 `BLOCKED_ENV`。
- `render --release` 必须具备 FFmpeg/ffprobe,且 FFmpeg 支持 `drawtext/libfreetype`;缺失时硬失败,不会写离线 stub。
- 能提供本机 CLI provider 时,不强制提供 API key。必须使用 key 时,doctor 只输出脱敏状态,不会把 key 写入日志、artifact 或导出包。
- 新用户先跑 `lj setup`,系统会优先继承已登录的官方 CLI 或本机能力,缺失时才引导提供 key。
- M1 渲染只包含 `ffmpeg_card` 最小卡片引擎;HyperFrames、Remotion、复杂 timeline、插件市场均不在 M1 范围内。

## 快速开始

推荐先用 `lj run` 走引导主线。默认会在 script / voice / visuals 三审点暂停;只有显式传 `--yes` 才会自动写入审批记录。

```bash
uv sync
uv run lj setup
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --json
```

逐条命令备选:

```bash
uv sync
uv run lj setup
uv run lj doctor --json
uv run lj init ./projects/demo --name "演示项目" --json
uv run lj ingest text ./projects/demo --file examples/product_intro_zh.txt --json
uv run lj extract ./projects/demo --json
uv run lj script ./projects/demo --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj approve script ./projects/demo --approved-by tester --json
uv run lj voice ./projects/demo --provider mock --voice test-voice --json
uv run lj approve voice ./projects/demo --approved-by tester --json
uv run lj visuals ./projects/demo --engine ffmpeg_card --template product --json
uv run lj approve visuals ./projects/demo --approved-by tester --json
uv run lj render ./projects/demo --platform douyin --language zh-CN --ratio 9:16 --json
uv run lj qa ./projects/demo --json
uv run lj export ./projects/demo --platform douyin --language zh-CN --ratio 9:16 --json
```

完整 onboarding 向导见 [`docs/ONBOARDING.md`](docs/ONBOARDING.md)。

Web 控制台:

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

若已登录 Claude Code `claude` 或 Codex `codex` CLI,灵剪会优先继承 LLM 能力,无需 key。TTS 通常不包含在订阅内,会优先检测 macOS `say`、Piper、espeak-ng 等本机 TTS。

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
