# 01 · 调研来源与核验(RESEARCH SOURCES)

> 核验时间:2026-07-01,使用 WebSearch(官方仓库 / 官方文档 / license 页 / 二手长文交叉验证)。
> 标注规则:**[已联网核验]** = 本轮检索到官方或多源一致证据;**[待确认]** = 未直接读到 LICENSE 文件或权威页,结论为强先验,实现前须以仓库 LICENSE 为准。
> 未能直接 `web_fetch` 各仓库 LICENSE 原文(受 URL 白名单限制),故凡未在检索结果中出现明确 license 字样者一律标 [待确认]。

---

## A. 渲染 / Agent 视频引擎

### HyperFrames — `heygen-com/hyperframes`
- URL: https://github.com/heygen-com/hyperframes ; https://hyperframes.heygen.com/
- License: **Apache-2.0**,官方明确"no per-render fees or commercial-use thresholds"。**[已联网核验]**
- 活跃度:2026-04 发布,7 月初仍高频提交(README/CLAUDE.md 近日更新);19 个 agent skills;架构含 cli/core/engine(Puppeteer+FFmpeg)/producer/studio/registry。**[已联网核验]**
- 核心能力:HTML+data-* → 无头 Chrome 逐帧捕获 → FFmpeg 编码;确定性 MP4;自带 TTS/字幕/Whisper/BGM 音频引擎;非交互 CLL,agent-first。
- 可借鉴:agent-first CLI 非交互 + `--non-interactive`、`doctor`、lint/validate/inspect 质量门、"narration 决定 scene 时长"的思路。
- 不能借鉴/复制:不复制其 skill 文本/registry blocks/组件代码。
- 与 LingJian 关系:**M2 富视觉渲染 adapter(经 subprocess)**;不作 M1 地板(仅 2–3 月龄、Node22+Chromium 重依赖、自带与 LingJian 重叠的音频/字幕栈、API 仍在演进)。
- M1/M2/M3/v2 影响:M1 不引入;M2 作为 `engines/hyperframes` 子进程 adapter。
- 可信度:**[已联网核验]**

### Remotion(官方)
- URL: https://www.remotion.dev/docs/license ; https://github.com/remotion-dev/remotion/blob/main/LICENSE.md ; https://www.remotion.pro/license
- License: 源码可见但**非许可式**;个人/非营利/**≤3 人营利**免费(含商用);**4+ 人营利需付费 company license**。价目:Creators $25/seat/月;**Automators $0.01/render、$100/月起(明确面向"构建视频生成工具/自动化")**;Enterprise $500/月起。**[已联网核验]**
- 活跃度:2021 起,约 46k stars,成熟。**[已联网核验]**
- 核心能力:React 组件化程序视频、类型安全、Lambda 云渲染、Agent Skills。
- 与 LingJian 关系:**M3 opt-in adapter,绝不默认/捆绑**。理由:Automators 档正对标"做视频工具"=本产品;Apache-2.0 主仓若默认集成会把付费义务静默转嫁 4+ 人用户。
- M1/M2/M3/v2 影响:M1/M2 不默认;M3 用户自行安装 + doctor 显著提示 license。
- 合规:**列入合规红线(见 D 节)**。
- 可信度:**[已联网核验]**

### hyperframes-motion-director — `geekjourneyx/...`
- URL: github.com/geekjourneyx/hyperframes-motion-director(GitHub topics 确认存在"Chinese-first HyperFrames motion-video production"agent skill,含 article/product/website/README→video)。**[已联网核验:项目存在与定位]**
- License: 提示词声明 **AGPL-3.0**。本轮未直接读到该仓库 LICENSE 文件 → **[待确认]**;但同类"agentic video production"项目(如 `calesthio/OpenMontage`)**已确认 AGPL-3.0**,AGPL 在该品类是普遍选择,故按 AGPL 处理。
- 核心能力(据定位):HyperFrames Agent Skill、两阶段确认、中文竖屏默认、设计提案、storyboard、review report、anti-PPT 质量门禁。
- 可借鉴:**仅产品流程思想**(两阶段确认、storyboard→review、anti-PPT/slideshow-risk 门禁的"理念")。
- 不能借鉴/复制:**AGPL → 禁止复制其 prompt/template/script/UI/代码进 Apache 主仓**;不得 vendor,不得改写照搬。
- 与 LingJian 关系:**只研究,不引入**。
- 合规:**列入合规红线**。
- 可信度:项目存在 [已联网核验];AGPL [待确认,强证据]。

### 相关旁证:`calesthio/OpenMontage`(非提示词要求,但直接同类)
- License: **AGPL-3.0**。**[已联网核验]** 说明"agentic video production"品类的 AGPL 传染风险真实存在。作用同上:只研究不引入。

---

## B. 一键短视频生成

### MoneyPrinterTurbo — `harry0703/MoneyPrinterTurbo`
- URL: https://github.com/harry0703/MoneyPrinterTurbo
- License: **MIT**。**[已联网核验]**
- 活跃度/热度:约 **76k stars / 10k+ forks**(2026-06);Python;Streamlit WebUI + FastAPI;uv/Docker/Colab。**[已联网核验]**
- 核心能力:主题/关键词→文案→**Pexels/Pixabay 素材**→TTS→字幕→BGM→1080p(9:16/16:9),zh+en,批量。
- 可借鉴:5 段流水线拆分、WebUI+API 双入口、faster-whisper 可选、config 化 provider。
- 不能借鉴/复制:不复制代码;**素材来自 Pexels/Pixabay,发布前 license 需用户核验**(与 LingJian"不内置盗版素材"一致)。
- 与 LingJian 关系:**竞品 + 参考流程**(topic-to-video,而 LingJian 是 source/审核-first)。
- M 影响:参考其 provider 抽象与 CLI/API,不引入代码。
- 可信度:**[已联网核验]**

### ShortGPT — `RayVentura/ShortGPT`
- URL: https://github.com/RayVentura/ShortGPT
- License:**[待确认]**(检索未见明确 license 字样,历史印象偏许可式)。
- 活跃度:实验性框架;Docker/Gradio(31415);ContentShort/Video/Translation Engine;Pexels/Bing 素材。**[已联网核验:能力]**
- 与 LingJian 关系:**竞品/参考流程**(LLM-oriented editing DSL、翻译配音 engine)。
- M 影响:参考,不引入。可信度:能力 [已联网核验],license [待确认]。

### MoneyPrinter(V1/V2)— `FujiwaraChoki/MoneyPrinter`
- URL: https://github.com/FujiwaraChoki/MoneyPrinter
- License:"See LICENSE file",历史 MIT → **[待确认]**。Ollama-first、Postgres 队列、MoviePy/ImageMagick。**[已联网核验:能力]**
- 与 LingJian 关系:**竞品/参考流程**(本地优先 + DB 队列可作 M2 队列参考)。可信度:license [待确认]。

### short-video-maker / OpenShorts(同类 MCP/REST/自托管 shorts)
- 未逐一新核验;历史印象 short-video-maker≈MIT、含 MCP/REST/Remotion/Pexels/Kokoro(偏英文)。**[待确认]**
- 与 LingJian 关系:**MCP/REST 三入口思路可参考**;英文/Pexels 生态非本产品重点;不引入代码。

---

## C. 字幕 / 翻译 / 配音 / 本地化 与 语音模型

### pyVideoTrans — `jianchang512/pyvideotrans`
- URL: https://github.com/jianchang512/pyvideotrans
- License:**GPL-3.0(强先验)** → **[待确认]**(本轮未读到 LICENSE 原文)。约 **16k stars**。**[已联网核验:热度/能力]**
- 能力:ASR+翻译+TTS+字幕+配音一体、打包 .exe、多角色配音、Windows 友好。
- 与 LingJian 关系:**只研究(若 GPL 则禁入主仓);ASR/字幕对齐属 M3 参考**。合规:若确为 GPL,**列入红线**。

### VideoLingo — `Huanshere/VideoLingo`
- URL: https://github.com/Huanshere/VideoLingo
- License:存在 LICENSE(印象 Apache-2.0)→ **[待确认]**。
- 能力:Netflix 级字幕切割/翻译/对齐/配音,Translate-Reflect-Adaptation 三步,Streamlit,**深度集成 yt-dlp 拉取源视频**,支持 GPT-SoVITS/Azure/OpenAI/Fish-TTS 克隆。**[已联网核验]**
- **重大合规警示**:其自述为"一键全自动**视频搬运** AI 字幕组"+ yt-dlp 直拉他人视频 → 正是 **D5 禁止的"下载他人视频"反模式**。即使代码许可式,**该产品模式不可复制**。
- 与 LingJian 关系:**只研究其翻译质量流程(三步反思),严禁复制其搬运/yt-dlp 下载路径**。合规:**列入红线(产品行为层)**。

### KrillinAI — `krillinai/KrillinAI`
- URL: https://github.com/krillinai/KrillinAI
- License:印象 Apache-2.0 → **[待确认]**。约 **10k stars**。**[已联网核验:热度/能力]**
- 能力:短视频本地化(TikTok/Shorts/Reels/抖音/B站),CosyVoice 克隆,WhisperKit(Apple Silicon 原生),字幕按平台 UI 自适应,一键安装。
- 可借鉴:**"字幕布局按平台 UI 遮挡自适应"**思路(与 LingJian 平台 preset safe_area 一致);Apple Silicon 路径。
- 与 LingJian 关系:**竞品/流程参考**(仍偏"翻译已有视频"),不引入代码。

### GPT-SoVITS — `RVC-Boss/GPT-SoVITS`
- License:**代码 MIT**。**[已联网核验]** 5s zero-shot / 1min few-shot 克隆,中英日韩粤。
- 与 LingJian 关系:**M3 本地 TTS/克隆 adapter(外部服务)**;**克隆必须默认关 + 授权确认**;权重条款独立于代码。合规:克隆授权门禁。

### CosyVoice — `FunAudioLLM/CosyVoice`
- License:**代码 Apache-2.0;权重商用状态存疑(官方 issue 有此问)** → 权重 **[待确认]**。**[已联网核验:代码 license]** 多语言、跨语言 zero-shot 克隆、~150ms 流式。
- 与 LingJian 关系:**M3 本地中文 TTS adapter(外部服务)**;不捆绑权重;记录 license。

### IndexTTS(-2)— `index-tts/index-tts`(B站/Index Team)
- License:**[待确认]**(权重条款需确认)。**[已联网核验:能力]** IndexTTS-2 情绪与音色解耦、**毫秒级时长控制(对口播视频对齐极有价值)**、WER 低。
- 与 LingJian 关系:**M3 本地 TTS adapter**;其毫秒级时长控制可作 M3 "音画字对齐"增强候选。

### FunASR — `modelscope/FunASR`
- License:**代码 MIT(强先验)** → **[待确认]**;权重独立。**[已联网核验:能力]** 中文生产级 ASR、VAD、标点、说话人、OpenAI-compatible 服务。
- 与 LingJian 关系:**M3 ASR adapter(外部服务),仅用于上传音视频转写/词级对齐**;不进 M1 主干。

---

## D. 剪辑基础设施

### LosslessCut — `mifi/lossless-cut`
- URL: https://github.com/mifi/lossless-cut
- License:**GPL-2.0**。约 **29.6k stars**。**[已联网核验]** Electron+FFmpeg 无损切割/合并、离线、无遥测。
- 与 LingJian 关系:**只研究,禁入 Apache 主仓**;它是"手动无损剪切 NLE",与 LingJian"生成式、无 timeline"是不同品类——**正是 LingJian M1 不做传统 timeline 的反证**。合规:**GPL 列入红线**。

### auto-editor — `WyattBlue/auto-editor`
- URL: https://github.com/WyattBlue/auto-editor
- License:**[待确认]**(印象宽松/Public-Domain 系,需确认)。能力:按静音/场景自动剪切已有视频。
- 与 LingJian 关系:**只研究**;属"自动剪已有视频",非本产品主链路;可作 M3"上传素材自动清洗"远期参考。

### FFmpeg(官方)
- URL: https://ffmpeg.org/
- License:**LGPL-2.1+ 或 GPL(取决于编译开关/编码器)**;启用 `--enable-gpl`/非自由编码器会升级到 GPL/不可分发。**[已联网核验:通用事实]**
- 与 LingJian 关系:**M1 核心底座(subprocess)**;必须记录 build/编码器并避开非自由编码器;分发形态用系统安装或 LGPL build。

### 字幕/字体生态(ASS/SRT/libass/CJK fallback)
- ASS/SRT 为通用格式;libass 烧录需字体可被 libass 访问;CJK 需 Noto Sans SC(**SIL OFL**,可分发但**本仓不提交**,doctor 下载到缓存)。**[已联网核验:通用事实]**
- 与 LingJian 关系:M1 字幕**画进帧**(自控字体路径)为主、SRT/VTT/ASS 作 sidecar;libass 烧录留 M2。

---

## E. Web/Agent 工程最佳实践来源(通用事实,非单一仓库)
- Next.js App Router / Route Handlers / Server Actions;FastAPI + Pydantic v2 + Typer + Rich + SQLite(SQLModel/SQLAlchemy);MCP server tool 设计;JSON Schema/OpenAPI/CLI JSON 一致性;离线 CI + golden files + snapshot；子进程 sandbox + 路径穿越防护 + API key(keychain/加密)+ prompt injection(网页内容当不可信输入)。落地建议见 03。**[通用工程实践]**

---

## 合规红线汇总(影响 Apache-2.0 主仓,必须单列)

| 项目 | License | 风险 | 处置 |
|---|---|---|---|
| hyperframes-motion-director | AGPL-3.0(待确认,强证据) | AGPL 传染 | **禁入主仓**;只学流程思想,不复制 prompt/template/script/UI |
| OpenMontage | AGPL-3.0(已核验) | AGPL 传染 | 同上,只研究 |
| LosslessCut | GPL-2.0(已核验) | GPL 传染 | **禁入主仓**;仅作品类反证研究 |
| pyVideoTrans | GPL-3.0(待确认) | GPL 传染 | 若确为 GPL,**禁入主仓**;只研究 |
| VideoLingo | 许可式(待确认)但**产品=视频搬运+yt-dlp** | **版权行为反模式** | 禁复制其下载/搬运路径;URL 默认不下载他人视频 |
| Remotion | 源码可见+company license | 4+ 人付费/Automators 档转嫁 | **不默认/不捆绑**;M3 opt-in;doctor 强提示 |
| CosyVoice/GPT-SoVITS/IndexTTS/FunASR | 代码宽松,**权重条款独立** | 权重商用不确定 | **不捆绑权重**;外部服务;doctor 记录 license;克隆需授权 |
| FFmpeg | LGPL/GPL 取决编译 | 非自由编码器不可分发 | 避非自由编码器;记录 build |
| Noto Sans SC | SIL OFL | 可分发但不宜入仓 | doctor 下载到缓存,不提交仓库 |
