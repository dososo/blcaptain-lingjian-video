# 渲染引擎

M1/M2 只实现 `ffmpeg_card` 范围内的静态卡片渲染。

## M1 允许

- 固定比例导出。
- 中文帧内字幕。
- CJK 断行规则。
- preview 与 release 物理隔离。
- `render_manifest.json` 记录 mode、platform、language、ratio 与 provider。

## M1 禁止

- 默认启用 Remotion。
- 默认启用 HyperFrames。
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
- release 字幕文本来自 script artifact 的 `narration_text`,断行复用 `engines/ffmpeg_card/text_layout.py`。
- release QA 会拒绝 `LINGJIAN_STUB_MP4` 哨兵字节,错误码为 `RELEASE_VIDEO_IS_STUB`。
- release QA 必须用 ffprobe 确认可用视频流与音频流;不可验证或 20 秒超时时返回 `RENDER_NOT_VERIFIABLE`,缺音频返回 `RELEASE_AUDIO_MISSING`。
