# 24 真实用户体验审查后整改说明

日期:2026-07-02

## 背景

Claude 以真实新用户身份从 GitHub clean clone 跑完整流程,判定 `PASS_WITH_NOTES`。核心发现:

- 开箱可跑通并出片,但产物是预览级:纯色卡片 + 预览级 say 音轨。
- 发布级视觉自动生成路径尚无真实 Codex 桌面宿主插件端到端成片证据。
- README 第一条快速开始命令不应默认走 mock,否则第一印象可能是 stub 或不可看产物。

## 本轮处理

### 1. 快速开始第一条命令改用 auto

- `README.md`:快速开始命令改为 `--script-provider auto --voice-provider auto`。
- `SKILL.md`:主线命令同步改为 `--script-provider auto --voice-provider auto`。
- mock 改为显式“仅验证流程”选项,并说明不是发布级视频。
- `tests/test_skill_packaging.py`:增加断言,锁住 README 同时包含 auto 主线和 mock 验证路径。

### 2. 插件安装标识符真实验证

使用临时环境验证:

- `HOME=/tmp/... npx -y skills@latest add heygen-com/hyperframes`:exit=0,可解析并安装 HeyGen/HyperFrames skill 集合。
- `HOME=/tmp/... npx -y skills@latest add remotion-dev/skills`:exit=0,可解析并安装 `remotion-best-practices`。

结论:

- 标识符可解析安装。
- 但安装 agent skill 不等于 `lj setup` 可探测到 `hyperframes/remotion` CLI,也不等于已经完成“宿主插件自动生成真实动态画面”的端到端验证。

因此文档口径调整为:

- 当前已验证的发布级视觉首选路径:用户或宿主把每镜 mp4/png 放到 `project/assets/scenes/`。
- HyperFrames/Remotion/imagegen:可选进阶,负责帮助宿主生成这些资产;端到端动态成片仍需真实 Codex 桌面宿主实测。

### 3. 自备每镜图片 release 路径真实验证

新增证据目录:`verification/release_visual_user_assets/`。

执行链:

1. `lj init`
2. `lj ingest text`
3. `lj extract`
4. `lj script --provider auto`
5. `lj voice --provider auto`
6. 为 script scenes 生成并放置 `assets/scenes/<scene_id>.png`
7. `lj visuals`
8. `lj render --release`
9. `lj qa --release`
10. `lj export --release`
11. `ffprobe`

结果:

- `release_ready=true`
- `RELEASE_VISUAL_IS_BLANK_CARD`:未出现
- `RELEASE_AUDIO_IS_PREVIEW_VOICE`:仍出现,符合当前只有预览级 TTS 的环境事实
- ffprobe:video=h264,audio=aac

证据:

- `verification/release_visual_user_assets/summary.json`
- `verification/release_visual_user_assets/12_qa_release.json`
- `verification/release_visual_user_assets/14_ffprobe.json`

## 仍未完成

- 真实 Codex 桌面宿主插件自动生成动态画面后,再由灵剪消费并 release 的端到端证据仍未完成。
- 火山等发布级 TTS 真 key 端到端发布音轨仍未完成。

## 验收结果

- `uv run pytest -q`:99 passed。
- `uv run ruff check .`:通过。
- 5 个扫描器:`check_false_success.py`、`check_no_force.py`、`check_forbidden_imports.py`、`check_render_engine_m1.py`、`check_ffmpeg_card_scope.py` 均 exit=0。
- `pnpm --dir apps/web lint`:通过。
- `pnpm --dir apps/web build`:首轮 Next standalone copy 偶发 `ENOENT`,立即重跑通过。
- `uv run python scripts/ci/run_verification.py`:52 PASS / 0 FAIL,`V-REAL-01` 走真实 release 分支。

## 边界保持

- 不 import/bundle Remotion/HyperFrames SDK。
- 不实现 MCP server。
- 不把 Web 静态骨架说成完整控制台。
- 不做爆款算法、平台知识包、声音克隆、ASR 或默认视频下载。
- mock/stub/ffprobe/audio/三审/key 脱敏门禁不变。
