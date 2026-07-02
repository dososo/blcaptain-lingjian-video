# 07 · GOAL 精确修改建议(GOAL PATCH SUGGESTIONS)

> 基线:`lingjian_video_studio_v1_GOAL_executable.md`(`_rebuilt` 版未随包提供)。重点:验收命令、真实可用判据、禁止事项、实现顺序。
> 格式:章节｜问题｜建议替换/新增文本｜理由｜优先级(P0/P1/P2)。

---

**P0-1｜固化决策｜删除 `--force`,补审批失效码**
替换 D3 行为为:"render 读 `approvals.json`,对 script/voice/visuals 重算 `artifact_sha256` 比对;缺项→`APPROVAL_REQUIRED`;hash 不符→`APPROVAL_STALE`;**无 `--force` 绕过**。"
理由:与 D3 一致,门禁不可绕。P0。

**P0-2｜§12 验收 / 新增错误码表｜结构化错误码清单**
新增:"CLI 必须返回稳定错误码:`APPROVAL_REQUIRED`、`APPROVAL_STALE`、`MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`、`FFMPEG_NOT_FOUND`、`FONT_CJK_MISSING`、`TTS_TIMEOUT`、`TTS_PROVIDER_ERROR`、`PROVIDER_NOT_CONFIGURED`、`TRAFILATURA_LICENSE_BLOCKED`、`PATH_OUTSIDE_PROJECT`。每个错误码 `--json` 输出 `{error_code, message_zh, hint}`。"
理由:Agent 需可解析错误;验收可断言。P0。

**P0-3｜§3.1 必做 / 新增"架构不变量"｜CI import guard + 渲染路径断言**
新增:"CI 必须包含:①禁止 `packages/core`/`providers`(除 web_extract)import remotion/hyperframes/playwright SDK;②断言 render 代码路径只 import `engines.ffmpeg_card`;违反即 CI 失败。"
理由:D1/D2 硬化。P0。

**P0-4｜§12 验收｜验收命令必须证明"真实可用"而非 demo**
替换 §12 验收为三段(见 08 §13 全集):基础质量 + **门禁失败断言** + **release 禁 mock 断言** + **真实 provider 模板**。明确"仅 mock 全绿不算通过"。
理由:防交付"能跑 mock 的玩具"。P0。

**P0-5｜§8/§3.2 MCP｜M1 占位、M2 实现,统一 22 工具**
替换:"M1:`packages/mcp_server` 提供骨架 + 22 工具名(含 approve_script/voice/visuals)+ 调用返回 `{status:'not_implemented', since:'M2'}`;M2 用 CLI/core 薄封装实现,状态机同源。文档不得出现'M1 已实现 MCP'。"
理由:避免 MCP 拖垮 M1 且防文档冲突。P0。

**P1-1｜§3.1 必做｜Web 5 页 + OCR 可选 + 云 TTS 同步**
替换:Web 从 8 页改 5 页(保人审);OCR 标"可选 provider,默认不装";云 TTS 标"仅同步,异步推 M2";EdgeTTS 标"非官方在线,doctor 标注,生产并列云 TTS"。
理由:压缩 M1 工期风险(A10/A12/A13/A14)。P1。

**P1-2｜§3.1/§6｜ffmpeg_card 能力封顶 + TTS 逐段时长**
新增:"ffmpeg_card SCOPE FREEZE(静态帧+帧内字幕+concat+finalizer,禁动画/转场);`synthesize` 后 ffprobe 实测逐段时长为时间真值;QA ffprobe 复核音画字一致。"
理由:防蔓延 + 对齐可靠(A11/A20)。P1。

**P1-3｜§9 平台 / §13 preset｜纯配置层 + canonical export 校验**
新增:"渲染/导出无平台名 if,全读 preset 字段;export 后校验 `exports/<project>/<platform>/<language>/<ratio>/` 含 video/metadata/captions(srt+vtt+ass)/source_map/qa_report/provider_manifest/license_manifest/cover_or_thumbnail,缺文件即失败。"
理由:防平台特化爆炸 + 保发布包完整(A15/A21)。P1。

**P1-4｜§10 测试｜离线 CI + golden + 契约 + smoke + 集成分离**
替换测试段:"默认 CI 全离线(mock provider,ffmpeg monkeypatch,无 GPU/网络);含 schema round-trip、CLI `--json` golden 快照、ffmpeg_card 固定输入像素/结构快照、Web Playwright smoke(对 mock 后端)、provider 契约测试;真实 provider 集成测试打 `@pytest.mark.integration` 需 env,不进默认 CI。"
理由:CI 不得依赖网络/GPU;可验收(A24)。P1。

**P1-5｜§11 合规硬规则｜AGPL/GPL 禁入 + 权重不捆绑 + URL 不下载**
新增:"禁止 vendor/复制/改写 AGPL/GPL 项目(motion-director/LosslessCut/pyVideoTrans);Remotion 不默认/不捆绑;不捆绑模型权重/字体;ingest url 默认不下载他人视频(不引入 yt-dlp 默认路径);发布包出 `license_manifest.md`。"
理由:合规红线落地(01-合规红线)。P1。

**P1-6｜§4 目录 / 安全｜安全基线 + 版本钉死**
新增:"注入/路径穿越/命令注入/key 脱敏基线(见 03 §6.4);固定 Python 3.11/3.12、Node 20 LTS、pnpm(packageManager)、uv;提交 lockfiles + .python-version。"
理由:真实用户安全 + 可复现(A28/A27)。P1。

**P1-7｜§13 实现顺序｜改为 3 个真实增量批次**
替换 §13 实现顺序为 08 的 Batch 1/2/3(每批真实增量 + 验收命令);明确"不退回 demo、不取消主干、门禁/release 判定/ffmpeg_card/canonical export 不推迟到 M2"。
理由:一次全量不可靠;批次化保交付(A24、§12 批次评审标准)。P1。

**P2-1｜§16 明确不做｜补充禁止项**
新增:"禁止 `--force` 门禁绕过;禁止 mock 用于 release;禁止渲染动画/转场(M1);禁止默认下载他人视频;禁止把 ASR/富 motion/本地克隆/Remotion/桌面写入 M1 段落。"
理由:把审计红线固化进"不做事项"。P2。

**P2-2｜§15 文档｜doctor/troubleshooting 覆盖中文用户**
新增:troubleshooting 覆盖 Windows/中文路径/FFmpeg/字体(Noto Sans SC 下载)/Playwright(`pip install playwright && playwright install`)/国内模型 base_url 配置。
理由:中国用户友好最低标准(05)。P2。
