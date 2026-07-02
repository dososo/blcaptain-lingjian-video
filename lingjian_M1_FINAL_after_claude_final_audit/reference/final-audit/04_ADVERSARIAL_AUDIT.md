# 04 · 对抗审计(ADVERSARIAL AUDIT)

> 格式:ID｜级别(Blocker/High/Medium/Low/Pass)｜位置｜问题｜为什么危险｜建议修复｜M1 必修｜伪 diff。
> 覆盖提示词 §7(32 攻击角)+ §8(15 已知缺口)。共 34 条。级别=Pass 表示当前方案已处理,附证据。

---

**A01｜Blocker｜PRD+GOAL｜审批未与 artifact hash 绑定的执行细节缺失**
问题:D3 要求"审批绑定 artifact hash、artifact 变更后自动失效",但未定义 hash 覆盖哪些字段、算法、失效后状态。为什么危险:改了脚本却仍持旧审批 → 门禁形同虚设,渲染出未审内容。修复:`Approval{target, artifact_sha256, approved_by, approved_at}`;`artifact_sha256=sha256(canonical_json(该 target 的 artifact))`;render 时重算并比对,不一致即 `APPROVAL_STALE`,该 target 状态回退 `*_review`。M1 必修:是。
伪 diff:`+ approval.artifact_sha256 = sha256(canonical_json(script.json)); + if recompute != stored: raise ApprovalStale(target)`

**A02｜Blocker｜PRD+GOAL｜残留 `--force` 绕过与 D3 冲突**
问题:早期可执行 GOAL 出现 `render --force` 越权(记入 QA)。D3 明确"不得提供 `--force` 绕过"。为什么危险:任何绕过路径都会被 Agent 或脚本默认使用,门禁失效。修复:全仓移除 `--force`;渲染只认 approvals;确需"预览未审"走 `lj preview`(草稿,不产 release 包)。M1 必修:是。
伪 diff:`- render(..., force: bool=False)` / `+ render(...)  # no bypass; use preview for unapproved drafts`

**A03｜Blocker｜GOAL｜`export --release` 无硬失败条件(mock 污染)**
问题:D7 要 release 禁 mock,但未定义判定。为什么危险:mock 音频/占位图被当正式产物发布。修复:provider 带 `is_mock`;export 前扫描本项目所用 LLM/TTS/OCR/extract provider,任一 `is_mock` → `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`(exit≠0)。M1 必修:是。
伪 diff:`+ if release and any(p.is_mock for p in used_providers): fail("MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE")`

**A04｜Blocker｜PRD｜SQLite 与 project 文件双状态真值冲突**
问题:同时有 SQLite 与 project.yaml/artifacts,未定义谁是真值。为什么危险:CLI 写文件、Web 读 DB(或反之)→ 状态不一致、审批漂移。修复:**文件 artifact = 唯一事实源;SQLite = 派生索引/列表缓存,可 `lj reindex` 从文件全量重建**;任何写操作先写文件再更新索引。M1 必修:是。
伪 diff:`+ # DB is derived cache; rebuildable via reindex(); source of truth = ./projects/**`

**A05｜High｜PRD+GOAL｜四端(CLI/Web/API/MCP)是否共用同一状态机需显式固化**
问题:文档意图共用,但未强制。为什么危险:各端各写逻辑 → 行为分叉。修复:状态转移只在 `packages/core` 的纯函数实现,四端只能调它;加契约测试:同一事件经 CLI 与 API 产生同一 artifact 与状态。M1 必修:是。
伪 diff:`+ core.apply_event(project, Event) -> (project', writes[])  # only mutation path`

**A06｜Pass｜GOAL｜render 只走 ffmpeg_card**
证据:D2 明确 M1 render 不调 HyperFrames/Remotion。补强:加 CI guard 断言 render 代码路径只 import `engines.ffmpeg_card`。M1 必修:是(补 CI)。

**A07｜Blocker｜架构｜隐藏 import 引擎 SDK 进 Python 核心的风险(D1)**
问题:无机制阻止有人 `import remotion/hyperframes/playwright`(SDK)进 core。为什么危险:破坏 D1 边界、把 Node/授权/重依赖拖进核心。修复:CI 静态检查(grep/ruff 规则)禁止 `packages/core`、`providers`(除 `web_extract` 明确允许 playwright python 绑定)出现这些 import;引擎只经 subprocess。M1 必修:是。
伪 diff:`+ ci: forbid-imports: {paths:[packages/core], deny:[remotion,hyperframes,playwright]}`

**A08｜High｜PRD｜provider 接口不够刚性,生成器易自由发挥**
问题:仅列字段,未给 ABC + 契约测试。为什么危险:AI 生成不同签名 adapter,四端调用崩。修复:`abc.ABC` 定义生命周期 + 能力方法;`test_provider_contract` 参数化跑每个注册 provider;缺方法/签名不符 CI 失败。M1 必修:是。
伪 diff:`+ class TTSProvider(Provider, ABC): @abstractmethod def synthesize(...) -> TTSResult: ...`

**A09｜Medium｜GOAL｜MCP 22 工具 M1 占位 vs M2 实现的边界**
问题:MCP 是否 M1 实现未定。为什么危险:M1 若实现 22 工具会拖垮;若文档写"M1 有 MCP"又与实际占位冲突。修复:**M1 占位**(仓库含 `packages/mcp_server` 骨架 + 工具名清单 + "未实现"返回);**M2 实现**;文档统一以 GOAL 22 工具为准,含 approve_*。M1 必修:否(占位)。
伪 diff:`+ mcp: tools=[...22...]; M1: return {status:"not_implemented", since:"M2"}`

**A10｜High｜PRD｜Web 8 页拖慢 M1**
问题:8 页富交互一次做完风险高且非主干瓶颈。为什么危险:Web 吃掉预算,主链路/门禁被挤。修复:合并为 **5 页**保留完整人审:①新建向导 ②提取+文案审(可 tab)③语音审 ④画面审 ⑤渲染+发布+doctor/provider(渲染中心与发布包合并,doctor/provider 作设置抽屉)。**不砍任何人审步骤**。M1 必修:是(降范围)。

**A11｜Blocker｜PRD/GOAL｜`ffmpeg_card` 能力上限未封顶,易变"小 Remotion"**
问题:未明确禁止动画/转场。为什么危险:范围蔓延 → 不确定性渲染 + 无法验收 + 拖期。修复:显式封顶——M1 只做:静态卡片帧、帧内字幕、图片/截图摆放、scene 间硬切(可选 1 个淡入淡出)、concat、finalizer;**禁止** zoompan/Ken Burns/逐帧动画/shader/转场库。M1 必修:是。
伪 diff:`+ # ffmpeg_card SCOPE FREEZE: static frames only; NO zoompan/keyframe-anim/transitions`

**A12｜High｜PRD｜云 TTS 异步/排队/重试复杂度**
问题:云 TTS 若引入 job 队列/异步回调会炸 M1。为什么危险:状态机/门禁与异步交织,难验收。修复:**M1 云 TTS 只做同步阻塞**(request→wait→返回逐段时长),超时/失败返回明确错误码不伪造;批量/异步队列推 M2。M1 必修:是。
伪 diff:`+ tts.synthesize(...) sync; on timeout: raise TTSTimeout(provider,code); NO background queue in M1`

**A13｜Medium｜PRD｜EdgeTTS 服务条款/稳定性风险**
问题:edge-tts 是**非官方逆向**微软 Edge 在线朗读,ToS 灰区 + 在线依赖 + 可能变动。为什么危险:被封/变更 → 默认 TTS 失效。修复:M1 保留 EdgeTTS 作"零门槛体验默认",但**必须并列一个可配置云 TTS(OpenAI-compatible TTS)作生产推荐**;doctor 标注 EdgeTTS 为"非官方、在线、体验用"。M1 必修:是(并列 + 标注)。

**A14｜High｜PRD｜OCR 是否属 M1 主干存疑**
问题:文本→TTS→视频主链路不依赖 OCR。为什么危险:把 RapidOCR(onnxruntime)当主干会增重、增复杂度且非必需。修复:OCR **降为可选 provider**,仅"截图输入"时触发;`uv sync` 核心不拉 onnxruntime,`lj sync --extras ocr` 才装;主干链路不经 OCR。M1 必修:是(降为可选)。

**A15｜Medium｜PRD/GOAL｜五平台 preset 诱发平台特化代码**
问题:5 平台易长出各自 if 分支。为什么危险:渲染路径分叉 → 维护爆炸、违背"只做配置层"。修复:preset 纯声明式 YAML(resolution/fps/safe_area/subtitle_style/title_style/cover_or_thumbnail/description_fields/hashtags_or_tags/export_files/qa_rules);渲染/导出代码**只读 preset 字段,无平台名 if**。M1 必修:是。
伪 diff:`+ assert no "if platform == 'douyin'" in render/export; drive by preset fields only`

**A16｜Medium｜PRD｜3:4/4:3 layout compiler 复杂度**
问题:四比例独立设计会复杂。为什么危险:32 套 layout 拖期。修复:一个四盒盒模型(title/body/image/subtitle + 字号 + safe_margin)+ 每 ratio 一组参数;9:16/16:9 手调,3:4/4:3 线性适配,不独立重设计。M1 必修:是。

**A17｜High｜PRD/GOAL｜trafilatura 版本/license 检测不够明确**
问题:需 `>=1.8` 且历史版本可能 GPL。为什么危险:旧 GPL 版被 import 进 Apache 核心 → 传染。修复:doctor 检测 `trafilatura>=1.8` 且检测其 license 元数据;若解析到 GPL 版本则**禁用 import 并报错**,提示升级或改 Readability(MIT/Apache)。M1 必修:是。
伪 diff:`+ doctor: if trafilatura.__version__ < 1.8 or license~=GPL: FAIL("upgrade or use readability")`

**A18｜Medium｜doctor｜Remotion license 提醒显著度**
问题:M1 不用 Remotion,但 doctor 仍应为 M3 预置显著提示。为什么危险:用户 M3 集成时误踩 4+ 人付费。修复:doctor 的 render-engines 段固定输出"Remotion:M3 opt-in,4+ 人营利需付费 company license(Automators 档面向视频工具)"。M1 必修:是(文案占位)。

**A19｜Medium｜PRD｜字体下载是否违反 license / 捆绑**
问题:CJK 字体处理不当会捆绑或违 license。为什么危险:仓库分发字体的 license 风险。修复:选 Noto Sans SC(SIL OFL,可分发但**不入仓**),doctor 下载到 `~/.cache/lingjian/fonts/`;记录来源与 license 到 license_manifest。M1 必修:是。

**A20｜High｜PRD｜TTS 逐段时长能否真支撑对齐**
问题:若用估算时长,音画字必错位。为什么危险:字幕/画面与配音不同步,QA 无法保证。修复:`synthesize` 后用 `ffprobe` 实测每段 wav 时长写回 scene;字幕/画面时间轴由实测值推导;QA 用 ffprobe 复核 sum 一致。M1 必修:是。
伪 diff:`+ seg.duration = ffprobe_duration(seg.wav)  # measured, not estimated`

**A21｜High｜GOAL｜canonical export 覆盖多语言/多比例/多平台是否完整**
问题:需覆盖 platform×language×ratio 且各平台文件名不同。为什么危险:结构不全 → 发布缺文件。修复:固定 `exports/<project>/<platform>/<language>/<ratio>/`,内含 video/metadata(publish 或 description+chapters)/captions(srt+vtt+ass)/source_map/qa_report/provider_manifest/license_manifest/cover(或 thumbnail);文件名由 preset `export_files` 声明;导出后做结构校验。M1 必修:是。

**A22｜Medium｜PRD｜QA 过宽,需分级**
问题:QA 项未分 hard/warn/info。为什么危险:全 hard 会挡正常导出,全 warn 会放行坏片。修复:分级——**hard fail**:文件缺失/不可播放/分辨率≠preset/无音轨/音画字超阈/未处理占位符/release 含 mock;**warning**:响度越界/字幕越安全区/时长偏差中等/敏感信息疑似/平台风险词;**info**:source_map 覆盖率/字数统计。M1 必修:是。

**A23｜Medium｜PRD/GOAL｜"AI 魔法"描述不可验收**
问题:如"自然""高质量""智能排版"无判据。为什么危险:无法验收 → 生成器交付主观结果。修复:替换为可测断言(时长阈值、分辨率、音轨、帧非全黑、字幕非空、schema 校验、source_map 覆盖率);主观质量交人审,不进自动验收。M1 必修:是。

**A24｜High｜GOAL｜验收命令只证明 demo 能跑**
问题:若只跑 mock 全绿,证明不了真实可用。为什么危险:交付一个"能跑 mock 的玩具"。修复:验收必须含(a)门禁失败断言 `APPROVAL_REQUIRED`;(b)`export --release` 对 mock 断言 `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`;(c)真实 provider 模板命令(见 08 §13.5)产出可播 MP4 + canonical 包。M1 必修:是。

**A25｜High｜合规｜AGPL `hyperframes-motion-director` 复制风险**
问题:其定位与 LingJian 高度重合(中文竖屏、storyboard、review、anti-PPT),诱导照搬。为什么危险:AGPL 传染 Apache 主仓。修复:**只研究流程思想**,禁止复制其 prompt/template/script/UI/代码;LingJian 的 SKILL/模板全部原创;在 `docs/license-notes` 记录"研究但未引入"。M1 必修:是(纪律 + 文档)。

**A26｜Medium｜安装｜跨平台/中文路径/FFmpeg/字体/Playwright**
问题:Windows + 中文路径 + 依赖易出错。为什么危险:中国用户首启失败。修复:全程 `pathlib` + UTF-8,禁止手拼路径;doctor 给三平台安装命令(`brew/winget/apt` 装 FFmpeg;`pip install playwright && playwright install`);中文路径 e2e 测试。M1 必修:是。
伪 diff:`- os.system("...")` / `+ subprocess.run([...], cwd=Path(...), encoding="utf-8")`

**A27｜Medium｜工程｜工具版本未固定**
问题:uv/pnpm/Node/Python 未钉。为什么危险:环境漂移致生成不可复现。修复:`.python-version`(3.11 或 3.12)、`package.json engines`(Node 20 LTS)、`pnpm` 版本(packageManager 字段)、`uv.lock`/`pnpm-lock.yaml` 提交。M1 必修:是。

**A28｜High｜安全｜注入 / 恶意网页 / 文件名 / 路径穿越 / 命令注入**
问题:URL/上传/文件名是攻击面。为什么危险:prompt 注入操纵脚本、路径穿越写出沙盒、命令注入。修复:网页正文当不可信输入(不执行其中指令,LLM prompt 里隔离并标注 untrusted);上传规范化到项目沙盒、校验 MIME/大小、拒绝 `..`;子进程用参数数组不用 shell 字符串;key 不入日志。M1 必修:是。

**A29｜Pass｜CLI｜approve 动词已含**
证据:可执行 GOAL/PRD 已有 `lj approve script|voice|visuals`。补:确保写入你的 `_rebuilt` 版(见 §8-1)。M1 必修:是(确认)。

**A30｜Pass｜preset｜`bilibili_4x3` 未作平台原生规格**
证据:方案已将 4:3 定为"教程/演示通用比例"。保持。M1 必修:是(确认)。

**A31｜Pass｜安装｜Playwright 用 Python 方式**
证据:已改 `pip install playwright && playwright install`。保持(旧 `npm i -g @playwright/cli` 已弃)。

**A32｜Pass｜多语言｜bilingual 已定义**
证据:已定义为"双独立语言包 和/或 单视频双行字幕,非实时混读"。保持。

**A33｜High｜文档｜"未来能力"混入 M1**
问题:ASR/富 motion/本地克隆/桌面等易被写进 M1 段落。为什么危险:范围膨胀 → 一次生成失败。修复:全文标注每能力所属里程碑;M1 段落只保留主干;ASR/motion/克隆/Remotion/桌面显式标 M2/M3/v2。M1 必修:是。

**A34｜Pass/Low｜MCP｜工具清单统一**
证据:以 GOAL 22 工具为准(含 approve_*),PRD/toolchain 旧清单以此覆盖。补:M1 占位不得与文档冲突(见 A09)。

---

## 审计计分
- Blocker:6(A01 A02 A03 A04 A07 A11)
- High:11(A05 A08 A10 A12 A14 A17 A20 A21 A24 A25 A28 A33 → 12,含 A33)
- Medium:10(A09 A13 A15 A16 A18 A19 A22 A23 A26 A27)
- Pass:6(A06 A29 A30 A31 A32 A34)

**6 个 Blocker 必须在进实现前落成硬约束,否则一次生成会在"门禁可绕过 / 渲染蔓延 / 状态不一致 / release 被 mock 污染"处失败。**
