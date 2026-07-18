# 能力矩阵

这张表回答一个问题:普通用户拿到灵剪后,哪些能力已经可用,哪些需要安装插件、提供 key 或提供素材。

## 三层能力口径

- 🟢 零 key 免费:Claude/Codex CLI 继承 LLM、HyperFrames 本地样片动效、Kokoro 中文样片 TTS、用户自备素材/录音、FFmpeg 渲染。Kokoro 为 Apache-2.0;HyperFrames 内置模板只能证明流程,不能自动等同发布级视频。
- 🟡 付费或需连接账号:火山豆包/OpenAI-compatible TTS、Fal/Picsart/HeyGen 数字人、Shutterstock/Canva/Cloudinary 等。能安装插件不代表服务免费可用。
- 🔴 发布需自建或人工:抖音/小红书/YouTube/TikTok 自动发布不在本仓库内;灵剪只导出发布包。

| 能力 | 当前角色 | 是否 release 硬门 | 用户怎么检查 | 缺失时怎么做 |
| --- | --- | --- | --- | --- |
| Codex Plugin / Skill | 让 Codex app 理解并触发灵剪主线 | 是,否则 agent 不会按灵剪流程执行 | Codex app Plugins 中安装,或 `scripts/install_skill_links.sh` 后确认 `~/.agents/skills/lingjian-video/SKILL.md` 存在 | 优先安装 plugin;开发备用才软链整个仓库目录 |
| CLI (`lj`) | 真正执行项目、审批、渲染、QA、导出 | 是 | `uv run lj --help` | `uv sync` |
| LLM | 写脚本 | release 需要真实非 mock | `uv run lj setup` 看 LLM 是否继承 `claude_cli`/`codex_cli` | 优先登录 Claude/Codex CLI;否则配置 `LINGJIAN_LLM_CLI` 或 OpenAI-compatible |
| TTS | 生成音轨 | 发布级必须是用户录音或自然中文云 TTS; Kokoro/Piper/say/espeak 只做样片/预览 | `uv run lj setup` 看 `quality_tier` | 优先用 `--voice-audio-file` 提供录好的口播;没有录音时默认引导火山豆包新版 TTS:先开通服务 https://console.volcengine.com/speech/new/setting/activate?projectName=default ,再到 API Key 管理 https://console.volcengine.com/speech/new/setting/apikeys?projectName=default 创建 API Key |
| 用户录音 | 替代 TTS 的正式口播来源 | 可用于 release | `lj voice --audio-file <音频>` 后看 `voice_plan.json` 的 `provider_id=user_audio` | 准备 wav/mp3/m4a/aiff 文件 |
| FFmpeg/ffprobe | 渲染、合音轨、QA 验证 | 是 | `uv run lj setup` | 安装支持 `drawtext/libfreetype` 和 AAC 的 FFmpeg |
| 字体 | 中文字幕烧录 | 是 | `uv run lj setup` | macOS 用 PingFang;其他系统放 NotoSansSC |
| 用户画面素材 | 稳定发布级视觉回落路径 | 发布级必须是每镜真实视频素材;图片只可做样片/参考 | 放入 `project/assets/scenes/<scene_id>.mp4` 后跑 visuals/render | 按 visual_plan 的 `expected_asset_path` 放置 mp4/mov/m4v |
| HyperFrames/Remotion/视频生成插件 | 由 Codex 宿主或本机 CLI 生成动态画面资产 | 发布级必须是内容相关的动态视频资产;静态图、内置 HyperFrames 模板、单图循环、fallback 都不能冒充发布级 | `uv run lj setup` 看 visuals 候选;只有 `safe_for_release=true` 或用户已提供每镜视频素材才算发布级 | 优先提供每镜真实视频素材;或在 Codex app 插件市场安装/启用生成动态画面的插件。imagegen 静图只能做参考,Node.js 22+ 为 HyperFrames 前置,Remotion 商用需核对 license |
| MCP | 未来给外部工具调用主线 | 当前不是主路径 | `packages/mcp_server/README.md` | 本版本不宣称 MCP 可用,先用 CLI |
| Web | 静态控制台骨架 | 不是主路径 | `pnpm --dir apps/web build` | 当前不能替代 CLI 审批流 |

## Codex app 的完整工作流

1. 用户在 Codex app 里说“帮我安装并使用灵剪做一条发布级短视频”。
2. Codex 优先通过 Plugins / Add to Codex 或 repo marketplace 安装灵剪 plugin;开发备用才用 `scripts/install_skill_links.sh`。
3. Codex 先跑 `uv run lj setup`,用人话把能力分成“已继承 / 已具备 / 必须补齐 / 可选增强”。
4. LLM 缺失:引导用户登录 Claude/Codex CLI 或提供 LLM API。
5. TTS 缺失:优先引导用户用 `--voice-audio-file` 提供录好的口播;没有录音时配置发布级 TTS API。Kokoro/Piper/say/espeak 只能样片/预览。
6. 画面缺失:优先引导提供每镜真实视频素材;也可用 HyperFrames、Remotion 或其他视频生成插件/skill 生成动态内容画面。imagegen 静图只能做参考图。静态图片、内置模板、单图循环、fallback_solid 不能说成真实发布级视频。
7. `lj run` 生成 script / voice / visuals 三个 artifact,每一步用对话让用户审核。
8. 脚本批准后,先做音色试听/选择;如果当前账号只验证到 1 个可用音色,就明确展示这个音色名称、`voice_id` 和试听文件,不要编造其它可选项。
9. 正式 TTS 生成前必须展示“配音导演确认单”:整体口播定位、目标听感、语速策略、情绪曲线、停顿重音、每镜表达、禁忌和试听策略都要写清楚。用户确认后才生成全片配音。
10. voice 审核时让用户试听正式音轨,并明确给出“批准配音 / 压到目标时长 / 调整语气情绪”三个反馈入口;如果用户说不自然、情绪不对或声音变化,先调整配音导演稿/音色参数,不要进入画面。
11. visuals 审核必须先在对话里完整展示“导演分镜确认单”:每镜画面目标、素材策略、构图焦点、视觉元素、关键帧节奏、转场、字幕避让、色彩氛围、音乐音效和禁止项都要写清楚;只列旁白和时长不合格,只给 `visual_plan.json` 链接也不合格。权威结构在 `visual_plan.json` 的 `director_review_sheet_v2.scenes[]`;素材缺口看 `asset_diagnosis_summary.single_next_action_zh`,一次只给用户一个最短动作。
12. P1 导演路由必须给每镜写入 `engine_policy`、`route_reason`、`asset_strategy_v2`、`expected_real_evidence`、`director_knowledge_refs` 和 `caption_contract`。普通用户不选引擎,但必须能看懂为什么这一镜需要 HyperFrames/Remotion/用户视频素材或待补素材。
13. HyperFrames/宿主画面插件按 `visual_plan.json` 的 `expected_asset_path` 写出每镜资产。
14. 导演契约层在三审前写入 `style_lock`、`profile_preset`、`layout_contract`、`motion_intent`、`keyframe_beats` 与自检记录;用户只需要一句中文,可选 `--style` 与 `--profile`。
15. `lj render` 用 FFmpeg 组装画面、底部字幕和音轨。
16. 发布级验收用 `lj qa --release --strict`,输出 hard failure / warning;质量门来自 render_manifest、ffprobe/抽帧和 QA,不是 LLM 自评。
17. `lj export --release --strict` 生成发布包。

## 插件与 skill 的边界

- 灵剪核心不 import、不 bundle Remotion/HyperFrames SDK。
- Codex app 用户可以安装 HyperFrames/Remotion/imagegen 相关插件或 skill;它们负责生成资产。
- 灵剪只负责生成规格、通过薄子进程委托或消费落盘资产、组装、QA 和导出。
- 缺插件时必须说清楚“当前只能 fallback”,不能把纯色卡片说成真实画面。
- MCP 未实现;当前不要把 MCP 当成可用主路径。
- 付费引擎需成本确认:火山、fal、picsart 等账号/付费能力会记录 `cost_notices`,Codex 必须先向用户说明费用/账号前提。

可参考的公开入口:

- Codex 官方 plugin:Codex app 的 Plugins / Add to Codex,或 `codex plugin marketplace add dososo/blcaptain-lingjian-video`
- HyperFrames skill 备用:`npx skills add heygen-com/hyperframes`(Node.js 22+、FFmpeg,Apache-2.0,零 key)
- Remotion skill 备用:`npx skills add remotion-dev/skills`(需核对商用 license;>3 人营利组织需付费)
- HyperFrames 官方文档: https://hyperframes.heygen.com/quickstart
- Remotion Agent Skills 官方文档: https://www.remotion.dev/docs/ai/skills
- 若使用 Codex 插件市场,按 Codex app 插件入口安装对应插件;安装后新开会话让 agent 重新加载能力。
