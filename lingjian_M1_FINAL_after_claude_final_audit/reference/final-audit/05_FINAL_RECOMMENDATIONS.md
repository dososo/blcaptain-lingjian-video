# 05 · 最终建议(FINAL RECOMMENDATIONS)

## M1 保留范围(不动)
纵向主干:`init → ingest(text/url/image) → extract → script → approve → voice → approve → visuals → approve → render(ffmpeg_card) → qa → export`。四端共用 core 状态机 + artifact 单一事实源 + 系统层三审门禁(hash 绑定)+ 真实 LLM(OpenAI-compatible + Anthropic)+ 真实 TTS(EdgeTTS + 云 TTS 同步)+ 五平台纯配置 preset + zh/en + 9:16/16:9 一等 + 3:4/4:3 盒模型适配 + canonical export + 分级 QA + doctor + release/mock 硬判定。

## M1 建议压缩范围
1. **Web 8 页 → 5 页**(保留全部人审,合并渲染+发布、doctor/provider 作抽屉)。
2. **OCR → 可选 provider**(默认不装、截图输入才触发),移出核心依赖与主链路。
3. **云 TTS → 仅同步**,异步/批量/队列推 M2。
4. **`ffmpeg_card` 封顶**:静态帧+帧内字幕+concat+finalizer,禁动画/转场。
5. **MCP → M1 占位**(骨架+清单+not_implemented),M2 实现。

## M1 必补范围
1. **审批 artifact hash 绑定 + 失效回退**(A01)。
2. **移除 `--force`,预览走 `lj preview`**(A02)。
3. **`export --release` mock 硬失败码**(A03)。
4. **文件=真值、SQLite=派生索引 + reindex**(A04)。
5. **CI 禁止引擎 SDK import 进 core**(A07)。
6. **provider ABC + 契约测试**(A08)。
7. **TTS 逐段时长 ffprobe 实测 + 音画字 QA**(A20)。
8. **安全基线**(注入/路径穿越/命令注入/key 脱敏)(A28)。
9. **版本钉死**(Python/Node/uv/pnpm/lockfiles)(A27)。

## M2 / M3 / v2 推荐路线
- **M2**:MCP 22 工具落地 + SKILL/AGENTS/CLAUDE 完整 + HyperFrames adapter(子进程,富视觉/Agent 路径)+ Web 富交互(波形/逐幕重做/4 比例实时)+ 云 TTS 异步队列 + libass 烧录可选。
- **M3**:ASR(上传转写 + WhisperX 词级对齐)+ PaddleOCR + 本地 TTS(CosyVoice/IndexTTS/GPT-SoVITS,外部服务 + 克隆授权门禁)+ Remotion opt-in(license 门禁)+ 图像生成(原创插画)。
- **v2**:Tauri 桌面壳 + Motion Canvas/Manim 插件 + 任务队列/Postgres/Redis + 更多平台(视频号/快手/Reels)。

## 技术选型最终建议
- 后端/核心/CLI/providers/MCP:**Python**(3.11 或 3.12)。前端:**Next.js + TS + Tailwind + shadcn/ui**。存储:**SQLite(派生)+ 文件(真值)**。渲染地板:**自研 ffmpeg_card**。引擎扩展:**HyperFrames(M2)/Remotion(M3 opt-in)子进程**。LLM:**OpenAI-compatible + Anthropic**(不锁单一家)。TTS:**EdgeTTS(体验)+ 云 TTS(生产)**,本地(M3)。OCR:**RapidOCR(可选)**。URL:**trafilatura>=1.8(+Readability 备选)+ Playwright opt-in 截图**。

## 开源合规最终建议
- 主仓 **Apache-2.0**。**AGPL/GPL 项目(motion-director/LosslessCut/pyVideoTrans)禁入主仓,只学思想**。**Remotion 不默认/不捆绑,M3 opt-in + doctor 显著提示**。**不捆绑模型权重/字体**,本地模型外部服务,doctor 记录代码 license 与权重来源,发布包出 `license_manifest.md`。**URL 默认不下载他人视频**(不复制 VideoLingo 搬运/yt-dlp 模式)。**声音克隆(M3)默认关 + 授权确认**。FFmpeg 避非自由编码器并记录 build。

## 中国用户友好最终建议(最低交付标准)
1. 中文 UI/文档/错误提示优先;全程 UTF-8 + `pathlib`,**中文路径零报错**(e2e 覆盖)。
2. **中文字体不乱码**:doctor 探测系统 CJK,缺则下载 Noto Sans SC 到缓存;渲染帧内绘字。
3. 中文标点/断句/字幕短句化;抖音/小红书/B站表达的 preset 与文案模板。
4. **国内可达的模型路径**:OpenAI-compatible 支持自定义 base_url(DeepSeek/Qwen/Moonshot/Ollama/vLLM);TTS 支持国内云 TTS 配置位。
5. Windows 一键体验:`lj doctor --fix` 装 FFmpeg/字体/Playwright 的清晰指引;Docker Compose 备选。
6. 首启向导按"视频目标 + 平台"给智能默认,避免平台×语言×比例组合劝退。

## Agent 工具链最终建议
- **M1 的 Agent 能力靠 CLI 满足**:全命令 `--json` + 稳定错误码(`APPROVAL_REQUIRED`/`APPROVAL_STALE`/`MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`/`TTS_TIMEOUT` 等)+ generate 返回 `awaiting_review`。Claude Code/Codex 直接编排 CLI 即可,不必等 MCP。
- **M2 的 MCP**是 CLI/core 的薄封装(同一状态机),22 工具含 approve_*;SKILL.md 作路由器,明确"停下等人审、缺工具先 doctor、不下载他人视频、不绕门禁"。
- HyperFrames/Remotion 作为**外部 skill/CLI**由 Agent 在 M2/M3 调用,LingJian 只提供 adapter 与 doctor,不复制其 skill 文本。

---

## §9 的 16 个问题 · 逐条明确回答

1. **M1 是否进实现?** **Conditional Go**。先落 6 个 Blocker 硬约束(A01/02/03/04/07/11)。
2. **Conditional Go 先修哪 5–10 个?** 见"M1 必补范围"9 条,最优先前 6 个 Blocker。
3. **M1 还需砍什么(不损真实可用)?** 砍:富 motion、ASR、本地克隆、云 TTS 异步、MCP 实现、Web 8→5、OCR 降可选。均不在主链路,不损"真实可发布"。
4. **M1 还缺什么(不引爆复杂度)?** 缺机制而非功能:hash 绑定、release 判定、文件↔DB 真值、CI import guard、provider 契约、安全基线。都是约束,不增功能面。
5. **Web 做 8 页还是合并?** **合并为 5 页**(向导 / 提取+文案 / 语音 / 画面 / 渲染+发布+设置),保留全部人审路径。
6. **OCR 留 M1 还是可选?** **可选 provider**,默认不装,截图输入才触发。
7. **EdgeTTS+云 TTS 合理吗?替代?** 合理但需并列定位:EdgeTTS=零门槛体验(非官方/在线,doctor 标注),**云 TTS(OpenAI-compatible TTS)=生产推荐**。替代/备选:火山/阿里/腾讯/Minimax 云 TTS 作可配置 provider;本地 CosyVoice/IndexTTS 推 M3。
8. **五平台 preset 合理吗?** 合理,**前提是纯配置层、单渲染路径、代码无平台名 if**(A15)。
9. **3:4/4:3 保留吗?如何降复杂度?** 保留,用**四盒盒模型 + 每 ratio 参数**,9:16/16:9 手调、3:4/4:3 线性适配,不独立重设计。
10. **M1 的 MCP 占位还是实现?M2 如何承接?** **M1 占位**(骨架+22 工具名+not_implemented);M2 用 CLI/core 薄封装实现,状态机同源。
11. **`ffmpeg_card` 最小能力边界?** 静态卡片帧 + 帧内字幕 + 图片/截图摆放 + scene 硬切(可选 1 淡入淡出)+ concat + finalizer;**不做**动画/zoompan/转场/shader。不做成小 Remotion。
12. **QA 哪些 hard/warn/info?** hard:缺文件/不可播/分辨率≠preset/无音轨/音画字超阈/未处理占位符/release 含 mock;warn:响度越界/字幕越安全区/时长中等偏差/敏感信息疑似/风险词;info:source_map 覆盖率/字数。
13. **M1 GOAL 能否一次生成?否则拆几批?** 不建议一次;拆 **3 个真实增量批次**(见 08):Batch1 状态机+schemas+CLI+provider mock/doctor+approvals+hash;Batch2 真实 LLM/TTS+ffmpeg_card+QA+export(release/mock 判定);Batch3 Next.js 5 页+provider 配置+跨平台 polish+docs。**不退回 demo,不取消主干,门禁/release 判定/ffmpeg_card/canonical export 不推迟。**
14. **哪些第三方只能研究不能引入?为何?** motion-director/OpenMontage(AGPL)、LosslessCut(GPL-2.0)、pyVideoTrans(GPL 待确认)——copyleft 传染 Apache 主仓;VideoLingo——即便许可式,其"下载他人视频搬运"模式违 D5。
15. **哪些适合作 adapter?放 M 几?** HyperFrames→**M2**(富视觉,Apache,子进程);Remotion→**M3 opt-in**(license 门禁);CosyVoice/GPT-SoVITS/IndexTTS/FunASR/PaddleOCR→**M3**(外部服务 adapter,权重不捆绑)。
16. **中国用户友好最低交付标准?** 见"中国用户友好最终建议"6 条:中文 UI/路径零报错、中文字体不乱码、平台化 preset、国内模型可配、Windows 一键指引、智能默认向导。
