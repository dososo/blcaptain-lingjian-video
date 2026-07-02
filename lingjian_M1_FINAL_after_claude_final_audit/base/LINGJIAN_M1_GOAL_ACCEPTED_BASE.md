# LingJian Video Studio / 灵剪 Video Studio · M1 最终 GOAL（Claude 审计优化版）

> 面向：Codex / Claude Code / 具备代码执行能力的工程 Agent  
> 目标：实现 M1 真实可用主干。不是 demo，不是 mock-only，不做全宽度 v1。  
> 交付方式：建议按 Batch 1 → Batch 2 → Batch 3 实现，但三批共同组成 M1；不能把门禁、release 判定、ffmpeg_card、QA、canonical export 推迟到 M2。

---

## 0. 你必须先理解的边界

你要实现的是一个正式开源项目的 M1 主干：

```text
文本 / URL / 截图 / 图片
→ 内容提取
→ LLM 生成脚本
→ 文案审批
→ TTS 逐段合成并 ffprobe 实测时长
→ 语音审批
→ 画面计划
→ 画面审批
→ ffmpeg_card 渲染
→ QA
→ canonical 发布包
```

M1 的 release-ready 判据：用户配置真实 LLM 与真实 TTS 后，能通过 CLI 或 Web，把输入内容变成可播放 MP4 与多平台发布包。mock 只能测试和预览，不能 release。

---

## 1. 不可协商决策

1. **语言边界**：Python = backend/core/CLI/providers/API；Next.js + TypeScript = Web 控制台。HyperFrames / Remotion / Playwright 不 import 进 Python 业务核心；M1 Playwright 通过 subprocess / CLI opt-in 调用。
2. **渲染地板**：M1 只实现 `ffmpeg_card`。HyperFrames 是 M2 adapter；Remotion 是 M3 opt-in。M1 不调用 HyperFrames / Remotion。
3. **审批门禁**：`render` 必须检查 `script / voice / visuals` 三审。缺项返回 `APPROVAL_REQUIRED`；hash 不符返回 `APPROVAL_STALE`；无 `--force`。
4. **审批 hash**：`Approval{target, artifact_path, artifact_sha256, approved_by, approved_at, comment}`；`artifact_sha256=sha256(canonical_json(target_artifact))`。voice hash 必须覆盖音频文件清单 `{path, sha256, duration_sec}`。
5. **模型/字体**：不捆绑模型权重和字体。本地模型是 M3 外部服务。字体下载到用户缓存并记录 license。
6. **合规**：Remotion 不默认、不捆绑；声音克隆 M1 不做；URL 默认不下载他人视频；AGPL/GPL 项目禁止 vendor / 复制 / 改写照搬。
7. **mock 边界**：provider 必须有 `is_mock`。`export --release` 遇任何 mock provider 必须失败，错误码 `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`。
8. **状态真值**：项目文件 artifact 是唯一事实源；SQLite 只是派生索引，可通过 `lj reindex` 从文件重建。
9. **主仓 license**：Apache-2.0。
10. **MCP**：M1 只占位，M2 实现 22 工具。M1 不得声称 MCP 已可用。

---

## 2. M1 成功定义

完成后必须满足：

- `uv sync && uv run pytest && uv run ruff check .` 通过。
- `apps/web` 可 `pnpm install && pnpm lint && pnpm build`。
- CLI 全命令支持 `--json`，输出纯 JSON。
- CLI / API / Web 共用 `packages/core` 状态机。
- `render` 缺审批必失败 `APPROVAL_REQUIRED`。
- 审批后改 artifact 必失败 `APPROVAL_STALE`。
- `export --release` 遇 mock provider 必失败 `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`。
- 配置真实 LLM/TTS 后，`export --release` 成功产出 canonical 发布包。
- QA hard fail 能阻止 release。
- 输出 MP4 可 ffprobe，有音轨，分辨率等于 preset，中文帧内字幕非空，音画字时长一致。
- 五个平台 preset 可导出；平台差异只在 YAML，不写平台名 if 分支。
- 默认 CI 离线，不依赖真实模型、网络、GPU、API key。

---

## 3. 必须实现的仓库结构

```text
lingjian-video-studio/
├── LICENSE
├── README.md
├── DISCLAIMER.md
├── AGENTS.md
├── CLAUDE.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── package.json
├── pnpm-lock.yaml
├── apps/
│   ├── cli/lingjian_cli/
│   ├── api/lingjian_api/
│   └── web/
├── packages/
│   ├── schemas/
│   ├── core/
│   └── mcp_server/README.md
├── providers/
│   ├── base.py
│   ├── llm/
│   ├── tts/
│   ├── ocr/
│   ├── web_extract/
│   └── mock/
├── engines/
│   └── ffmpeg_card/
├── config/
│   ├── presets/
│   └── templates/
├── docs/
├── examples/
├── tests/
└── projects/
```

版本固定：

- Python 3.11 或 3.12，`.python-version`。
- Node 20 LTS，`package.json engines`。
- pnpm 版本写入 `packageManager`。
- 提交 `uv.lock` 和 `pnpm-lock.yaml`。

---

## 4. Batch 1：核心状态机 + schema + CLI + mock + doctor + approval hash

### 4.1 交付物

1. `packages/schemas`
   - Pydantic v2 权威 schema。
   - JSON Schema 导出。
   - 必含 `Approval`、`Project`、`InputAsset`、`ExtractedContent`、`VideoScript`、`VoicePlan`、`VisualPlan`、`RenderPlan`、`QAReport`、`ProviderManifest`、`ExportPackage`。

2. `packages/core`
   - `apply_event(project, event)` 作为唯一状态转移入口。
   - artifact 读写。
   - approval gate。
   - canonical JSON hash。
   - `APPROVAL_REQUIRED` / `APPROVAL_STALE`。
   - 文件为真值；SQLite 派生索引；`reindex`。

3. `providers`
   - Provider ABC：`id/name/kind/capabilities/is_mock/is_installed/is_configured/doctor/setup_hint/license_info`。
   - LLM / TTS / OCR / WebExtractor 抽象能力方法。
   - mock provider 全覆盖，`is_mock=True`。
   - provider 契约测试。

4. `apps/cli`
   - Typer CLI，命令完整，`--json` 纯 JSON。
   - approve 动词：`lj approve script|voice|visuals`。
   - `lj preview` 作为未审草稿路径。
   - 无 `render --force`。

5. `apps/api`
   - FastAPI 薄封装，调用 core，不复制状态机。

6. `doctor`
   - 检测 FFmpeg / ffprobe / Python / uv / Node / pnpm / 字体 / provider / trafilatura / Playwright / Remotion license 提示。
   - `--fix` 只做安全修复。

7. CI guard
   - 禁止 core / providers import remotion / hyperframes / playwright SDK。
   - 渲染路径只允许 `engines.ffmpeg_card`。
   - 默认 CI 不联网、不需要 GPU、不需要真实 key。

### 4.2 Batch 1 验收命令

```bash
uv sync
uv run pytest
uv run ruff check .
uv run lj doctor --json

rm -rf ./projects/b1
uv run lj init ./projects/b1 --name "批次1" --json
uv run lj ingest text ./projects/b1 --file examples/product_intro_zh.txt --json
uv run lj extract ./projects/b1 --provider mock --json
uv run lj script ./projects/b1 --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj render ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --json
```

最后一条必须失败：

```json
{"ok":false,"error_code":"APPROVAL_REQUIRED"}
```

审批后改脚本必须 stale：

```bash
uv run lj approve script ./projects/b1 --approved-by tester --json
uv run lj script ./projects/b1 --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj render ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --json
```

最后一条必须失败：

```json
{"ok":false,"error_code":"APPROVAL_STALE"}
```

reindex 必须可重建：

```bash
rm -f ./projects/b1/.lingjian/index.sqlite
uv run lj reindex ./projects/b1 --json
uv run lj status ./projects/b1 --json
```

---

## 5. Batch 2：真实 LLM/TTS + ffmpeg_card + QA + export

### 5.1 交付物

1. LLM provider
   - `openai_compatible`：自定义 `base_url` / `api_key` / `model`。
   - `anthropic`。
   - 输出必须经 Pydantic 校验，不合 schema 要重试或失败。

2. TTS provider
   - `edge_tts`：体验用，doctor 标注非官方在线依赖。
   - `openai_compatible_tts` 或一个云 TTS：生产推荐。
   - 同步阻塞实现，无异步队列。
   - 合成后用 `ffprobe` 实测每段时长。
   - 超时返回 `TTS_TIMEOUT`，provider 错误返回 `TTS_PROVIDER_ERROR`。

3. OCR provider
   - `rapidocr` 为 extras，可选。
   - 核心 `uv sync` 不拉 onnxruntime。

4. WebExtractor
   - `trafilatura>=1.8`，doctor 检测 license；旧 GPL 版本返回 `TRAFILATURA_LICENSE_BLOCKED`。
   - Playwright opt-in 截图，subprocess 调用，安装提示 `pip install playwright && playwright install`。
   - 默认不下载他人视频，不集成 yt-dlp 默认路径。

5. `ffmpeg_card`
   - 静态卡片帧。
   - 帧内字幕。
   - 图片 / 截图摆放。
   - scene 硬切。
   - concat。
   - FFmpeg finalizer。
   - 禁止 zoompan / Ken Burns / keyframe animation / shader / transition。

6. Preset
   - `douyin`、`xiaohongshu`、`bilibili`、`youtube`、`youtube_shorts`。
   - 9:16 / 16:9 一等支持；3:4 / 4:3 通过盒模型适配。
   - 渲染 / 导出代码不得写平台名 if。

7. QA
   - hard / warning / info 三级。
   - hard fail 阻止 release。
   - ffprobe 校验 MP4、分辨率、音轨、时长。
   - 中文帧内字幕非空。
   - source_map、敏感信息、平台风险。

8. Export
   - canonical 结构：`exports/<project>/<platform>/<language>/<ratio>/`。
   - 输出 `video.mp4`、cover/thumbnail、metadata、captions、source_map、qa_report、provider_manifest、license_manifest、export_manifest。
   - `export --release` 禁 mock。

### 5.2 Batch 2 验收命令

完成三审后，mock 可渲染 preview，但不能 release：

```bash
uv run lj voice ./projects/b1 --provider mock --voice test-voice --json
uv run lj approve voice ./projects/b1 --approved-by tester --json
uv run lj visuals ./projects/b1 --engine ffmpeg_card --template product --json
uv run lj approve visuals ./projects/b1 --approved-by tester --json
uv run lj render ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --json
uv run lj qa ./projects/b1 --json
uv run lj export ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --release --json
```

最后一条必须失败：

```json
{"ok":false,"error_code":"MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE"}
```

非 release 可导出 preview 包：

```bash
uv run lj export ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --json
test -d "exports/b1/douyin/zh-CN/9x16"
test -f "exports/b1/douyin/zh-CN/9x16/video.mp4"
test -f "exports/b1/douyin/zh-CN/9x16/provider_manifest.json"
test -f "exports/b1/douyin/zh-CN/9x16/license_manifest.md"
```

---

## 6. Batch 3：Next.js Web 控制台 + provider 配置 + docs + 跨平台 polish

### 6.1 交付物

1. Web 5 页
   - 新建向导。
   - 提取 + 文案审核。
   - 语音审核。
   - 画面审核。
   - 渲染 + 发布包，doctor/provider 作为设置抽屉。

2. Web 功能
   - 调 API，不复制状态机。
   - 三个主操作：批准、重新生成、手动编辑。
   - 生成后展示 `awaiting_review`。
   - 低清 preview。
   - release 前展示 QA、provider、license。

3. provider 配置页 / 抽屉
   - base_url、model、API key 状态、测试连通。
   - 日志与 UI 脱敏。

4. 跨平台 polish
   - Windows 中文路径。
   - 字体下载。
   - docker-compose。

5. 文档
   - README、installation、providers、render-engines、platform-presets、skill-and-mcp、license-notes、troubleshooting、AGENTS、CLAUDE、DISCLAIMER。

### 6.2 Batch 3 验收命令

```bash
cd apps/web
pnpm install
pnpm lint
pnpm build
cd ../..
uv run pytest -m web_smoke
```

web smoke 路径：

```text
新建 → 提取 → 审文案 → 审语音 → 审画面 → 渲染 → 发布包页可下载
```

---

## 7. CLI 命令必须完整实现

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

禁止出现：

```bash
lj render --force
lj export --force
LINGJIAN_SKIP_APPROVAL=1
```

---

## 8. 稳定错误码

所有 `--json` 失败输出结构：

```json
{
  "ok": false,
  "error_code": "ERROR_CODE",
  "message_zh": "中文错误说明",
  "hint": "下一步建议"
}
```

必须至少实现：

```text
INVALID_ARGUMENT
PROJECT_NOT_FOUND
PROVIDER_NOT_CONFIGURED
TOOL_NOT_INSTALLED
FFMPEG_NOT_FOUND
FONT_CJK_MISSING
APPROVAL_REQUIRED
APPROVAL_STALE
MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE
TTS_TIMEOUT
TTS_PROVIDER_ERROR
TRAFILATURA_LICENSE_BLOCKED
PATH_OUTSIDE_PROJECT
QA_BLOCKING
RENDER_FAILED
```

---

## 9. Artifact 与 hash 要求

### 9.1 必须输出的项目 artifact

```text
project.yaml
manifest.json
assets/input_assets.json
artifacts/extracted_content.json
artifacts/script.json
artifacts/voice_plan.json
artifacts/voice_segments/*
artifacts/visual_plan.json
artifacts/render_plan.json
artifacts/approvals.json
artifacts/source_map.json
artifacts/qa_report.json
artifacts/qa_report.md
artifacts/provider_manifest.json
artifacts/license_manifest.md
previews/*
output/*
```

### 9.2 approvals.json 示例

```json
{
  "script": {
    "target": "script",
    "artifact_path": "artifacts/script.json",
    "artifact_sha256": "...",
    "approved_by": "tester",
    "approved_at": "2026-07-01T00:00:00Z",
    "comment": null
  },
  "voice": {
    "target": "voice",
    "artifact_path": "artifacts/voice_plan.json",
    "artifact_sha256": "...",
    "approved_by": "tester",
    "approved_at": "2026-07-01T00:00:00Z",
    "comment": null
  },
  "visuals": {
    "target": "visuals",
    "artifact_path": "artifacts/visual_plan.json",
    "artifact_sha256": "...",
    "approved_by": "tester",
    "approved_at": "2026-07-01T00:00:00Z",
    "comment": null
  }
}
```

### 9.3 canonical JSON

实现 `canonical_json_hash(obj)`：

- UTF-8。
- key 排序。
- 去除非内容字段：`generated_at`、绝对路径、日志路径、临时缓存路径。
- voice hash 覆盖音频文件清单。

---

## 10. `ffmpeg_card` 实现约束

只能做：

```text
static PNG card per scene
burn subtitles into frame
place images/screenshots
hard cut scenes
optional one global fade-in/fade-out
concat
FFmpeg finalizer
```

禁止：

```text
zoompan
Ken Burns
keyframe animation
shader
transition library
per-element timeline animation
Remotion-like Python reimplementation
```

必须有静态扫描测试，发现上述词或对应 FFmpeg filter 时失败。

---

## 11. Preset 与 export

### 11.1 Preset

实现 5 个 YAML：

```text
config/presets/douyin.yaml
config/presets/xiaohongshu.yaml
config/presets/bilibili.yaml
config/presets/youtube.yaml
config/presets/youtube_shorts.yaml
```

字段必须覆盖：

```text
id/version/resolution/fps/safe_area/subtitle_style/title_style/export_files/qa_rules
```

渲染 / 导出代码不得出现平台名 if。写测试扫描：

```text
if platform ==
if preset.id == "douyin"
```

### 11.2 Export canonical structure

```text
exports/<project>/<platform>/<language>/<ratio>/
├── video.mp4
├── cover.png 或 thumbnail.png
├── metadata/publish.md 或 description.md/chapters.md
├── captions/subtitles.srt
├── captions/subtitles.vtt
├── captions/subtitles.ass
├── source_map.json
├── qa_report.json
├── qa_report.md
├── provider_manifest.json
├── license_manifest.md
└── export_manifest.json
```

导出后必须结构校验，缺文件失败。

---

## 12. QA 规则

hard fail：

- 文件缺失。
- MP4 不可播放。
- 分辨率不等于 preset。
- 无音轨。
- 音频、视频、字幕末尾时长偏差超过阈值。
- 中文帧内文字为空或疑似方块。
- 未处理占位符。
- release 含 mock。
- 三审缺失或 stale。

warning：

- 响度越界。
- 字幕越安全区。
- 敏感信息疑似。
- 平台风险词。
- source_map 覆盖率低。

info：

- 字数、scene 数、provider 列表、运行耗时。

`QAReport.release_ready` 必须真实反映 hard fail。

---

## 13. Web 控制台

实现 Next.js + TS + Tailwind + shadcn/ui。

页面为 5 页：

1. 新建向导。
2. 提取 + 文案审核。
3. 语音审核。
4. 画面审核。
5. 渲染 + 发布包，doctor/provider 为设置抽屉。

Web 必须调用 API；API 调 core。Web 不允许本地复制审批 / 状态机逻辑。

---

## 14. MCP 占位

M1 创建 `packages/mcp_server/README.md`，写明 22 工具清单和 M2 实现计划。若生成任何 MCP server 代码，所有工具必须返回：

```json
{"status":"not_implemented","since":"M2"}
```

不得让 M1 文档或 CLI 声称 MCP 已可用。

22 工具清单：

```text
lingjian.doctor
lingjian.create_project
lingjian.open_project
lingjian.get_project_status
lingjian.ingest_text
lingjian.ingest_url
lingjian.ingest_image
lingjian.extract_content
lingjian.generate_script
lingjian.approve_script
lingjian.generate_voice_preview
lingjian.approve_voice
lingjian.generate_visual_plan
lingjian.approve_visuals
lingjian.preview_video
lingjian.render_final
lingjian.qa_report
lingjian.export_package
lingjian.list_templates
lingjian.list_platforms
lingjian.list_providers
lingjian.install_tool
```

---

## 15. Doctor 必须覆盖

`lj doctor --json` 必须返回结构化结果，至少包含：

```text
ffmpeg/ffprobe
Python/uv
Node/pnpm
字体/CJK/Noto Sans SC 缓存
LLM provider
TTS provider
OCR extras
trafilatura version/license
Playwright CLI/browser
Remotion M3 opt-in license warning
HyperFrames M2 opt-in info
FFmpeg build/license flags
```

Remotion 提示文案必须显著：

```text
Remotion 是 M3 opt-in，不默认、不捆绑。4+ 人营利与自动化视频生成工具可能需要 Remotion company / Automators license，用户需自行确认。
```

---

## 16. 安全要求

必须实现或测试覆盖：

- `pathlib` 规范化，路径必须在项目沙盒内。
- 拒绝 `..`。
- 子进程用参数数组，不用 shell 拼接。
- API key 脱敏。
- 上传校验 MIME / 大小 / 扩展名。
- URL 内容视为 untrusted input，不执行网页指令。
- release 包不包含 API key、环境变量、私密绝对路径。

---

## 17. 文档要求

必须写中文优先文档：

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

- `hyperframes-motion-director`：只研究流程思想，不引入 AGPL 代码 / prompt / template / UI。
- LosslessCut / pyVideoTrans：GPL 风险，只研究不引入。
- VideoLingo：不复制下载他人视频 / 搬运模式。
- Remotion：M3 opt-in，不默认、不捆绑。
- 模型权重：不捆绑，用户确认 license。
- 字体：不入仓，缓存下载，记录 license。

---

## 18. 明确不做

M1 不做：

```text
ASR / Whisper / WhisperX / FunASR
上传已有音视频转写
本地 TTS 大模型
声音克隆
HyperFrames adapter
Remotion adapter
MCP 完整实现
Skill 完整实现
复杂 motion / transition
传统 timeline editor
Tauri 桌面端
Redis/Postgres/任务队列
插件市场
默认下载他人视频
AGPL/GPL 代码或 prompt/template/UI 复制
```

---

## 19. 最终验收命令全集

### 19.1 基础质量

```bash
uv sync
uv run pytest
uv run ruff check .
uv run pyright || true
uv run lj doctor --json

cd apps/web
pnpm install
pnpm lint
pnpm build
cd ../..
```

`pyright` 建议核心 strict、全仓 basic；第三方 stub 缺失不阻断 M1，但 core/schemas 类型错误不能放行。

### 19.2 审批门禁

```bash
rm -rf ./projects/m1_gate_test
uv run lj init ./projects/m1_gate_test --name "门禁测试" --json
uv run lj ingest text ./projects/m1_gate_test --file examples/product_intro_zh.txt --json
uv run lj extract ./projects/m1_gate_test --provider mock --json
uv run lj script ./projects/m1_gate_test --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj render ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --json
```

必须失败：`APPROVAL_REQUIRED`。

```bash
uv run lj approve script ./projects/m1_gate_test --approved-by tester --json
uv run lj voice ./projects/m1_gate_test --provider mock --voice test-voice --json
uv run lj approve voice ./projects/m1_gate_test --approved-by tester --json
uv run lj visuals ./projects/m1_gate_test --engine ffmpeg_card --template product --json
uv run lj approve visuals ./projects/m1_gate_test --approved-by tester --json
uv run lj render ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --json
uv run lj qa ./projects/m1_gate_test --json
```

此时 render 成功，产出 preview/output MP4。

审批 stale 测试：

```bash
uv run lj script ./projects/m1_gate_test --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj render ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --json
```

必须失败：`APPROVAL_STALE`。

### 19.3 mock 不能 release

```bash
uv run lj export ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --release --json
```

必须失败：`MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`。

### 19.4 canonical export 结构

```bash
uv run lj export ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --json

test -d "exports/m1_gate_test/douyin/zh-CN/9x16"
test -f "exports/m1_gate_test/douyin/zh-CN/9x16/video.mp4"
test -f "exports/m1_gate_test/douyin/zh-CN/9x16/captions/subtitles.srt"
test -f "exports/m1_gate_test/douyin/zh-CN/9x16/captions/subtitles.vtt"
test -f "exports/m1_gate_test/douyin/zh-CN/9x16/captions/subtitles.ass"
test -f "exports/m1_gate_test/douyin/zh-CN/9x16/source_map.json"
test -f "exports/m1_gate_test/douyin/zh-CN/9x16/qa_report.json"
test -f "exports/m1_gate_test/douyin/zh-CN/9x16/qa_report.md"
test -f "exports/m1_gate_test/douyin/zh-CN/9x16/provider_manifest.json"
test -f "exports/m1_gate_test/douyin/zh-CN/9x16/license_manifest.md"

uv run lj export ./projects/m1_gate_test --platform youtube --language en-US --ratio 16:9 --json
test -f "exports/m1_gate_test/youtube/en-US/16x9/thumbnail.png"
test -f "exports/m1_gate_test/youtube/en-US/16x9/description.md"
test -f "exports/m1_gate_test/youtube/en-US/16x9/chapters.md"
```

### 19.5 真实 provider release 路径

```bash
export LINGJIAN_LLM_PROVIDER=openai_compatible
export OPENAI_BASE_URL=...
export OPENAI_API_KEY=...
export OPENAI_MODEL=...
export LINGJIAN_TTS_PROVIDER=edge_tts
# 生产推荐替代：openai_compatible_tts 或云 TTS provider

rm -rf ./projects/m1_real_test
uv run lj init ./projects/m1_real_test --name "真实链路测试" --json
uv run lj ingest text ./projects/m1_real_test --file examples/product_intro_zh.txt --json
uv run lj extract ./projects/m1_real_test --provider local --json
uv run lj script ./projects/m1_real_test --provider openai_compatible --platform douyin --language zh-CN --ratio 9:16 --duration 45 --json
uv run lj approve script ./projects/m1_real_test --approved-by human --json
uv run lj voice ./projects/m1_real_test --provider edge_tts --voice zh-CN-XiaoxiaoNeural --json
uv run lj approve voice ./projects/m1_real_test --approved-by human --json
uv run lj visuals ./projects/m1_real_test --engine ffmpeg_card --template product --json
uv run lj approve visuals ./projects/m1_real_test --approved-by human --json
uv run lj render ./projects/m1_real_test --platform douyin --language zh-CN --ratio 9:16 --json
uv run lj qa ./projects/m1_real_test --json
uv run lj export ./projects/m1_real_test --platform douyin --language zh-CN --ratio 9:16 --release --json
```

必须成功，并产出 release 包；`provider_manifest.json` 不含 mock；`qa_report.json.release_ready=true`。

多平台 / 多语言抽验：

```bash
uv run lj export ./projects/m1_real_test --platform xiaohongshu --language zh-CN --ratio 3:4 --release --json
uv run lj export ./projects/m1_real_test --platform bilibili --language zh-CN --ratio 16:9 --release --json
uv run lj export ./projects/m1_real_test --platform youtube --language en-US --ratio 16:9 --release --json
uv run lj export ./projects/m1_real_test --platform youtube_shorts --language en-US --ratio 9:16 --release --json
```

### 19.6 URL 合规

```bash
rm -rf ./projects/m1_url_test
uv run lj init ./projects/m1_url_test --name "URL 合规测试" --json
uv run lj ingest url ./projects/m1_url_test --url "https://example.com/article" --json
uv run lj extract ./projects/m1_url_test --provider trafilatura --json
```

要求：

- 不下载视频流。
- 不调用 yt-dlp。
- artifact 标注 `is_untrusted_input=true`。

截图 opt-in：

```bash
uv run lj ingest url ./projects/m1_url_test --url "https://example.com/article" --screenshot --json
```

只有带 `--screenshot` 才调用 Playwright subprocess。

### 19.7 中文路径

```bash
rm -rf "./projects/中文 路径 测试"
uv run lj init "./projects/中文 路径 测试" --name "中文路径" --json
uv run lj ingest text "./projects/中文 路径 测试" --file examples/product_intro_zh.txt --json
uv run lj extract "./projects/中文 路径 测试" --provider mock --json
uv run lj script "./projects/中文 路径 测试" --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
```

必须通过，不得路径乱码。

### 19.8 禁止伪成功扫描

必须提供测试或脚本检查：

```text
无 --force / SKIP_APPROVAL / bypass
mock release 必失败
core/providers 不 import remotion/hyperframes/playwright SDK
ffmpeg_card 无 zoompan/Ken Burns/keyframe/shader/transition
render/export 无平台名 if
CI 不依赖网络/GPU/真实 key
SQLite 可 reindex
AGPL/GPL 代码/prompt/template/UI 未复制
```

---

## 20. Definition of Done

M1 只有全部满足才算完成：

1. 三批交付物全部实现。
2. 所有验收命令通过；真实 provider 路径在有 key 时通过。
3. 6 个 Blocker 测试全部通过：审批 hash、无 force、release 禁 mock、文件真值、import guard、ffmpeg_card scope freeze。
4. 12 个 High 均有代码或测试落实。
5. Web 5 页可完成主路径。
6. 文档完整，中文优先。
7. release 包结构完整，含 provider/license manifest。
8. 无伪成功扫描项。
9. 不违反 Apache-2.0 主仓边界。
