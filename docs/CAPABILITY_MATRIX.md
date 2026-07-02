# 能力矩阵

这张表回答一个问题:普通用户拿到灵剪后,哪些能力已经可用,哪些需要安装插件、提供 key 或提供素材。

## 三层能力口径

- 🟢 零 key 免费:Claude/Codex CLI 继承 LLM、HyperFrames 本地动态图形、Kokoro 中文 TTS、用户自备素材/录音、FFmpeg 渲染。Kokoro 为 Apache-2.0;HyperFrames 为开源本地渲染能力。
- 🟡 付费或需连接账号:火山豆包/OpenAI-compatible TTS、Fal/Picsart/HeyGen 数字人、Shutterstock/Canva/Cloudinary 等。能安装插件不代表服务免费可用。
- 🔴 发布需自建或人工:抖音/小红书/YouTube/TikTok 自动发布不在本仓库内;灵剪只导出发布包。

| 能力 | 当前角色 | 是否 release 硬门 | 用户怎么检查 | 缺失时怎么做 |
| --- | --- | --- | --- | --- |
| Codex Plugin / Skill | 让 Codex app 理解并触发灵剪主线 | 是,否则 agent 不会按灵剪流程执行 | Codex app Plugins 中安装,或 `scripts/install_skill_links.sh` 后确认 `~/.agents/skills/lingjian-video/SKILL.md` 存在 | 优先安装 plugin;开发备用才软链整个仓库目录 |
| CLI (`lj`) | 真正执行项目、审批、渲染、QA、导出 | 是 | `uv run lj --help` | `uv sync` |
| LLM | 写脚本 | release 需要真实非 mock | `uv run lj setup` 看 LLM 是否继承 `claude_cli`/`codex_cli` | 优先登录 Claude/Codex CLI;否则配置 `LINGJIAN_LLM_CLI` 或 OpenAI-compatible |
| TTS | 生成音轨 | 发布级必须是用户录音、云 TTS、Kokoro/Piper 零 key 本地 TTS; say/espeak 只预览 | `uv run lj setup` 看 `quality_tier` | 优先安装 Kokoro;商用质量配火山/OpenAI TTS,或用 `--voice-audio-file` 提供录好的口播 |
| 用户录音 | 替代 TTS 的正式口播来源 | 可用于 release | `lj voice --audio-file <音频>` 后看 `voice_plan.json` 的 `provider_id=user_audio` | 准备 wav/mp3/m4a/aiff 文件 |
| FFmpeg/ffprobe | 渲染、合音轨、QA 验证 | 是 | `uv run lj setup` | 安装支持 `drawtext/libfreetype` 和 AAC 的 FFmpeg |
| 字体 | 中文字幕烧录 | 是 | `uv run lj setup` | macOS 用 PingFang;其他系统放 NotoSansSC |
| 用户画面素材 | 稳定发布级视觉回落路径 | 发布级质量门,能避免 blank card | 放入 `project/assets/scenes/<scene_id>.mp4|png` 后跑 visuals/render | 按 visual_plan 的 `expected_asset_path` 放置 |
| HyperFrames/Remotion/imagegen | 由 Codex 宿主或本机 CLI 生成真实画面资产 | 发布级质量门;缺失会 fallback,strict 阻断 | `uv run lj setup` 看 visuals 是否为 host_hyperframes/host_remotion/host_imagegen | 优先 HyperFrames 零 key;在 Codex app 插件市场安装/启用插件或 skill。Node.js 22+ 为 HyperFrames 前置,Remotion 商用需核对 license |
| MCP | 未来给外部工具调用主线 | 当前不是主路径 | `packages/mcp_server/README.md` | 本版本不宣称 MCP 可用,先用 CLI |
| Web | 静态控制台骨架 | 不是主路径 | `pnpm --dir apps/web build` | 当前不能替代 CLI 审批流 |

## Codex app 的完整工作流

1. 用户在 Codex app 里说“帮我安装并使用灵剪做一条发布级短视频”。
2. Codex 优先通过 Plugins / Add to Codex 或 repo marketplace 安装灵剪 plugin;开发备用才用 `scripts/install_skill_links.sh`。
3. Codex 先跑 `uv run lj setup`,用人话把能力分成“已继承 / 已具备 / 必须补齐 / 可选增强”。
4. LLM 缺失:引导用户登录 Claude/Codex CLI 或提供 LLM API。
5. TTS 缺失:优先引导安装 Kokoro 中文本地 TTS;商用质量引导配置发布级 TTS API,或用 `--voice-audio-file` 提供录好的口播;不要把 macOS say/espeak 说成发布级。
6. 画面缺失:优先引导安装/启用 HyperFrames 零 key 画面能力;也可用 Remotion、imagegen 插件/skill,或提供已有 mp4/png;不要把 fallback_solid 说成真实画面。
7. `lj run` 生成 script / voice / visuals 三个 artifact,每一步用对话让用户审核。
8. HyperFrames/宿主画面插件按 `visual_plan.json` 的 `expected_asset_path` 写出每镜资产。
9. `lj render` 用 FFmpeg 组装画面、底部字幕和音轨。
10. 发布级验收用 `lj qa --release --strict`,输出 hard failure / warning。
11. `lj export --release --strict` 生成发布包。

## 插件与 skill 的边界

- 灵剪核心不 import、不 bundle Remotion/HyperFrames SDK。
- Codex app 用户可以安装 HyperFrames/Remotion/imagegen 相关插件或 skill;它们负责生成资产。
- 灵剪只负责生成规格、通过薄子进程委托或消费落盘资产、组装、QA 和导出。
- 缺插件时必须说清楚“当前只能 fallback”,不能把纯色卡片说成真实画面。
- MCP 未实现;当前不要把 MCP 当成可用主路径。

可参考的公开入口:

- Codex 官方 plugin:Codex app 的 Plugins / Add to Codex,或 `codex plugin marketplace add dososo/blcaptain-lingjian-video`
- HyperFrames skill 备用:`npx skills add heygen-com/hyperframes`(Node.js 22+、FFmpeg,Apache-2.0,零 key)
- Remotion skill 备用:`npx skills add remotion-dev/skills`(需核对商用 license;>3 人营利组织需付费)
- HyperFrames 官方文档: https://hyperframes.heygen.com/quickstart
- Remotion Agent Skills 官方文档: https://www.remotion.dev/docs/ai/skills
- 若使用 Codex 插件市场,按 Codex app 插件入口安装对应插件;安装后新开会话让 agent 重新加载能力。
