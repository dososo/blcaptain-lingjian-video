# 灵剪 lingjian-video

**中文** · [English](README.en.md)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE) ![Agent Skill](https://img.shields.io/badge/Agent-Skill-d98e3a.svg) ![FFmpeg](https://img.shields.io/badge/FFmpeg-required-2b2622.svg) ![CLI](https://img.shields.io/badge/CLI-agent%20agnostic-2E6B4F.svg)

> 一句话进 —— 脚本 / 分镜 / 配音 / 画面 / 配乐 / 字幕 / 音效全自动，**但每一关，都能审**。

<div align="center">
  <video src="https://github.com/user-attachments/assets/f96e4b95-c723-40a0-a1f5-e16cc686d6c1" controls playsinline width="82%"></video>
</div>

> **▶ 主介绍片 · VOX 清爽科技 · 16:9** —— 网页版上方播放器可直接播放。本片由灵剪端到端产出。
>
> 📱 GitHub 手机 App 不显示内嵌播放器 —— 点链接进 [在线画廊](https://dososo.github.io/blcaptain-lingjian-video/docs/gallery.html) 在线观看全部四套作品。

---

## 为什么做这个

市面上的 AI 视频「一句话出片」是个黑箱：一句话进去，出一条成片。第三个镜头不对，你想「就改那一处」—— 做不到，只能整条重新生成，碰运气看下一次是否更好。

**灵剪相反**：一句话进去，脚本、分镜、配音、画面、配乐、字幕、音效全自动往下走，**但每一关都会停下来，把这一关的候选摆给你看，你确认后才继续**。不是碰运气，是你在逐关做决定。

> 诚实前提：灵剪只保证**流程可复跑、每一关可审计**，不承诺成片质量或「爆款」。

---

## 独家差异化 · 五个设计支柱

任何一条丢了，灵剪就退化成又一个黑箱。

1. **蓝图先行** —— 一部片由一张贯穿全片的蓝图统领（整片能量曲线 + 视觉母题 + 每一关的产物与门禁），而不是逐镜各自为政。（从流水线产物自动生成能量曲线正接入主线,见 Roadmap）
2. **本地导演控制台** —— 每一关在**你自己电脑的本地页面**（`localhost`）打开一个可读、可交互的导演板，把这一关的候选逐镜摆给你看。**绝不用任何云端或开发地址**，你看到的每一步都在你自己机器上。
3. **调研贯穿始终** —— 调研不是只在开头，而是每一关持续吸收顶级证据、内化成基线、牵引产出。
4. **关卡确认，给候选不给 yes/no** —— 每一关不是问「行不行」，而是给出候选让你挑、让你改，你点头才进下一关。
5. **可审计** —— 每一关的产物、门禁、证据都可追溯复核；审批用签名绑定产物内容，**内容一改，批准自动失效**。

### ▸ 灵剪运行实拍 · 导演控制台

每一关都在控制台把候选逐镜摆到你面前，你逐关确认才往下走 —— 下面是**分镜/动效关**、**脚本关**、**配音关**的真实界面。

<div align="center">
  <img src="assets/screenshots/console-director-board.jpg" width="92%" alt="分镜/动效关 · 整片能量曲线 + 逐镜候选确认">
  <br><sub><b>分镜/动效关</b> —— 一条整片能量曲线看全片律动，7 镜逐镜拆解（脚本 · 分帧 beat · signature 动效 · 进出转场），逐镜点头才进渲染</sub>
</div>

<br>

<div align="center">
  <img src="assets/screenshots/console-script-gate.png" width="92%" alt="脚本关 · 同一主题三版脚本、逐镜候选">
  <br><sub><b>脚本关</b> —— 同一主题、三版脚本三种讲法，逐镜候选摆给你，挑你最想要的那一版</sub>
</div>

<br>

<div align="center">
  <img src="assets/screenshots/console-voice-gate.png" width="92%" alt="配音关 · 音色候选试听 + 11 步工作流">
  <br><sub><b>配音关</b> —— 音色候选真合成试听、逐个可听，底部 11 步工作流每一关都能审</sub>
</div>

---

## 四套风格（同一套能力，换皮不重做）

> 四条都由灵剪产出。点击任意封面进 [在线画廊](https://dososo.github.io/blcaptain-lingjian-video/docs/gallery.html) 播放。

<table>
<tr>
<td width="50%"><a href="https://dososo.github.io/blcaptain-lingjian-video/docs/gallery.html"><img src="assets/posters/vox-16x9.jpg" alt="VOX 清爽科技"></a><br><b>① VOX · 清爽科技</b>（9:16 + 16:9）— 明亮、直给，产品介绍的本行。</td>
<td width="50%"><a href="https://dososo.github.io/blcaptain-lingjian-video/docs/gallery.html"><img src="assets/posters/dark-keynote.jpg" alt="DARK KEYNOTE 暗场史诗"></a><br><b>② DARK KEYNOTE · 暗场史诗</b>（16:9）— 厚重、发布会仪式感。</td>
</tr>
<tr>
<td><a href="https://dososo.github.io/blcaptain-lingjian-video/docs/gallery.html"><img src="assets/posters/cinematic.jpg" alt="CINEMATIC 电影级人文短片"></a><br><b>③ CINEMATIC · 电影级人文短片</b>（16:9）—《一根线的三千年》，一根金线串起叙事。</td>
<td><a href="https://dososo.github.io/blcaptain-lingjian-video/docs/gallery.html"><img src="assets/posters/neue-sachlichkeit.jpg" alt="NEUE SACHLICHKEIT 实证纪实"></a><br><b>④ NEUE SACHLICHKEIT · 实证纪实</b>（16:9）— 手 + 实物 + 一个真实物理现象扛全片，无旁白。</td>
</tr>
</table>

---

## 生产流程（一句话 → 成片，每一关你都能审）

你只用说人话，技术复杂度留在后台。整条主线：

| 关卡 | 你做什么 | 灵剪做什么 | 停下来给你审 |
|---|---|---|---|
| **0 · 说清目标** | 说一句：做什么平台、什么主题、什么比例、给哪份内容依据 | 复述成清楚的制作目标 | — |
| **0 · 能力门诊** | 看一眼「已具备 / 需补齐」 | 检测本机能力，缺什么用人话告诉你怎么补 | — |
| **1 · 脚本** | 读脚本，说「批准」或直接改 | 按你的内容依据写脚本，不替你编产品细节 | ⏸ 审脚本 |
| **2 · 配音** | 先试听几个音色挑一个 → 确认语气情绪 → 批准 | 生成真实试听、导演确认单、整段连贯配音 | ⏸ 审配音 |
| **3 · 画面** | 逐镜看「这一镜会看到什么、怎么动、怎么转场」，点头或补素材 | 出每镜导演分镜确认单，在本地控制台摆给你看 | ⏸ 审画面 |
| **4 · 字幕 / 配乐 / 音效** | 试听 BGM 选气质 | 烧录逐字字幕（不带标点）、垫 BGM、点音效卡点 | 随画面关一并确认 |
| **5 · 渲染 / QA / 导出** | 拿成片 | 用 FFmpeg 渲染、严格 QA 拦掉样片、导出多平台分发包 | 发布级 QA 全绿才导出 |

**三道人工审批门**：脚本 / 配音 / 画面，渲染前必须全部批准。审批用签名绑定产物内容，**内容一改，批准自动失效**（没有 `--force`）。

命令是底层执行引擎，普通用户不用直接敲：

```bash
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --json
# 默认在 脚本 / 配音 / 画面 三关自动停下等你确认，approve 后继续。
```

---

## 工具链与分工（诚实分层）

灵剪核心是一个 **agent 无关的编排器 + FFmpeg 组装器 + 可审计门禁**。工具按接入方式分三层，`doctor` 会如实告诉你每一项是「已具备 / 需补齐」：

**① 灵剪内置（自己的代码干的）**
- 编排 / 状态机 / 三审批门（签名绑产物，改内容自动失效）
- **FFmpeg / ffprobe** 渲染（H.264 + 烧录中文字幕 + AAC + 响度归一）、QA 硬门、多平台导出 + license 清单
- **Seedance 文生视频（发布级）**：检测到火山方舟 ARK key 时，画面关按分镜提示词**直接调用** Seedance 生成真实动态视频 mp4（`--engine seedance`；这是零素材用户「一句话 → 真视频」的核心，非引导用户自己生成）
- **Whisper 逐字对齐**：配音合成后识别音频，产出真时间轴字幕（替代字数估算，治「逐镜错位」的老坑）
- **silencedetect 卡点**：测配音停顿 → 语音段起点，画面事件卡这些点、绝不早于配音
- provider 探测与桥接、中文字体处理

**② 宿主 / CLI 即插即用（灵剪只探测 + 消费产物，不 bundle SDK）**
- **LLM**：继承你已登录的 `claude` / `codex` CLI，或 `ollama` / OpenAI-compatible
- **配音 TTS**：用户录音（发布级首选），或**火山豆包语音大模型**（唯一发布级云 TTS）；无 key 时本地 Kokoro 仅供预览样片
- **动态画面**：宿主 HyperFrames（发布级）/ Remotion / 你自备的每镜 mp4
- **AI 生图**：Codex 内置生图能力；其他 agent（Claude / Gemini / Cursor 等）经 `codex exec` CLI 调用 Codex 生图（灵剪消费产出的图，恒为参考级）
- **配乐 / 音效**：免版税 BGM/SFX 由宿主 agent 浏览器（Chrome use / computer use）从 Pixabay 抓取（Pixabay 无公开音乐 API），或用户自带；`lj ingest audio --kind bgm/sfx` 挂载，渲染自动混（BGM 默认低于人声 16dB）
- **网页截图**：Playwright（`ingest url --screenshot`）

**③ 固化能力库 · 随仓库发布（`capabilities/` + `director-board/`）**
- **导演板**（关卡确认台旗舰）· **转场库**（42 转场谱系 + 内容匹配器，`node` 测试可复现稀缺守卫）· **cadence**（silencedetect 精确卡点）· **音效策略**（动作→音效映射五铁律）· **版式安全**（字形级溢出兜底）—— 全比例全风格通用的横切能力，是「一句话直出」比不了的差异化内核。索引见 [`capabilities/README.md`](capabilities/README.md)。

**④ 结构项 · 集成中（详见 Roadmap）**
- 整片能量曲线自动生成 · 律动关 · 调研证据门 · 风格关 / 音乐关候选式关卡 · 脚本多版本候选 —— 核心差异化的**流程关卡**补全，方法论已在四套样片验证，正在接入主线。

### 哪些 Agent 能用

- **agent 无关**：`lj` 是纯 CLI，任何能跑 shell 命令的 agent 或人都能驱动 —— 这是「多 agent」的真实底座。
- **一等公民打包**：Claude Code 走 `scripts/install_skill_links.sh` 软链安装；Codex 走插件市场。
- **其它 agent（Gemini / Cursor 等）**：现在即可经 `lj` CLI 使用；专属安装打包在 Roadmap。

---

## 安装

灵剪 **agent 无关** —— 任何能跑 shell 命令的 agent 或人都能驱动。

**最简单（推荐）· 对话式**——把本仓库地址发给你的 AI agent，让它安装并跑能力门诊：

- **Claude Code**：对它说「安装 `https://github.com/dososo/blcaptain-lingjian-video` 这个 skill」
- **Codex app**：`codex plugin marketplace add dososo/blcaptain-lingjian-video`

**手动 · 本地**：

```bash
git clone https://github.com/dososo/blcaptain-lingjian-video && cd blcaptain-lingjian-video
uv sync
scripts/install_skill_links.sh   # 软链到 ~/.claude/skills 与 ~/.agents/skills
uv run lj setup                  # 能力门诊：已继承 / 已具备 / 必须补齐 / 可选增强
```

其它 agent（Gemini / Cursor 等）同样用 `lj` CLI 驱动。

**FFmpeg 是发布硬门**，且须支持 `drawtext` 与 AAC：

```bash
# macOS
brew install ffmpeg && ffmpeg -filters | grep drawtext
# Ubuntu/Debian
sudo apt-get install -y ffmpeg && ffmpeg -filters | grep drawtext
# Windows
winget install Gyan.FFmpeg
```

配音、真实 provider、火山豆包 key 的安全配置详见 [`docs/ONBOARDING.md`](docs/ONBOARDING.md) 与 [`docs/CAPABILITY_MATRIX.md`](docs/CAPABILITY_MATRIX.md)。**任何 key 只从当前环境读取，绝不写进仓库、日志或导出包。**

---

## 本地导演控制台（director-board）

灵剪的关卡控制台是一个**数据驱动的本地导演板**，随仓库发布（`director-board/`）：

```bash
cd director-board
python3 -m http.server 8080
# 浏览器打开 http://localhost:8080/standalone.html
```

- **只在本机 `localhost` 打开**，逐镜展示能量档、台词、分帧节奏、招牌动效、进出转场，一个「确认」按钮。全部确认才放行下一关。
- 纯原生 JS + SVG，无第三方库、无网络请求（读本地数据除外），渲染可复现。
- `lj console` 一键起本地服务 + 右侧自动打开 + 从流水线产物自动生成 `board.json` 的集成正在推进（见 Roadmap）。

---

## 隐私与安全

- **数据默认留本机**：项目文件、产物、渲染成片、导出包都写到你指定的本地目录。
- **key 默认不落盘**：真实 provider 的 key 只从当前 shell 环境读取，不写仓库、日志、manifest 或 release 包。
- **能继承就不问 key**：已登录的 Claude / Codex CLI 只通过官方命令行调用，不读 token、cookie、Keychain 内部文件。
- **控制台只连本机**：导演板不发外部请求、不嵌远程资源、不使用任何云端或开发地址。

---

## 后续计划（Roadmap）

- **结构项补全**（进行中）：整片能量曲线自动生成、律动关、调研证据门、风格关 / 音乐关候选式关卡、脚本多版本候选（Seedance 文生视频、Whisper 对齐、silencedetect 卡点、转场库 + 匹配器、cadence、音效策略、版式安全均已随仓库发布）。
- **`lj console`**：一键起本地服务 + 右侧自动打开 + 从流水线产物自动生成 `board.json`。
- **更多 Agent 打包**：Gemini、Cursor 等专属安装方式。
- **MCP server**：让宿主 agent 通过 MCP 调用主线工具。
- **平台知识包**：抖音 / 小红书 / Bilibili / YouTube 的发布结构与字幕模板。
- **更多风格**（同一套能力换皮扩充，规划自 16 套风格谱系、已实现 4 套）：双色调硬核 DUOTONE · Riso 错版套印 RISOGRAPH · 波普漫画 POP ART · 墨象水墨 INK WASH · 剪纸拼贴定格 PAPER CUT · 瑞士栅格 SWISS GRID · 等距纸片 ISO 3D · 赛博数据流 DATA STREAM · 手绘白板 WHITEBOARD · 杂志摄影 EDITORIAL · 禅意极简 ZEN · 复古胶印招贴 LETTERPRESS。

---

## FAQ

**灵剪保证做出爆款吗？** 不。只保证流程可复跑、每一关可审计。质量结论来自真实命令、渲染 manifest、ffprobe 与 QA 硬门，不靠 AI 自评。

**不给 key 能用吗？** 能走预览：继承 LLM 写脚本 + 本地样片 TTS + 本机 FFmpeg。但发布级需要真实配音（录音或云 TTS）与真实动态视频画面。

**它会偷偷调付费服务吗？** 不会。火山等付费能力会先说明账号与费用前提，取得你确认再执行。

---

## 关于作者

**灵剪 lingjian-video** 由 **爆裂队长NEXT（BLCaptain）** 独立创作与维护 —— 一个把「一句话 → 可审的短视频」做成可复跑、可审计、可归档流程的开源 Agent Skill。

- GitHub：[@dososo](https://github.com/dososo)
- X / Twitter：[@thinkszyg](https://x.com/thinkszyg)
- 邮箱：blteam2026@outlook.com

欢迎在 [Issues](https://github.com/dososo/blcaptain-lingjian-video/issues) 提反馈、提需求。如果这个项目对你有用，欢迎 Star。

---

## License

本仓库按 **Apache License 2.0** 授权，详见 [LICENSE](LICENSE)。

第三方工具、模型与字体各自的授权以其原始条款为准；商用发布前请自行核验所用 TTS / 视频生成 / 素材 / 字体的授权状态。
