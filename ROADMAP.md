# ROADMAP

## M2 待办

以下内容进入 M2,不在 M1 封版中实现。

- MCP server 最小实现:暴露主线工具,让宿主 agent 能通过 MCP 调用 init / ingest / script / voice / visuals / approve / render / qa / export。
- Web 控制台交互化:把当前静态骨架接入后端 API,支持项目状态、三审、渲染和导出结果查看。
- 真实 provider 扩展:补更多云 TTS、本机 TTS、LLM CLI 与 OpenAI-compatible 供应商适配。
- 平台知识包与模板:沉淀抖音、小红书、Bilibili、YouTube Shorts 的发布结构、字幕风格和导出模板。
- 发布体验:补远端安装分发、CI 发布流水线、依赖审计工作流和更多跨平台安装验证。

## 继续保持的 M1 约束

- mock 不能 release。
- doctor 未 ready 必须停下,不得伪造 PASS。
- key/token 不进仓库、日志、manifest、`results.json` 或 release 包。
- Web/MCP 未实现能力不得对外宣称可用。
