# 最终交付包 · LingJian Video Studio M1(Claude 最终审计 + 最终版)

## 本轮审计结论(Claude)
对 ChatGPT 交付的 `LINGJIAN_M1_PRD/GOAL_FINAL_AFTER_CLAUDE_AUDIT.md`:
- **文档层达标(诚实、高质量)。** 已逐节核对:6 个 Blocker + 12 个 High 在 PRD/GOAL 均有真实落点(Approval+canonical hash、ffmpeg_card SCOPE FREEZE、canonical 发布包+release_ready、GOAL §19 具体到 `test -f` 的验收、DoD);运行时项全部诚实标 `PENDING_AGENT`,无一假 pass;并把 Playwright 收紧为全程 subprocess(合理加强)。
- **同意其"有条件达标":文档层通过,运行时合法待 Codex 执行。**
- **我在其上加固:** 补齐你点名的软定义层(受众/场景/最终目标/约束/边界、UI/UX、业务流),并对它的文档做对抗审计,追加 **10 项精修**(preview/release 物理隔离、doctor Agent 语义、artifact 历史、CJK 断行、真实 provider 错误分类、稀薄输入校验、状态机回环、审批 provenance、快照容差、extract 路由歧义)。

**结论:进入开发(第 ④ 步)。工程基线已接受,软定义与精修已补齐,Codex 可据此实现。**

## 这份"最终版"的构成(为什么不重写 2200 行)
ChatGPT 的 PRD/GOAL 我验证过、质量足够,重写只是内耗。最终版 = **已验收工程基线 + 我的刷新层 + 10 项精修 + 按 8 步流程重组的 Codex 提示词**。冲突时优先级:精修 > 基线 GOAL > 基线 PRD > 产品/UX 定义 > 调研底稿。

## 文件地图
```text
README_FINAL.md                          # 本文件:审计结论 + 用法 + 闭环
00_PRODUCT_DEFINITION_FINAL.md           # ★ 受众/场景/最终目标/约束/边界(软定义终稿)
01_UX_AND_BUSINESS_FLOW_FINAL.md         # ★ UI/UX 规范 + 业务流泳道 + 8 步流程映射
02_PRD_GOAL_REFINEMENTS.md               # ★ 对基线的 10 项精修(相对基线优先)
03_CODEX_M1_EXECUTION_PROMPT_8STEP.md    # ★ 交给 Codex 的执行提示词(调研→…→总结)
base/
  LINGJIAN_M1_PRD_ACCEPTED_BASE.md       # 已验收工程基线 PRD(ChatGPT 版,未改动)
  LINGJIAN_M1_GOAL_ACCEPTED_BASE.md      # 已验收工程基线 GOAL(验收命令 §19 + DoD §20)
reference/
  CHATGPT_AUDIT_RESPONSE_MATRIX.md       # ChatGPT 的逐条响应(留档)
  CHATGPT_BLOCKER_RESOLUTIONS.md         # ChatGPT 的 6 Blocker 机制(留档)
  final-audit/00..08                     # 我的原始调研+对抗审计底稿(可追溯)
```

## 怎么用(下一步)
把**整包**交给 Codex,执行根目录 `03_CODEX_M1_EXECUTION_PROMPT_8STEP.md`。它会按 调研→分析→计划→开发→验证→测试→审计验收→总结 推进,以 `base/GOAL + 02 精修` 为唯一实现依据,产出代码 + `verification/` 证据 + `AUDIT_READY.md`,打包回交。

## 8 步闭环与角色(你的流程)
调研①/分析②/计划③ = **Claude Code 已完成(本包即终稿)** → 开发④/验证⑤/测试⑥ = **Codex(用 03)** → 审计验收⑦ = **Claude Code 复核 Codex 证据** → 总结⑧ → 未达标回 ④ 迭代,直到 DoD 全绿。

## 达标闸门(第 ⑦ 步 Claude Code 复核的判据)
DoD §20 全满足 + 10 项精修全落 + GOAL §19 验收全绿(真实 provider 项可 BLOCKED_ENV 置顶待 key 复验)+ 离线 CI 绿 + 13 条伪成功扫描在代码上真跑"未发现" + 证据三件套一致无夸大。**未达标不算最终审计通过。**

## 仍存在的唯一外部依赖
真实 LLM/TTS 的 release 路径需要真实 key。Codex 环境若无 key,该项标 `BLOCKED_ENV` 并置顶;最终终审需在有 key 环境复验一次真实 release 包。其余全部可在离线环境判定。
