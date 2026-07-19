# 更新日志(Changelog)

本项目变更遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/) 与语义化版本。

## [v1.1.0] — 2026-07-19 · 本机导演控制台一键命令

### 新增(Added)
- **`lj console <项目>`** —— 命根子落地成单条命令:起本机 `localhost` 服务(只绑 `127.0.0.1`、永不对外),按当前关**自动生成候选页** —— 配音关 = 音色卡 + 内联试听播放器;脚本 / 分镜关 = `render.js` 能量曲线导演板 + 每镜「确认」。打印 `http://127.0.0.1:<port>/` 供宿主 agent 在右侧浏览器打开;逐项确认经 `/confirm` 写回 `artifacts/console_state.json`。`--gate auto` 按已有产物自动判关。从此每个装 skill 的用户在配音/脚本/分镜关都能在**本机控制台**逐项审候选,不再靠 agent 手搭、也不把候选当文件甩进对话。

### 变更(Changed)
- README / SKILL 控制台章节更新:`lj console` 已是主用法(手动 `python3 -m http.server` 留作备选);去掉 SKILL「尚未是单条命令」的旧诚实边界。

### 说明
- 仍在推进(未宣称已做):画面关(`visual_plan`)专用视图、确认自动转 `lj approve`、`lj run` 每关自动调起 console。

## [v1.0.9] — 2026-07-18 · 首个公开开源发布

### 新增(Added)
- **宿主自产脚本**(`lj script --emit-contract` / `--from-file`,`lj run --script-provider host`):灵剪是 agent 通用 skill,宿主 agent(Claude/Codex/Gemini)本身就是 LLM,脚本内容由宿主直接创作再交 `lj` 结构化/校验/门禁,不再 fork 外部 `claude -p`/`codex exec` 子进程。`auto`/`claude_cli`/`codex_cli` 降为「宿主非 LLM / CI」的兜底路径。
- **4 套已实现风格库**(`--style`):`vox_cut`(Vox 编辑剪影)、`dark_keynote`(暗场发布·史诗)、`cinematic`(写实电影感·国风人文)、`neue_sachlichkeit`(新客观主义·实物档案)。每套含真实色板/字体/质感/动画/prompt 约束,完整方法论见 `styles/<key>.md`。换风格 = 复用横切能力换皮重排。
- **无旁白模式**(`--no-voiceover`):不合成配音,文字卡(`on_screen_text`)代旁白承担叙事,音频 = BGM+SFX 或纯静音基轨。适合「作者退场、让对象自己说话」的实物档案 / 蓝晒类风格。
- **固化能力库**(`capabilities/`):导演板 + 转场库(42 转场谱系 + 内容匹配器 + 稀缺守卫)+ cadence(精确卡点)+ 音效策略(五铁律)+ 版式安全。全比例全风格通用,SKILL 写成宿主 agent 硬约束。
- **Seedance 文生视频**:火山方舟 ARK 适配器,零素材「一句话 → 真动态视频」。
- **Whisper 逐字对齐 + silencedetect 卡点**:配音 → 整段识别 → 按句边界定各镜时长 + 各镜真字幕,治「字数估偏 1 秒逐镜错位」。
- **跨 OS 安全存 key**:macOS 钥匙串 / Linux Secret Service / Windows 用户环境变量,存后自动注入;引导见 `docs/ONBOARDING.md`。

### 修复(Fixed)
- 成片响度统一 **−14 LUFS / −1.0 dBTP**(抖音 / B站 / YouTube 通用),代码 / 文档 / 测试一致。
- key 命名 Blocker:`docs/ONBOARDING.md` 存 key 命名对齐 `read_credential`(service = account = `lingjian:<NAME>`),修复「按官方文档配 key 却读到空」。
- 音乐 / 配音**连贯硬规则**:固定音量、固定节奏,清除早期 sidechain / ducking / 「BGM 呼吸」旧账(一动就割裂)。

### 变更(Changed)
- 配乐 / 音效来源明确为 **Pixabay**(无公开音乐 API,宿主 agent 浏览器抓取)+ `lj ingest audio` 挂载。
- 生图澄清:Codex 内置生图,非 Codex 宿主经 `codex exec` CLI 调用;灵剪只消费产出的 PNG 作参考。

### 说明
- 控制台永远是**本机 localhost 服务**(`director-board/`),绝不含任何云端 / 隧道 / 开发地址。
- 密钥只从环境 / 系统安全存储读取,绝不写入仓库、日志或导出包。
