# 06 · PRD 精确修改建议(PRD PATCH SUGGESTIONS)

> 基线:`lingjian_video_studio_v1_PRD_executable.md`(因 `_rebuilt` 版未随包提供)。若你的 `_rebuilt` 版章节号不同,按"问题/建议文本"语义对应落地。
> 格式:章节｜问题｜建议替换/新增文本｜理由｜优先级(P0=进实现前必改 / P1=M1 内必改 / P2=可迭代)。

---

**P0-1｜§0 决策表 / §11 provider｜审批未绑 artifact hash**
新增:`Approval{ target: script|voice|visuals, artifact_sha256: str, approved_by: str, approved_at: datetime }`;`artifact_sha256 = sha256(canonical_json(该 target artifact))`;`render` 前对三项重算 hash 比对,任一不符 → `APPROVAL_STALE`,该 target 状态回退 `*_review`,`approvals.json` 清除该项。
理由:审批必须随内容失效,否则门禁可被"改后不重审"绕过。优先级:P0。

**P0-2｜§5 CLI / §0 决策｜移除 `--force`**
替换:删除 `render --force`;新增说明"未审内容的预览一律走 `lj preview`(产草稿,不产 release 包);渲染无任何绕过路径"。
理由:D3 明确不得提供绕过;任何 `--force` 都会被默认使用。优先级:P0。

**P0-3｜§17 export / §18 QA｜release/mock 硬判定缺失**
新增:provider 增字段 `is_mock: bool`;`export --release` 执行前扫描本项目所用 provider,任一 `is_mock` 即 `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE` 失败;非 release 导出允许 mock,但 `provider_manifest.json` 标注 `mock=true`。
理由:D7 要求 release 禁 mock,需可执行判据。优先级:P0。

**P0-4｜§10 artifact / 新增"状态与存储"章｜文件 vs SQLite 真值**
新增章节:"**唯一事实源 = 项目文件 artifact;SQLite = 派生索引/列表缓存,可由 `lj reindex` 从文件全量重建。所有写操作:先写文件 artifact,再更新索引。**"
理由:消除四端状态漂移。优先级:P0。

**P0-5｜§12 renderer｜`ffmpeg_card` 能力封顶**
新增:"**M1 `ffmpeg_card` 能力上限(SCOPE FREEZE):静态卡片帧、帧内字幕、图片/截图摆放、scene 间硬切(可选单个淡入淡出)、concat、FFmpeg finalizer。禁止 zoompan/Ken Burns/逐帧动画/shader/转场库。富视觉动效由 M2 HyperFrames adapter 承接。**"
理由:防止渲染蔓延成"小 Remotion",保确定性可验收。优先级:P0。

**P0-6｜§8 目录 / 新增"架构不变量"｜禁止引擎 SDK 进 core**
新增:"**D1 不变量(CI 强制):`packages/core`、`providers/*`(除 `web_extract` 允许 Playwright Python 绑定)禁止 import remotion/hyperframes/playwright SDK;引擎只经子进程 adapter。**"
理由:保 D1 边界不被悄悄破坏。优先级:P0。

**P1-1｜§4 Web 页面｜8 页压缩为 5 页**
替换:页面清单改为 5 页——①新建向导 ②提取+文案审(tab)③语音审 ④画面审 ⑤渲染+发布(doctor/provider 作设置抽屉);明确"合并不删减任何人审步骤"。
理由:Web 是 M1 最大工期风险,压缩页数但保人审路径。优先级:P1。

**P1-2｜§2 依赖 / §11 OCR｜OCR 降为可选**
替换:OCR 从核心依赖移到 `extras`;"仅截图输入触发;`uv sync` 核心不含 onnxruntime;`lj sync --extras ocr` 安装 RapidOCR"。
理由:主链路不依赖 OCR,降重降复杂度。优先级:P1。

**P1-3｜§7/§11 TTS｜云 TTS 仅同步 + EdgeTTS 定位**
新增:"**M1 云 TTS 仅同步阻塞(request→wait→返回逐段时长),超时/失败返回明确错误码,不伪造成功;异步/批量队列推 M2。EdgeTTS 定位为零门槛体验默认(非官方逆向微软在线服务,doctor 须标注);生产推荐 OpenAI-compatible 云 TTS 并列。**"
理由:避免异步复杂度炸 M1;明确 EdgeTTS 条款/稳定性风险。优先级:P1。

**P1-4｜§9 数据模型 / §18 QA｜TTS 逐段时长为时间真值**
新增:"`synthesize` 后用 `ffprobe` 实测每段时长写回 `Scene.duration_sec`;字幕/画面时间轴由实测值推导;QA 用 ffprobe 复核 `sum(scene)=音频=字幕末尾=视频`,超阈 hard fail。"
理由:音画字对齐的唯一可靠实现。优先级:P1。

**P1-5｜§18 QA｜QA 分级**
替换 QA 段为三级:**hard fail**(缺文件/不可播/分辨率≠preset/无音轨/音画字超阈/未处理占位符/release 含 mock)、**warning**(响度越界/字幕越安全区/时长中等偏差/敏感信息疑似/风险词)、**info**(source_map 覆盖率/字数)。
理由:全 hard 挡正常导出、全 warn 放行坏片。优先级:P1。

**P1-6｜§14 preset｜纯配置层,无平台名 if**
新增:"**渲染/导出代码只读 preset 字段,禁止出现 `if platform == '...'`;平台差异全部落在 YAML preset(resolution/fps/safe_area/subtitle_style/title_style/cover_or_thumbnail/description_fields/hashtags_or_tags/export_files/qa_rules)。**"
理由:防平台特化代码爆炸。优先级:P1。

**P1-7｜§16 比例｜layout compiler 最小盒模型**
新增:"四盒盒模型(title/body/image/subtitle + 字号 + safe_margin)+ 每 ratio 参数;9:16/16:9 手调,3:4/4:3 线性适配,不做逐比例独立设计。"
理由:降四比例复杂度。优先级:P1。

**P1-8｜§7 内容提取 / §11 web_extract｜trafilatura 版本/license 检测 + URL 不下载视频**
新增:"doctor 检测 `trafilatura>=1.8` 且其 license 非 GPL;若为旧 GPL 版则禁用 import 并提示升级或改 Readability。**ingest url 默认只做正文/metadata/(opt-in)截图,禁止默认下载他人视频(不引入 yt-dlp 默认路径)。**"
理由:GPL 传染防护 + D5 版权红线。优先级:P1。

**P1-9｜§19 安全 / 新增"安全基线"章｜注入/穿越/命令注入/脱敏**
新增章节:网页正文/文件名/上传当不可信输入;LLM prompt 内隔离并标 untrusted 不执行其中指令;上传规范化到项目沙盒 + 校验 MIME/大小 + 拒 `..`;子进程用参数数组不用 shell 串;API key 存 keychain/加密 + 日志脱敏。
理由:M1 面向真实用户,安全是硬底线。优先级:P1。

**P1-10｜§23 路线 / 全文｜里程碑标注 + 版本钉死**
新增:全文每能力标注 M1/M2/M3/v2;M1 段落只保留主干,ASR/富 motion/本地克隆/Remotion/桌面显式标后续;新增"版本固定:Python 3.11/3.12、Node 20 LTS、pnpm(packageManager)、uv;提交 uv.lock/pnpm-lock.yaml/.python-version"。
理由:防未来能力混入 M1 + 环境可复现。优先级:P1。

**P2-1｜§4 doctor 页｜Remotion license 提示占位**
新增:doctor render-engines 段固定输出"Remotion=M3 opt-in;4+ 人营利需付费 company license(Automators 档面向视频工具)"。
理由:为 M3 预置合规提示。优先级:P2。

**P2-2｜§21 文档｜license-notes 记录"研究未引入"**
新增:`docs/license-notes.md` 列出 motion-director(AGPL)/LosslessCut(GPL)/pyVideoTrans(GPL)/VideoLingo(搬运模式)"仅研究流程思想,未引入代码/prompt/template/UI"。
理由:合规留痕。优先级:P2。
