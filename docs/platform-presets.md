# 平台 Preset

平台差异通过 `config/presets/*.yaml` 管理,不在 render/export 代码中写平台名条件分支。

M1 内置:

- `douyin`: 9:16,中文短视频。
- `xiaohongshu`: 3:4 或 9:16,封面与正文强相关。
- `bilibili`: 16:9,适合横屏教程。
- `youtube`: 16:9,需要 thumbnail、description、chapters。
- `youtube_shorts`: 9:16,短视频版本。

导出包路径:

```text
exports/<project>/<platform>/<language>/<ratio>/
```

ratio 目录会把 `9:16` 写成 `9x16`。
