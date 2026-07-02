# 00 · 执行摘要(EXECUTIVE SUMMARY)

> 审计对象:LingJian Video Studio / 灵剪 Video Studio(M1 主干)
> 审计时间:2026-07-01
> 审计基准:本轮上传包内**仅含审计提示词本身**,未包含 `lingjian_video_studio_v1_M1_PRD_rebuilt.md` 与 `lingjian_video_studio_M1_FINAL_GOAL_rebuilt.md`。按提示词第 0/28 节要求,列为缺失文件、不中断,改以**上一轮已产出的可执行 PRD/GOAL**(`lingjian_video_studio_v1_PRD_executable.md`、`lingjian_video_studio_v1_GOAL_executable.md`)+ 本提示词固化决策 D1–D9 作为"当前方案事实"进行审计。

## 缺失文件清单(必须补齐后二次核对)
- ❌ `lingjian_video_studio_v1_M1_PRD_rebuilt.md`(未随包提供)
- ❌ `lingjian_video_studio_M1_FINAL_GOAL_rebuilt.md`(未随包提供)
- 说明:本报告的 PRD/GOAL patch(06/07)基于"可执行 PRD/GOAL"撰写。若你的 `_rebuilt` 版与其存在差异,需按 06/07 的 patch 语义在你的 `_rebuilt` 版上二次落地。

---

## 最终结论:**Conditional Go(有条件通过)**

一句话判断:**M1 方案架构正确、边界清晰、真实可用性目标成立,可以进入实现;但必须先把"审批-hash 绑定、mock/release 判定、ffmpeg_card 能力上限、真实 provider 异步失败处理"这 4 类机制从"文档承诺"落成"可验收的硬约束",并按 3 个真实增量批次交付,否则一次性生成会在门禁与渲染两处失败。**

它不是 No-Go(方向、选型、D1–D9 都站得住,且已消除上一轮的过度修正);也不是无条件 Go(有 6 个 Blocker 级机制若不先固化,AI 生成器会各自发挥、留下可绕过的门禁或伪成功的导出)。

---

## Top 10 必修问题(Blocker/High,进实现前)

1. **[Blocker] 审批与 artifact hash 绑定缺执行细节**:D3 要求"审批绑定 artifact hash、artifact 变更后自动失效",但没定义 hash 算法、覆盖哪些字段、失效后状态回退到哪。必须写死(见 04-A01、06)。
2. **[Blocker] `--force` 与 D3 冲突**:上一轮 PRD/GOAL 仍出现 `--force` 越权路径;D3 明确"不得提供 `--force` 绕过"。必须全仓移除 `--force`,渲染门禁只认 approvals(04-A02、07)。
3. **[Blocker] mock/release 判定无硬失败条件**:`export --release` 遇 mock provider 必须返回 `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`;需要在 provider 上打 `is_mock` 标志并在 export 层强校验(04-A03、07)。
4. **[Blocker] SQLite 与 project 文件双状态真值冲突**:必须钉死"文件 artifact = 唯一事实源,SQLite = 派生索引/缓存,可从文件重建";否则 CLI/Web/API/MCP 会读到不一致状态(04-A04、06)。
5. **[Blocker] `ffmpeg_card` 能力边界未封顶,有变成"小 Remotion"的风险**:必须显式列出 M1 只做静态卡片帧 + 帧内字幕 + concat + finalizer,**不做**逐帧动画/zoompan/转场特效(04-A11、05-Q11)。
6. **[Blocker] 隐藏 import 风险(D1)**:必须加一条 CI 静态检查,禁止 Python 业务核心 import HyperFrames/Remotion/Playwright SDK;引擎只能经 subprocess(04-A08、07)。
7. **[High] 云 TTS 异步/失败/重试复杂度会拖垮 M1**:M1 只需**同步阻塞式** TTS + 明确超时/错误码 + 不伪造成功;异步队列推 M2(04-A17、05-Q7)。
8. **[High] OCR 是否属于 M1 主干存疑**:文本→TTS→视频主链路不依赖 OCR;OCR 应降为**可选 provider**(默认关,截图输入才触发),不阻塞主干(04-A19、05-Q6)。
9. **[High] `hyperframes-motion-director` = AGPL-3.0(待联网确认,强证据)**:同类"agentic video"项目(OpenMontage 已确认 AGPL-3.0)普遍 AGPL;只能学流程思想,禁止复制其 prompt/template/script/UI 进 Apache 主仓(01-合规红线、04-A25)。
10. **[High] Web 8 页会拖慢 M1**:建议合并为 **5 页**保留完整人审路径(向导/提取+文案二合一可选、语音、画面、渲染+发布二合一、doctor/provider),不砍人审(04-A22、05-Q5)。

## Top 10 保留决策(不动)

1. D1 语言边界(Python core + Next.js console + 子进程引擎)——彻底消除 polyglot 歧义,保留。
2. D2 渲染地板 = 自研 `ffmpeg_card`——可靠性正确,保留。
3. D3 系统层三审门禁——产品核心价值,保留(仅补 hash 绑定 + 删 `--force`)。
4. D4 不捆绑权重/字体,本地大模型走外部 adapter——合规正确,保留。
5. D5 合规边界(Remotion 不默认、克隆需授权、URL 不下载他人视频)——保留。
6. D6 分阶段(M1 纵向主干,不做全宽度)——保留,是可交付性的前提。
7. D7 mock 仅测试/预览、release 禁 mock——保留(补硬失败码)。
8. D8 Apache-2.0 主仓——保留。
9. artifact-first 单一事实源——保留(补文件↔DB 真值优先级)。
10. 五平台"只做配置层、不分叉渲染路径"——保留,是控制复杂度的关键。

---

## M1 最小真实可用主干

`init → ingest(text/url/image) → extract → script → approve → voice → approve → visuals → approve → render(ffmpeg_card) → qa → export`,加:Agent 级 CLI(全 `--json` + 三审动词)、doctor(FFmpeg/字体/Playwright/provider/Remotion 提示/trafilatura 版本)、真实 LLM(OpenAI-compatible + Anthropic)、真实 TTS(EdgeTTS + 一个云 TTS 的**真实 adapter 接口**,若无法真跑则明确报错不伪造)、RapidOCR(**可选**)、trafilatura(+Playwright opt-in)、五平台 preset(纯配置)、zh/en、9:16/16:9 一等 + 3:4/4:3 layout compiler、canonical export、QA 分级(hard fail/warning/info)。Web 建议 5 页保留人审。

## M2 / M3 / v2 边界

- **M2**:MCP server(22 工具落地)+ SKILL/AGENTS/CLAUDE 完整 + HyperFrames adapter(富视觉)+ Web 富交互(波形/逐幕重做)+ 云 TTS 异步队列。
- **M3**:ASR(上传转写 + WhisperX 词级对齐)+ PaddleOCR + 本地 TTS(CosyVoice/IndexTTS/GPT-SoVITS,外部服务 + 克隆授权门禁)+ Remotion opt-in adapter + 图像生成。
- **v2**:Tauri 桌面壳 + Motion Canvas/Manim 插件 + 任务队列/Postgres/Redis + 更多平台。

---

## 三大风险

- **最大技术风险**:`ffmpeg_card` 与三审门禁两处的"确定性 + 状态一致性"。若渲染引入非确定性(时间戳/字体/并发)或门禁可被绕过/hash 不失效,则"可审、可复跑"卖点崩塌。缓解:冻结渲染 recipe + hash 绑定 + CI 快照测试。
- **最大合规风险**:AGPL/GPL 传染 + 他人视频版权 + 模型权重许可。`hyperframes-motion-director`(AGPL,待确认)、LosslessCut(GPL-2.0 已确认)、pyVideoTrans(GPL 强先验)、VideoLingo(自称"视频搬运"+yt-dlp)——只能学思想。权重(CosyVoice/GPT-SoVITS/IndexTTS)代码宽松但权重条款独立。缓解:AGPL/GPL 禁入主仓 + URL 默认不下载视频 + 不捆绑权重 + doctor 记录 license。
- **最大 Agent 交付风险**:一次性生成 M1 全量(core+CLI+API+Web+真实 provider+渲染+QA+export)超出单次可靠上限;且 provider 接口若不够刚性,生成器会自由发挥出不一致的 adapter。缓解:3 个真实增量批次(见 08)+ provider 生命周期接口写死 + 契约测试。

## 下一步建议

先补齐两份缺失 `_rebuilt` 文档并按 06/07 打 patch → 用 04 的 25 条对照修复(重点 6 个 Blocker)→ 按 08 的 Batch 1/2/3 顺序实现,每批用 08 的验收命令卡住"伪成功"。**不退回 demo,不取消 M1 主干,不把门禁/release 判定/ffmpeg_card/canonical export 推迟到 M2。**
