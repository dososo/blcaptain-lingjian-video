# Provider 配置

## 状态分层

- `mock`: 只用于预览、测试和离线 CI。
- `inherited-cli`: 已登录的官方 CLI 能力,如 `claude`、`codex`,只调用命令,不读取凭据文件。
- `cli`: 用户本机已有的真实 LLM/TTS 命令,可替代 API key。
- `openai_compatible`: 通过 base URL、model 和 key 接入的真实 provider。
- `volcengine_tts`: 火山豆包 TTS,中文发布级配音 provider。
- `user_audio`: 用户已经录好的口播音频,通过 `--audio-file` 或 `--voice-audio-file` 接入。
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

1. 火山豆包 TTS key。
2. OpenAI-compatible TTS key。
3. 自定义真实 TTS CLI。
4. 本机预览级 TTS:`say`、`piper`、`espeak-ng`。

ChatGPT/Claude 订阅通常只提供 LLM,不代表 TTS 可用。继承订阅只走官方 CLI,不读取 OAuth token、cookie 或私密凭据文件。只有 Kokoro/Piper/say/espeak-ng 等本机样片级 TTS 时,严格发布会给 `RELEASE_AUDIO_IS_PREVIEW_VOICE` hard failure;请改用用户录音或自然中文云 TTS。

如果用户已有录好的口播音频,不需要配置 TTS key:

```bash
uv run lj voice ./projects/demo --provider auto --voice user --audio-file narration.m4a --json
uv run lj run ./projects/demo --input-file input.txt --script-provider auto --voice-audio-file narration.m4a --json
```

该路径会写 `provider_id=user_audio`、`provider_is_mock=false`,导出 license manifest 只记录用户提供音频,不记录原始路径。

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

## 火山豆包 TTS provider

```bash
export VOLCENGINE_TTS_API_KEY=...
# 可选高级覆盖:
# export VOLCENGINE_TTS_RESOURCE_ID=seed-tts-2.0
# export VOLCENGINE_TTS_VOICE_TYPE=zh_female_vv_uranus_bigtts
uv run lj doctor --json
```

Provider ID 为 `volcengine_tts`,别名为 `volcengine` / `doubao`。

- 默认调用火山豆包新版 HTTP 单向流式 TTS 接口,端点为 `https://openspeech.bytedance.com/api/v3/tts/unidirectional`。
- 请求头使用 `X-Api-Key`、`X-Api-Resource-Id`、`X-Api-Request-Id`;默认 Resource ID 为 `seed-tts-2.0`。
- 请求体按新版接口组织 `user.uid` 与 `req_params.text/speaker/audio_params`。
- 不同音色通过 `req_params.speaker` 传入,不是旧版 `voice_type`。语音指令与标签用于控制表达风格,不能替代 `speaker`。
- 普通用户不需要手填音色 ID。先运行 `uv run lj voice-options ./projects/my-video --provider volcengine_tts --json`,生成最多 5 个实际合成通过的试听音频;用户选中后,再用对应 `--voice <speaker>` 生成正式配音。
- 如果当前账号只能合成默认音色,灵剪只展示默认音色并说明原因,不编造“热门前 5”。
- `VOLCENGINE_TTS_API_KEY` 只从环境读取,不会写入 artifact、日志、manifest 或 release 包。
- `license_manifest.md` 只记录 `Volcengine Doubao TTS API provider`,不记录 API Key、Resource ID 或音色值。
- 旧版 `VOLCENGINE_TTS_APP_ID` / `VOLCENGINE_TTS_ACCESS_TOKEN` / `VOLCENGINE_TTS_CLUSTER` 仍保留兼容,但不作为普通用户默认路径。

官方文档:

- 火山引擎「单向流式语音合成HTTP--豆包语音」: https://www.volcengine.com/docs/6561/2528925
- 火山引擎「API Key使用--豆包语音」: https://www.volcengine.com/docs/6561/1816214?lang=zh
- 火山引擎「语音指令与标签--豆包语音」: https://www.volcengine.com/docs/6561/1871062?lang=zh

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

继承 CLI 不做无限重试;外部 CLI 偶发失败会轻量重试一次,仍失败时返回 `PROVIDER_CLI_FAILED` 并提示用户单独运行官方 CLI 确认登录。失败时应让用户看见明确原因并补配置。
