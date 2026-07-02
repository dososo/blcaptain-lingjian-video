# MCP Server 说明

M1 不交付完整 MCP server,这里只保留边界说明。

未来 MCP server 需要提供:

- 项目创建、状态读取、artifact 列表。
- 触发生成、审批、渲染、QA 与导出。
- provider 配置状态读取,但不得回传明文 key。
- 与 CLI 相同的错误码和门禁语义。

当前版本请使用 `uv run lj ...` 与 Web 控制台。
