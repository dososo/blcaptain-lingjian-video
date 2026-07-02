# 01 调研

日期: 2026-07-01

## 资产读取结果

- 已读根目录最终文件: `README_FINAL.md`、`00_PRODUCT_DEFINITION_FINAL.md`、`01_UX_AND_BUSINESS_FLOW_FINAL.md`、`02_PRD_GOAL_REFINEMENTS.md`、`03_CODEX_M1_EXECUTION_PROMPT_8STEP.md`。
- 已读权威基线: `lingjian_M1_FINAL_after_claude_final_audit/base/LINGJIAN_M1_GOAL_ACCEPTED_BASE.md`、`lingjian_M1_FINAL_after_claude_final_audit/base/LINGJIAN_M1_PRD_ACCEPTED_BASE.md`。
- 已读审计参考: `reference/CHATGPT_AUDIT_RESPONSE_MATRIX.md`、`reference/CHATGPT_BLOCKER_RESOLUTIONS.md`、`reference/final-audit/00..08`。
- 同名副本 hash 已核对一致;实现时以根目录最终文件与子目录 `base/`、`reference/` 为准。

## 实现目标

实现 LingJian Video Studio M1 纵向主干:

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

M1 不是 demo,也不是 mock-only。mock 只允许测试、预览和非 release 导出;`export --release` 遇 mock 必须失败。

## 待实现模块清单

| 模块 | 责任 |
|---|---|
| `packages/schemas` | Pydantic v2 权威 schema、JSON Schema 导出、错误码、artifact 模型 |
| `packages/core` | 状态机、artifact 读写、canonical hash、approval gate、history、reindex、QA/release 判定 |
| `providers` | Provider ABC、mock、LLM、TTS、OCR extras、web extractor、doctor 生命周期 |
| `engines/ffmpeg_card` | 静态卡片渲染、帧内字幕、CJK 断行、concat、FFmpeg finalizer |
| `apps/cli` | Typer CLI,全命令 `--json`,稳定错误码,无 `--force` |
| `apps/api` | FastAPI 薄封装,只调用 core |
| `apps/web` | Next.js 5 页控制台,调用 API,不复制状态机 |
| `config/presets` | 5 平台 YAML,平台差异纯配置 |
| `scripts/ci` | import guard、scope scan、preset scan、forbidden scan |
| `docs` | 中文优先安装、provider、渲染、preset、MCP 占位、license、troubleshooting |
| `verification` | 命令证据、结果 JSON、审计报告 |

## 依赖与 license 初表

| 依赖/工具 | 用途 | M1 口径 | license/风险 |
|---|---|---|---|
| Python 3.11/3.12 | core/CLI/API/providers | 固定 `.python-version` | Python PSF |
| uv | Python 环境与 lock | 提交 `uv.lock` | 宽松 |
| Pydantic v2 | schema | 核心依赖 | MIT |
| Typer | CLI | 核心依赖 | MIT |
| FastAPI | API | 核心依赖 | MIT |
| SQLite | 派生索引 | 文件为真值,SQLite 可重建 | Public domain |
| FFmpeg/ffprobe | 渲染与 QA | 系统安装,subprocess 调用 | LGPL/GPL 取决 build;记录 build |
| Pillow | 生成静态 PNG 卡片 | 核心渲染依赖 | HPND |
| trafilatura >=1.8 | URL 正文提取 | license 检测,GPL 阻断 | Apache-2.0 口径;旧 GPL 风险 |
| Playwright CLI/helper | opt-in 截图 | subprocess,opt-in;不进 core/provider SDK import | Apache-2.0;浏览器另计 |
| EdgeTTS | 体验 TTS | doctor 标注非官方在线,不作为生产唯一依赖 | 条款/稳定性风险 |
| OpenAI-compatible LLM/TTS | 真实 provider | 用户配置 key/base_url/model | 由服务商条款决定 |
| Anthropic provider | 真实 LLM | 用户配置 key/model | 由服务商条款决定 |
| RapidOCR/onnxruntime | OCR extras | 不进核心 `uv sync`;仅 `extra=ocr` | 需按实际包确认 |
| Next.js/React/TypeScript | Web 控制台 | Node 20,pnpm lock | MIT |
| Tailwind/shadcn/ui | Web UI | 仅 Web | MIT |
| Noto Sans SC | CJK 字体 | 不入仓,doctor 下载到缓存 | SIL OFL |

## 合规红线

- 主仓 Apache-2.0。
- AGPL/GPL 项目只研究,不复制代码、prompt、template、UI,不 vendor。
- `hyperframes-motion-director`、OpenMontage、LosslessCut、pyVideoTrans 按禁入处理。
- Remotion 不默认、不捆绑;M3 opt-in,doctor 强 license 提示。
- URL 默认不下载他人视频,不引入 yt-dlp 默认路径。
- 不捆绑模型权重和字体;本地模型/权重进入 M3 外部服务。
- release 包不得包含 API key、环境变量、私密绝对路径。

## 环境需求

- Python 3.11 或 3.12。
- Node 20 LTS。
- pnpm,版本写入 `packageManager`。
- uv。
- FFmpeg 和 ffprobe。
- CJK 字体;缺失时 doctor 下载 Noto Sans SC 到用户缓存。
- 可选:Playwright CLI/browser、OCR extras、真实 LLM/TTS key。

## 模型与能力接入 UX

安装初始化必须做能力分层检查:

- 宿主能力:Codex/Claude Code 可主持流程,但不等于用户已经配置真实外部模型。
- CLI provider:如果本机已有可调用 CLI 模型,优先引导使用 CLI,不强制 API key。
- OpenAI-compatible / Anthropic / 云 TTS key:只有业务路径必须走真实远端 provider 时才要求配置。
- mock/template 示例只能用于测试和预览,不能计入 release-ready。

密钥安全规则:

- `doctor --json` 只输出脱敏状态,不输出原文 key。
- 日志、artifact、verification、release 包不得包含 key、环境变量值或私密绝对路径。
- provider 配置错误要给出可执行引导:缺 key、缺 base_url、CLI 不存在、CLI 退出非 0、模型未配置分别返回稳定状态。
- 真实 key 不存在时,真实 release 验收标 `BLOCKED_ENV`;如果用户提供 CLI provider 且满足 release 真实 provider 语义,则可不要求 API key。

## 置顶外部阻塞

`V-REAL-01` 真实 LLM/TTS release 路径需要真实 provider 能力。真实 provider 可以来自安全配置的 CLI provider 或 API key provider;若两者都缺,必须在 `verification/results.json` 和最终总结中标 `BLOCKED_ENV`,不得标 PASS,并输出配置引导。
