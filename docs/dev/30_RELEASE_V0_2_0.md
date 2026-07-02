# v0.2.0 封版发布说明

日期:2026-07-03

## 结论

- 本轮只做封版收尾,未新增主线功能,未削弱 mock/stub/release QA/三审/`--strict`/key 脱敏等门禁。
- 版本已提升到 `0.2.0`;HyperFrames 场景 HTML 不再暴露 `motion_spec.main` 的原始 motion 基元字面。
- 本机已复现零 key 发布级链路:HyperFrames 逐镜真实动态画面 + Kokoro 中文本地配音 + 底部安全区字幕,`--release --strict` 通过,QA 0 warning。

## 改动文件与行锚点

- `scripts/providers/hyperframes_scene_cli.py:23`:新增 `ACCENT_LABELS`,用有意义中文短标签替代原始 motion 基元。
- `scripts/providers/hyperframes_scene_cli.py:129`:HTML 的 `data-motion` 改为 `layout-*`,不再写入 `kinetic_pan` / `kenburns_zoom_in` 等原始基元。
- `scripts/providers/hyperframes_scene_cli.py:328`: `_accent_word()` 只返回中文 accent label,不读取 `motion_spec.main`。
- `tests/test_ecosystem_integration.py:151`:新增 `test_hyperframes_scene_html_does_not_expose_raw_motion_primitive`,断言渲染 HTML 不含 `kinetic_pan`、`kinetic`、`kenburns_zoom_in`。
- `pyproject.toml:3`、`.codex-plugin/plugin.json:3`、`package.json:3`、`apps/web/package.json:3`:版本统一为 `0.2.0`;`uv.lock` 与 `lingjian_video_studio.egg-info/PKG-INFO` 已由 `uv lock` / `uv run` 同步。
- `CHANGELOG.md:3`:新增 `v0.2.0 - Codex 发布级 Skill 封版`,记录零 key HyperFrames/Kokoro、`--strict`、底部字幕、plugin 化与诚实边界。
- `docs/dev/AUDIT_READY.md:140`:将 v0.1.0 发布准备段标记为历史口径,避免和当前 v0.2.0 封版混淆。

## 自动验证

- `uv run pytest -q`:112 passed。
- `uv run ruff check .`:通过。
- `uv run python scripts/ci/check_false_success.py`:13 项 PASS。
- `uv run python scripts/ci/check_no_force.py`:通过。
- `uv run python scripts/ci/check_forbidden_imports.py`:通过。
- `uv run python scripts/ci/check_render_engine_m1.py`:通过。
- `uv run python scripts/ci/check_ffmpeg_card_scope.py`:通过。
- `pnpm --dir apps/web lint`:通过。
- `pnpm --dir apps/web build`:通过。
- `uv run python scripts/ci/run_verification.py`:写入 `verification/results.json`,结果为 52 PASS / 0 FAIL。
- `git diff --check`:通过。

## 零 key 发布级成片复现

命令:

```bash
uv run lj run ./projects/release_v0_2_0_verify_20260703 \
  --name v0.2.0封版验收 \
  --input-file examples/product_intro_zh.txt \
  --script-provider auto \
  --voice-provider auto \
  --release \
  --strict \
  --yes \
  --approved-by codex-v0.2.0 \
  --json
```

结果:

- 导出目录:`exports/release_v0_2_0_verify_20260703/douyin/zh-CN/9x16`。
- 视频:`projects/release_v0_2_0_verify_20260703/renders/release/douyin/video.mp4`。
- QA:`release_ready=true`,`hard_failures=[]`,`warnings=[]`。
- render manifest:`visual_total=6`,`visual_real_count=6`,6 个 scene 均为 `render_source=video`,provider 为 `claude_cli`、`kokoro_zh_tts`、`delegated_scene_assembly`,均 `is_mock=false`。
- ffprobe:`video=h264 1080x1920 duration=45.000000`,`audio=aac duration=44.971000`。
- release 包泄漏扫描:`provider_manifest.json`、`license_manifest.md`、`export_manifest.json` 未命中 `api_key`、`access_token`、`base_url`、本机绝对路径或私密环境变量名。

抽帧证据:

- `verification/release_v0_2_0_frames/frame_02.png`:痛点版式,画面仅短关键词,底部字幕承载全文。
- `verification/release_v0_2_0_frames/frame_05.png`:证明版式,与痛点版式明显不同。
- `verification/release_v0_2_0_frames/frame_06.png`:CTA 版式,底部字幕位于安全区。
- 人工核查:抽帧未出现 `kinetic` / `kinetic_pan` 等原始 motion 基元字样。

## Codex Plugin / Skill 烟测

- `.codex-plugin/plugin.json` 当前版本为 `0.2.0`。
- `scripts/install_skill_links.sh` 已刷新软链:
  - `/Users/manxiaochu/.agents/skills/lingjian-video -> /Users/manxiaochu/Documents/Codex/lingjian-video`
  - `/Users/manxiaochu/.claude/skills/lingjian-video -> /Users/manxiaochu/Documents/Codex/lingjian-video`
- 只读 Codex 触发命令:

```bash
codex exec --ephemeral -s read-only -C /Users/manxiaochu/Documents/Codex/lingjian-video \
  "只做只读触发验证: 当用户说『用 lingjian-video 帮我做一条抖音短视频』时,你会触发哪个 skill? 下一步进入哪个阶段? 只输出两行: skill=... 和 phase=..."
```

输出:

```text
skill=lingjian-video:lingjian-video
phase=视频需求澄清阶段
```

远端 marketplace 复核:

- `codex plugin marketplace upgrade blcaptain-lingjian-video`:成功刷新 GitHub marketplace snapshot。
- `codex plugin add lingjian-video@blcaptain-lingjian-video --json`:返回 `version=0.2.0`,`installedPath=/Users/manxiaochu/.codex/plugins/cache/blcaptain-lingjian-video/lingjian-video/0.2.0`。
- `codex plugin list`:显示 `lingjian-video@blcaptain-lingjian-video installed, enabled 0.2.0`。
- 升级后再次执行只读触发烟测,输出仍为:

```text
skill=lingjian-video:lingjian-video
phase=视频需求澄清阶段
```

## 干净态首用自检

- 干净 clone 路径:`/tmp/lingjian-v020-clean-oibJpM/blcaptain-lingjian-video`。
- clone 来源:本地 git 提交 `f2459fd`,用于验证待发布内容在干净目录可安装运行。
- 执行:
  - `uv sync`:成功,安装 `lingjian-video-studio==0.2.0`。
  - `scripts/install_skill_links.sh`:成功创建 Codex/Claude skill 软链。
  - `uv run lj setup`:成功,显示已继承/检测到 Claude Code CLI、Kokoro 中文本地 TTS、HyperFrames、FFmpeg/ffprobe、中文字体;必须补齐项为“无”。
  - `uv run lj run ./projects/clean_preview --name 干净态预览 --input-file examples/product_intro_zh.txt --script-provider mock --voice-provider mock --yes --json`:成功。
  - `uv run lj qa ./projects/clean_preview --json`:成功。
- 结果:`status=exported`,`mode=preview`,`video_exists=True`,`qa_hard_failures=[]`,`qa_warnings=[]`。
- 自检后已恢复本机 `~/.agents/skills/lingjian-video` 与 `~/.claude/skills/lingjian-video` 软链指回主仓库。

## Tag 与推送

- 已提交封版改动。
- 已打 annotated tag `v0.2.0`。
- 已推送 `main` 与 `v0.2.0` 到 `origin=https://github.com/dososo/blcaptain-lingjian-video.git`。
