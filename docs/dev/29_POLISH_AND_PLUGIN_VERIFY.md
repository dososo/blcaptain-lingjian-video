# 29 画面质量打磨与 Codex Plugin 真机补验

日期: 2026-07-02

## 结论

本轮完成 Track A 与 Track B:

- Track A: HyperFrames 画面适配器已从单一模板升级为确定性多版式蓝图;画面只显示短视觉关键词,完整口播由底部字幕承载。真机 `lj run --release --strict` 通过,最终视频 6/6 镜均为 HyperFrames mp4,QA 无 warning/hard failure,ffprobe 为 h264+aac。
- Track B: Codex plugin marketplace 安装与 plugin add 均成功;新 Codex 只读会话能识别 `lingjian-video:lingjian-video` 并进入灵剪主线。
- 门禁未削弱:仍只通过 subprocess 委托 HyperFrames,core 不 import/bundle 引擎 SDK;`--strict`、mock/stub、ffprobe 视频/音频 hard gate 均保持。

## 改动清单

| 文件 | 行锚点 | 改动 | 对应任务 |
| --- | --- | --- | --- |
| `scripts/providers/hyperframes_scene_cli.py` | 15-22,115-210,221-238,241-285,300-319 | 新增 5 种确定性版式 `hook/pain/solution/proof/cta`;按 role 或 scene index 选版式;HTML 根节点写入 `data-layout`;关键词优先来自 `on_screen_text`,不再把整句口播放进画面主标题。 | A1/A2 |
| `packages/core/visual_generation.py` | 16-18,37-48,119-143 | 向宿主生成器传 `role/on_screen_text/narration_text`;将宿主视觉素材生成时长限制为 0.8-1.5 秒短循环,最终时长由 render 阶段 loop/裁切。 | A1/真机稳定性 |
| `apps/cli/lingjian_cli/main.py` | 366-423 | visual plan 写入脚本短屏幕词和视觉提示;当 voice 只有整段单音频而脚本有多镜时,用脚本分镜时长,避免第一镜被整段 TTS 时长拖到超时。 | A1/A2/真机稳定性 |
| `tests/test_ecosystem_integration.py` | 105-148 | 覆盖宿主素材短循环时长、版式确定性、feature/proof/cta 相邻映射、画面不重复整句口播。 | A1/A2 测试 |
| `tests/test_m2_visual_generation_tts.py` | 104-153 | 覆盖“多镜脚本 + 单段整音频”时 visual plan 使用脚本分镜时长,并保留 `role/on_screen_text`。 | A1 真机超时修复测试 |

## Track A 真机验证

环境:

- OS: macOS 26.5, arm64
- Node.js: v22.17.1
- HyperFrames: 0.7.26
- FFmpeg/ffprobe: 8.1.2,路径通过本次 shell `PATH=/opt/homebrew/bin:/Users/manxiaochu/.local/bin:$PATH` 暴露
- LLM: `claude_cli`,继承 CLI,未写 key
- TTS: `kokoro_zh_tts`,零 key 中文本地 TTS

命令:

```bash
PATH="/opt/homebrew/bin:/Users/manxiaochu/.local/bin:$PATH" \
  /Users/manxiaochu/.local/bin/uv run lj run ./projects/polish_verify_20260702_v4 \
  --name 画面打磨验收v4 \
  --input-file examples/product_intro_zh.txt \
  --script-provider auto \
  --voice-provider auto \
  --release \
  --strict \
  --yes \
  --approved-by codex-polish \
  --json
```

结果:

- `status=exported`
- `strict=true`
- QA: `hard_failures=[]`, `warnings=[]`, `release_ready=true`
- 导出视频: `exports/polish_verify_20260702_v4/douyin/zh-CN/9x16/video.mp4`
- render manifest: `visual_real_count=6`, `visual_total=6`
- providers: `claude_cli`、`kokoro_zh_tts`、`delegated_scene_assembly`,均 `is_mock=false`
- ffprobe:

```json
{
  "streams": [
    {"index": 0, "codec_name": "h264", "codec_type": "video", "duration": "42.466667"},
    {"index": 1, "codec_name": "aac", "codec_type": "audio", "duration": "42.517000"}
  ]
}
```

抽帧证据:

- `verification/polish_frames_v4/frame_01.png`: hook 开场大字,只含短关键词,底部字幕承载口播全文。
- `verification/polish_frames_v4/frame_02.png`: pain 分栏/堆叠版式。
- `verification/polish_frames_v4/frame_03.png`: solution 卡片版式。
- `verification/polish_frames_v4/frame_04.png`: proof 数据版式。
- `verification/polish_frames_v4/frame_05.png`: cta 行动收口版式。
- `verification/polish_frames_v4/frame_06.png`: hook 收尾聚焦版式。

布局序列由脚本场景与 `_layout_for` 计算为:

```text
1 -> hook
2 -> pain
3 -> solution
4 -> proof
5 -> cta
6 -> hook
```

结论:相邻镜头版式不重复;画面里没有整句口播重复,完整口播只在底部字幕;视频包含真实 HyperFrames 动态画面与 Kokoro/aac 音轨,通过 `--strict`。

## Track B 插件安装与触发验证

已执行:

```bash
/Users/manxiaochu/.local/bin/codex plugin marketplace add dososo/blcaptain-lingjian-video --json
/Users/manxiaochu/.local/bin/codex plugin add lingjian-video@blcaptain-lingjian-video --json
/Users/manxiaochu/.local/bin/codex plugin list
```

结果摘要:

- marketplace add 成功,marketplace root: `/Users/manxiaochu/.codex/.tmp/marketplaces/blcaptain-lingjian-video`
- plugin add 成功,installed path: `/Users/manxiaochu/.codex/plugins/cache/blcaptain-lingjian-video/lingjian-video/0.1.0`
- `codex plugin list` 显示 `lingjian-video@blcaptain-lingjian-video installed, enabled 0.1.0`
- `~/.agents/skills/lingjian-video` 软链存在,指向当前仓库。

触发烟测:

```bash
/Users/manxiaochu/.local/bin/codex exec --ephemeral -s read-only \
  -C /Users/manxiaochu/Documents/Codex/lingjian-video \
  "用 lingjian-video 帮我做一条抖音短视频。本次只验证 Codex plugin/skill 触发,不要运行 shell 命令,不要改文件。请用中文简短回答:你识别到的 skill 名称是什么,灵剪主线第一步是什么。"
```

返回要点:

```text
识别到的 skill 名称是: lingjian-video:lingjian-video
灵剪主线第一步是: 先进入需求澄清/目标确认,明确这条抖音短视频要表达什么、面向谁、预期成片形式是什么。
```

结论:当前 Codex app/plugin 环境可安装并启用灵剪 plugin;只读新会话能识别 skill 并进入主线。未使用伪触发,未运行写操作。

## 本轮发现与修复

真机第一轮发现 `visual_real_count=5/6`:Kokoro 输出整段单音频,旧 visual plan 把整段 TTS 时长赋给第一镜,导致第一镜 HyperFrames 生成超过 90 秒超时并回落。修复方式:

- visual plan 在“多镜脚本 + 单段整音频”时使用脚本分镜时长。
- 宿主视觉生成器只生成短循环素材,最终时长由 render 阶段 `stream_loop` 与 `-t` 对齐。

真机后续抽帧发现相邻场景可能落到同一 proof/cta 版式。修复方式:

- 明确 `feature/benefit` role 映射到 `hook` 聚焦版式,避免与常见 `proof/cta` 收尾相撞。
- 新增离线测试锁定 `feature/proof/cta` 的相邻差异。

## 全量回归结果

已执行:

```bash
/Users/manxiaochu/.local/bin/uv run pytest -q
/Users/manxiaochu/.local/bin/uv run ruff check .
/Users/manxiaochu/.local/bin/uv run python scripts/ci/check_false_success.py
/Users/manxiaochu/.local/bin/uv run python scripts/ci/check_no_force.py
/Users/manxiaochu/.local/bin/uv run python scripts/ci/check_forbidden_imports.py
/Users/manxiaochu/.local/bin/uv run python scripts/ci/check_render_engine_m1.py
/Users/manxiaochu/.local/bin/uv run python scripts/ci/check_ffmpeg_card_scope.py
pnpm --dir apps/web build
PATH="/opt/homebrew/bin:/Users/manxiaochu/.local/bin:$PATH" /Users/manxiaochu/.local/bin/uv run python scripts/ci/run_verification.py
git diff --check
```

结果:

- `pytest -q`:111 passed
- `ruff check .`:通过
- `check_false_success.py`:13 项 PASS
- `check_no_force.py`:通过
- `check_forbidden_imports.py`:通过
- `check_render_engine_m1.py`:通过
- `check_ffmpeg_card_scope.py`:通过
- `pnpm --dir apps/web lint`:通过
- `pnpm --dir apps/web build`:通过
- `run_verification.py`:52 PASS / 0 FAIL,`V-REAL-01=PASS`
- `git diff --check`:通过
