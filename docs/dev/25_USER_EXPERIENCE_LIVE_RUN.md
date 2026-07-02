# 25 真实用户现场体验跑通记录

日期:2026-07-02

## 目的

本轮不是再次读代码或写审计结论,而是把用户作为真实体验者带过一遍:能力检测 -> 脚本 -> 配音 -> 画面资产 -> 三审 -> release 渲染 -> QA -> export -> 抽帧/ffprobe。

## 当前能力状态

- LLM:`claude_cli`,继承当前登录订阅能力,`is_mock=false`。
- TTS:`macos_say`,本机零 key 可用,但 `quality_tier=preview`。
- Render:`ffmpeg/ffprobe` 就绪,支持 release。
- Font:macOS 中文字体就绪。
- Visuals:未检测到 HyperFrames/Remotion CLI 自动生成能力;本轮使用 Codex 宿主 `imagegen` 生成每镜图片,再作为用户/宿主资产放入 `assets/scenes/`。

## 跑通项目

- Project:`projects/user_experience_live_20260702T081937Z`
- Export video:`exports/user_experience_live_20260702T081937Z/douyin/zh-CN/9x16/video.mp4`
- Evidence:`verification/user_experience_live_user_experience_live_20260702T081937Z/`

## 实际流程

1. `uv run lj setup --json`
2. `uv run lj doctor --json`
3. `uv run lj init`
4. `uv run lj ingest text`
5. `uv run lj extract`
6. `uv run lj script --provider auto`
7. `uv run lj approve script`
8. `uv run lj voice --provider auto`
9. `uv run lj approve voice`
10. `uv run lj visuals`
11. 用 Codex 宿主 `imagegen` 生成 6 张 9:16 场景图,复制为:
    - `assets/scenes/1.png`
    - `assets/scenes/2.png`
    - `assets/scenes/3.png`
    - `assets/scenes/4.png`
    - `assets/scenes/5.png`
    - `assets/scenes/6.png`
12. 重跑 `uv run lj visuals`,确认 `visual_real_count=6/6`,6 镜均为 `generator=user-asset`。
13. `uv run lj approve visuals`
14. `uv run lj render --release`
15. `uv run lj qa --release`
16. `uv run lj export --release`
17. `ffprobe` 与抽帧核查。

## 结果

- `visual_real_count`:6
- `visual_total`:6
- render sources:6 个 scene 全部为 `image`
- QA hard failures:`[]`
- QA warning:`RELEASE_AUDIO_IS_PREVIEW_VOICE`
- 未出现:`RELEASE_VISUAL_IS_BLANK_CARD`
- ffprobe:
  - video:h264,1080x1920
  - audio:aac

## 抽帧证据

- `verification/user_experience_live_user_experience_live_20260702T081937Z/frames/frame_01.jpg`
- `verification/user_experience_live_user_experience_live_20260702T081937Z/frames/frame_03.jpg`
- `verification/user_experience_live_user_experience_live_20260702T081937Z/frames/frame_05.jpg`

## 结论

这次用户体验链路已经不是纯色卡片:灵剪成功消费宿主/用户提供的每镜图片,用 Ken Burns/字幕/音轨组装出 release 视频,QA 无 blank-card warning。

仍需诚实说明:当前音轨来自 macOS say,属于预览级 TTS,因此 release QA 保留 `RELEASE_AUDIO_IS_PREVIEW_VOICE` warning。若要发布级配音,下一步应配置火山豆包/OpenAI-compatible TTS,或提供真实录音文件。

