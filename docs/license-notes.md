# License 说明

主仓采用 Apache-2.0。

M1 不引入 AGPL/GPL 项目代码、prompt、template 或 UI 复制。以下项目仅可用于研究和对比,不得复制进主仓:

- VideoLingo
- LosslessCut
- motion-director

Remotion 属于未来 opt-in 能力,不默认捆绑。营利团队或自动化生成工具使用 Remotion 前,需要自行确认其商业授权。

字体、模型、素材与平台内容授权由用户自行确认。导出包会生成 `license_manifest.md`,但它只是记录,不是法律意见。

M2 起支持用户自带 CLI provider:

- `llm_cli`: `User supplied CLI provider`
- `tts_cli`: `User supplied CLI provider`

M2 起支持 OpenAI-compatible API provider:

- `openai_compatible`: `OpenAI-compatible API provider`
- `openai_compatible_tts`: `OpenAI-compatible API provider`

CLI/API provider 的模型、声音、输出内容和商业授权由用户自行确认。灵剪只记录 provider 类型,不把 CLI 命令、base URL、model、key、token 或环境变量值写入 artifact、日志或 release 包。
