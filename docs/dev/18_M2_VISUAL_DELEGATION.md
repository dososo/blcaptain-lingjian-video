# 18 M2 画面委托说明

日期:2026-07-02

## 定位

本轮只落地 M2 第 1 步:委托宿主 HyperFrames/Remotion/imagegen 或用户素材生成每镜画面,lj 核心只消费 `project/assets/scenes/` 中的 mp4/png 并用 FFmpeg 组装。未实现自研 Remotion/HyperFrames 引擎,也未把相关 SDK import 进 core/providers。

## 文件落点

- `apps/cli/lingjian_cli/main.py`:visuals 产物改为每镜 storyboard,写入 `generator`、`asset_path`、`motion`、`subtitle_burn`、`brief`、`visual_real_count`、`visual_total`。
- `packages/core/rendering.py`:release/real-preview 在存在 visual scenes 时逐镜消费视频/图片资产,无资产回落 `fallback_solid`,再 concat 与 AAC 配音混合。
- `packages/core/qa.py`:release manifest 中 `visual_total>0` 且 `visual_real_count==0` 时给 `RELEASE_VISUAL_IS_BLANK_CARD` warning。
- `packages/core/capabilities.py`:新增 `visuals` 能力分档,报告宿主 HyperFrames/Remotion/imagegen 或回落卡片;不作为 release 硬门。
- `SKILL.md`、`README.md`、`docs/render-engines.md`:更新宿主画面委托和诚实边界。
- `verification/FORBIDDEN_SCAN.md`:记录扫描口径,允许宿主 generator 字符串,继续禁止 SDK import/bundle。

## 新增 warning

- `RELEASE_VISUAL_IS_BLANK_CARD`:release 视频全部来自 `fallback_solid`,未消费宿主动态图形/图片/用户素材。当前为 warning,不削弱 ffprobe、音轨、mock、stub 等 hard gate。

## 能力与诚实边界

- `lj setup --json` 新增 `capabilities.visuals`。
- `LINGJIAN_HOST_HYPERFRAMES_READY=1`、`LINGJIAN_HOST_REMOTION_READY=1`、`LINGJIAN_HOST_IMAGEGEN_READY=1` 可用于宿主环境显式声明能力已启用;本地 CLI 若存在并可 `--version` 也会被识别。
- 缺宿主画面能力时,visuals 会生成 `fallback_solid` 计划;render 仍可出片,但 QA 会 warning,不能宣称动态画面已生成。
- release 硬门不变:mock 不可 release,release 必须真实 LLM/TTS、FFmpeg/ffprobe/drawtext、非 stub、可验证视频流与音频流。

## 新增测试

- `test_release_render_consumes_delegated_video_and_image_scene_assets`
- `test_release_render_falls_back_to_solid_when_delegated_asset_missing_and_qa_warns`
- `test_capability_detection_reports_visual_generation_tier`
- `test_doctor_optional_notice_describes_host_visual_delegation`

## 验证命令

```bash
uv run pytest tests/test_batch2_release_export.py tests/test_capability_onboarding.py tests/test_cli_contract.py -q
uv run ruff check .
uv run python scripts/ci/check_forbidden_imports.py
uv run python scripts/ci/check_render_engine_m1.py
uv run python scripts/ci/check_ffmpeg_card_scope.py
```

## 本轮验证结果

- `uv run pytest -q`:87 passed。
- `uv run ruff check .`:通过。
- `uv run python scripts/ci/run_verification.py`:52 PASS / 0 FAIL。
- 5 个扫描器:全部 exit=0。
- `pnpm --dir apps/web lint && pnpm --dir apps/web build`:通过。
- `verification/evidence/V-REAL-01.log`:当前机器未检测到宿主画面插件,`capabilities.visuals=fallback_solid`;release QA 给 `RELEASE_VISUAL_IS_BLANK_CARD` warning,同时 ffprobe 仍确认 h264 视频流与 aac 音频流。
