# 23 开源发布收尾说明

日期:2026-07-02

## 发布仓库

- GitHub 仓库: https://github.com/dososo/blcaptain-lingjian-video
- Git remote: `origin https://github.com/dososo/blcaptain-lingjian-video.git`
- 可见性:当前按用户要求为 `PRIVATE`;公开发布前需再切回 public 或确认仅授权用户分发。
- 发布 tag:`v0.1.0`。

## 整改项

### P0-1 替换 `<REPO_URL>`

改动:

- `README.md`:把安装 prompt 中的 `git clone <REPO_URL>` 替换为 `git clone https://github.com/dososo/blcaptain-lingjian-video.git ~/Developer/lingjian-video`。
- `README.md`:把 skills.sh 示例替换为 `npx skills add https://github.com/dososo/blcaptain-lingjian-video.git --skill lingjian-video`。
- `README.md`:保留 fork 用户说明,提示自建/fork 仓库可替换成自己的仓库地址。

验证:

- `grep -R "<REPO_URL>" README.md SKILL.md docs/CREATOR_QUICKSTART.md docs/ONBOARDING.md docs/CAPABILITY_MATRIX.md`:无输出。
- `gh repo view dososo/blcaptain-lingjian-video --json nameWithOwner,visibility,url`:PUBLIC。

### P1-1 校准画面插件安装标识符

改动:

- `SKILL.md`:保留 `npx skills add heygen-com/hyperframes` 与 `npx skills add remotion-dev/skills`,并说明入口变化时以官方文档或 Codex 插件市场为准。
- `docs/CREATOR_QUICKSTART.md`、`docs/ONBOARDING.md`、`docs/CAPABILITY_MATRIX.md`:补 HyperFrames 与 Remotion 官方文档入口。
- `packages/core/capabilities.py`:缺画面能力时的 next step 同步说明“若入口变化,以官方文档和 Codex 插件市场为准”。

依据:

- HyperFrames Quickstart: https://hyperframes.heygen.com/quickstart
- Remotion Agent Skills: https://www.remotion.dev/docs/ai/skills

### P2-1 README Web 段就地免责

改动:

- `README.md`:在项目能力总述中补“Web 控制台当前为静态骨架,不能替代 CLI 审批流”。
- `README.md`:在 Web 控制台命令段前补同口径免责,并指向 `docs/CAPABILITY_MATRIX.md`。

### P2-2 `--strict`

本轮不做。原因:

- 该项会改变 QA/export 行为,属于可选增强。
- 当前发布收尾目标是不改已通过主线/门禁。
- 默认 warning 语义保持不变: `RELEASE_VISUAL_IS_BLANK_CARD` 与 `RELEASE_AUDIO_IS_PREVIEW_VOICE` 仍为 warning,不伪装发布质量。

## 保持的边界

- 不实现 MCP server。
- 不做完整 Web 审批控制台。
- 不 import/bundle Remotion/HyperFrames SDK。
- 不做爆款算法、平台知识包、声音克隆、ASR、默认视频下载。
- 不削弱 mock/stub/ffprobe/音频流/三审/key 脱敏/用户录音无路径泄漏等门禁。

## 验收结果

- `uv run pytest -q`:99 passed。
- `uv run ruff check .`:All checks passed。
- 5 个扫描器:`check_false_success.py` / `check_no_force.py` / `check_forbidden_imports.py` / `check_render_engine_m1.py` / `check_ffmpeg_card_scope.py` 均 exit=0。
- `pnpm --dir apps/web lint`:通过。
- `pnpm --dir apps/web build`:通过。首次构建在 Next standalone copy 阶段出现一次 `.next` 瞬态 ENOENT,重跑通过。
- `uv run python scripts/ci/run_verification.py`:通过,`verification/results.json` 为 52 PASS / 0 FAIL。
- `git diff --check`:通过。

## 发布后干净机自检

已在临时 `HOME` 中执行,避免改写当前用户真实 skill 软链:

```bash
git clone https://github.com/dososo/blcaptain-lingjian-video.git /tmp/lingjian-video-clean
cd /tmp/lingjian-video-clean
uv sync
scripts/install_skill_links.sh
uv run lj setup
uv run lj run ./projects/demo --name "演示项目" --input-file examples/product_intro_zh.txt --yes --json
```

自检结论:通过。干净 clone 可按 README 主线完成 `uv sync`、安装 skill 软链、`lj setup`、mock 预览档 `lj run --yes`、QA 与 export。

证据:

- `verification/release_closing/clean_clone_path.txt`
- `verification/release_closing/install_skill_links.txt`
- `verification/release_closing/setup.txt`
- `verification/release_closing/preview_run.json`
- `verification/release_closing/preview_qa.json`
- `verification/release_closing/preview_export.json`
