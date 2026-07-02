# 02 · PRD/GOAL 精修(最终版)· 对已验收基线的 10 项加固

> 对象:`base/LINGJIAN_M1_PRD_ACCEPTED_BASE.md` 与 `base/LINGJIAN_M1_GOAL_ACCEPTED_BASE.md`(ChatGPT 版,已由我验收)。
> 这 10 项是我对**它的文档**做对抗审计后仍发现的真实缺口/可加固点。**这些精修相对基线优先生效**;Codex 实现时以"基线 + 本精修"为准。
> 每项:问题｜为什么危险｜精修(伪 diff / 规则)｜优先级(P0 进实现前 / P1 M1 内)｜归入 Batch。

---

**R1｜渲染产物 preview/release 物理隔离(把 A03 下沉到 render 层)**
问题:基线在 export 层扫描 mock(A03),但 render 产物 preview 与 release 未物理隔离,§19.2 出现"render 成功,产出 preview/output MP4"的措辞模糊——mock 渲染的 MP4 可能被误当/误拷进 release。
危险:一条 mock 预览片被打进正式发布包,绕过"release 禁 mock"的初衷。
精修:render 产物按模式分目录并带来源标记——`renders/preview/`(允许 mock,产物内嵌/命名标 preview)vs `renders/release/`(仅真实 provider)。新增 `render_manifest.json{mode: preview|release, providers[]}`。export 组包只能引用 `renders/release/` 的产物;引用 preview 产物即失败 `PREVIEW_ARTIFACT_NOT_RELEASABLE`。
优先级:P0。Batch:2。

**R2｜`extract` 的 provider 语义歧义**
问题:基线 §19.4 用 `lj extract --provider mock`,§19.5 用 `--provider local`,但 extract 对 text 无需 provider、对 url 是 trafilatura、对 image 是 OCR——单一 `--provider` 指代不清。
危险:Codex 会实现出一个含糊的"extract provider",与实际按资产类型路由冲突,四端行为分叉。
精修:extract **按资产类型自动路由**;如需覆盖,用**分类型参数**:`--url-extractor trafilatura|playwright`、`--ocr-provider rapidocr|none`;text 直通无 provider。OCR extras 缺失时:该图跳过 OCR + warn,不使整个 extract 失败。统一 §19 示例命令去除裸 `--provider mock|local`。
优先级:P1。Batch:2(接口)/1(占位)。

**R3｜artifact 版本化 / history(让"可审、可复跑"落到实处)**
问题:基线各步 overwrite 当前 artifact(如 §19.2 stale 测试直接重跑 `lj script` 覆盖 script.json),无历史快照。
危险:审核失效时无法回答"改了什么导致失效",无法回退——与产品核心卖点"可审核·可复跑·可归档"相悖。
精修:每步写当前 artifact 时,若覆盖已存在版本,先把旧版快照到 `history/<step>/<ISO8601>.json`;`approvals.json` 记录审批指向的 hash(已含),使"审批 vs 当前"可 diff。新增 `lj diff <step> [--from hash --to hash]`(可 M2 增强,M1 至少保留 history 落盘)。
优先级:P1。Batch:1(history 落盘)/。

**R4｜`ffmpeg_card` 快照测试的确定性容差**
问题:基线要求"像素/结构快照"(§24.2),但 Pillow/freetype/OS 差异会让逐像素快照跨环境闪断。
危险:CI 假失败 → 团队对"门禁/快照"失去信任 → 绕过测试。
精修:钉死渲染确定性依赖(字体文件版本 + Pillow/freetype 版本);快照断言用**容差**(SSIM ≥ 阈值 或 分区结构 hash),而非逐字节相等;核心断言改为可判定项——"字幕区非空 + 各布局盒坐标正确 + 分辨率==preset + 帧非全黑"。
优先级:P1。Batch:2。

**R5｜真实 provider 错误分类学(超出 timeout)**
问题:基线错误码有 `TTS_TIMEOUT` 等,但缺限流/配额/鉴权/JSON 修复失败等真实高频错误。
危险:真实 LLM/TTS 一接就碎且错误不可解释,Agent 无法据错重试或提示用户。
精修:补稳定错误码 `LLM_RATE_LIMITED`、`TTS_RATE_LIMITED`、`PROVIDER_QUOTA_EXCEEDED`、`PROVIDER_AUTH_FAILED`、`LLM_INVALID_JSON`(重试后仍失败→回退确定性骨架或明确失败)。M1 同步、不做无限重试;`provider_manifest` 记录 token/char 用量供**透明**(不计费)。
优先级:P1。Batch:2。

**R6｜状态机的"导出后再编辑"回环显性化**
问题:基线状态列看似线性,终态 `exported_preview/exported_release`;失效表隐含可回流但未显式说明"导出后改稿→重渲染→重导出"。
危险:Codex 可能实现成一次性线性流,用户改一版就卡住。
精修:状态机显式为**可循环**:从任意 `exported_*` 编辑任一 artifact → 回到对应 `*_review` 且下游 stale → 允许重渲染/重导出。文档补一句"导出不是终态,是可回环节点"。
优先级:P1。Batch:1。

**R7｜审批 provenance 传播到发布包**
问题:基线 `Approval` 有 who/hash/when,但未要求把三审 provenance 写进导出包。
危险:团队场景无法在交付物里追溯"谁在哪个版本批准了什么"。
精修:`export_manifest.json` 增 `approvals: [{target, approved_by, artifact_sha256, approved_at}]`;release 包据此可审计。
优先级:P1。Batch:2。

**R8｜稀薄/退化输入的最小可用校验**
问题:基线未定义输入过薄(URL 正文<阈值 / OCR 空 / 粘贴 5 个字)时的行为。
危险:产出 3 秒垃圾视频或崩溃,"真实可用"破功。
精修:extract/script 前置最小输入校验(正文字数下限、可用素材下限);不足→warn + 引导补充(而非 hard 崩溃或硬造内容);脚本阶段若素材不足以支撑目标时长,提示缩短或补料。
优先级:P1。Batch:2。

**R9｜中文字幕断行规则(帧内字幕质量)**
问题:基线"字幕画进帧"未定义 CJK 断行,直接决定"能看"。
危险:中文按 Latin 规则断行、单行过长、超安全区 → 观感差。
精修:layout compiler 内置 CJK 断行——中文逐字换行、Latin 不词中断;每行最大字数按 ratio 定;最多 2 行;超长自动分镜或缩写并给 warn。纳入 §19 视觉验收断言。
优先级:P1。Batch:2。

**R10｜`lj doctor` 的 Agent 判定语义**
问题:基线 doctor 输出状态,但未定义"总体是否就绪"与退出码语义。
危险:Agent 无法据 doctor 结果 gate(把可选缺失当致命,或反之)。
精修:`lj doctor --json` 返回 `{ready: bool, required: [...], optional: [...]}`;**required 缺失(FFmpeg、CJK 字体)→ 退出码≠0**;仅 optional 缺失(OCR extras、Playwright、真实 key)→ 退出码 0 + warn。Agent 以 `ready` 与退出码 gate。
优先级:P0。Batch:1。

---

## 汇总:进实现前必落(P0)= R1、R10;M1 内必落(P1)= R2–R9。全部归入既有 Batch,不新增里程碑、不降低 M1。
