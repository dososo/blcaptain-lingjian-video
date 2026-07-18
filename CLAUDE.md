# Claude 审计入口

本仓库由 Codex 执行代码实现、命令验证和证据落盘。Claude Code 可从以下文件开始复核:

- `docs/dev/AUDIT_READY.md`: DoD、R1-R10、验证项和阻塞项总表。
- `verification/results.json`: 逐条命令结果。
- `verification/VERIFICATION_REPORT.md`: 验证摘要。
- `verification/FORBIDDEN_SCAN.md`: 13 项伪成功扫描。
- `tasks/todo.md`: 8 步执行轨迹。

重点复核:

- `V-REAL-01` 是否在无真实 key/CLI 环境中置顶为 `BLOCKED_ENV`。
- mock release 是否稳定失败。
- 三审门禁是否绑定 artifact hash 与审批签名。
- 13 项伪成功扫描是否在代码路径上真跑。
