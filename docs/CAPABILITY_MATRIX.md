# 能力矩阵

这张表回答一个问题:普通用户拿到灵剪后,哪些能力已经可用,哪些需要安装插件、提供 key 或提供素材。

| 能力 | 当前角色 | 是否 release 硬门 | 用户怎么检查 | 缺失时怎么做 |
| --- | --- | --- | --- | --- |
| Skill | 让 Codex/Claude 理解灵剪主线 | 是,否则 agent 不会按灵剪流程执行 | `scripts/install_skill_links.sh` 后确认 `~/.codex/skills/lingjian-video/SKILL.md` 存在 | 重新软链整个仓库目录,不是只复制 SKILL.md |
| CLI (`lj`) | 真正执行项目、审批、渲染、QA、导出 | 是 | `uv run lj --help` | `uv sync` |
| LLM | 写脚本 | release 需要真实非 mock | `uv run lj setup` 看 LLM 是否继承 `claude_cli`/`codex_cli` | 优先登录 Claude/Codex CLI;否则配置 `LINGJIAN_LLM_CLI` 或 OpenAI-compatible |
| TTS | 生成发布音轨 | release 需要真实音轨;发布级质量建议云 TTS 或用户录音 | `uv run lj setup` 看 `quality_tier` | 配火山/OpenAI TTS,或用 `--voice-audio-file` 提供录好的口播 |
| 用户录音 | 替代 TTS 的正式口播来源 | 可用于 release | `lj voice --audio-file <音频>` 后看 `voice_plan.json` 的 `provider_id=user_audio` | 准备 wav/mp3/m4a/aiff 文件 |
| FFmpeg/ffprobe | 渲染、合音轨、QA 验证 | 是 | `uv run lj doctor --json` | 安装支持 `drawtext/libfreetype` 和 AAC 的 FFmpeg |
| 字体 | 中文字幕烧录 | 是 | `uv run lj doctor --json` | macOS 用 PingFang;其他系统放 NotoSansSC |
| HyperFrames/Remotion/imagegen | 生成真实画面资产 | 不是硬门,但缺失会 fallback warning | `uv run lj setup` 看 visuals 是否为 host_hyperframes/host_remotion/host_imagegen | 在 Codex 桌面版安装/启用插件或 skill;安装后新开会话 |
| 用户画面素材 | 替代生成器的真实画面来源 | 不是硬门,但能避免 blank card | 放入 `project/assets/scenes/<scene_id>.mp4|png` 后跑 visuals/render | 按 visual_plan 的 `expected_asset_path` 放置 |
| MCP | 未来给外部工具调用主线 | 当前不是主路径 | `packages/mcp_server/README.md` | 本版本不宣称 MCP 可用,先用 CLI |
| Web | 静态控制台骨架 | 不是主路径 | `pnpm --dir apps/web build` | 当前不能替代 CLI 审批流 |

## Codex 桌面版的完整工作流

1. 安装灵剪 skill。
2. 新开 Codex 会话,说“用 lingjian-video 帮我做一条视频”。
3. Codex 先跑 `uv run lj setup`,把能力分成“已继承”和“缺失”。
4. LLM 缺失:引导用户登录 Claude/Codex CLI 或提供 LLM API。
5. TTS 缺失:引导用户配置 TTS API,或用 `--voice-audio-file` 提供录好的口播。
6. 画面缺失:引导用户安装/启用 HyperFrames、Remotion、imagegen 插件/skill;如果用户不装,允许放已有 mp4/png。
7. `lj run` 生成 script / voice / visuals 三个 artifact,每一步让用户审核。
8. 宿主画面插件按 `visual_plan.json` 的 `expected_asset_path` 写出每镜资产。
9. `lj render` 用 FFmpeg 组装画面、字幕和音轨。
10. `lj qa` 输出 hard failure / warning。
11. `lj export` 生成发布包。

## 插件与 skill 的边界

- 灵剪核心不 import、不 bundle Remotion/HyperFrames SDK。
- Codex 桌面版用户可以安装 Remotion/HyperFrames/imagegen 相关插件或 skill;它们负责生成资产。
- 灵剪只负责生成规格、消费落盘资产、组装、QA 和导出。
- 缺插件时必须说清楚“当前只能 fallback”,不能把纯色卡片说成真实画面。
- MCP 未实现;当前不要把 MCP 当成可用主路径。

可参考的公开入口:

- HyperFrames skill: `npx skills add heygen-com/hyperframes`
- Remotion skill: `npx skills add remotion-dev/skills`
- HyperFrames 官方文档: https://hyperframes.heygen.com/quickstart
- Remotion Agent Skills 官方文档: https://www.remotion.dev/docs/ai/skills
- 若使用 Codex 插件市场,按桌面版插件入口安装对应插件;安装后新开会话让 agent 重新加载能力。
