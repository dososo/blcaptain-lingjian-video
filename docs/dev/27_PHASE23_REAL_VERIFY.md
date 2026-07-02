# Phase 2+3 真机验证记录

日期: 2026-07-02

## 结论

- Phase 2 本地 Codex Plugin 安装与触发:通过。
- Phase 3 HyperFrames 真机渲染真实动态画面:通过。
- Phase 3 灵剪消费 HyperFrames mp4 并去除 blank-card warning:通过。
- Phase 3 发布级 `--release --strict` 完整成片:通过。先验证 `macOS say` 会被 strict 正确阻断,随后使用免费本地 Kokoro 中文 TTS 生成口播 wav,作为本地音频 artifact 接入 `--voice-audio-file`,strict QA/export 均通过且无质量 warning。

## 环境

- OS: macOS 26.5, Darwin 25.5.0 arm64。
- Codex CLI: `codex-cli 0.142.5`。
- Node.js: `v22.17.1` (`/Users/manxiaochu/.local/bin/node`)。
- npx: `11.8.0`。
- FFmpeg/ffprobe: `8.1.2`,来自 `/opt/homebrew/Cellar/ffmpeg-full/8.1.2`。
- `ffmpeg -hide_banner -h filter=drawtext`:确认 `Draw text on top of video frames using libfreetype library`。

## Phase 2: Codex Plugin 安装与触发

官方依据:

- OpenAI Codex plugins 文档说明 `codex plugin marketplace add owner/repo`、Git URL 与本地 marketplace root 均可作为 marketplace source。
- `Build plugins` 文档说明 plugin 需要 `.codex-plugin/plugin.json`,repo marketplace 位于 `$REPO_ROOT/.agents/plugins/marketplace.json`,plugin 可包含 `skills/`。

本地验证:

```bash
uv run python -m json.tool .codex-plugin/plugin.json
uv run python -m json.tool .agents/plugins/marketplace.json
codex plugin marketplace add /Users/manxiaochu/Documents/Codex/lingjian-video --json
codex plugin add lingjian-video@blcaptain-lingjian-video --json
codex plugin list --json
```

结果:

- `.codex-plugin/plugin.json` 与 `.agents/plugins/marketplace.json` 均为合法 JSON。
- 本地 marketplace add 成功:`marketplaceName=blcaptain-lingjian-video`。
- plugin add 成功:`pluginId=lingjian-video@blcaptain-lingjian-video`,`installedPath=/Users/manxiaochu/.codex/plugins/cache/blcaptain-lingjian-video/lingjian-video/0.1.0`。
- `codex plugin list --json` 显示该 plugin `installed=true`,`enabled=true`。
- 备用 skill 软链存在:`~/.agents/skills/lingjian-video -> /Users/manxiaochu/Documents/Codex/lingjian-video`。

触发验证:

- 新建 Codex 线程 `019f22b6-2091-7722-83d5-885c3e772757`。
- 输入:`用 lingjian-video 帮我做一条抖音短视频`。
- 返回:`lingjian-video:lingjian-video；下一步进入视频需求澄清阶段`。

未通过项:

- `codex plugin marketplace add dososo/blcaptain-lingjian-video --json` 当前失败:`marketplace root does not contain a supported manifest`。
- 判定:本地 plugin 文件尚未提交/推送到 GitHub,远端仓库还不是可安装 marketplace;不是本地 schema 失败。

额外发现:

- 本地 plugin source 目前指向 repo root。用本地 marketplace 安装时,Codex cache 会复制当前工作树内容。远端 GitHub 安装只会取已提交文件,但发布前仍应确保 `projects/`、`exports/`、凭据与旧交付包不进入公开发布物。

## Phase 3: HyperFrames 真机渲染

安装/探测:

```bash
npx skills add heygen-com/hyperframes
npx hyperframes --version
npx hyperframes --help
uv run lj setup --json
```

结果:

- `npx skills add heygen-com/hyperframes` 成功,安装 20 个 HyperFrames skills。
- `npx hyperframes --version` 返回 `0.7.26`。
- `npx hyperframes --help` 可用。
- `uv run lj setup --json` 仍显示 `visuals.id=fallback_solid`。原因:HyperFrames skill 已安装不等于灵剪 CLI 可自动调用的 JSON contract 生成器;当前没有全局 `hyperframes` 命令,也没有 `LINGJIAN_HOST_HYPERFRAMES_CLI` adapter。

真实 HyperFrames 渲染:

```bash
npx hyperframes init /tmp/lingjian-hyperframes-verify --example blank --resolution portrait --non-interactive
npm run check
npm run render -- --output /tmp/lingjian-hyperframes-verify/scene.mp4 --quality draft
ffprobe -v error -show_entries stream=index,codec_type,codec_name,width,height,duration -of json /tmp/lingjian-hyperframes-verify/scene.mp4
ffmpeg -y -i /tmp/lingjian-hyperframes-verify/scene.mp4 -vf fps=1/3 /tmp/lingjian-hyperframes-verify/frame_%02d.png
```

结果:

- `npm run check`:lint 0 errors/0 warnings;validate 无 console errors;inspect 0 layout issues。
- render 成功:`/tmp/lingjian-hyperframes-verify/scene.mp4`,2.7 MB,10.0s。
- ffprobe:video stream `h264`,1080x1920,10s。
- 抽帧证明非纯色画面:见 `/tmp/lingjian-hyperframes-verify/frame_02.png`。

## Phase 3: 灵剪消费真实动态画面

流程:

```bash
uv run lj run ./projects/publish_real_phase23 --name 发布级画面验证 --input-file /tmp/lingjian_phase23_input.txt --script-provider auto --voice-provider auto --release --yes --json
```

初次结果:

- 成功导出,但因尚未接入画面资产,QA warning 包含:
  - `RELEASE_VISUAL_IS_BLANK_CARD`
  - `RELEASE_AUDIO_IS_PREVIEW_VOICE`

随后把 HyperFrames mp4 作为宿主已生成资产交给每镜:

```bash
mkdir -p projects/publish_real_phase23/assets/scenes
cp /tmp/lingjian-hyperframes-verify/scene.mp4 projects/publish_real_phase23/assets/scenes/s1.mp4
cp /tmp/lingjian-hyperframes-verify/scene.mp4 projects/publish_real_phase23/assets/scenes/s2.mp4
cp /tmp/lingjian-hyperframes-verify/scene.mp4 projects/publish_real_phase23/assets/scenes/s3.mp4
cp /tmp/lingjian-hyperframes-verify/scene.mp4 projects/publish_real_phase23/assets/scenes/s4.mp4
cp /tmp/lingjian-hyperframes-verify/scene.mp4 projects/publish_real_phase23/assets/scenes/s5.mp4
cp /tmp/lingjian-hyperframes-verify/scene.mp4 projects/publish_real_phase23/assets/scenes/s6.mp4
uv run lj approve visuals ./projects/publish_real_phase23 --approved-by codex-phase23 --json
uv run lj render ./projects/publish_real_phase23 --release --ratio 9:16 --platform douyin --language zh-CN --json
uv run lj qa ./projects/publish_real_phase23 --release --json
```

结果:

- `render_manifest.json`: `visual_real_count=6`,`visual_total=6`,6 个场景均为 `render_source=video`,`generator=user-asset`。
- QA 非 strict:`hard_failures=[]`,不再出现 `RELEASE_VISUAL_IS_BLANK_CARD`,只剩 `RELEASE_AUDIO_IS_PREVIEW_VOICE`。
- ffprobe 成片:`h264` 视频流 1080x1920 + `aac` 音频流。
- 抽帧目录:`verification/phase23_frames/`;`phase23_02.png` 可见真实画面与底部字幕。
- 导出包:`exports/publish_real_phase23/douyin/zh-CN/9x16`。
- 脱敏检查:`rg "VOLCENGINE|OPENAI|ACCESS_TOKEN|API_KEY|BASE_URL|/tmp/lingjian|/Users/manxiaochu/.+scene.mp4" exports/publish_real_phase23/douyin/zh-CN/9x16` 无命中。

## 发布级 strict 结果

第一次 strict 验证时的发布级配音能力:

```bash
VOLCENGINE_TTS_APP_ID=unset
VOLCENGINE_TTS_ACCESS_TOKEN=unset
VOLCENGINE_TTS_CLUSTER=unset
VOLCENGINE_TTS_VOICE_TYPE=unset
OPENAI_TTS_BASE_URL=unset
OPENAI_TTS_API_KEY=unset
OPENAI_TTS_MODEL=unset
LINGJIAN_TTS_CLI=unset
```

严格门禁:

```bash
uv run lj qa ./projects/publish_real_phase23 --release --strict --json
uv run lj export ./projects/publish_real_phase23 --release --strict --platform douyin --language zh-CN --ratio 9:16 --json
```

结果:

- strict QA:`hard_failures=[RELEASE_AUDIO_IS_PREVIEW_VOICE]`,`release_ready=false`。
- strict export:失败并返回 `QA_BLOCKING`。
- 结论:本轮没有使用 macOS say 冒充发布级配音;strict 门禁正确拦截了预览音。

## 免费本地 Kokoro 口播补验

用户要求优先使用不花钱的免费能力。执行路径为 HyperFrames media 的本地 Kokoro TTS,不使用云 key。

依赖安装:

```bash
brew install espeak-ng
uv pip install kokoro-onnx soundfile
```

发现与修正:

- `npx hyperframes tts --voice zf_xiaobei --lang zh` 当前失败:底层 phonemizer/espeak 不接受 `zh`。
- 本机 `espeak-ng --voices` 显示普通话语言码为 `cmn`。
- 由于 HyperFrames CLI 参数校验只允许 `zh`,改用 `kokoro-onnx` Python API 直接指定 `lang="cmn"` 生成 wav。

生成口播:

```bash
uv run python - <<'PY'
from kokoro_onnx import Kokoro, EspeakConfig
import soundfile as sf
from pathlib import Path
project=Path('projects/publish_real_phase23')
text=(project/'artifacts/phase23_tts_script.txt').read_text().strip()
model=Path.home()/'.cache/hyperframes/tts/models/kokoro-v1.0.onnx'
voices=Path.home()/'.cache/hyperframes/tts/voices/voices-v1.0.bin'
out=project/'artifacts/phase23_kokoro_voice.wav'
kokoro=Kokoro(str(model), str(voices), espeak_config=EspeakConfig(lib_path='/opt/homebrew/lib/libespeak-ng.dylib', data_path='/opt/homebrew/Cellar/espeak-ng/1.52.0/share/espeak-ng-data'))
audio, sr = kokoro.create(text, voice='zf_xiaobei', speed=1.08, lang='cmn')
sf.write(out, audio, sr)
PY
```

生成结果:

- 音频:`projects/publish_real_phase23/artifacts/phase23_kokoro_voice.wav`。
- ffprobe:`pcm_s16le`,24kHz,mono,47.04s。

新建 strict 发布项目:

```bash
uv run lj run ./projects/publish_real_kokoro --name 发布级免费口播验收 --input-file /tmp/lingjian_phase23_input.txt --script-provider auto --voice-audio-file /Users/manxiaochu/Documents/Codex/lingjian-video/projects/publish_real_phase23/artifacts/phase23_kokoro_voice.wav --release --yes --json
```

随后把 HyperFrames mp4 放入 `projects/publish_real_kokoro/assets/scenes/s1..s6.mp4`,更新 `visual_plan.json` 为 `generator=user-asset`,重新审批 visuals,再执行:

```bash
uv run lj render ./projects/publish_real_kokoro --release --ratio 9:16 --platform douyin --language zh-CN --json
uv run lj qa ./projects/publish_real_kokoro --release --strict --json
uv run lj export ./projects/publish_real_kokoro --release --strict --platform douyin --language zh-CN --ratio 9:16 --json
```

最终结果:

- `uv run lj qa --release --strict`: `hard_failures=[]`,`warnings=[]`,`release_ready=true`。
- `uv run lj export --release --strict`: `ok=true`,`strict=true`。
- 成片:`exports/publish_real_kokoro/douyin/zh-CN/9x16/video.mp4`。
- ffprobe:视频流 `h264` 1080x1920 46.998s;音频流 `aac` 24kHz mono 46.976s。
- provider manifest:`claude_cli` + `user_audio` + `delegated_scene_assembly`,均 `is_mock=false`,`release_allowed=true`。
- 脱敏扫描:`rg "VOLCENGINE|OPENAI|ACCESS_TOKEN|API_KEY|BASE_URL|HEYGEN|ELEVEN|/tmp/lingjian|phase23_kokoro_voice|/Users/manxiaochu/.+wav" exports/publish_real_kokoro/douyin/zh-CN/9x16` 无命中。
- 抽帧证据:`verification/phase23_kokoro_frames/`。

注意:Kokoro 是免费本地 TTS,不是云发布级音色。门禁上它作为已落盘本地音频通过 `user_audio` 路径;正式对外使用前仍应由用户试听确认口播自然度。

## 当前 DoD 状态

- Codex 本地 plugin 安装与一句话触发:达成。
- HyperFrames CLI 真机渲染真实动态 mp4:达成。
- 灵剪消费真实动态 mp4 并消除 blank-card warning:达成。
- 发布级严格成片:通过。免费本地 Kokoro 口播经 `user_audio` 路径接入,`--release --strict` 导出成功且 QA 无 warning。
- 门禁语义:未削弱;strict 正确阻断预览级音轨。
