# 28 生态零 key 引擎接入说明

日期:2026-07-02

## 结论

本轮把灵剪默认体验从“纯色卡片 + say 机器音”推进为“HyperFrames 零 key 动态画面 + Kokoro 中文本地配音 + 底部字幕 + strict 发布门”。核心仍只做编排、三审、QA 与导出,不 import HyperFrames/Remotion/Kokoro/Piper SDK;Kokoro ONNX 运行包作为默认安装依赖,由独立适配脚本子进程调用。

真机验收结论:

- `uv run lj setup --json`:visuals=`host_hyperframes`,tts=`kokoro_zh_tts`,render/font/llm 均 ready。
- `uv run lj run ./projects/eco_publish --name 生态验收 --input-file /tmp/lingjian_eco_input.txt --script-provider auto --voice-provider auto --release --strict --yes --approved-by codex-eco --json`:通过。
- `uv run python scripts/ci/run_verification.py`:52 PASS / 0 FAIL,`V-REAL-01=PASS`。
- QA strict:`hard_failures=[]`,`warnings=[]`,`release_ready=true`。
- ffprobe:`video=h264 1080x1920`,`audio=aac 24000Hz mono`。
- `render_manifest.json`: `visual_real_count=6`,`visual_total=6`,6 镜均为 `generator=hyperframes`,`render_source=video`,`subtitle_burn=true`。
- 泄漏扫描:导出包、artifacts、release render 中未命中 key/base_url/token/私密 wav 路径。

## 文件落点

- `packages/core/capabilities.py:316`:新增 `kokoro_zh_tts` 能力候选,`quality_tier=zero_key`。
- `pyproject.toml:10`:默认安装 `kokoro-onnx` 与 `soundfile`,确保 `uv sync` 后 Kokoro 适配器可复现;Piper 因 GPL 仍不进入依赖树。
- `packages/core/capabilities.py:336`:macOS `say` 保留预览能力,但 `safe_for_release=false`。
- `packages/core/capabilities.py:377`:HyperFrames 作为 `host_hyperframes` 视觉候选。
- `packages/core/capabilities.py:713`:用 `npx hyperframes --version` 探测 HyperFrames,不把裸 `npx` 当 JSON generator。
- `packages/core/capabilities.py:730`:本地 TTS 用适配器 `--probe` 探测,不导入 TTS SDK。
- `packages/core/visual_generation.py:19`:渲染前调用 `ensure_scene_asset`。
- `packages/core/visual_generation.py:35`:调用生成器前创建 `assets/scenes` 目录。
- `packages/core/visual_generation.py:99`:未配置自定义 HyperFrames JSON CLI 时,调用 `scripts/providers/hyperframes_scene_cli.py`。
- `scripts/providers/hyperframes_scene_cli.py:47`:创建临时 HyperFrames 项目并调用 `npx hyperframes render --quality draft` 写出目标 mp4。
- `providers/local_zero_key_tts.py:18`:本地 TTS provider 基类只通过子进程适配器执行。
- `providers/local_zero_key_tts.py:104`:注册 Kokoro 中文本地 TTS,license 标 Apache-2.0。
- `providers/local_zero_key_tts.py:116`:注册 Piper 中文本地 TTS,license 标 GPL-3.0,用户自装。
- `scripts/providers/kokoro_zh_tts.py:41`:Kokoro probe 支持 `kokoro_onnx` 缓存或官方 `kokoro` 包。
- `scripts/providers/kokoro_zh_tts.py:60`:优先用 HyperFrames Kokoro ONNX 缓存生成中文 wav。
- `scripts/providers/kokoro_zh_tts.py:89`:兼容官方 `KPipeline(lang_code="z")` 路径。
- `providers/registry.py:21`:注册 Kokoro/Piper provider。
- `providers/registry.py:50`:新增 `kokoro` / `kokoro_zh` provider alias。
- `packages/core/qa.py:126`:strict preview TTS 列表只保留 `macos_say` 与 `espeak_ng`;Kokoro/Piper 不被当成预览音。
- `apps/cli/lingjian_cli/main.py:329`:HyperFrames visual route 默认 `subtitle_burn=true`,由灵剪烧底部字幕。
- `apps/cli/lingjian_cli/main.py:1027`:用户提供 `--voice-audio-file` 时,release doctor 不再要求 TTS provider。

## 能力分层

🟢 零 key 免费:

- LLM:继承 Claude/Codex CLI。
- 画面:HyperFrames 本地 HTML 渲染,需 Node.js 22+ 与 FFmpeg。
- 配音:Kokoro 中文本地 TTS;Piper 为用户自装 GPL 路径。
- 音效/BGM:HyperFrames 自带媒体能力可由宿主 agent 使用;灵剪当前不把音效库打入核心依赖。
- 渲染:本机 FFmpeg/ffprobe/drawtext/AAC。

🟡 付费或需连接账号:

- 火山豆包/OpenAI-compatible TTS。
- Fal/Picsart/HeyGen 数字人、Shutterstock/Canva/Cloudinary 等第三方素材/生成能力。
- Remotion 在个人、非营利和 3 人以内营利组织可免费;超过条件需购买商用 license。

🔴 发布需自建:

- 抖音、小红书、YouTube、TikTok 发布动作不在本仓库内;灵剪只导出发布包。

## 真机验收记录

能力检测:

```bash
uv run lj setup --json
uv run lj doctor --json
```

关键结果:

- `capabilities.visuals.id=host_hyperframes`
- `capabilities.tts.id=kokoro_zh_tts`
- `doctor.ready=true`
- `doctor.optional` 仅提示本地 TTS 不是云端商用发布级,不阻断 strict。

端到端命令:

```bash
uv run lj run ./projects/eco_publish \
  --name 生态验收 \
  --input-file /tmp/lingjian_eco_input.txt \
  --script-provider auto \
  --voice-provider auto \
  --release \
  --strict \
  --yes \
  --approved-by codex-eco \
  --json
```

结果:

```json
{
  "ok": true,
  "status": "exported",
  "mode": "release",
  "strict": true,
  "qa": {
    "release_ready": true,
    "hard_failures": [],
    "warnings": []
  }
}
```

ffprobe:

```json
{
  "streams": [
    {"codec_name": "h264", "codec_type": "video", "width": 1080, "height": 1920, "duration": "6.000000"},
    {"codec_name": "aac", "codec_type": "audio", "duration": "5.973000"}
  ]
}
```

抽帧:

- `verification/eco_publish_frames/eco_01.png`
- `verification/eco_publish_frames/eco_02.png`
- `verification/eco_publish_frames/eco_03.png`
- `verification/eco_publish_frames/eco_04.png`
- `verification/eco_publish_frames/eco_05.png`
- `verification/eco_publish_frames/eco_06.png`

抽帧可见 HyperFrames 动态图形背景与灵剪底部字幕安全区,非纯色卡片。

无泄漏扫描:

```bash
rg -n "VOLCENGINE|OPENAI|ACCESS_TOKEN|API_KEY|BASE_URL|sk-|/tmp/lingjian|/Users/.+\\.wav|phase23|Z_AI_API_KEY" \
  exports/eco_publish/douyin/zh-CN/9x16 \
  projects/eco_publish/artifacts \
  projects/eco_publish/renders/release/douyin
```

结果:无命中。

## 离线单测

新增:

- `tests/test_ecosystem_integration.py::test_kokoro_zero_key_tts_is_auto_release_candidate`
- `tests/test_ecosystem_integration.py::test_say_is_not_release_tts_candidate`
- `tests/test_ecosystem_integration.py::test_kokoro_provider_uses_json_adapter`
- `tests/test_ecosystem_integration.py::test_hyperframes_default_adapter_generates_scene_asset`
- `tests/test_ecosystem_integration.py::test_release_qa_allows_kokoro_zero_key_tts`

局部验证:

```bash
uv run pytest tests/test_ecosystem_integration.py tests/test_capability_onboarding.py -q
uv run ruff check packages/core/capabilities.py packages/core/doctor.py packages/core/visual_generation.py providers/local_zero_key_tts.py providers/registry.py scripts/providers/kokoro_zh_tts.py scripts/providers/piper_cli.py scripts/providers/hyperframes_scene_cli.py tests/test_ecosystem_integration.py tests/test_capability_onboarding.py
```

结果:

- `18 passed`
- `All checks passed`

全量验证:

```bash
uv run python scripts/ci/run_verification.py
```

结果:

- `verification/results.json`:52 PASS / 0 FAIL。
- `V-REAL-01`:真实执行 `claude_cli -> kokoro_zh_tts -> hyperframes scene assets -> render -> qa -> export -> ffprobe`,最终视频包含 h264 视频流与 aac 音频流。

## 诚实边界

- HyperFrames 适配器当前生成的是基础动态图形镜头,不是承诺“爆款画面”。宿主 agent 可用 HyperFrames skills 做更丰富创作,灵剪消费落盘产物。
- Kokoro 是零 key 中文默认 TTS,默认安装 `kokoro-onnx/soundfile` 运行包,但不是云端商用音色承诺;商用发布仍建议人工试听或使用用户录音/火山豆包。
- Piper 为 GPL 用户自装路径,不进入灵剪核心依赖树。
- macOS say 与 espeak-ng 仍是预览级,strict release 会阻断。
- 任何第三方账号、key、base_url、完整命令不进入仓库、日志、manifest 或 release 包。
