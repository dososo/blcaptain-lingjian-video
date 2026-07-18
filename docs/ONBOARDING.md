# 灵剪 Onboarding:能力检测与继承优先

灵剪面向 Codex app 用户。第一步不是让你填 key,而是在 Codex app 里安装插件/skill 后,由 Codex 自动检测这台机器和当前会话已经具备什么能力,能继承就直接继承。

## 心智模型

- 预览档:可使用 mock、macOS say/espeak-ng 或 fallback_solid,用于离线体验、门禁验证和流程演示。
- 发布档:必须同时具备真实 LLM、用户录音或自然中文云 TTS、真实动态内容画面插件/每镜视频素材、FFmpeg/ffprobe/drawtext/AAC、中文字体和底部字幕安全区。`--strict --release` 下 Kokoro/Piper/say/espeak、静态图片、单素材循环、内置模板与 fallback_solid 会阻断。

mock 永远不能用于正式 release。doctor 未 ready 时,真实终验必须停下,不得伪造 PASS。

用户入口保持极简:一句中文描述目标即可,最多可选两个收敛参数。`--style` 控制统一视觉风格(`clean_product`/`bold_news`/`warm_lifestyle`/`tech_minimal`),`--profile` 控制平台和受众预设(`douyin_product`/`xiaohongshu_life`/`shipinhao_knowledge`)。这些参数会进入导演契约层,不承诺爆款。

能力分三层:

- 🟢 零 key 免费:继承 Claude/Codex CLI、HyperFrames 本地样片动效、Kokoro 中文样片 TTS、用户自备素材/录音、FFmpeg。
- 🟡 付费或需连接账号:火山豆包/OpenAI-compatible TTS、Fal/Picsart/HeyGen 数字人、商业素材库等。
- 🔴 发布需自建或人工:抖音/小红书/YouTube/TikTok 自动发布不在本仓库内,导出后人工上传或自建。

## 第一步:自动检测

Codex 对话里只需要说“先做灵剪能力门诊”。底层可用命令是 `uv run lj setup`;`uv run lj setup --json` 和 `uv run lj doctor --json` 只给 Codex/审计脚本使用,不要把原始 JSON 当作普通用户界面。

能力门诊后,在生成脚本前必须确认内容依据。用户可以给一句话说明、Markdown、PDF、PPT、Word、已有脚本、网页链接、GitHub 仓库或截图。只有主题、没有内容依据时,灵剪必须先问用户要基于哪份内容做,不能凭模型常识直接编完整产品脚本。

脚本批准后,进入正式配音前必须先做配音导演确认。Codex 要用人话列出整体口播定位、目标听感、语速策略、情绪曲线、停顿重音和每镜表达方式;用户确认后才调用火山豆包/OpenAI-compatible 等发布级 TTS。只让用户选音色不够,直接生成全片配音也不符合灵剪主线。

`lj setup` 会按优先级检测:

- LLM:先找 Claude Code 的 `claude`、Codex 的 `codex` 等官方订阅 CLI;再找 `ollama`、`llm`;最后才看 OpenAI-compatible key。
- TTS:先找用户录音、发布级云 TTS 或经用户确认自然的真实 TTS CLI;Kokoro/Piper/macOS `say`、espeak-ng 只作为样片/预览音,并在严格发布 QA 中阻断。
- 画面:优先检测用户自带 `assets/scenes/` 视频素材或显式验证过的宿主视频生成器。HyperFrames 本地路径可做零 key 动态样片,但只有 `safe_for_release=true` 或每镜真实视频素材齐备时才算发布级。都没有时才回落卡片,严格发布 QA 会阻断。
- 渲染:检查本机 `ffmpeg`、`ffprobe`,并确认 `ffmpeg` 支持 `drawtext/libfreetype`。
- 字体:macOS 用 PingFang;其他系统可放 `~/.cache/lingjian/fonts/NotoSansSC-Regular.otf`。

命中可继承能力时,灵剪会显示「无需 key」。只对缺失项给下一条命令。

## LLM:先继承,后 key

如果你已经登录 Claude Code 或 Codex CLI:

```bash
claude --version
codex --version
uv run lj setup
```

灵剪只调用官方 CLI 命令,不读取、不复制、不搬运 OAuth token 或凭据文件。

如果没有订阅 CLI,可以使用本机模型:

```bash
ollama --version
llm --version
uv run lj setup
```

如果以上都没有,再配置 OpenAI-compatible 三件套:

```bash
export OPENAI_BASE_URL=https://api.example.com/v1
export OPENAI_API_KEY=...
export OPENAI_MODEL=...
uv run lj doctor --json
```

## TTS:订阅通常不包含

ChatGPT/Claude 订阅通常只提供 LLM,不代表 TTS 也可用。TTS 分两档:

- 商用发布优选:用户录音、火山豆包、OpenAI-compatible TTS、自定义真实 TTS CLI。默认自动择优,有云 TTS 或录音就优先使用。
- 零 key样片:Kokoro 中文本地 TTS。Apache-2.0 权重,可用于免费试听和流程验证,但不再默认通过 `--strict` 发布门;发布级仍建议用户录音或自然中文云 TTS。
- 用户自装零 key:Piper 中文本地 TTS。Piper/模型涉及 GPL-3.0,只能由用户自装,灵剪只子进程调用,不进入核心依赖树。
- 预览级:macOS `say`、espeak-ng。零 key、可验证流程,但不是发布级;`--strict --release` 会因 `RELEASE_AUDIO_IS_PREVIEW_VOICE` 阻断。

先安装零 key 中文 Kokoro:

```bash
uv sync
npx hyperframes tts --list
uv run lj setup
```

`uv sync` 会安装灵剪的 Kokoro ONNX 运行包;`npx hyperframes tts --list` 用于确认 HyperFrames 的本地 Kokoro 资源可用。

只确认本机预览级是否可用:

```bash
say "灵剪语音检测"
uv run lj setup
```

macOS 的 `say` 不需要 key,但只用于预览。其他系统可安装 espeak-ng 预览音,或安装 Kokoro/Piper 作为本地 TTS。

如果你已经录好了口播音频,可以不用 TTS provider:

```bash
uv run lj voice ./projects/demo --provider auto --voice user --audio-file narration.m4a --json
# 或主线:
uv run lj run ./projects/demo --input-file input.txt --script-provider auto --voice-audio-file narration.m4a --json
```

这会写入 `provider_id=user_audio`,不标 mock,也不会把原始文件路径写进导出包。

无论使用用户录音还是云 TTS,都要先确认“这条视频应该怎么说”。产品介绍视频默认是清晰、亲和、可信、有产品发布感;教程类更稳、更清楚;带货类可以更有行动感,但不能夸张吼叫。配音导演确认通过后,再进入试听和 voice 审批。

试听正式音轨后,Codex 必须给用户三个清楚入口:满意就说“批准配音”;觉得慢就说“压到 45 秒”或目标时长;觉得语气不对就直接描述听感,例如“更有激情一点 / 更像产品发布 / 更亲切 / CTA 更有号召力”。普通用户不需要理解 TTS 参数名。

Piper(GPL-3.0,用户自装):

```bash
pip install piper-tts
python3 -m piper.download_voices zh_CN-huayan-medium
uv run lj setup
```

Ubuntu/Debian 预览音:

```bash
sudo apt-get update && sudo apt-get install -y espeak-ng
uv run lj setup
```

Windows:

```powershell
winget install Gyan.FFmpeg
ffmpeg -filters | findstr drawtext
```

Windows 本机 TTS 当前建议通过 Piper、espeak-ng 或 OpenAI-compatible TTS 接入;macOS `say` 仅在 macOS 可用。

确实需要云 TTS 时再配置:

中文发布级 TTS 首选火山豆包:

新版开通入口:

- 开通服务/领取活动: https://console.volcengine.com/speech/new/setting/activate?projectName=default
- 创建 API Key: https://console.volcengine.com/speech/new/setting/apikeys?projectName=default

普通用户只需要复制 `API Key`。`Resource ID` 默认使用 `seed-tts-2.0`,`Voice Type` 默认使用中文女声;高级用户才需要覆盖。不要把完整 key 发到聊天里。

拿到 API Key 后,按你的系统选择一条命令。粘贴 key 时都不要加双引号。

macOS zsh:保存到 Keychain,再加载到当前终端:

```bash
echo "现在把火山豆包 API Key 保存到 macOS 钥匙串。"
echo "下一步请直接粘贴 API Key 原文,不要加双引号。"
echo "粘贴时终端不会显示内容,这是正常的。"
printf "请粘贴 API Key,然后按回车:"
stty -echo
IFS= read -r LINGJIAN_VOLC_KEY
stty echo
printf "\n"
security add-generic-password -a lingjian:VOLCENGINE_TTS_API_KEY -s lingjian:VOLCENGINE_TTS_API_KEY -w "$LINGJIAN_VOLC_KEY" -U
unset LINGJIAN_VOLC_KEY
export VOLCENGINE_TTS_API_KEY="$(security find-generic-password -a lingjian:VOLCENGINE_TTS_API_KEY -s lingjian:VOLCENGINE_TTS_API_KEY -w)"
uv run lj setup
```

Linux:安装 `secret-tool`,保存到 Secret Service,再加载到当前终端:

```bash
sudo apt install libsecret-tools
printf "请粘贴 API Key,不要加双引号,然后按回车:"
stty -echo
IFS= read -r LINGJIAN_VOLC_KEY
stty echo
printf "\n"
printf "%s" "$LINGJIAN_VOLC_KEY" | secret-tool store --label="Lingjian Volcengine TTS API Key" service lingjian:VOLCENGINE_TTS_API_KEY account lingjian:VOLCENGINE_TTS_API_KEY
unset LINGJIAN_VOLC_KEY
export VOLCENGINE_TTS_API_KEY="$(secret-tool lookup service lingjian:VOLCENGINE_TTS_API_KEY account lingjian:VOLCENGINE_TTS_API_KEY)"
uv run lj setup
```

Windows PowerShell:最短路径是只配置当前会话,不落盘:

```powershell
$secure = Read-Host "请粘贴 API Key,不要加双引号" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $env:VOLCENGINE_TTS_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
uv run lj setup
```

Windows 要持久化时,写成**用户环境变量**(灵剪在 Windows 上就是从进程环境读取 key,这样重开终端后自动读到,无需每次设置):

```powershell
# 持久化到用户环境变量(推荐)
[Environment]::SetEnvironmentVariable("VOLCENGINE_TTS_API_KEY", (Read-Host "请粘贴 API Key,不要加双引号"), "User")
# 或经典命令行等价写法:  setx VOLCENGINE_TTS_API_KEY "你的KEY"
# ⚠ 设完必须【重开一个新终端】才生效(User 级变量不影响当前已开的会话)
uv run lj setup
```

临时试用也可以只在当前终端设置:

```bash
export VOLCENGINE_TTS_API_KEY=...
# 可选高级覆盖:
# export VOLCENGINE_TTS_RESOURCE_ID=seed-tts-2.0
# export VOLCENGINE_TTS_VOICE_TYPE=zh_female_vv_uranus_bigtts
uv run lj doctor --json
```

也可以使用 OpenAI-compatible TTS:

```bash
export OPENAI_TTS_BASE_URL=https://api.example.com/v1
export OPENAI_TTS_API_KEY=...
export OPENAI_TTS_MODEL=...
uv run lj doctor --json
```

## 画面能力:Seedance 文生视频(发布级)

零素材用户「一句话 → 真动态视频」的核心。灵剪内置 Seedance 适配器,检测到火山方舟 ARK key 时,画面关按分镜提示词**直接调用 Seedance 生成发布级真实视频**(不是引导你自己去生成)。ARK 与火山 TTS 同源一个火山账号。

开通与领 key:

- 火山方舟控制台开通 Seedance 模型(`doubao-seedance-2-0-mini`);**只开这个模型,别点 OpenAllModels**。
- 视频生成有账户余额门槛,以火山官方页为准。
- 在 API Key 管理页创建 ARK API Key。

配置 ARK key(与火山 TTS 同一套安全存储;存一次,灵剪启动自动加载,无需每次手动 export)。粘贴 key 时都不显示字符,是正常的:

macOS(钥匙串):

```bash
printf "请粘贴火山方舟 ARK API Key,然后按回车:"
stty -echo; IFS= read -r LJ_ARK; stty echo; printf "\n"
security add-generic-password -a "lingjian:VOLCENGINE_ARK_API_KEY" -s "lingjian:VOLCENGINE_ARK_API_KEY" -w "$LJ_ARK" -U
unset LJ_ARK
uv run lj setup
```

Linux(Secret Service):

```bash
printf "请粘贴 ARK API Key,然后按回车:"
stty -echo; IFS= read -r LJ_ARK; stty echo; printf "\n"
printf "%s" "$LJ_ARK" | secret-tool store --label="Lingjian Volcengine ARK API Key" service lingjian:VOLCENGINE_ARK_API_KEY account lingjian:VOLCENGINE_ARK_API_KEY
unset LJ_ARK
uv run lj setup
```

Windows PowerShell — 持久化(推荐,重开终端后灵剪自动读到):

```powershell
[Environment]::SetEnvironmentVariable("VOLCENGINE_ARK_API_KEY", (Read-Host "请粘贴 ARK API Key"), "User")
# 或:  setx VOLCENGINE_ARK_API_KEY "你的KEY"
# ⚠ 设完必须【重开一个新终端】才生效
uv run lj setup
```

只想当前会话临时试用(关终端即失效):`$env:VOLCENGINE_ARK_API_KEY = "你的KEY"`(bash 下 `export VOLCENGINE_ARK_API_KEY=...`)。key 只从环境/安全存储读取,绝不写仓库、日志或导出包;`lj doctor` 只显示是否具备,不回显 key。配好后 `lj doctor` 会把「Seedance 文生视频(发布级)」列为已具备画面能力;`lj run ... --engine seedance` 或缺素材时自动用它按镜生成真视频。

## FFmpeg 与字体

release 渲染必须本机安装 FFmpeg/ffprobe,并且 FFmpeg 必须支持:

- `drawtext/libfreetype`:用于烧录中文字幕。
- AAC 音频编码:用于把真实 TTS 配音合入发布视频。

只安装到二进制还不够;`lj doctor` 会实际探测这些能力,缺失时保持 `ready=false`。

macOS:

```bash
brew install ffmpeg
ffmpeg -hide_banner -h filter=drawtext
```

如果 `drawtext` 不存在,请安装或切换到带 freetype 的 FFmpeg,例如:

```bash
brew reinstall ffmpeg
brew install ffmpeg-full
brew unlink ffmpeg && brew link ffmpeg-full
ffmpeg -filters | grep drawtext
```

Ubuntu/Debian:

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
ffmpeg -filters | grep drawtext
```

Windows:

```powershell
winget install Gyan.FFmpeg
ffmpeg -filters | findstr drawtext
```

字体:

- macOS 默认使用 PingFang。
- 其他系统缺字体时,放置 `~/.cache/lingjian/fonts/NotoSansSC-Regular.otf`。

## 画面能力:HyperFrames 零 key 优先,自备素材稳态回落

灵剪核心不内置 Remotion/HyperFrames SDK。它会在 visuals 阶段生成每镜 storyboard,每镜包含:

- `generator`: `hyperframes`、`remotion`、`image-gen`、`user-asset` 或 `fallback_solid`;其中 `image-gen` 只能作为静态参考图/样片素材,不能单独满足发布级画面。
- `visual_prompt`: 给 imagegen 的画面提示词。
- `motion_spec`: 给 HyperFrames/Remotion 的主运动结构描述。
- `brief`: 比例、安全区、禁项。
- `layout_contract`: textRect/subjectRect/ctaRect/quiet_text_zone/safeBottomY/title_tier,用于提前锁定字幕与主体/CTA 关系。
- `motion_intent`: 主运动意图、转场意图、全时长发展与确定性规则,不指定具体动画基元。
- `expected_asset_path`: 约定资产落点。
- `duration_sec`: 与配音时长对齐。

当前已验证的零 key 画面路径是检测到 `npx hyperframes` 后,用薄子进程适配器按镜头生成:

```text
project/assets/scenes/<scene_id>.mp4
```

你也可以直接提供每镜素材,这是稳定回落路径:

```text
project/assets/scenes/<scene_id>.mp4
project/assets/scenes/<scene_id>.png
```

Codex app 用户也可以在 Plugins / Add to Codex 中安装或启用更完整的宿主画面插件/skill。命令只是备用:

```bash
npx skills add heygen-com/hyperframes
npx skills add remotion-dev/skills
```

上面两个标识符分别来自 HyperFrames 与 Remotion 官方 skill 安装入口。注意:

- HyperFrames 需要 Node.js 22+ 与 FFmpeg。本仓库内置适配器只能生成样片动效;发布级必须人工确认画面不是单图/模板循环,或使用宿主插件/用户素材生成真实内容画面。
- Remotion 需要 Node.js 与自动下载的 Chrome Headless;营利组织若超过 3 人使用,需核对 Remotion 商用 license。
- 若 skills CLI 或 Codex 插件市场发生变化,以官方文档和 Codex app 插件市场为准:

- HyperFrames: https://hyperframes.heygen.com/quickstart
- Remotion Agent Skills: https://www.remotion.dev/docs/ai/skills

安装后新开 Codex 会话,再跑 `uv run lj setup`。宿主 agent 或灵剪薄适配器使用已启用的 HyperFrames/Remotion/imagegen 产出:

```text
project/assets/scenes/<scene_id>.mp4
project/assets/scenes/<scene_id>.png
```

如果宿主没有这些能力,也没有用户自备视频素材,lj 会回落纯色卡片。普通 release 默认给 warning;发布级验收请使用 `--strict`,此时会阻断回落卡片、内置样片模板、单素材循环和静态图片镜头。

这不是默认 release 硬门,是发布级质量门:没有真实画面仍可做低保真预览,但不能声称已经生成可发布动态画面。

画面三审时请看 `artifacts/visual_plan.json` 的 `director_review_sheet_v2.scenes[]`。每镜的 `asset_diagnosis` 会说明素材是“发布级动态视频候选”还是“静态参考/缺素材”;如果缺素材,`asset_diagnosis_summary.single_next_action_zh` 是当前最短补齐动作。

P1 起,`visual_plan.json` 还会带 `director_router_summary` 和 `director_knowledge_base_v1`。这些字段主要给 Codex 翻译成人话:每镜为什么选 HyperFrames、Remotion、用户视频素材或待补素材,以及这一类视频必须具备哪些真实证据画面。普通用户只需要看 Codex 总结出来的“路由理由”和“下一步动作”。

付费/账号能力不会静默调用。火山、fal、picsart 等会在 artifact 中记录 `cost_notices`;Codex 必须先说明账号/费用前提并得到确认。Remotion 作为 opt-in 第二引擎时,必须提示 Node/Chrome Headless 与商用 license,并把用户确认写入 `engine_policy.license_confirmation.status=confirmed` 或等价字段。只提示不确认时,`--release --strict` 会阻断 Remotion 镜头。

CLI 委托入口可选:

```bash
export LINGJIAN_HOST_IMAGEGEN_CLI=/path/to/real-imagegen
export LINGJIAN_HOST_HYPERFRAMES_CLI=/path/to/hyperframes
export LINGJIAN_HOST_REMOTION_CLI=/path/to/remotion
```

这些命令只接收 storyboard JSON 并把资产写到 `expected_asset_path`;灵剪不会读取它们的凭据文件。

## 安全承诺

我郑重承诺:

- 默认只读取当前 shell 环境变量,不把 key 写入仓库、日志、manifest、release 包或 stdout。
- 能继承 CLI 能力时,不会要求你提供 key。
- 继承订阅只调用厂商官方 CLI,不读取 OAuth token、cookie、Keychain 内部文件或私密凭据文件。
- 需要持久化凭据时:macOS 用 Keychain、Linux 用 Secret Service、Windows 用**用户环境变量**(灵剪 Windows 从进程环境读取,故存成 User 级变量、重开终端即自动生效)。
- 没有安全存储时,只有在你明确同意后才允许使用 `0600` 权限本地配置文件。
- `lj credentials status --json` 只显示是否存在,不显示值。
- `lj credentials forget NAME --json` 可撤销已存凭据;当前 shell 里的变量仍需你自己 `unset`。

## 真实终验

当 Codex 确认能力门诊 ready 后,再执行真实终验:

```bash
uv run python scripts/ci/run_verification.py
```

此时 `V-REAL-01` 才会真实执行 script -> voice -> visuals -> approve -> render --release -> qa --release -> export --release -> ffprobe。

人工抽验发布视频时,应看到至少一个视频流和一个音频流:

```bash
ffprobe -v error -show_entries stream=codec_type,codec_name -of json <release-video.mp4>
```

真实环境终验以 `scripts/ci/run_verification.py` 的输出为准(results.json + 各步 evidence)。

## 用户、Codex、Claude 分工

- 用户:提供本机已登录 CLI、真实 provider key 或安装 FFmpeg 等外部条件。
- Codex:改代码、跑命令、生成证据、打包交付。
- Claude Code:拆需求、做架构规划与第 7 步审计复核。

任何前置不满足时,流程必须停下并说明缺什么。不能用 echo、固定 JSON、假 CLI 冒充真实 provider。
