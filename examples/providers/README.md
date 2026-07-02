# Provider 示例骨架

这些文件只演示灵剪 CLI provider 的 I/O 契约,不是模型、不是语音引擎,禁止用于 release 冒充真实 provider。

真实 CLI provider 合同:

- LLM:从 stdin 读 JSON,向 stdout 输出 JSON object,顶层包含非空 `scenes`。
- TTS:从 stdin 读 JSON,向 stdout 输出 JSON object,包含非空 `audio_base64` 与 `duration_sec > 0`。

真实发布请使用已登录的官方 CLI、本机 TTS 引擎或真实 OpenAI-compatible provider。
