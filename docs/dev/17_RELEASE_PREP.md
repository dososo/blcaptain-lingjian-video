# 17 M1 开源发布准备说明

日期:2026-07-02

## 范围

本轮是 M1 封版后的发布准备,不修改已通过 Claude 第 7 步复审的功能与门禁语义。

## 已完成

- 版本对齐:`pyproject.toml`、根 `package.json`、`apps/web/package.json` 均为 `0.1.0`。
- 发布记录:新增 `CHANGELOG.md`,复用 `docs/dev/16_CLOSING.md` 的 M1 收官结论。
- 后续计划:新增 `ROADMAP.md`,把 MCP server、Web API 接入、更多真实 provider、平台知识包列入 M2。
- 隐私安全:README 补充数据默认本地、key 默认不落盘、CLI 继承不读取凭据文件、可选依赖审计说明。
- 跨平台说明:README 与 `docs/ONBOARDING.md` 补充 macOS/Linux/Windows 的 FFmpeg `drawtext` 自检与 TTS 路径。
- 忽略规则:`.gitignore` 排除 `.env*`、`.lingjian/`、`projects/`、`exports/`、`.venv/`、`node_modules/` 与构建缓存。
- 首用自检:用本地仓库作为 clean clone 源,按 README 顶部流程执行 `uv sync`、`scripts/install_skill_links.sh`、`uv run lj setup`、`uv run lj doctor --json`,并用 `lj run --yes` 跑通预览档 render -> QA -> export。
- 验证矩阵:`run_verification.py`、pytest、ruff、5 个扫描器、Web lint/build 均已通过。

## 阻塞项

本地仓库当前没有 `git remote`,因此无法确认真实开源仓库地址。`README.md` 中的 `<REPO_URL>` 需要在用户提供地址后替换,再创建最终发布 tag。

## 发布前自检要求

- 已在干净 clone 中完成 `uv sync`、`scripts/install_skill_links.sh`、`uv run lj setup`、`uv run lj doctor --json`。
- 已用预览档最小 demo 跑到 render/QA/export,证明新用户零 key 路径可复现。
- 已重跑 `uv run python scripts/ci/run_verification.py`,主 `verification/results.json` 为 52 PASS / 0 FAIL。
- 已重跑 pytest、ruff、5 个扫描器、Web lint/build。

## 证据落点

- 主验证:`verification/results.json`
- 真实 PASS 快照:`verification/results.real_pass_20260702.json`
- 离线回落快照:`verification/results.offline_fallback_20260702.json`
- 首用自检日志:`verification/release_prep/`

## 本轮命令结果

- `uv run python scripts/ci/run_verification.py`:failures=0,`verification/results.json` 为 52 PASS。
- `uv run pytest -q`:83 passed。
- `uv run ruff check .`:通过。
- `uv run python scripts/ci/check_false_success.py`:13 项 PASS。
- `uv run python scripts/ci/check_no_force.py`:通过。
- `uv run python scripts/ci/check_forbidden_imports.py`:通过。
- `uv run python scripts/ci/check_render_engine_m1.py`:通过。
- `uv run python scripts/ci/check_ffmpeg_card_scope.py`:通过。
- `pnpm --dir apps/web lint`:通过。
- `pnpm --dir apps/web build`:通过。
