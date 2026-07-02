# Skill 与 MCP

M1 以 CLI 和 Web 控制台为主。MCP 为后续里程碑,本轮只提供接口边界说明,不把外部 MCP 能力假装成已安装能力。

Codex 桌面版用户可以安装额外插件或 skill 来补足画面生成能力,例如 HyperFrames、Remotion、imagegen。它们不是灵剪核心依赖,也不是 MCP server;它们负责按 `visual_plan.json` 写出每镜 mp4/png,灵剪负责消费资产、组装、QA 与导出。

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

当前主路径:

1. `uv run lj setup` 检测 Skill/CLI/provider/画面插件能力。
2. 画面插件缺失时,引导用户安装/启用 Codex 桌面版 HyperFrames、Remotion、imagegen 插件或 skill。
3. 插件仍缺失时,允许用户自己放置 `project/assets/scenes/<scene_id>.mp4|png`。
4. MCP 未实现不阻断以上流程。
