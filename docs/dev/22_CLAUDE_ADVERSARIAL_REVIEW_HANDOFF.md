# 22 Claude 对抗式审查移交:开源首用路径、行业对标与边界

日期:2026-07-02

## 一句话结论

灵剪当前已经从“工程可跑”推进到“Codex 桌面版用户可按能力检测进入主线”:先安装 skill,再由 `lj setup` 检测 LLM/TTS/画面插件/FFmpeg/字体,缺什么就引导补什么;脚本、配音、画面三审后由 FFmpeg 组装、QA、导出。

但它不是一个“开箱即生成发布级爆款视频”的系统。发布级体验仍取决于用户环境是否具备:

- 真实 LLM:优先继承 Claude/Codex CLI,或用户配置 API/CLI。
- 真实音轨:发布级 TTS API,或用户已录好的口播音频。
- 真实画面:Codex 桌面版已安装/启用 HyperFrames、Remotion、imagegen 插件或 skill,或用户提供每镜 mp4/png。
- 本机 FFmpeg/ffprobe/drawtext/AAC。

## 行业对标观察

本轮参考的是开源 agent video skill / video production 生态,不是传统剪辑软件。

### 1. video-use

参考点:

- 第一屏把用户动作压缩成“把素材放进文件夹,和 agent 对话,拿到 final.mp4”。
- install 文档强调 agent 安装后读取 `SKILL.md`,用户只需要在素材目录里说一句要编辑什么。

灵剪吸收:

- 新增 `docs/CREATOR_QUICKSTART.md`,按“有文案 / 有录音 / 缺 TTS / 缺画面插件 / 发布前检查”给用户路径。
- `README.md` 增加真内容命令,不再只给 mock 预览。

不吸收:

- video-use 聚焦已有视频素材剪辑。灵剪主线是“文案/素材 -> 脚本 -> 配音 -> 画面 -> 渲染 -> QA -> 导出”,不做通用时间线剪辑器。

### 2. chengfeng-videocut-skills

参考点:

- 定位非常窄:口播教程、产品演示、知识讲解、结果展示。
- 明确“不是通用剪辑软件”,把传统时间线操作改成 agent 可读写工作流。

灵剪吸收:

- `SKILL.md` 和 README 继续强调“短视频生产主干”而非全类型剪辑工具。
- `docs/CAPABILITY_MATRIX.md` 把 Skill、CLI、MCP、Web、画面插件、TTS、FFmpeg 的能力状态拆开,减少误解。

不吸收:

- 不把平台玩法、爆款算法、平台知识包并入核心主线。

### 3. codex-storyboard

参考点:

- 面向 Codex 的本地分镜工作台,让用户不必理解 MCP/API/文件路径。
- 支持让 Codex 调 Image Generation、HyperFrames、Remotion 生成图片/视频素材并回填分镜。

灵剪吸收:

- 明确 Codex 桌面版完整路径:灵剪核心不内置 Remotion/HyperFrames,但应引导用户安装/启用宿主插件或 skill;宿主按 `visual_plan.json` 的 `expected_asset_path` 生成资产,灵剪消费资产。
- `packages/core/capabilities.py` 缺画面能力时 now 给出插件/skill 安装和新开会话提示。

不吸收:

- 本轮不实现完整 MCP server,也不宣称 Web 控制台可替代 CLI 审批流。

### 4. hyperframes-motion-director

参考点:

- 把产品故事、文章、README 或网站转成 HyperFrames motion-video production。
- 强调 Chinese-first 竖屏视频、可读 hold frames、交付前 review step。
- 生产分两阶段:先结构化方案/brief,再生成。

灵剪吸收:

- `visuals` 阶段已生成每镜 `visual_prompt`、`motion_spec`、`brief`、`expected_asset_path`、`duration_sec`,作为宿主生成契约。
- script / voice / visuals 三审仍是硬主线,不是后台自动乱跑。

不吸收:

- 不在核心内实现 HyperFrames 引擎,不把 `engines/ffmpeg_card` 扩展成复杂动画引擎。

### 5. OpenMontage

参考点:

- 定位为 agentic video production system,把研究、脚本、资产、配音、音乐、剪辑、合成拆成 pipeline。
- Agent guide 强调 agent 读 pipeline manifest、stage skill、工具、self-review、checkpoint,再交人审批。
- 社区讨论也承认用户可以提供自己的 narration/素材集合。

灵剪吸收:

- 保留 pipeline artifact:script / voice_plan / visual_plan / render_manifest / qa_report / export_manifest。
- 新增用户录音入口:`lj voice --audio-file` 与 `lj run --voice-audio-file`,不强迫用户必须接 TTS API。

不吸收:

- OpenMontage 是大而全的视频生产系统。灵剪当前不扩成 12 pipelines / 52 tools / 大量 provider 的系统,先保证主线可审计、可复跑。

### 6. video-editing-skill / Prompt gallery 类项目

参考点:

- 给用户大量可复制提示词。
- 明确前置依赖和适用边界。

灵剪吸收:

- `docs/CREATOR_QUICKSTART.md` 给了可复制给 Codex 的提示词。
- `README.md` 顶部仍保留 30 秒对话式安装提示词。

不吸收:

- 不把 README 堆成巨型 prompt 库;只保留主线场景。

### 7. viral TikTok / content-skill 类项目

参考点:

- 适合做 hook、脚本、平台内容策略和短视频标题。

灵剪态度:

- 这些可以作为未来可选 skill 组合,但不进核心。灵剪不承诺爆款、不内置平台算法、不以“1.3 秒钩子”等营销规则作为 release 门禁。

## 当前灵剪完整用户工作流

### 0. 安装 skill 与依赖

用户复制 README 顶部 prompt 给 Codex/Claude Code。agent 应执行:

```bash
uv sync
scripts/install_skill_links.sh
uv run lj setup
uv run lj doctor --json
```

审查点:

- 是否仍有 `<REPO_URL>` 阻断公开发布安装。当前是已知发布前 P0。
- 是否软链整个目录,而不是只复制 `SKILL.md`。

### 1. 能力检测

`lj setup` 应把能力分成:

- 已继承:例如 Claude/Codex CLI 做 LLM,macOS say 做预览级 TTS,FFmpeg/字体。
- 缺失:例如发布级 TTS、真实画面插件、FFmpeg drawtext。

审查点:

- 缺画面能力时,是否明确引导 Codex 桌面版用户安装/启用 HyperFrames、Remotion、imagegen 插件或 skill。
- 安装插件/skill 后是否提示“新开会话再跑 setup”。
- 缺 TTS 时,是否同时给 API 和用户录音两条路,而不是只要 key。

### 2. 输入素材

当前支持:

- 文本:`--input-file input.txt`
- URL:`lj ingest url`
- 图片:`lj ingest image`
- 用户已录口播:`--voice-audio-file narration.m4a` 或 `lj voice --audio-file narration.m4a`
- 用户已有画面:放入 `project/assets/scenes/<scene_id>.mp4|png`

审查点:

- 用户录音是否标为 `provider_id=user_audio`、`provider_is_mock=false`。
- 导出包是否泄漏用户原始音频路径。

### 3. 脚本生成

真内容推荐:

```bash
uv run lj run ./projects/demo \
  --name "演示项目" \
  --input-file input.txt \
  --script-provider auto \
  --voice-provider auto \
  --json
```

审查点:

- README 是否还把 mock 当作真内容默认路径。当前已补“真做内容建议 `--script-provider auto`”。
- mock 是否仍被禁止 release。当前门禁未削弱。

### 4. 配音

优先级:

1. 用户录音:`--voice-audio-file`。
2. 发布级 TTS:火山豆包、OpenAI-compatible TTS、真实 TTS CLI。
3. 预览级本机 TTS:macOS say/Piper/espeak-ng,release 可出但 QA warning。

审查点:

- 预览级 TTS 是否仍触发 `RELEASE_AUDIO_IS_PREVIEW_VOICE`。
- 用户录音是否可进入 release 音轨,并被 ffprobe 验证 audio stream。

### 5. 画面生成

主线:

1. `visuals` 生成每镜可执行规格。
2. Codex 宿主插件/skill 按 `expected_asset_path` 写出 mp4/png。
3. 灵剪 render 前探测并消费已有资产。
4. 缺失时 fallback_solid,QA warning。

审查点:

- 核心是否仍未 import/bundle Remotion/HyperFrames SDK。
- 缺插件时是否没有把 fallback_solid 宣称为真实动态画面。
- `visual_real_count` 是否真实反映消费到的资产。

### 6. 三审、渲染、QA、导出

主线:

- script 审核。
- voice 审核。
- visuals 审核。
- render preview 或 release。
- qa。
- export。

审查点:

- `--yes` 是否只用于显式自动审批,而不是隐藏绕过。
- release 仍需 doctor ready、非 mock、非 stub、视频流和音频流可验证。
- `QA_BLOCKING` 是否仍能阻断 release export。

## 已落地文件

- `docs/CREATOR_QUICKSTART.md`:创作者路径。
- `docs/CAPABILITY_MATRIX.md`:能力矩阵。
- `docs/dev/21_OPEN_SOURCE_USABILITY.md`:本轮实现说明。
- `README.md`:入口链接、真内容命令、录音命令、插件说明。
- `SKILL.md`:agent 执行规则。
- `docs/ONBOARDING.md`:检测与继承优先。
- `docs/providers.md`:provider 与用户录音路径。
- `docs/troubleshooting.md`:warning 和缺能力处理。
- `docs/skill-and-mcp.md`:Skill/插件/MCP 边界。
- `apps/cli/lingjian_cli/main.py`:用户录音 CLI 入口。
- `packages/core/capabilities.py`:缺画面能力时的插件/skill 引导。
- `packages/core/exporting.py`:用户录音 license manifest。

## 验证证据

本轮已跑:

- `uv run pytest -q`:99 passed。
- `uv run ruff check .`:All checks passed。
- 5 个扫描器:
  - `check_false_success.py`
  - `check_no_force.py`
  - `check_forbidden_imports.py`
  - `check_render_engine_m1.py`
  - `check_ffmpeg_card_scope.py`
- `pnpm --dir apps/web lint`:通过。
- `pnpm --dir apps/web build`:通过。
- `uv run python scripts/ci/run_verification.py`:52 PASS / 0 FAIL。
- `verification/results.json`:52 PASS。
- `V-REAL-01`:PASS,真实 release 补验已执行。

提交:

- `73745be feat: 补强开源首用工作流`
- `ba07bb1 chore: 忽略开源首用交付包`

交付包:

- `lingjian_open_source_usability_iter_12.zip`

## 对抗式审查建议

请 Claude 重点挑战以下问题:

1. 普通用户不懂 CLI/MCP/plugin 时,README 第一屏是否足够让 agent 接管安装?
2. `<REPO_URL>` 是否仍阻断真实开源发布?
3. `lj setup` 缺画面能力时,是否真的引导安装/启用 HyperFrames、Remotion、imagegen,而不是只说 fallback?
4. `--voice-audio-file` 是否足以覆盖用户已有口播音频的真实业务路径?
5. 用户录音是否会进入 release manifest、license manifest 或 stdout 泄漏本机路径?
6. 预览级 TTS 是否仍被明确 warning,没有被包装成发布级?
7. fallback_solid 是否仍被明确 warning,没有被包装成真实画面?
8. 灵剪是否仍没有 import/bundle Remotion/HyperFrames SDK?
9. MCP 是否仍被诚实标为未实现?
10. Web 是否仍被诚实标为静态骨架,没有宣称完整审批控制台?
11. 是否有任何新增路径削弱 mock 不可 release、stub 不可 release、ffprobe/audio hard gate?
12. `lj run --yes` 是否仍是显式授权,不是隐式绕过三审?
13. 参考行业项目后,灵剪是否仍保持聚焦,没有滑向大而全视频平台?

## 已知未完成项

- 公开发布前必须替换 `README.md` 中 `<REPO_URL>`。
- 最终 tag / GitHub release 需要在真实 remote 确认后执行。
- MCP server 仍未实现,但当前不阻断主线。
- Web 控制台仍是静态骨架,不能对外称为完整产品控制台。
- 发布级画面体验依赖用户在 Codex 桌面版安装/启用宿主插件或 skill;没有插件时仍是 fallback warning。
- 发布级配音体验依赖 TTS API 或用户录音;只有 say/Piper/espeak-ng 时仍 warning。

## 行业参考链接

- `video-use`: https://github.com/browser-use/video-use
- `video-use install.md`: https://github.com/browser-use/video-use/blob/main/install.md
- `chengfeng-videocut-skills`: https://github.com/Agentchengfeng/chengfeng-videocut-skills
- `codex-storyboard`: https://github.com/Yuuhann1999/codex-storyboard
- `hyperframes-motion-director`: https://github.com/geekjourneyx/hyperframes-motion-director
- `OpenMontage`: https://github.com/calesthio/OpenMontage
- `OpenMontage AGENT_GUIDE`: https://github.com/calesthio/OpenMontage/blob/main/AGENT_GUIDE.md
- `video-editing-skill`: https://github.com/maxazure/video-editing-skill
- `video-editing-skill prompts`: https://github.com/maxazure/video-editing-skill/blob/main/docs/prompts/README.md
- `viral-content` 方向参考: https://claudemarketplaces.com/skills/gonzalochale/skills/viral-tiktok-hooks
