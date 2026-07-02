# Lessons

## 2026-07-01

- 真实 provider / CLI / MCP 能力不是可选注释,而是用户安装后初始化流程必须主动检查和引导补齐的能力。缺少必须能力时要明确阻塞下一步,给出安全配置方式;不能把 `BLOCKED_ENV` 当成沉默跳过。
- 模型接入要区分三类状态:宿主 Codex 能主持、用户提供的 CLI 模型可用、外部 API key/base_url/provider 已真实配置。mock、模板示例、`codex_builtin` 不能被当作真实外部模型就绪。
- 能通过 CLI provider 完成的,不强制用户提供 API key;只有业务流程必须调用真实远端 provider 时才引导用户提供 key。key 必须脱敏、不得写日志、不得进入 release 包。
