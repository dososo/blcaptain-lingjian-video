# Skill 与 MCP

M1 以 CLI 和 Web 控制台为主。MCP 为后续里程碑,本轮只提供接口边界说明,不把外部 MCP 能力假装成已安装能力。

## 初始化检查

安装后用户先运行:

```bash
uv run lj doctor --json
```

doctor 会明确区分:

- 本机工具能力: FFmpeg、ffprobe、中文字体。
- 真实模型能力: CLI provider 或 API provider。
- mock 能力: 只用于预览。
- optional 能力: OCR extras、截图、未来 MCP 扩展。

## MCP 边界

缺少 MCP 不应阻断 M1 主路径。若后续某功能必须依赖 MCP,doctor 需要把它列为 required 并给出安装指引。
