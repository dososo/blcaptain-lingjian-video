# 渲染引擎

M1 只实现 `ffmpeg_card` 范围内的静态卡片渲染。
M2 允许按 `visual_plan.json` 委托宿主 agent/CLI 生成每镜视频产物,再由 lj 端用 FFmpeg 组装,但仍不把 Remotion/HyperFrames 作为核心引擎 bundle 或 import。静态图片产物只可用于样片/参考。

## M1 允许

- 固定比例导出。
- 中文帧内字幕。
- CJK 断行规则。
- preview 与 release 物理隔离。
- `render_manifest.json` 记录 mode、platform、language、ratio 与 provider。

## M2 允许

- `visual_plan.json` 记录每镜 `generator`、`visual_prompt`、`motion_spec`、`brief`、`expected_asset_path`、`duration_sec`、`asset_path` 与 `subtitle_burn`。
- render 前可通过 `LINGJIAN_HOST_IMAGEGEN_CLI`、`LINGJIAN_HOST_HYPERFRAMES_CLI`、`LINGJIAN_HOST_REMOTION_CLI` 委托宿主生成器写入 `expected_asset_path`。
- 发布级消费 `project/assets/scenes/<scene_id>.mp4|mov|m4v` 中的宿主产物或用户视频素材;图片路径只用于样片预览。
- 视频镜头统一 scale/pad/FPS;图片镜头仅用于样片预览时的 Ken Burns/zoompan;缺资产时回落纯色卡片。
- `render_manifest.json` 记录 `visual_real_count`、`visual_total` 与每镜 `render_source`。
- release QA 对 `visual_real_count==0` 给 `RELEASE_VISUAL_IS_BLANK_CARD` warning;`--strict` 还会阻断内置样片模板、单素材复用和静态图片镜头,避免把“一张图反复闪几秒”或 Ken Burns/轻微缩放当作发布级视频。

## M1 禁止

- 默认启用 Remotion。
- 默认启用 HyperFrames。
- 在 `packages/core`、`providers` 或 `engines` 中 import/bundle Remotion/HyperFrames SDK。
- 引入复杂 timeline editor。
- 引入 shader、转场库或复杂动效管线。

## 目录规则

```text
renders/preview/<platform>/video.mp4
renders/preview/<platform>/render_manifest.json
renders/release/<platform>/video.mp4
renders/release/<platform>/render_manifest.json
```

release 导出只能引用 release manifest。引用 preview 产物时必须失败。

## release 校验

- `render --release` 必须可调用 FFmpeg 和 ffprobe,且 FFmpeg 支持 `drawtext/libfreetype`;缺失时不会写 stub。
- preview 仍允许写离线 stub,仅用于本地门禁和包结构验证。
- release 会调用 FFmpeg 生成 H.264/yuv420p MP4,通过 `drawtext` 烧录 CJK 字幕,并把 voice 音频合入 AAC 音轨。
- release 字幕文本优先来自 visual scene 的 `narration_text`,回落 script artifact 的 `narration_text`,断行复用 `engines/ffmpeg_card/text_layout.py`。
- release QA 会拒绝 `LINGJIAN_STUB_MP4` 哨兵字节,错误码为 `RELEASE_VIDEO_IS_STUB`。
- release QA 必须用 ffprobe 确认可用视频流与音频流;不可验证或 20 秒超时时返回 `RENDER_NOT_VERIFIABLE`,缺音频返回 `RELEASE_AUDIO_MISSING`。
