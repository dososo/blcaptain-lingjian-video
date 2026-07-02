# LingJian Video Studio / 灵剪 Video Studio · M1 最终 PRD（Claude 审计优化版）

> 版本：M1 Final after Claude Audit  
> 日期：2026-07-01  
> 状态：文档与架构已按 Claude 审计意见优化；运行时验证需交由 Codex / Claude Code 在真实仓库执行。  
> 原则：M1 是真实可用的纵向主干，不是 demo；M2/M3/v2 是有序路线图，不混入 M1 实现范围。

---

## 0. 本轮优化结论

本版吸收 Claude 审计包中的 6 个 Blocker、12 个 High、10 个 Medium 与 PRD/GOAL 精确 patch。核心修正如下：

1. **审批从“人工确认记录”升级为“artifact hash 绑定的系统门禁”**：`script / voice / visuals` 三项审批必须写入 `approvals.json`，并绑定被审批 artifact 的 `sha256(canonical_json(...))`。内容变更后审批自动失效，`render` 返回 `APPROVAL_STALE`。
2. **移除所有门禁绕过路径**：M1 不允许 `--force`、隐藏环境变量、管理员模式等绕过审批。未审内容只能走 `lj preview`，产物只能是草稿，不能进入 release 包。
3. **mock 不能伪装正式产物**：provider 必须有 `is_mock` 字段；`export --release` 遇到任何 mock provider 直接失败，错误码为 `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`。
4. **状态真值单一化**：项目目录内文件 artifact 是唯一事实源；SQLite 只是派生索引和列表缓存，可通过 `lj reindex` 从项目文件全量重建。
5. **Web 从 8 页收敛为 5 页**：保留完整人审链路，但压缩页面复杂度，避免 M1 被 Web 富交互拖垮。
6. **M1 渲染能力封顶**：`ffmpeg_card` 只做静态卡片帧、帧内字幕、图片/截图摆放、scene 硬切、concat、FFmpeg finalizer。禁止 zoompan、Ken Burns、逐帧动画、shader、转场库。
7. **TTS 逐段实际时长是时间真值**：每段 TTS 合成后必须用 `ffprobe` 实测时长，分镜、字幕、最终视频都以实测时长对齐。
8. **MCP 明确 M1 只占位，M2 实现**：M1 保留 22 个 canonical 工具名和 schema，占位返回 `not_implemented`，避免把 MCP 全实现拖入 M1。
9. **OCR 降为可选 provider**：M1 主链路是 `text/url/screenshot → script → TTS → video`，OCR 只在截图输入时触发，不进入核心依赖。
10. **合规红线显式化**：AGPL/GPL 项目只研究思想，不复制代码、prompt、template、UI；Remotion 不默认、不捆绑；URL 默认不下载他人视频；不捆绑模型权重和字体。

---

## 1. 固化决策 D1–D9

| ID | 决策 | M1 执行口径 |
|---|---|---|
| D1 | Python = backend/core/CLI/providers/API；Next.js + TypeScript = Web 控制台。HyperFrames / Remotion / Playwright 只能作为外部进程 adapter。 | `packages/core` 与业务 provider 不 import HyperFrames / Remotion / Playwright SDK。Playwright 只通过 CLI / helper subprocess 做 opt-in 截图；CI 静态扫描禁止 SDK import。 |
| D2 | M1 渲染只走自研 `ffmpeg_card`。HyperFrames = M2 可选 adapter；Remotion = M3 opt-in。 | `render` 只注册 `ffmpeg_card`；HyperFrames / Remotion 不进入 M1 渲染路径。 |
| D3 | 文案、语音、画面三审未齐时 `render` 硬拒绝。审批持久化到 `approvals.json`。 | 审批绑定 artifact hash。缺审批返回 `APPROVAL_REQUIRED`；hash 不符返回 `APPROVAL_STALE`；没有 `--force`。 |
| D4 | 不捆绑模型权重和字体。本地大模型作为外部服务 / 子进程 adapter。 | doctor 记录模型、权重、字体来源和 license；字体下载到用户缓存，不提交仓库。 |
| D5 | Remotion 不默认、不捆绑；声音克隆默认关闭并需授权确认；URL 默认不下载他人视频。 | M1 不做声音克隆，不引入 yt-dlp 默认路径；URL 只提取正文、metadata、opt-in 截图。 |
| D6 | 分阶段交付，M1 必须真实可用。 | M1 按 Batch 1/2/3 实现同一主干，每批都有真实价值，不推迟门禁、渲染、QA、export。 |
| D7 | mock / fixtures 只用于测试和 UI 预览，正式导出必须标注 provider，缺能力不能伪造成功。 | `provider_manifest.json` 标注 provider 与 `is_mock`；`export --release` 禁 mock。 |
| D8 | 主仓 Apache-2.0。 | `LICENSE` 为 Apache-2.0；第三方合规记录在 `docs/license-notes.md` 与发布包 `license_manifest.md`。 |
| D9 | 不复制第三方代码、README、prompt、UI、模板。只通过 CLI/API/SDK/子进程调用，并记录 license 与版本。 | AGPL/GPL 项目列入禁入清单；HyperFrames/Remotion 只通过 adapter 调用；`hyperframes-motion-director` 只学习流程思想。 |

### 1.1 对 Claude 审计中 Playwright 边界的处理

审计意见允许 `providers/web_extract` 例外使用 Playwright Python 绑定。本版采取更严格口径：**M1 默认不在 Python provider 中 import Playwright SDK，而是通过 `playwright` CLI 或隔离 helper 子进程调用**。这样完全满足原始 D1，并降低核心依赖污染风险。若未来确需 Python 绑定，只能进入独立 optional package，并继续禁止 core import。

---

## 2. 产品定位

**LingJian Video Studio / 灵剪 Video Studio** 是面向中文创作者、小团队和 Agent 工具链的本地 / 自部署 AI 视频生产工作台。

它不重造传统 NLE，也不重造 HyperFrames / Remotion，而是把 AI 内容生产编排成一条可审、可复跑、可导出的主干：

```text
输入素材
→ 内容提取
→ LLM 生成脚本
→ 文案审批
→ TTS 逐段合成并实测时长
→ 语音审批
→ 画面计划
→ 画面审批
→ ffmpeg_card 渲染
→ QA
→ canonical 发布包
```

M1 的目标不是“最炫视觉效果”，而是“真实用户配置真实 provider 后，能稳定产出可发布 MP4 与多平台发布包”。

---

## 3. 用户与场景

### 3.1 M1 优先用户

1. **中文知识 / 产品 / 教程创作者**：把文字、网页、产品资料、截图变成短视频。
2. **小团队 / MCN / 企业市场团队**：需要可审、可复跑、可归档的批量视频生产流程。
3. **AI Agent / Codex / Claude Code 使用者**：希望通过 CLI JSON 编排整个生产流程。
4. **自部署团队**：希望 API key、素材、审稿记录和导出包留在自己机器或私有服务器。

### 3.2 M1 真实场景

| 场景 | 输入 | 输出 | M1 支持方式 |
|---|---|---|---|
| 产品介绍短视频 | 产品文案 / 网页 / 截图 | 抖音 / 小红书 / Shorts 竖屏短视频 | LLM 脚本 + TTS + 静态卡片 + 字幕 |
| 教程 / 演示视频 | 步骤文档 / 截图 | B站 / YouTube 16:9 或 4:3 教程视频 | 脚本分镜 + 截图卡片 + 旁白 |
| 公众号 / 博客视频化 | URL / 正文 | 小红书 / YouTube Shorts | trafilatura 提取正文 + 生成短视频脚本 |
| 双语分发 | 中文或英文稿 | zh-CN / en-US 双独立发布包，或双行字幕版本 | bilingual 规则与多语言 export |

### 3.3 M1 明确不覆盖

M1 不做传统时间线编辑、ASR 上传音视频转写、声音克隆、本地 TTS 大模型、复杂 motion、Remotion、HyperFrames、桌面端、任务队列、多人协作、插件市场。它们按路线进入 M2/M3/v2。

---

## 4. M1 用户路径

### 4.1 Web 用户路径

```text
新建项目
→ 选择输入类型：文本 / URL / 截图 / 图片
→ 内容提取并生成脚本草案
→ 文案审核：批准 / 重生成 / 手动编辑
→ 生成语音预览并展示逐段时长
→ 语音审核：批准 / 换声音 / 重生成
→ 生成画面计划和低清预览
→ 画面审核：批准 / 编辑布局 / 重生成
→ 渲染
→ QA
→ 导出平台发布包
```

关键交互规则：

- 每一步生成类动作返回 `status: awaiting_review`，并展示 artifact 路径或审核链接。
- 用户批准后写入 `approvals.json`。
- 用户编辑脚本 / 语音计划 / 画面计划后，对应审批失效。
- Web 不维护第二套状态机，只调用后端 API，API 再调用 `packages/core.apply_event`。

### 4.2 CLI / Agent 用户路径

```bash
lj init ./projects/p1 --name "产品短视频" --json
lj ingest text ./projects/p1 --file examples/product_intro_zh.txt --json
lj extract ./projects/p1 --provider local --json
lj script ./projects/p1 --provider openai_compatible --platform douyin --language zh-CN --ratio 9:16 --duration 45 --json
# 这里必须停下等人审
lj approve script ./projects/p1 --approved-by human --json
lj voice ./projects/p1 --provider edge_tts --voice zh-CN-XiaoxiaoNeural --json
# 这里必须停下等人审
lj approve voice ./projects/p1 --approved-by human --json
lj visuals ./projects/p1 --engine ffmpeg_card --template product --json
# 这里必须停下等人审
lj approve visuals ./projects/p1 --approved-by human --json
lj render ./projects/p1 --platform douyin --language zh-CN --ratio 9:16 --json
lj qa ./projects/p1 --json
lj export ./projects/p1 --platform douyin --language zh-CN --ratio 9:16 --release --json
```

Agent 规则：生成类命令返回 `awaiting_review` 时必须停止，不能自动 approve，不能用 `preview` 冒充 release。

---

## 5. 信息架构与状态机

### 5.1 顶层对象

```text
Workspace
└── Project
    ├── Inputs / Assets
    ├── ExtractedContent
    ├── Script
    ├── VoicePlan
    ├── VisualPlan
    ├── RenderPlan
    ├── Approvals
    ├── RenderedOutputs
    ├── QAReport
    └── ExportPackage
```

### 5.2 状态机

唯一状态转移入口：`packages/core/state_machine.py::apply_event(project, event) -> StateTransitionResult`。

状态建议：

```text
created
→ input_ready
→ extracted
→ script_review
→ script_approved
→ voice_review
→ voice_approved
→ visuals_review
→ visuals_approved
→ render_ready
→ rendered
→ qa_passed / qa_blocked
→ exported_preview / exported_release
```

失效规则：

| 变更 | 自动失效 |
|---|---|
| `script.json` 变更 | `script` 审批失效；同时 voice / visuals / render 相关 artifact 标记 stale |
| `voice_plan.json` 或音频文件变更 | `voice` 审批失效；render 相关 artifact 标记 stale |
| `visual_plan.json` 变更 | `visuals` 审批失效；render 相关 artifact 标记 stale |
| platform preset 变更 | 对应 platform/language/ratio 的 render/export 失效 |

---

## 6. Web 控制台（M1 必做：5 页）

M1 Web 不做传统 timeline，也不做复杂富交互。页面压缩为 5 页，但不删减三审流程。

### 6.1 页面 1：新建向导

- 新建项目、选择模板、语言、平台、比例、目标时长。
- 输入文本 / URL / 截图 / 图片。
- 展示 doctor 摘要：FFmpeg、字体、LLM、TTS、OCR extras、Playwright、Remotion license 提示。

### 6.2 页面 2：提取 + 文案审核

- 展示原始输入、提取正文、metadata、截图预览。
- 展示 `script.json` 的 scenes、字幕文本、source_map。
- 三个主按钮：批准、重新生成、手动编辑。
- 编辑后重新计算 script hash，旧审批失效。

### 6.3 页面 3：语音审核

- 展示 voice provider、voice id、每段音频、逐段实测时长、总时长。
- 支持试听、换声音、重生成。
- 审批绑定 `voice_plan.json` 与音频文件清单 hash。

### 6.4 页面 4：画面审核

- 展示 `visual_plan.json`、scene 卡片、比例预览、安全区、字体状态。
- 支持低清预览 `lj preview`。
- 审批绑定 visual plan hash。

### 6.5 页面 5：渲染 + 发布包

- 展示审批状态、render 按钮、QA 报告、导出包目录。
- doctor / provider 配置作为设置抽屉，不单独拆页。
- release 导出前展示 provider/license manifest 与 QA blocking 状态。

---

## 7. CLI（M1 必做，Agent 级）

### 7.1 CLI 硬规则

- 所有命令支持 `--json`；JSON 输出不得混入日志。
- 所有失败必须返回稳定 `error_code`、中文 `message_zh`、可执行 `hint`。
- `render` 没有 `--force`。
- `preview` 可在未审时生成草稿，但不产 release 包。
- `export --release` 必须检查 provider 与 QA。

### 7.2 命令清单

```bash
lj doctor [--fix] [--json]
lj studio [--port 17860] [--api-port 17861]
lj init <project> --name <name> [--template <template>] [--json]
lj status <project> [--json]
lj reindex <project> [--json]

lj ingest text <project> --file <path> [--language zh-CN|en-US] [--json]
lj ingest url <project> --url <url> [--screenshot] [--json]
lj ingest image <project> --file <path> --role screenshot|product|logo|chart|reference [--json]

lj extract <project> [--provider local|trafilatura|mock] [--json]
lj script <project> --type product|article|tutorial|website --platform <platform> --language <language> --ratio <ratio> [--duration 45] --provider <provider> [--json]
lj approve script <project> [--approved-by <name>] [--comment <text>] [--json]

lj voice <project> --provider edge_tts|openai_tts|mock --voice <voice-id> [--json]
lj approve voice <project> [--approved-by <name>] [--comment <text>] [--json]

lj visuals <project> --engine ffmpeg_card [--template card_default|product|tutorial|article] [--json]
lj approve visuals <project> [--approved-by <name>] [--comment <text>] [--json]

lj preview <project> --platform <platform> --language <language> --ratio <ratio> [--json]
lj render <project> --platform <platform> --language <language> --ratio <ratio> [--json]
lj qa <project> [--json]
lj export <project> --platform <platform> [--language <language>] [--ratio <ratio>] [--all-platforms] [--release] [--json]
```

### 7.3 稳定错误码

| error_code | 触发条件 |
|---|---|
| `INVALID_ARGUMENT` | 参数非法、缺必填字段 |
| `PROJECT_NOT_FOUND` | 项目不存在 |
| `PROVIDER_NOT_CONFIGURED` | provider 未配置 |
| `TOOL_NOT_INSTALLED` | 依赖工具缺失 |
| `FFMPEG_NOT_FOUND` | FFmpeg / ffprobe 不存在 |
| `FONT_CJK_MISSING` | 缺 CJK 字体且未能下载 |
| `APPROVAL_REQUIRED` | render 前缺 script / voice / visuals 审批 |
| `APPROVAL_STALE` | 审批 hash 与当前 artifact 不一致 |
| `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE` | release 导出时发现 mock provider |
| `TTS_TIMEOUT` | 同步 TTS 超时 |
| `TTS_PROVIDER_ERROR` | TTS provider 返回错误 |
| `TRAFILATURA_LICENSE_BLOCKED` | trafilatura 版本 / license 不合规 |
| `PATH_OUTSIDE_PROJECT` | 上传 / 输出路径越过项目沙盒 |
| `QA_BLOCKING` | QA hard fail 阻止 release |
| `RENDER_FAILED` | 渲染失败 |

错误 JSON 结构：

```json
{
  "ok": false,
  "error_code": "APPROVAL_REQUIRED",
  "message_zh": "渲染前必须完成文案、语音和画面三项审批。",
  "hint": "运行 lj approve script / voice / visuals 后重试。",
  "missing": ["script", "voice", "visuals"]
}
```

---

## 8. MCP（M1 占位，M2 实现）

M1 只交付 `packages/mcp_server/README.md`、工具名清单、JSON schema 占位，所有工具返回：

```json
{"status":"not_implemented","since":"M2","message_zh":"MCP 工具将在 M2 作为 CLI/core 薄封装实现。"}
```

M2 canonical 22 个工具如下，PRD/GOAL/Skill 统一以此为准：

```text
1.  lingjian.doctor
2.  lingjian.create_project
3.  lingjian.open_project
4.  lingjian.get_project_status
5.  lingjian.ingest_text
6.  lingjian.ingest_url
7.  lingjian.ingest_image
8.  lingjian.extract_content
9.  lingjian.generate_script
10. lingjian.approve_script
11. lingjian.generate_voice_preview
12. lingjian.approve_voice
13. lingjian.generate_visual_plan
14. lingjian.approve_visuals
15. lingjian.preview_video
16. lingjian.render_final
17. lingjian.qa_report
18. lingjian.export_package
19. lingjian.list_templates
20. lingjian.list_platforms
21. lingjian.list_providers
22. lingjian.install_tool
```

---

## 9. Skill（M2，不属于 M1 实现）

M2 才实现 `skills/lingjian-video/SKILL.md`、`AGENTS.md`、`CLAUDE.md`。M1 文档只固定原则：

- Skill 是 CLI/MCP 路由器，不复制业务逻辑。
- 生成 script / voice / visuals 后必须停下等审批。
- 不绕门禁，不使用 `preview` 冒充 release。
- 不下载未授权视频。
- 不复制 `hyperframes-motion-director` 的 AGPL prompt / template / script / UI。
- HyperFrames 只作为 M2 adapter，被 LingJian 以 subprocess 调用。

---

## 10. 仓库目录结构

```text
lingjian-video-studio/
├── LICENSE                         # Apache-2.0
├── README.md
├── DISCLAIMER.md
├── AGENTS.md                       # M1 说明 CLI 编排规则；完整 Skill 到 M2
├── CLAUDE.md                       # M1 说明 Claude Code 编排规则
├── pyproject.toml
├── uv.lock
├── .python-version                 # 3.11 或 3.12
├── package.json                    # packageManager + Node 20 engines
├── pnpm-lock.yaml
├── apps/
│   ├── cli/lingjian_cli/
│   ├── api/lingjian_api/
│   └── web/                        # Next.js + TS，仅 console
├── packages/
│   ├── schemas/                    # Pydantic 权威 schema + JSON Schema 导出
│   ├── core/                       # 状态机、artifact、approval gate、reindex
│   └── mcp_server/README.md        # M1 占位；M2 实现
├── providers/
│   ├── base.py
│   ├── llm/openai_compatible.py
│   ├── llm/anthropic.py
│   ├── tts/edge_tts.py
│   ├── tts/openai_compatible_tts.py
│   ├── ocr/rapidocr.py             # extras: ocr
│   ├── web_extract/trafilatura_extractor.py
│   ├── web_extract/playwright_cli.py # opt-in subprocess，不 import SDK
│   └── mock/
├── engines/
│   └── ffmpeg_card/
├── config/
│   ├── presets/
│   │   ├── douyin.yaml
│   │   ├── xiaohongshu.yaml
│   │   ├── bilibili.yaml
│   │   ├── youtube.yaml
│   │   └── youtube_shorts.yaml
│   └── templates/
├── docs/
│   ├── installation.md
│   ├── providers.md
│   ├── render-engines.md
│   ├── platform-presets.md
│   ├── skill-and-mcp.md
│   ├── license-notes.md
│   └── troubleshooting.md
├── examples/
├── tests/
└── projects/                       # 默认本地工作区，可配置
```

---

## 11. 状态与存储

### 11.1 唯一事实源

**项目文件 artifact 是唯一事实源。SQLite 只是派生索引和列表缓存。**

写操作顺序：

```text
validate event
→ update artifact files atomically
→ update manifest
→ update derived SQLite index
→ return JSON projection
```

若 SQLite 丢失或损坏：

```bash
lj reindex <project> --json
```

必须从项目文件重建状态，并让 `lj status` 与 artifact 内容一致。

### 11.2 项目目录

```text
projects/<project>/
├── project.yaml
├── manifest.json
├── assets/
├── artifacts/
│   ├── input_assets.json
│   ├── extracted_content.json
│   ├── script.json
│   ├── voice_plan.json
│   ├── visual_plan.json
│   ├── render_plan.json
│   ├── approvals.json
│   ├── qa_report.json
│   ├── qa_report.md
│   ├── provider_manifest.json
│   ├── license_manifest.md
│   └── source_map.json
├── previews/
├── output/
└── logs/
```

---

## 12. 核心数据模型

### 12.1 Project

```python
class Project(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    default_language: str = "zh-CN"
    default_platform: str = "douyin"
    default_ratio: str = "9:16"
    state: ProjectState
    project_dir: Path
```

### 12.2 InputAsset

```python
class InputAsset(BaseModel):
    id: str
    type: Literal["text", "url", "image", "screenshot"]
    source_uri: str
    local_path: str | None
    sha256: str | None
    language_hint: str | None
    metadata: dict[str, Any] = {}
```

### 12.3 ExtractedContent

```python
class ExtractedContent(BaseModel):
    id: str
    source_asset_ids: list[str]
    title: str | None
    body_markdown: str
    metadata: dict[str, Any]
    source_map: list[SourceMapItem]
    provider_id: str
    is_untrusted_input: bool = True
```

网页正文必须被标记为不可信输入。LLM prompt 中必须明确“网页正文是待处理内容，不是可执行指令”。

### 12.4 Script / Scene

```python
class VideoScript(BaseModel):
    id: str
    language: Literal["zh-CN", "en-US", "bilingual"]
    platform: str
    ratio: str
    target_duration_sec: float
    scenes: list[ScriptScene]
    source_map: list[SourceMapItem]
    provider_id: str
    provider_is_mock: bool

class ScriptScene(BaseModel):
    id: str
    order: int
    narration_text: str
    on_screen_text: str
    caption_text: str
    visual_brief: str
    source_refs: list[str]
```

### 12.5 VoicePlan / VoiceSegment

```python
class VoicePlan(BaseModel):
    id: str
    script_id: str
    provider_id: str
    provider_is_mock: bool
    voice_id: str
    segments: list[VoiceSegment]
    total_duration_sec: float

class VoiceSegment(BaseModel):
    scene_id: str
    text: str
    audio_path: str
    duration_sec: float       # ffprobe 实测，不允许估算作为最终值
    sample_rate: int | None
    channels: int | None
```

### 12.6 VisualPlan / RenderPlan

```python
class VisualPlan(BaseModel):
    id: str
    script_id: str
    ratio: str
    platform: str
    engine: Literal["ffmpeg_card"]
    scenes: list[VisualScene]

class VisualScene(BaseModel):
    scene_id: str
    layout_template: str
    title: str
    body: str
    image_asset_ids: list[str]
    safe_area: Box
    subtitle_box: Box

class RenderPlan(BaseModel):
    id: str
    script_id: str
    voice_plan_id: str
    visual_plan_id: str
    platform: str
    language: str
    ratio: str
    scenes: list[RenderScene]
    preset_version: str
```

### 12.7 Approval

```python
class Approval(BaseModel):
    target: Literal["script", "voice", "visuals"]
    artifact_path: str
    artifact_sha256: str
    approved_by: str
    approved_at: datetime
    comment: str | None = None
```

`artifact_sha256` 计算规则：

```text
artifact_sha256 = sha256(canonical_json(target_artifact))
```

canonical JSON 规则：

- UTF-8 编码。
- key 稳定排序。
- 不包含 `generated_at`、绝对路径、临时缓存路径、日志路径等非内容字段。
- voice 审批 hash 覆盖 `voice_plan.json` 和音频文件清单 `{path, sha256, duration_sec}`。

`render` 前检查：

```text
script approval missing  → APPROVAL_REQUIRED
voice approval missing   → APPROVAL_REQUIRED
visuals approval missing → APPROVAL_REQUIRED
hash mismatch            → APPROVAL_STALE
```

### 12.8 ProviderManifest / LicenseManifest

```python
class UsedProvider(BaseModel):
    id: str
    name: str
    kind: Literal["llm", "tts", "ocr", "web_extract", "renderer"]
    version: str | None
    is_mock: bool
    mode: Literal["real", "mock", "degraded"]
    license: str | None
    config_redacted: dict[str, Any]

class ProviderManifest(BaseModel):
    providers: list[UsedProvider]
    release_allowed: bool
```

`license_manifest.md` 必须列出 FFmpeg build、字体来源、provider、外部模型服务、是否使用 Remotion / HyperFrames / Playwright、是否含 mock。

### 12.9 QAReport / ExportPackage

```python
class QAReport(BaseModel):
    hard_failures: list[QAIssue]
    warnings: list[QAIssue]
    info: list[QAIssue]
    release_ready: bool

class ExportPackage(BaseModel):
    project_id: str
    platform: str
    language: str
    ratio: str
    export_dir: str
    files: dict[str, str]
    release: bool
```

---

## 13. Artifact schema

M1 必须稳定输出以下 artifact：

| 文件 | 说明 |
|---|---|
| `project.yaml` | 项目元信息 |
| `manifest.json` | artifact 索引、版本、hash |
| `assets/input_assets.json` | 输入素材索引 |
| `artifacts/extracted_content.json` | 提取结果 |
| `artifacts/script.json` | 脚本与分镜文本 |
| `artifacts/voice_plan.json` | 语音计划与逐段时长 |
| `artifacts/voice_segments/*.wav|mp3` | 分段音频 |
| `artifacts/visual_plan.json` | 画面计划 |
| `artifacts/render_plan.json` | 渲染计划 |
| `artifacts/approvals.json` | 三审记录，含 hash |
| `artifacts/source_map.json` | 输入到脚本/画面的来源映射 |
| `artifacts/qa_report.json` / `.md` | QA 结果 |
| `artifacts/provider_manifest.json` | provider 与 mock 状态 |
| `artifacts/license_manifest.md` | license 记录 |
| `previews/*.mp4` | 草稿预览，只能 preview |
| `output/*.mp4` | 渲染产物 |

所有 JSON schema 由 Pydantic 导出到 `packages/schemas/json_schema/`，CLI/API/Web/MCP 共用。

---

## 14. Provider 接口

### 14.1 生命周期接口

```python
class Provider(ABC):
    id: str
    name: str
    kind: ProviderKind
    capabilities: list[str]
    is_mock: bool

    @abstractmethod
    def is_installed(self) -> bool: ...

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def doctor(self) -> ProviderStatus: ...

    @abstractmethod
    def setup_hint(self) -> str: ...

    @abstractmethod
    def license_info(self) -> LicenseInfo: ...
```

必须有 provider 契约测试：所有注册 provider 都要通过 `test_provider_contract`，缺方法、签名不一致、返回 schema 不合法均 CI 失败。

### 14.2 LLMProvider

```python
class LLMProvider(Provider):
    def generate_script(self, input: ScriptGenerationInput) -> VideoScript: ...
```

M1 provider：

- `openai_compatible`：支持自定义 `base_url`，便于 DeepSeek / Qwen / Moonshot / Ollama / vLLM。
- `anthropic`：支持 Claude API。
- `mock`：仅测试和 UI 预览，`is_mock=True`。

LLM 输出必须经 Pydantic 校验。不合 schema 必须重试或失败，不能吞错。

### 14.3 TTSProvider

```python
class TTSProvider(Provider):
    def list_voices(self) -> list[VoiceInfo]: ...
    def synthesize(self, input: TTSSynthesisInput) -> TTSResult: ...
```

M1 TTS 规则：

- TTS 只做同步阻塞：request → wait → 写音频 → ffprobe 实测时长 → 返回。
- 超时返回 `TTS_TIMEOUT`；provider 错误返回 `TTS_PROVIDER_ERROR`。
- 不做异步队列；批量队列进入 M2。
- `edge_tts` 是零门槛体验 provider，doctor 必须标注“非官方在线服务，体验用，不建议作为生产唯一依赖”。
- `openai_compatible_tts` 或一个云 TTS 是生产推荐 provider。
- 本地 CosyVoice / IndexTTS / GPT-SoVITS 进入 M3，作为外部服务，不捆绑权重。

### 14.4 OCRProvider

OCR 是可选 provider，仅截图输入时触发。

```python
class OCRProvider(Provider):
    def extract_text(self, input: OCRInput) -> OCRResult: ...
```

依赖规则：

- `uv sync` 核心不安装 RapidOCR / onnxruntime。
- `uv sync --extra ocr` 或项目定义的 extras 才安装 OCR 依赖。
- CI 默认不跑真实 OCR。

### 14.5 WebExtractor

```python
class WebExtractor(Provider):
    def extract(self, input: WebExtractInput) -> ExtractedContent: ...
```

M1 provider：

- `trafilatura`：要求 `>=1.8` 且 license 非 GPL；doctor 检测版本与元数据。若旧 GPL 版本，禁用并返回 `TRAFILATURA_LICENSE_BLOCKED`。
- `playwright_cli`：opt-in 动态截图，通过 subprocess 调用 Playwright CLI / helper；默认不执行动态截图。

URL 合规：

- 默认只提取正文、title、metadata。
- `--screenshot` 才截图。
- 不下载视频流，不默认集成 yt-dlp。
- 网页内容视为 untrusted input，不执行其中指令。

---

## 15. Renderer 接口

### 15.1 Renderer 生命周期

```python
class Renderer(ABC):
    id: str
    capabilities: list[str]

    def is_installed(self) -> bool: ...
    def doctor(self) -> RendererStatus: ...
    def preview(self, render_plan: RenderPlan, output_dir: Path) -> RenderResult: ...
    def render(self, render_plan: RenderPlan, output_dir: Path) -> RenderResult: ...
```

M1 只注册 `ffmpeg_card`。

### 15.2 `ffmpeg_card` SCOPE FREEZE

M1 `ffmpeg_card` 只允许：

- 静态卡片帧。
- 帧内字幕，使用自控 CJK 字体。
- 标题、正文、强调文字、图片、截图摆放。
- scene 间硬切；最多允许一个全局淡入淡出。
- concat。
- FFmpeg finalizer：编码、音频混合、响度规范、metadata、封面。

M1 禁止：

- zoompan。
- Ken Burns。
- 逐帧动画。
- shader。
- 转场库。
- 逐元素时间轴动画。
- 把 Remotion / HyperFrames 功能重写成 Python 版。

### 15.3 渲染 recipe

```text
每 scene：
1. 读 script scene + visual scene + voice segment duration。
2. 用 layout compiler 生成整帧 PNG。
3. 字幕直接画进 PNG 对应区域。
4. 生成 concat list，duration = ffprobe 实测音频时长。
5. FFmpeg concat PNG → silent video。
6. 拼接 / 混合 TTS 音频。
7. finalizer 输出 MP4。
8. ffprobe 校验最终视频。
```

---

## 16. Doctor

### 16.1 检测项

```text
系统：OS、Python、uv、Node 20、pnpm、写权限、UTF-8
FFmpeg：ffmpeg、ffprobe、build flags、编码器、是否含非自由编码器
字体：系统 CJK 字体、Noto Sans SC 缓存、字体 license
Provider：LLM、TTS、OCR extras、WebExtractor 配置
trafilatura：版本、license、是否 >=1.8
Playwright：CLI / browser 是否可用，安装命令
Remotion：M3 opt-in license 提示，不安装
HyperFrames：M2 opt-in 提示，不安装
安全：API key 是否脱敏、项目路径是否可写
```

### 16.2 `--fix` 规则

`lj doctor --fix` 只允许安全修复：

- 创建缓存目录。
- 下载可再分发 CJK 字体到 `~/.cache/lingjian/fonts/`。
- 运行 Playwright 浏览器安装命令，但不安装 Playwright 包本身。

禁止自动执行：

- 安装 Remotion。
- 安装 HyperFrames。
- 下载模型权重。
- 把字体提交到仓库。
- 修改用户 shell 配置。

### 16.3 安装提示

- FFmpeg：提供 `brew` / `winget` / `apt` 命令。
- Playwright：`pip install playwright && playwright install`。
- 字体：Noto Sans SC 下载到缓存并记录 license。
- 国内模型：提供 OpenAI-compatible `base_url` 配置示例，不硬编码某家厂商。

---

## 17. 平台 preset

### 17.1 M1 五平台 preset

| preset | 默认用途 | 主要比例 |
|---|---|---|
| `douyin` | 抖音短视频 | 9:16 |
| `xiaohongshu` | 小红书笔记视频 | 3:4 / 9:16 |
| `bilibili` | B站横屏 / 教程 | 16:9 / 4:3 |
| `youtube` | YouTube 横屏 | 16:9 |
| `youtube_shorts` | YouTube Shorts | 9:16 |

`4:3` 是教程 / 演示通用比例，不绑定“B站原生 4:3 规格”。

### 17.2 preset 是纯配置层

渲染和导出代码禁止出现：

```python
if platform == "douyin": ...
```

全部平台差异落在 YAML 字段：

```yaml
id: douyin
version: 1
resolution:
  "9:16": [1080, 1920]
  "16:9": [1920, 1080]
fps: 30
safe_area:
  top: 120
  bottom: 260
  left: 72
  right: 72
subtitle_style:
  font_family: Noto Sans SC
  font_size: 54
  max_lines: 2
title_style:
  font_size: 72
export_files:
  video: video.mp4
  cover: cover.png
  metadata: publish.md
  captions_srt: captions/subtitles.srt
  captions_vtt: captions/subtitles.vtt
  captions_ass: captions/subtitles.ass
qa_rules:
  max_duration_sec: 60
  require_audio: true
  require_burned_subtitles: true
```

---

## 18. 多语言

M1 支持：

- `zh-CN`
- `en-US`
- `bilingual`

`bilingual` 定义为：

1. 双独立语言包：同一项目输出中文包和英文包；或
2. 单视频双行字幕：主语言旁白 + 双行字幕。

M1 不做“实时中英混读”或同一段 TTS 自动混杂双语。

---

## 19. 多比例

M1 支持四个比例：

```text
9:16
16:9
3:4
4:3
```

实现方式：一个四盒 layout compiler：

```text
title box
body box
image/screenshot box
subtitle box
```

规则：

- 9:16 / 16:9 手工调参数。
- 3:4 / 4:3 由同一盒模型线性适配。
- 不为每个平台 × 每比例写独立布局代码。
- QA 检查字幕是否越安全区。

---

## 20. 发布包结构（canonical）

统一目录：

```text
exports/<project>/<platform>/<language>/<ratio>/
```

基础结构：

```text
exports/m1_real_test/douyin/zh-CN/9x16/
├── video.mp4
├── cover.png                  # 或 preset 声明为 thumbnail.png
├── metadata/
│   └── publish.md
├── captions/
│   ├── subtitles.srt
│   ├── subtitles.vtt
│   └── subtitles.ass
├── source_map.json
├── qa_report.json
├── qa_report.md
├── provider_manifest.json
├── license_manifest.md
└── export_manifest.json
```

YouTube preset 可声明：

```text
thumbnail.png
description.md
chapters.md
```

导出后必须做结构校验，缺文件即失败。

Release 判定：

```text
release_ready =
  三审有效
  AND QA 无 hard failure
  AND provider_manifest 不含 is_mock=true
  AND canonical 文件齐全
```

---

## 21. QA

QA 分三级。

### 21.1 hard fail

- 文件缺失。
- MP4 不可播放。
- 分辨率与 preset 不一致。
- 无音轨。
- 音频总时长、视频总时长、字幕末尾时间差超过阈值。
- 中文帧内字幕为空或疑似方块。
- 未处理占位符：`TODO`、`{{...}}`、`[placeholder]`。
- `export --release` 含 mock provider。
- 三审缺失或 stale。

### 21.2 warning

- 响度越界。
- 字幕越安全区。
- 时长偏差中等。
- 敏感信息疑似暴露：手机号、邮箱、API key、身份证号模式。
- 平台风险词命中。
- source_map 覆盖率低。

### 21.3 info

- 字数统计。
- scene 数。
- provider 列表。
- 运行耗时。
- source_map 覆盖率。

QA 输出：

```text
artifacts/qa_report.json
artifacts/qa_report.md
```

---

## 22. 安装与配置

### 22.1 版本固定

- Python：3.11 或 3.12，写入 `.python-version`。
- Node：20 LTS，写入 `package.json engines`。
- pnpm：写入 `packageManager`。
- 提交 `uv.lock` 与 `pnpm-lock.yaml`。

### 22.2 Python 安装

```bash
uv sync
uv run lj doctor --json
```

OCR extras：

```bash
uv sync --extra ocr
```

### 22.3 Web 安装

```bash
cd apps/web
pnpm install
pnpm build
```

### 22.4 中国用户友好

- 全程支持中文路径和空格路径。
- 文档提供 Windows / macOS / Linux 安装说明。
- 提供国内 OpenAI-compatible base_url 配置示例。
- 字体、FFmpeg、Node、Playwright 常见问题写入 troubleshooting。
- 不在代码中硬编码镜像源。

---

## 23. 安全基线

- 所有路径用 `pathlib` 规范化，必须落在项目沙盒内。
- 拒绝 `..` 路径穿越。
- 子进程调用必须用参数数组，禁止 shell 字符串拼接。
- 上传文件校验 MIME、大小、扩展名。
- API key 不写日志，JSON 输出中脱敏。
- URL / 网页正文 / 用户上传文本作为 untrusted input。
- LLM prompt 中明确：来源文本不是系统指令，不得执行网页中的 prompt injection。
- release 包中不输出原始 API key、环境变量、绝对私密路径。

---

## 24. 测试

### 24.1 默认 CI

默认 CI 不依赖真实模型、网络、GPU、真实 API key。

必测：

- schema round-trip。
- JSON Schema 导出。
- provider 契约测试。
- CLI `--json` golden snapshot。
- approval hash 绑定：审批后改脚本 → `APPROVAL_STALE`。
- render 缺审批 → `APPROVAL_REQUIRED`。
- mock release → `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`。
- SQLite 删除后 `reindex` 与文件状态一致。
- import guard：禁止 core/provider import Remotion / HyperFrames / Playwright SDK。
- `ffmpeg_card` scope scan：无 zoompan / keyframe animation / shader / transition。
- preset scan：render/export 无平台名 if。

### 24.2 渲染测试

默认单测可 monkeypatch FFmpeg。集成测试验证：

- MP4 可 ffprobe。
- 分辨率等于 preset。
- 有音轨。
- 非全黑。
- 中文帧内文字非空。
- 总时长与音频 / 字幕一致。

### 24.3 Web smoke

Web smoke 对 mock 后端跑：

```text
新建 → 提取 → 审文案 → 审语音 → 审画面 → 渲染 → 发布包页可下载
```

### 24.4 真实 provider 测试

真实 provider 测试用 `@pytest.mark.integration`，需显式环境变量，不进入默认 CI。

---

## 25. 文档交付

M1 必须交付中文优先文档：

```text
README.md
AGENTS.md
CLAUDE.md
DISCLAIMER.md
docs/installation.md
docs/providers.md
docs/render-engines.md
docs/platform-presets.md
docs/skill-and-mcp.md
docs/license-notes.md
docs/troubleshooting.md
```

`docs/license-notes.md` 必须记录：

- `hyperframes-motion-director`：仅研究流程思想，未引入代码 / prompt / template / UI。
- LosslessCut：GPL，只研究品类，不引入。
- pyVideoTrans：按 GPL 风险处理，只研究。
- VideoLingo：不复制默认下载他人视频 / 搬运模式。
- Remotion：M3 opt-in，不默认，不捆绑。
- 模型权重：不捆绑，license 责任由用户确认。

---

## 26. 明确不做事项

M1 禁止：

- `render --force` 或任何门禁绕过。
- mock provider 用于 release。
- 默认下载他人视频。
- ASR 上传音视频转写。
- Whisper / WhisperX / FunASR 主链路。
- 本地 TTS / 声音克隆。
- Remotion adapter。
- HyperFrames adapter。
- 复杂动画、逐帧 motion、转场库。
- 传统 timeline / NLE。
- Tauri 桌面端。
- Redis / Postgres / 任务队列。
- 插件市场。
- 复制第三方 AGPL/GPL 代码、prompt、template、UI。

---

## 27. 分阶段路线

### M1 / v1.0：纵向主干真实可用

M1 内部按 3 个真实增量批次实现。

**Batch 1：核心状态机 + schema + CLI + mock provider + doctor + approval hash**

真实价值：Agent 可驱动全链路并被强制停审，项目状态可信、可复跑。

**Batch 2：真实 LLM/TTS + ffmpeg_card + QA + export**

真实价值：配置真实 provider 后可产出可播放、结构合规、可发布的多平台 MP4 包。

**Batch 3：Next.js 5 页 Web 控制台 + provider 配置 + 文档 + 跨平台 polish**

真实价值：非开发者可通过 Web 完成同一条主干。

### M2 / v1.1：Agent 与富视觉

- MCP 22 工具完整实现。
- Skill / AGENTS / CLAUDE 完整化。
- HyperFrames adapter，subprocess 调用。
- Web 富交互：波形、逐幕重做、实时比例预览。
- 云 TTS 异步队列。
- libass 可选字幕烧录。

### M3 / v1.2：语音与视觉扩展

- ASR：上传音视频转写、WhisperX 词级对齐、FunASR 外部服务。
- 本地 TTS：CosyVoice / IndexTTS / GPT-SoVITS 外部服务。
- 声音克隆授权门禁。
- PaddleOCR。
- Remotion opt-in adapter，doctor 强 license 提示。
- 图像生成 / 原创插画 provider。

### v2：平台化

- Tauri 桌面壳。
- 插件引擎。
- Postgres / Redis / 任务队列。
- 多人协作。
- 更多平台：视频号、快手、Reels、TikTok。

---

## 28. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---:|---|
| 审批 hash 实现不严导致门禁绕过 | 高 | canonical JSON + render 前重算 + stale 测试 |
| `ffmpeg_card` 蔓延成复杂动画引擎 | 高 | SCOPE FREEZE + 静态扫描 + M2 HyperFrames 承接富视觉 |
| mock 产物误发 | 高 | `is_mock` + release 硬失败 + manifest 标注 |
| SQLite 与文件状态漂移 | 高 | 文件为唯一事实源 + `reindex` 测试 |
| TTS 时长估算导致音画字不同步 | 高 | ffprobe 实测逐段时长 + QA hard fail |
| Web 拖慢 M1 | 中 | 5 页收敛 + API/CLI 先行 |
| EdgeTTS 不稳定 / 条款灰区 | 中 | 标注体验用 + 并列生产云 TTS |
| OCR 依赖过重 | 中 | extras 可选，非主链路 |
| AGPL/GPL 传染 | 高 | 禁复制、禁 vendor、license-notes 留痕 |
| URL 版权风险 | 高 | 默认不下载视频，只处理正文/metadata/截图 |
| Windows 中文路径 | 中 | pathlib + UTF-8 + 中文路径 e2e |

---

## 29. 开源与合规

- 主仓：Apache-2.0。
- FFmpeg：通过系统安装或用户环境调用；doctor 记录 build 与编码器，避开非自由编码器分发风险。
- 字体：Noto Sans SC 可作为下载目标，但不提交仓库；doctor 下载到缓存并记录 SIL OFL。
- Remotion：M3 opt-in，不默认、不捆绑；doctor 提示公司 / 自动化生成工具 license 风险。
- HyperFrames：M2 外部 CLI adapter，不复制其 skill / registry / 组件代码。
- `hyperframes-motion-director`：按 AGPL 风险处理，只研究流程思想，不复制 prompt、template、script、UI、代码。
- 本地模型：代码 license 与权重 license 分离；不捆绑权重；外部服务方式；用户确认商用责任。
- VideoLingo 式默认下载他人视频模式不复制。

---

## 30. M1 达标定义

M1 只有在以下条件全部成立时达标：

1. CLI、API、Web 共用 `packages/core` 状态机。
2. `render` 缺审返回 `APPROVAL_REQUIRED`。
3. 审批后修改 artifact 返回 `APPROVAL_STALE`。
4. `export --release` 遇 mock 返回 `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`。
5. 配置真实 LLM/TTS 后能产出 release 包。
6. MP4 可播放，分辨率、音轨、字幕、时长通过 QA。
7. export 目录符合 `exports/<project>/<platform>/<language>/<ratio>/`。
8. 五平台 preset 可导出，平台差异纯配置。
9. zh-CN / en-US / bilingual 定义清晰并可导出。
10. CI 离线，不依赖真实 key、网络、GPU。
11. import guard、scope freeze、forbidden scan 全通过。
12. 文档、license-notes、troubleshooting 完整。
