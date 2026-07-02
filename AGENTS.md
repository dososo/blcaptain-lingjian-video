# 灵剪项目协作规则

- 所有说明、文档和交付记录使用中文。
- 修改代码前先核对 `02_PRD_GOAL_REFINEMENTS.md`、base GOAL 与 base PRD。
- mock provider 不得用于正式 release。
- 审批门禁不得添加绕过入口。
- SQLite 只作为派生索引,文件 artifact 才是真值。
- 真实 provider 缺失时标记 `BLOCKED_ENV`,不得谎报通过。
- 不批量删除文件或目录;生成物在打包时排除。
