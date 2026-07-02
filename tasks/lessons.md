# Lessons

## 2026-07-01

- 真实 provider / CLI / MCP 能力不是可选注释,而是用户安装后初始化流程必须主动检查和引导补齐的能力。缺少必须能力时要明确阻塞下一步,给出安全配置方式;不能把 `BLOCKED_ENV` 当成沉默跳过。
- 模型接入要区分三类状态:宿主 Codex 能主持、用户提供的 CLI 模型可用、外部 API key/base_url/provider 已真实配置。mock、模板示例、`codex_builtin` 不能被当作真实外部模型就绪。
- 能通过 CLI provider 完成的,不强制用户提供 API key;只有业务流程必须调用真实远端 provider 时才引导用户提供 key。key 必须脱敏、不得写日志、不得进入 release 包。
- 用户要求“对标之前给的仓库实现”时,先找附件/参考包并做差距矩阵,再补代码;不能只按当前实现自证。每个补项要同时列出“不做边界”,尤其是 Remotion/HyperFrames 不自研不 bundle、不新增命令、不做爆款算法/平台知识包/克隆/ASR/默认下载视频。
- 能力检测必须尽量行为化:仅二进制存在或 `exit 0` 不等于能力可用。发布级画面 CLI 至少要能按 contract 写出临时资产;发布级 TTS 要在 doctor 中用稳定分档字段标明。
