# 03 · 给 Codex 的 M1 执行提示词(按 8 步业务流)
## 调研 → 分析 → 计划 → 开发 → 验证 → 测试 → 审计验收 → 总结

> 角色分工:**Claude Code = 读代码 / 拆需求 / 架构规划 / review 审计;你(Codex)= 改代码 / 跑命令 / 修测试 / 补验证证据。**
> 本轮你负责第 ④–⑥ 步(开发/验证/测试)+ 产出第 ⑦ 步(审计验收)所需证据 + 第 ⑧ 步总结。前三步(调研/分析/计划)已由 Claude Code 完成并固化在本包。
> **委托方硬立场:在你交出"DoD 全绿 + 10 项精修全落 + 伪成功扫描在代码上真跑通过 + 证据齐全"之前,本轮不算达标、不进最终审计。任一未过,照审计意见改进并继续迭代,不得谎报完成、不得静默缩范围、不得用 mock/占位冒充真实、不得编造运行结果。**

---

## 唯一实现依据(冲突时的优先级,从高到低)
1. `02_PRD_GOAL_REFINEMENTS.md` — 我的 10 项精修(**相对基线优先**)。
2. `base/LINGJIAN_M1_GOAL_ACCEPTED_BASE.md` — 已验收 GOAL(实现目标 + 验收命令全集 §19 + DoD §20)。
3. `base/LINGJIAN_M1_PRD_ACCEPTED_BASE.md` — 已验收 PRD(数据模型/接口/状态机/发布包/QA)。
4. `00_PRODUCT_DEFINITION_FINAL.md`、`01_UX_AND_BUSINESS_FLOW_FINAL.md` — 产品/UX/业务流上下文(Web 5 页与门禁 UX 以此为准)。
5. `reference/final-audit/*` — 调研与对抗审计底稿(许可证红线见 01;禁止伪成功见 08)。

`base/` 与 `reference/` 视为只读参考,不回写。

---

## 不可协商 D1–D9(违反任一 = 本轮判失败)
Python core/CLI/providers/API/(M2)MCP;Next.js 仅 Web;HyperFrames/Remotion/Playwright 全部子进程,**core/provider 禁 import 其 SDK**;M1 渲染只走 `ffmpeg_card`(SCOPE FREEZE);三审门禁系统层强制 + 绑 artifact hash + **无 `--force`**;不捆绑权重/字体;Remotion 不默认/不捆绑、克隆默认关+授权、**URL 默认不下载他人视频**;M1 主干真实可用不做全宽度;**mock 不能 release**;主仓 Apache-2.0;**AGPL/GPL 只研究不引入**(motion-director/LosslessCut/pyVideoTrans;不复制 VideoLingo 搬运模式)。

---

## ① 调研(充分收集汇总)—— 产出 `docs/dev/01_RESEARCH.md`
- 通读上述 1–5 全部依据;列出你将实现的模块清单 + 依赖清单 + 每个第三方依赖的 license(引用 `reference/final-audit/01`,不确定标"待确认",以仓库 LICENSE 为准)。
- 跑环境体检:`lj`/仓库尚不存在时,先记录目标环境需求(Python 3.11/3.12、Node 20、pnpm、uv、FFmpeg、CJK 字体);实现 doctor 后以其输出为准。
- 输出"许可证合规清单":确认无 AGPL/GPL 进主仓、无权重入仓、Remotion 不默认。

## ② 分析(架构与风险)—— 产出 `docs/dev/02_ANALYSIS.md`
- 画模块边界与数据流(core 状态机 / providers / engines / api / cli / web),标 D1 边界线。
- 逐条确认 10 项精修如何落地(R1 preview/release 隔离、R10 doctor 语义…),分配到 Batch。
- 风险表:确定性渲染、状态一致性、门禁不可绕、真实 provider 失败分类、CJK 断行。
- **不得在此步写实现代码**;这是规划产物。

## ③ 计划(最佳方案)—— 产出 `docs/dev/03_PLAN.md`
- 采用 GOAL 三批 + 精修分配:Batch 1(core/schema/CLI/mock/doctor/approval-hash + R3 history、R6 回环、R10 doctor 语义)→ Batch 2(真实 LLM/TTS/ffmpeg_card/QA/export + R1、R2、R4、R5、R7、R8、R9)→ Batch 3(Next.js 5 页 + provider 配置 + docs + 跨平台)。
- 每批列 DoD 与验收命令(引用 GOAL §19 对应段 + 精修新增断言)。
- 固定版本、lockfiles、CI 结构。

## ④ 开发(执行)
- 严格按 base GOAL §4/§5/§6 三批交付物 + 精修实现。硬规则:无 `--force`、无门禁绕过、`export --release` 遇 mock 失败、core/provider 无引擎 SDK import、`ffmpeg_card` 无 zoompan/动画/转场、preset 无平台名 if、file=真值/SQLite=派生。
- Web 5 页与门禁 UX 按 `01_UX_AND_BUSINESS_FLOW_FINAL.md` §C/§D 实现(每屏 3 主按钮、awaiting_review/stale/blocked 状态)。
- 每写一块,配对应测试与证据,不留"待补"。

## ⑤ 验证(逐条真跑,产证据)—— 产出 `verification/results.json` + `verification/evidence/<ID>.log`
执行 GOAL §19 全集 + 精修新增断言,至少覆盖:
`V-BASE-01..05`(uv sync / pytest 离线 / ruff / lj doctor --json 且 required 缺失退出码≠0[R10] / pnpm build);`V-GATE-01..04`(未审 render=APPROVAL_REQUIRED / 三审后出片 / 改稿=APPROVAL_STALE / 删 SQLite→reindex→status 一致);`V-REL-01`(mock export --release=MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE);**`V-REL-02`(export 引用 preview 产物=PREVIEW_ARTIFACT_NOT_RELEASABLE[R1]）**;`V-EXP-01/02`(canonical 结构 + YouTube thumbnail/description/chapters + export_manifest 含 approvals[R7]);`V-QA-01/02`(ffprobe 音画字一致 + 分级);`V-REND-01`(可解析/分辨率==preset/有音轨/非全黑/**中文帧内非空且断行合规[R9]**);`V-BLK-A01..A11`(6 Blocker 测试);`V-DEGRADE-01`(稀薄输入被 warn 引导不崩[R8]);`V-FORBID`(伪成功扫描在**代码上真跑**全"未发现");`V-REAL-01`(真实 provider release 包;无 key 则 `BLOCKED_ENV` 并置顶声明,不计通过)。
每项证据含完整命令 + stdout + stderr + exit code；results.json 每项 `{id,title,command,expect,exit_code,error_code,pass:true|false|"BLOCKED_ENV",evidence_file,notes}`。

## ⑥ 测试(CI 与质量门)
- 默认 CI **离线**:mock provider、ffmpeg 调用 monkeypatch、无网络/GPU/付费 key。
- golden(CLI `--json` 快照)+ provider 契约测试 + `ffmpeg_card` 容差快照[R4] + Web Playwright smoke(对 mock 后端)。
- 真实 provider 集成测试打 `@pytest.mark.integration` 需 env,不进默认 CI。
- import guard + render-path 断言 + ffmpeg_card scope 扫描 + `rg force/SKIP_APPROVAL/BYPASS_APPROVAL` 均纳入 CI。

## ⑦ 审计验收(为 Claude Code 复核产出证据)—— 产出 `verification/VERIFICATION_REPORT.md` + `verification/FORBIDDEN_SCAN.md`(代码版)+ `docs/dev/AUDIT_READY.md`
- `AUDIT_READY.md`:一张表,DoD §20 每条 + 10 项精修每条 → 已落实/位置(代码模块+测试名)/证据文件。Blocker 与 High 必须"已落实"。
- `FORBIDDEN_SCAN.md`:13 条伪成功**在代码上真扫描**,逐条"未发现/发现+位置+已修"。
- 达标闸门(全绿才可声明达标):DoD §20 全满足;10 项精修全落;⑤ 全绿(V-REAL 可 BLOCKED_ENV 置顶待复验);⑥ CI 绿;伪成功扫描全"未发现";三份证据彼此一致无夸大。**任一红 → 不得声明达标,修到绿或如实上报失败证据+诊断+拟修方案并停下等审计方。**

## ⑧ 总结 —— 产出 `docs/dev/08_SUMMARY.md` + 打包 `lingjian_M1_codex_delivery_iter_N.zip`
- 摘要:本轮结论(达标/有条件达标 BLOCKED_ENV/未达标)、三批完成度、DoD x/x、精修 x/x、验证 PASS/FAIL/BLOCKED_ENV、伪成功扫描结果、未达标/待复验清单、delta。
- 打包交回:全部实现代码 + `docs/dev/01..03,08` + `AUDIT_READY.md` + `verification/`(results.json + evidence + FORBIDDEN_SCAN)+ 两份 base 文档(标注未改动)。
- 交回后进入第 ⑦ 步的 **Claude Code 复核**;未达标 → Claude Code 出新意见 → 回 ④ 迭代,直到 DoD 全绿。

---

## 纪律
全程中文;直接可执行不空泛;不确定标"待确认"并以仓库 LICENSE 为准;不复制第三方 README/prompt/template/UI/AGPL·GPL 代码;不谎报完成、不静默缩范围、不用 mock/占位冒充真实、不加门禁绕过、不编造运行结果;对 D1–D9 或 10 项精修有充分技术理由反对时,必须写明理由+替代+迁移成本+风险变化,不得无声忽略。

开始:先产出 ① ② ③(调研/分析/计划),经确认后再进 ④ 开发。
