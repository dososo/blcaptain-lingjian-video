# 03 计划

日期: 2026-07-01

## 总策略

按资产包要求执行 8 步流程,但实现阶段采用 3 个真实增量批次。每批都必须有可运行命令、测试与证据,不得用 mock 冒充 release,不得跳过门禁,不得把未实现能力写成已完成。

## 文件结构计划

```text
LICENSE
README.md
DISCLAIMER.md
AGENTS.md
CLAUDE.md
pyproject.toml
uv.lock
.python-version
package.json
pnpm-lock.yaml
apps/
  cli/lingjian_cli/
  api/lingjian_api/
  web/
packages/
  schemas/
  core/
  mcp_server/README.md
providers/
  base.py
  mock/
  llm/
  tts/
  ocr/
  web_extract/
engines/
  ffmpeg_card/
config/
  presets/
  templates/
scripts/
  ci/
docs/
examples/
tests/
projects/
verification/
```

## Batch 1:核心状态机 + CLI/API + mock + doctor + 门禁

目标:Agent 可通过 CLI 跑到生成脚本并被 render 门禁拦住;审批后改稿能 stale;SQLite 可重建;doctor 具备 required/optional 语义。

开发项:

- 创建 Python/Node 基础工程与 lockfile。
- 写 `packages/schemas` 核心模型与 JSON Schema 导出。
- 写 `packages/core` artifact 管理、canonical hash、history、状态机、approval gate、reindex。
- 写 Provider ABC 和 mock LLM/TTS/OCR/web_extract。
- 写 Typer CLI 命令骨架与稳定 JSON 错误输出。
- 写 FastAPI 薄封装。
- 写 doctor required/optional 检查、provider 能力分层、CLI/key 安全引导与 exit code 语义。
- 写 CI guard:无 force、import guard、render engine guard、provider 契约。

验证:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run lj doctor --json
uv run lj init ./projects/b1 --name "批次1" --json
uv run lj ingest text ./projects/b1 --file examples/product_intro_zh.txt --json
uv run lj extract ./projects/b1 --json
uv run lj script ./projects/b1 --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj render ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --json
uv run lj approve script ./projects/b1 --approved-by tester --json
uv run lj script ./projects/b1 --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj render ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --json
uv run lj reindex ./projects/b1 --json
uv run lj status ./projects/b1 --json
```

预期:

- 第一次 render 返回 `APPROVAL_REQUIRED`。
- 改稿后 render 返回 `APPROVAL_STALE`。
- `doctor --json` required 缺失 exit 非 0,仅 optional 缺失 exit 0。
- `doctor --json` 区分 CLI provider、API key provider、Codex host/mock/template 状态;CLI provider 可用时不强制 key,无真实 provider 能力时给 `BLOCKED_ENV` 可用的配置引导。
- 静态扫描无 `--force`、`SKIP_APPROVAL`、`BYPASS_APPROVAL` 可用路径。

## Batch 2:真实 provider 接口 + ffmpeg_card + QA + export

目标:三审后可生成 mock preview MP4,非 release 可导出 canonical 包;release 遇 mock 必失败;真实 provider 有 key 时可 release,无 key 标 `BLOCKED_ENV`。

开发项:

- 实现 OpenAI-compatible / Anthropic LLM provider 与错误分类。
- 实现 EdgeTTS / OpenAI-compatible TTS provider 接口,同步合成,ffprobe 实测时长。
- 实现 trafilatura extract、Playwright opt-in subprocess、RapidOCR extras 占位/可选。
- 实现 `ffmpeg_card` 静态卡片、CJK 断行、帧内字幕、concat、finalizer。
- 实现 renders/preview 与 renders/release 物理隔离、`render_manifest.json`。
- 实现 QA hard/warn/info 与 `release_ready`。
- 实现 canonical export、`provider_manifest`、`license_manifest`、`export_manifest.approvals`。
- 实现 5 平台 preset 与平台名 if 扫描。
- 实现稀薄输入 warn 引导。

验证:

```bash
uv run lj voice ./projects/b1 --provider mock --voice test-voice --json
uv run lj approve voice ./projects/b1 --approved-by tester --json
uv run lj visuals ./projects/b1 --engine ffmpeg_card --template product --json
uv run lj approve visuals ./projects/b1 --approved-by tester --json
uv run lj render ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --json
uv run lj qa ./projects/b1 --json
uv run lj export ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --release --json
uv run lj export ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --json
```

预期:

- release 导出返回 `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`。
- 非 release 导出含完整 canonical 结构。
- 引用 preview 产物走 release 返回 `PREVIEW_ARTIFACT_NOT_RELEASABLE`。
- QA 能检查 MP4、分辨率、音轨、非全黑、中文帧内非空、时长一致。

## Batch 3:Web 控制台 + 文档 + 跨平台 polish

目标:非开发者可在 Web 走同一条主路径;文档、license 与 troubleshooting 完整。

开发项:

- 初始化 `apps/web` Next.js + TS + Tailwind。
- 做 5 页:新建向导、提取+文案审核、语音审核、画面审核、渲染+发布包。
- 每屏保留 3 主按钮:批准、重新生成、手动编辑。
- 右侧低清 preview,状态含 empty/loading/awaiting_review/stale/error/degraded/success。
- provider 配置抽屉,key 状态脱敏。
- 写 README、installation、providers、render-engines、platform-presets、skill-and-mcp、license-notes、troubleshooting、AGENTS、CLAUDE、DISCLAIMER。
- 中文路径、字体下载、docker-compose 与 Web smoke。

验证:

```bash
cd apps/web
pnpm install
pnpm lint
pnpm build
cd ../..
uv run pytest -m web_smoke
```

预期:

- Web build 通过。
- smoke 跑通新建→提取→审文案→审语音→审画面→渲染→发布包页。
- 文档明确 M1/M2/M3 边界和合规红线。

## 验证与证据产物

- `verification/results.json`:每项包含 id、title、command、expect、exit_code、error_code、pass、evidence_file、notes。
- `verification/evidence/*.log`:完整命令、stdout、stderr、exit code。
- `verification/VERIFICATION_REPORT.md`:按 V 项总结。
- `verification/FORBIDDEN_SCAN.md`:13 条伪成功代码扫描。
- `docs/dev/AUDIT_READY.md`:DoD §20 + R1-R10 落点表。
- `docs/dev/08_SUMMARY.md`:结论、完成度、PASS/FAIL/BLOCKED_ENV、delta。

## 进入开发前确认

确认后我将先执行 Batch 1,不并行跳到 Batch 2/3。若 Batch 1 验证不绿,先修到绿再继续。
