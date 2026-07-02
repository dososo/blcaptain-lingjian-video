# 安装说明

## 基础环境

- Python: `>=3.11,<3.13`,当前工程使用 `.python-version` 指向 3.12.9。
- Node.js: 20 LTS 或更新版本。
- 包管理: `uv` 与 `pnpm`。
- 必需运行能力: FFmpeg、ffprobe、中文字体、真实 LLM provider、真实 TTS provider。

## 安装命令

```bash
uv sync
pnpm install
uv run lj doctor --json
```

`doctor` 会检查 required 与 optional。required 缺失时 exit code 非 0,用户需要按 hint 补齐环境后再进入正式发布流程。

## 中文字体

macOS 默认会检测 PingFang/STHeiti。其他系统可把 `NotoSansSC-Regular.otf` 放到:

```text
~/.cache/lingjian/fonts/NotoSansSC-Regular.otf
```

## key 安全

不要把 key 写进项目文件。仅通过环境变量或本机密钥管理器注入。doctor 输出会按字段名脱敏,导出包不会包含 key。
