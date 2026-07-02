# 02 · 竞品对标矩阵(COMPETITIVE BENCHMARK)

> 评级:强 / 中 / 弱,均附一句理由。对象:LingJian-M1(目标态)、video-editing-skill、hyperframes-motion-director、HyperFrames、Remotion、MoneyPrinterTurbo、ShortGPT、pyVideoTrans、VideoLingo/KrillinAI、LosslessCut、auto-editor。
> 数据依据见 01;凡涉及 license/热度以 01 的核验状态为准。

## 主矩阵(项目 × 关键维度)

维度缩写:AF=Agent-first｜Web=Web console｜CLI=CLI/API 可编排｜Art=Artifact 可审计｜Gate=人工审批门禁｜中文=中文友好｜字幕=中文字体/字幕/preset｜TTS｜ASR｜URL=网页提取｜OCR｜渲染=渲染可靠性｜Motion=富视觉动效｜包=发布包｜QA=QA/合规｜自部署｜Lic=License 友好｜一次生成=Agent 一次生成可行性

| 项目 | AF | Web | CLI | Art | Gate | 中文 | 字幕 | TTS | ASR | URL | OCR | 渲染 | Motion | 包 | QA | 自部署 | Lic | 一次生成 | 纳入 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **LingJian-M1(目标)** | 强 | 强 | 强 | 强 | 强 | 强 | 强 | 中 | 弱 | 中 | 中 | 中 | 弱 | 强 | 强 | 强 | 强 | 中 | 本体 |
| video-editing-skill | 强 | 弱 | 中 | 中 | 中 | 中 | 中 | 中 | 中 | 弱 | 弱 | 中 | 中 | 弱 | 中 | 强 | 待确认 | 中 | 参考流程 |
| hyperframes-motion-director | 强 | 弱 | 中 | 中 | 强 | 强 | 中 | 中 | 弱 | 中 | 弱 | 强 | 强 | 中 | 中 | 强 | **AGPL(禁入)** | 中 | 只研究 |
| HyperFrames | 强 | 中 | 强 | 中 | 弱 | 中 | 中 | 中 | 中 | 中 | 弱 | 强 | 强 | 中 | 中 | 强 | Apache | 中 | **M2 adapter** |
| Remotion | 中 | 中 | 强 | 中 | 弱 | 弱 | 中 | 弱 | 弱 | 弱 | 弱 | 强 | 强 | 弱 | 弱 | 强 | **4+ 付费** | 弱 | **M3 opt-in** |
| MoneyPrinterTurbo | 弱 | 中 | 中 | 弱 | 弱 | 中 | 中 | 中 | 中 | 弱 | 弱 | 中 | 弱 | 中 | 弱 | MIT | 中 | 竞品/参考 |
| ShortGPT | 中 | 中 | 中 | 弱 | 弱 | 弱 | 弱 | 中 | 中 | 中 | 弱 | 中 | 弱 | 中 | 弱 | 待确认 | 中 | 竞品/参考 |
| pyVideoTrans | 弱 | 中 | 中 | 弱 | 弱 | 强 | 中 | 强 | 强 | 弱 | 弱 | 中 | 弱 | 弱 | 弱 | **GPL(待确认,禁入)** | 弱 | 只研究 |
| VideoLingo/KrillinAI | 弱 | 中 | 中 | 弱 | 弱 | 强 | 强 | 强 | 强 | 强(下载他人) | 弱 | 中 | 弱 | 中 | 弱 | 待确认/**搬运反模式** | 弱 | 只研究 |
| LosslessCut | 弱 | 强(桌面NLE) | 弱 | 弱 | 弱 | 中 | 弱 | 弱 | 弱 | 弱 | 弱 | 强(无损) | 弱 | 弱 | 弱 | 强 | **GPL-2.0(禁入)** | 弱 | 品类反证 |
| auto-editor | 弱 | 弱 | 强 | 弱 | 弱 | 弱 | 弱 | 弱 | 中 | 弱 | 弱 | 中 | 弱 | 弱 | 弱 | 待确认 | 中 | 只研究 |

## 逐维度领先者与对 LingJian 的含义(覆盖第 5 节全部 19 维)

1. **Agent-first 能力**:领先=HyperFrames / motion-director(skill-native、非交互 CLI)。含义:LingJian 靠"Agent 级 CLL + 三审门禁 + artifact"达到强,但要学 HyperFrames 的 `--non-interactive`/plain 输出纪律。
2. **Web console 成熟度**:通用工具普遍弱(多为 Streamlit/Gradio 或桌面 NLE)。含义:**这是 LingJian 最大差异化**——真正的审核-first Next.js 控制台是空白市场。
3. **CLI/API 可编排性**:领先=HyperFrames/Remotion/auto-editor(CLI 成熟)。含义:LingJian 要把"全命令 `--json` + 结构化错误码"做成一等,才谈得上 Agent 编排。
4. **Artifact-first 可审计**:多数弱(状态藏在内存/TinyDB/临时文件)。含义:**LingJian 的 artifact-first + 单一事实源是核心壁垒**,不能被 SQLite 双状态破坏。
5. **人工审批门禁**:唯一可比=motion-director 的"两阶段确认"(prompt 层)。含义:**LingJian 的系统层强制门禁(render 硬拒)是更强形态**,是与所有一键工具的根本区别。
6. **中文用户友好度**:领先=pyVideoTrans/KrillinAI/motion-director。含义:LingJian 需匹配中文安装/路径/字体/平台表达,至少不落后。
7. **中文字体/字幕/平台 preset**:领先=KrillinAI(字幕按平台 UI 自适应)。含义:借鉴其 safe_area 思路到 preset。
8. **TTS/配音**:领先=pyVideoTrans/VideoLingo(多 provider+克隆)。含义:LingJian M1 只需 EdgeTTS+云 TTS 达"中",本地/克隆推 M3,不追平。
9. **ASR/转写**:领先=pyVideoTrans/VideoLingo(WhisperX/FunASR)。含义:**LingJian M1 主动不做**(文本→TTS→视频不需要),M3 再补,避免复杂度。
10. **URL/网页提取**:领先=VideoLingo(yt-dlp 下载)——但那是**违规方向**。含义:LingJian 走 trafilatura 正文 + Playwright 截图,**默认不下载视频**,这是合规优势不是能力短板。
11. **OCR/截图理解**:普遍弱。含义:LingJian 用 RapidOCR 达"中"即可,且应降为**可选**。
12. **渲染可靠性**:领先=LosslessCut(无损)/HyperFrames/Remotion(确定性)。含义:LingJian 用自研 `ffmpeg_card` 求"确定性可靠"而非"炫",这是正确取舍。
13. **富视觉 motion**:领先=HyperFrames/Remotion/motion-director。含义:**LingJian M1 主动放弃 motion**(卡片+帧内字幕),富视觉靠 M2 HyperFrames adapter 补,避免 ffmpeg_card 变小 Remotion。
14. **发布包能力**:普遍弱(多输出裸 MP4)。含义:**LingJian 的 canonical 多平台/多语言/多比例发布包 + credits/manifest 是明确差异化**。
15. **QA/合规检查**:普遍弱;motion-director 有 anti-PPT 质量门(思想可借鉴)。含义:LingJian 的分级 QA(hard/warn/info)+ source_map + 合规检查是壁垒。
16. **本地/自部署友好**:领先=LosslessCut/HyperFrames/MoneyPrinterTurbo。含义:LingJian 本地优先 + doctor 引导达强。
17. **License 友好度**:领先=HyperFrames(Apache)/MoneyPrinterTurbo(MIT)。含义:LingJian 选 Apache-2.0 且严守 AGPL/GPL 禁入,是长期社区优势。
18. **Agent 一次生成可行性**:所有大项目都"中/弱"(单次难全量)。含义:**印证 LingJian 必须分 3 批交付**,不可一次全量。
19. **纳入 M1/M2/M3/v2/不纳入**:见主矩阵末列——本体=LingJian;M2 adapter=HyperFrames;M3 opt-in=Remotion + 本地 TTS/ASR;只研究/禁入=motion-director(AGPL)、LosslessCut(GPL)、pyVideoTrans(GPL 待确认)、VideoLingo(搬运反模式);竞品参考=MoneyPrinterTurbo/ShortGPT。

## 一句话结论
LingJian 在 **Web 审核体验、artifact 可审计、系统层审批门禁、多平台发布包、合规** 五项是市场空白或领先;在 **富视觉 motion、成熟 TTS/ASR** 上主动落后并靠 M2/M3 adapter 补齐。这个"强控制点 + 有序补齐"的组合成立——前提是别在 M1 就去追 motion/ASR/本地克隆而引爆复杂度。
