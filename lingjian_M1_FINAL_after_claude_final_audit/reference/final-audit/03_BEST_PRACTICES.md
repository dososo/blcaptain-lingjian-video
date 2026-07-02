# 03 · 业界最佳实践与 LingJian 落地(BEST PRACTICES)

> 每条都给"实践 → LingJian 落地(落到 M1/M2)"。不写无落点的"未来探索"。

## 6.1 产品 / 流程

- **M1 必须是纵向主干,不是功能清单**。落地:验收只认"一条命令链从 init 走到 export 出真包",任何单点功能若不服务这条链就移出 M1(如 ASR、富 motion、本地克隆)。功能清单式交付会得到 20 个各 30% 的半成品。
- **三审门禁在系统层强制,不在 prompt 层约定**。落地:`render` 读 `approvals.json`,三项缺一即返回 `APPROVAL_REQUIRED` 并列出缺项;prompt/SKILL 只是提示,真值在磁盘。motion-director 的"两阶段确认"停在 prompt 层,LingJian 要做成硬约束(M1)。
- **Agent 流:停 → 返回 artifact → 等人审 → 续**。落地:generate 类命令返回 `{status:"awaiting_review", review_url, artifact_paths, next_actions}`;SKILL 明确"看到 awaiting_review 必须停并把审核链接交给人";CLI 非交互不得自动 approve(M1)。
- **Web 与 CLI 共享同一状态机**。落地:状态机 = `packages/core` 里的纯函数(输入 project 状态 + 事件 → 新状态 + 需写 artifact);API/CLI/(M2)MCP 都是它的薄封装;Web 不得自己维护第二套状态(M1)。
- **mock 只做 preview/test,不污染 release**。落地:provider 带 `is_mock=True`;`export --release` 见任一 mock provider 立即 `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`;非 release 导出可用 mock 但产物内 `provider_manifest` 标注 mock(M1)。

## 6.2 架构

- **分层**:`packages/core`(状态机/pipeline/artifact/门禁,无 IO 副作用尽量纯)→ `apps/api`(FastAPI 薄封装)/`apps/cli`(Typer 薄封装)→ `providers/*`(生命周期 adapter)→ `engines/*`(子进程 adapter)。`schemas` 为 Pydantic 权威并导出 JSON Schema。落地:core 不 import fastapi/typer;providers 不被 core 直接 new,由注册表按 id 解析(M1)。
- **Next.js 只做 console,不承载渲染/核心状态真值**。落地:Web 只调 API 读写 artifact,渲染在后端子进程;真值永远在后端文件(M1)。
- **子进程 adapter 边界**:每个外部引擎/重模型经 `run(cmd, cwd, timeout, env)` 封装,统一超时/退出码/stderr 采集/日志脱敏;绝不把其 SDK import 进 Python 核心。落地:加 CI 规则禁止 `import remotion|hyperframes|playwright` 出现在 `packages/core`/`providers`(Playwright 若用 Python 绑定,仅限 `providers/web_extract` 且标注)(M1)。
- **provider 生命周期统一接口**(D 层已定):`id / name / capabilities / is_installed() / is_configured() / doctor() -> ProviderStatus / setup_hint() -> str` + 每类能力方法(`LLM.generate` / `TTS.list_voices+synthesize` / `OCR.extract_text` / `WebExtractor.extract`)。落地:抽象基类 + 契约测试,任一实现缺方法 CI 失败,防生成器自由发挥(M1)。
- **renderer 接口统一**:`id / capabilities / is_installed() / doctor() / preview(storyboard,ratio)->draft / render(render_plan,dir)->RenderResult`;最终一律经 FFmpeg finalizer。落地:M1 只注册 `ffmpeg_card`;M2 注册 `hyperframes`;接口不变(M1)。
- **artifact schema = 单一事实源**;CLI JSON 输出 = artifact 的投影。落地:CLI `--json` 直接序列化 schema 对象;Web/API/MCP 复用同一序列化,保证四端一致(M1)。

## 6.3 渲染 / 字幕 / 音频

- **`ffmpeg_card` 作为可靠性地板**:确定性(同输入同输出)、纯 FFmpeg+Pillow/HTML、可 CI 快照。落地:冻结一条 recipe——每 scene 一张整帧 PNG(标题/正文/强调/截图/**字幕画进帧**)→ 图片清单带 duration → `-f concat` 单次 H.264 → 混 AAC → finalizer(响度/尺寸/封面/metadata);**禁止** zoompan/逐帧动画/转场(那会变小 Remotion,M1)。
- **字幕画进帧 vs sidecar**:M1 字幕画进帧(永远"已烧录"、用自控字体路径、跨平台稳),同时输出 SRT/VTT/ASS sidecar 供平台;libass 烧录留 M2。权衡结论:M1 选画进帧,规避 libass+字体+滤镜三重脆弱。
- **中文字体 fallback + license + doctor 下载**:探测系统 CJK(YaHei/PingFang/Noto CJK/文泉驿)→ 缺则下载 **Noto Sans SC(SIL OFL)** 到 `~/.cache/lingjian/fonts/`(**不入仓**);doctor 报告字体状态;帧内绘制与(M2)libass 共用此路径(M1)。
- **TTS 逐段时长作为时间真值**:`synthesize` 必须返回每段音频真实时长(合成后 ffprobe 实测,不用估算);scene/字幕时间轴由此推导,保证 sum(scene)=音频=字幕末尾=视频(M1)。
- **`ffprobe` 校验音画字一致**:QA 用 ffprobe 读实际 duration/分辨率/音轨,与 render_plan 比对,偏差超阈值 → hard fail(M1)。
- **9:16/16:9/3:4/4:3 layout compiler 最小可行**:一个"区块盒模型"(title/body/image/subtitle 四盒 + 字号 + safe_margin),按 ratio 给参数;M1 只需 9:16/16:9 手调 + 3:4/4:3 由同一 compiler 线性适配,**不做**逐 ratio 独立设计(M1)。

## 6.4 合规 / 安全

- **Apache-2.0 主仓处理 GPL/AGPL**:GPL/AGPL 项目(motion-director/LosslessCut/pyVideoTrans)**只学思想,禁止 vendor/复制/改写照搬**;若必须用其能力,只经**独立进程 CLI 调用且用户自行安装**,不进仓库、不静态链接(M1 文档 + CI/依赖审查)。
- **Remotion 仅 opt-in + doctor 显著提示**:M1/M2 不集成;M3 用户自装,doctor 输出 4+ 人付费/Automators 档提醒(M1 doctor 文案已需含此提示占位)。
- **模型权重与代码 license 分离**:不捆绑任何权重;本地模型外部服务;doctor 记录代码 license 与权重来源,发布包 `license_manifest.md` 列出(M1)。
- **声音克隆授权确认 + 默认关**:克隆能力(M3)默认关闭,启用需勾选"我拥有该声音授权"并记录到 QA;M1 不做克隆(M1/M3)。
- **URL 不下载他人视频(默认)**:ingest url 只做 trafilatura 正文 + metadata + (opt-in)Playwright 截图;**默认不触发 yt-dlp/视频下载**;如未来做需显式开关 + 授权声明(M1)。
- **安全基线**:API key 存 keychain 或加密文件、日志脱敏(key/token 不落日志);网页/文件名/上传当**不可信输入**;子进程不拼接未转义用户串(用参数数组);上传限制 MIME/大小/路径(防路径穿越,规范化到项目沙盒内)(M1)。

## 6.5 测试 / 交付

- **离线 CI**:全部单测用 mock provider,不联网/不 GPU/不需真 ffmpeg(ffmpeg 调用 monkeypatch)。落地:`pytest` 默认离线;真实 provider 集成测试用 `@pytest.mark.integration` 且需显式 env,不进默认 CI(M1)。
- **golden files / schema validation / CLI contract / Web smoke**:schema round-trip + JSON Schema 校验;CLI 每命令 `--json` 输出对 golden 快照;render 用固定输入产固定帧做像素/结构快照;Web Playwright smoke 对 mock 后端跑通主路径(M1)。
- **FFmpeg 输出最低验收**:ffprobe 断言 MP4 可解析、分辨率==preset、有音轨、时长在阈值、非全黑帧;中文帧内文字非空(M1)。
- **真实 provider 可选集成测试**:提供 `docs` 模板命令(见 08 §13.5),CI 不跑,人工/夜间跑(M1)。
- **release-ready vs preview-only 判定**:release = 无 mock provider + 三审齐 + QA 无 hard fail + canonical 结构完整;preview = 允许 mock、允许缺审(仅生成草稿)。两者在 export 层用不同校验门(M1)。
