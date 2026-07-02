# Provider 配置

## 状态分层

- `mock`: 只用于预览、测试和离线 CI。
- `inherited-cli`: 已登录的官方 CLI 能力,如 `claude`、`codex`,只调用命令,不读取凭据文件。
- `cli`: 用户本机已有的真实 LLM/TTS 命令,可替代 API key。
- `openai_compatible`: 通过 base URL、model 和 key 接入的真实 provider。
- `codex_host`: 仅表示宿主能协助编排,不能视为用户的真实发布 provider。

## 能力继承优先

```bash
uv run lj setup
uv run lj doctor --json
```

LLM 优先级:

1. 已登录的官方订阅 CLI:`claude`、`codex`。
2. 本机模型 CLI:`ollama`、`llm`。
3. OpenAI-compatible API key。

TTS 优先级:

1. 本机 TTS:`say`、`piper`、`espeak-ng`。
2. OpenAI-compatible TTS key。

ChatGPT/Claude 订阅通常只提供 LLM,不代表 TTS 可用。继承订阅只走官方 CLI,不读取 OAuth token、cookie 或私密凭据文件。

## 自定义 CLI provider

```bash
export LINGJIAN_LLM_CLI=your-llm-command
export LINGJIAN_TTS_CLI=your-tts-command
uv run lj doctor --json
```

doctor 会检查命令是否可执行。CLI 可用时,不会强制要求 API key。

CLI provider 合同:

- LLM CLI 从 stdin 读取 JSON,stdout 输出 JSON object,至少可返回 `{"scenes":[{"id":"s1","narration_text":"..."}]}`。
- TTS CLI 从 stdin 读取 JSON,stdout 输出 JSON object,返回 `audio_base64` 与 `duration_sec`。
- CLI provider 输出会写入 artifact,但命令内容、key、环境变量值不会写入 release 包。
- `llm_cli` 与 `tts_cli` 的 license 记录为 `User supplied CLI provider`,具体授权由用户负责确认。

## OpenAI-compatible API provider

```bash
export OPENAI_BASE_URL=https://api.example.com/v1
export OPENAI_API_KEY=...
export OPENAI_MODEL=...
export OPENAI_TTS_BASE_URL=https://api.example.com/v1
export OPENAI_TTS_API_KEY=...
export OPENAI_TTS_MODEL=...
```

LLM provider ID 为 `openai_compatible`,TTS provider ID 为 `openai_compatible_tts`。

- LLM 调用 `<OPENAI_BASE_URL>/chat/completions`,要求模型返回 JSON object,顶层包含 `scenes`。
- TTS 调用 `<OPENAI_TTS_BASE_URL>/audio/speech`,返回音频字节。
- 缺少 base URL、model 或 key 时,该 provider 不算 release-ready。
- key、base URL、model 值不写入 artifact、日志或 release 包;doctor 只输出脱敏状态。
- `license_manifest.md` 只记录 `OpenAI-compatible API provider`,不记录账号或密钥信息。

## 错误分类

真实 provider 错误会归入稳定错误码:

- `PROVIDER_AUTH_FAILED`
- `LLM_RATE_LIMITED`
- `TTS_RATE_LIMITED`
- `PROVIDER_QUOTA_EXCEEDED`
- `PROVIDER_API_FAILED`
- `LLM_INVALID_JSON`
- `LLM_OUTPUT_TOO_THIN`
- `PROVIDER_TIMEOUT`
- `PROVIDER_CLI_FAILED`
- `TTS_OUTPUT_MISSING`
- `TTS_OUTPUT_INVALID`

M1 不做无限重试。失败时应让用户看见明确原因并补配置。
