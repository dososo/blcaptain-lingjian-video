# Lessons

## 2026-07-01

- 真实 provider / CLI / MCP 能力不是可选注释,而是用户安装后初始化流程必须主动检查和引导补齐的能力。缺少必须能力时要明确阻塞下一步,给出安全配置方式;不能把 `BLOCKED_ENV` 当成沉默跳过。
- 模型接入要区分三类状态:宿主 Codex 能主持、用户提供的 CLI 模型可用、外部 API key/base_url/provider 已真实配置。mock、模板示例、`codex_builtin` 不能被当作真实外部模型就绪。
- 能通过 CLI provider 完成的,不强制用户提供 API key;只有业务流程必须调用真实远端 provider 时才引导用户提供 key。key 必须脱敏、不得写日志、不得进入 release 包。
- 用户要求“对标之前给的仓库实现”时,先找附件/参考包并做差距矩阵,再补代码;不能只按当前实现自证。每个补项要同时列出“不做边界”,尤其是 Remotion/HyperFrames 不自研不 bundle、不新增命令、不做爆款算法/平台知识包/克隆/ASR/默认下载视频。
- 能力检测必须尽量行为化:仅二进制存在或 `exit 0` 不等于能力可用。发布级画面 CLI 至少要能按 contract 写出临时资产;发布级 TTS 要在 doctor 中用稳定分档字段标明。
- “不内置 Remotion/HyperFrames”不能写成“用户自己解决画面”。正确产品路径是:Codex 桌面版先检测插件/skill,缺失时引导安装/启用 HyperFrames、Remotion、imagegen,安装后新开会话重跑 setup;仍缺失才允许用户素材或 fallback。
- 配音能力缺失不能只引导 TTS key。自媒体用户常有录好的口播,主线必须提供 `--audio-file` / `--voice-audio-file` 这种明确入口,并保持本地、不泄漏路径、不标 mock。
- 用户要求“体验全流程”时,不能只提交审计证据或说明文档。必须用用户视角跑出一个可打开的视频,把 setup/doctor 的能力状态、三审节点、资产生成或缺失路径、QA warning、ffprobe 和抽帧都展示给用户。
- 普通用户工作流不是“让用户逐条敲 CLI/看 JSON/手动 approve”,也不是“Agent 黑盒全自动跑完”。正确形态是 Codex skill 对话式编排:用户只表达目标和提供素材;Codex 代跑底层命令;只在脚本、配音、画面、发布级能力缺口这些创作/授权决策点用人话请用户确认。
- Codex app 的公开分发主路径是 Plugin/marketplace/Add to Codex;官方用户级 skill 目录是 `~/.agents/skills`。不要再把 `~/.codex/skills`、`doctor --json` 或 CLI 手敲流程写成普通用户主入口。
- 发布级短视频的最小能力集合不能把 `macOS say`、`fallback_solid`、mock 或 stub 放进去。它们只能是预览/开发/回落路径;发布级主线必须引导真实 TTS 或用户录音、真实画面插件或用户素材、底部字幕与严格 QA。
- HyperFrames/Remotion skill 安装成功只代表 Codex agent 会读编排说明,不代表 `lj setup` 可检测到自动生成器。发布级画面自动化必须额外有可调用 CLI/adapter 能按 JSON contract 写出资产;否则只能诚实标为宿主手工/自备资产路径。
- Codex plugin 的 marketplace source 指向 repo root 时,本地安装 cache 会复制当前工作树。发布前必须确保远端仓库和 release 包不含 `projects/`、`exports/`、凭据、旧 zip 等本地生成物;必要时把 plugin source 收敛到干净子目录。
