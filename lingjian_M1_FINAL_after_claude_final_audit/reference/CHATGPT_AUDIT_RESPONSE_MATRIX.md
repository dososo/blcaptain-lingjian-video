# Audit Response Matrix · Claude 对抗审计逐条响应

> 范围：回应 `04_ADVERSARIAL_AUDIT.md` 的 A01–A34，以及 06/07 patch。  
> 运行时状态：本轮为文档优化；代码级验证待 Codex / Claude Code 执行，标记 `PENDING_AGENT`。  
> 文档层结论：6 个 Blocker 与 12 个 High 均已在最终 PRD / GOAL 落实。

## 1. A01–A34 响应矩阵

| ID | 级别 | 是否落实 | 落实位置 | 落实方式 | 证据/验证 |
|---|---|---|---|---|---|
| A01 | Blocker | 已落实 | PRD §12.7；GOAL §1、§9、§19.2 | 定义 `Approval`、canonical hash、`APPROVAL_STALE`；render 前重算比对。 | 审批后改脚本 → render 必须 `APPROVAL_STALE`；PENDING_AGENT。 |
| A02 | Blocker | 已落实 | PRD §7、§26；GOAL §7、§18 | 删除 `--force`；未审草稿走 `lj preview`。 | 静态扫描无门禁绕过；PENDING_AGENT。 |
| A03 | Blocker | 已落实 | PRD §12.8、§20；GOAL §1、§5、§19.3 | provider `is_mock`；`export --release` 遇 mock 硬失败。 | mock release 必须 `MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE`；PENDING_AGENT。 |
| A04 | Blocker | 已落实 | PRD §11；GOAL §1、§4、§19.2 | 文件 artifact 是唯一事实源；SQLite 派生；`lj reindex`。 | 删 SQLite 后 reindex/status 一致；PENDING_AGENT。 |
| A05 | High | 已落实 | PRD §5.2、§7、§24；GOAL §2、§4、§13 | CLI/API/Web 共用 `packages/core.apply_event`。 | CLI/API 契约测试；PENDING_AGENT。 |
| A06 | Pass/补强 | 已落实 | PRD §15；GOAL §10、§19.8 | M1 render 只走 `ffmpeg_card`，并加 import/render path guard。 | 静态扫描；PENDING_AGENT。 |
| A07 | Blocker | 已落实 | PRD §1.1、§10、§24；GOAL §1、§4、§19.8 | 禁 core/provider import remotion/hyperframes/playwright；Playwright 更严格走 subprocess。 | CI import guard；PENDING_AGENT。 |
| A08 | High | 已落实 | PRD §14；GOAL §4 | Provider ABC 与契约测试。 | `test_provider_contract`；PENDING_AGENT。 |
| A09 | Medium | 已落实 | PRD §8；GOAL §14 | M1 MCP 只占位，M2 实现 22 工具。 | 占位返回 `not_implemented`；PENDING_AGENT。 |
| A10 | High | 已落实 | PRD §6；GOAL §6、§13 | Web 从 8 页收敛为 5 页，不删三审。 | Web smoke；PENDING_AGENT。 |
| A11 | Blocker | 已落实 | PRD §15.2；GOAL §10、§19.8 | `ffmpeg_card` SCOPE FREEZE，禁 zoompan/动画/shader/转场。 | 静态扫描；PENDING_AGENT。 |
| A12 | High | 已落实 | PRD §14.3；GOAL §5 | 云 TTS 仅同步阻塞；无后台队列；超时明确错误码。 | TTS timeout 测试；PENDING_AGENT。 |
| A13 | Medium | 已落实 | PRD §14.3、§16、§28；GOAL §5、§15 | EdgeTTS 标体验用；并列生产云 TTS。 | doctor 文案检查；PENDING_AGENT。 |
| A14 | High | 已落实 | PRD §14.4、§22；GOAL §5、§6 | OCR 降为 extras，仅截图输入；核心不装 onnxruntime。 | `uv sync` 依赖检查；PENDING_AGENT。 |
| A15 | Medium | 已落实 | PRD §17；GOAL §11、§19.8 | preset 纯 YAML；渲染/导出无平台名 if。 | 静态扫描；PENDING_AGENT。 |
| A16 | Medium | 已落实 | PRD §19；GOAL §5 | 四盒 layout compiler；3:4/4:3 线性适配。 | layout 单测；PENDING_AGENT。 |
| A17 | High | 已落实 | PRD §14.5、§16；GOAL §5、§15 | trafilatura `>=1.8` + license 检测；GPL 阻断。 | doctor 返回 `TRAFILATURA_LICENSE_BLOCKED`；PENDING_AGENT。 |
| A18 | Medium | 已落实 | PRD §16.1、§29；GOAL §15 | doctor 固定 Remotion M3 opt-in license 提示。 | doctor JSON/text 检查；PENDING_AGENT。 |
| A19 | Medium | 已落实 | PRD §16、§22、§29；GOAL §15、§17 | Noto Sans SC 下载到缓存，不入仓，license manifest 记录。 | 字体检测测试；PENDING_AGENT。 |
| A20 | High | 已落实 | PRD §12.5、§14.3、§15.3、§21；GOAL §5、§12 | TTS 合成后 ffprobe 实测逐段时长，QA 复核音画字。 | ffprobe 时长一致测试；PENDING_AGENT。 |
| A21 | High | 已落实 | PRD §20；GOAL §11、§19.4 | canonical export `exports/<project>/<platform>/<language>/<ratio>/`；文件由 preset 声明。 | 结构校验命令；PENDING_AGENT。 |
| A22 | Medium | 已落实 | PRD §21；GOAL §12 | QA 分 hard/warn/info。 | QA 分级单测；PENDING_AGENT。 |
| A23 | Medium | 已落实 | PRD §21、§24、§30；GOAL §2、§19、§20 | 自动验收只用可测断言，主观质量交人审。 | 验收命令均可执行；PENDING_AGENT。 |
| A24 | High | 已落实 | PRD §30；GOAL §19 | 验收含门禁失败、mock release 失败、真实 provider release。 | V-GATE/V-REL/V-REAL；PENDING_AGENT。 |
| A25 | High | 已落实 | PRD §25、§29；GOAL §17、§18 | `hyperframes-motion-director` 只研究，不复制 AGPL 内容。 | license-notes 检查；PENDING_AGENT。 |
| A26 | Medium | 已落实 | PRD §22、§23；GOAL §16、§19.7 | pathlib、UTF-8、中文路径 e2e、Playwright 安装命令。 | 中文路径命令；PENDING_AGENT。 |
| A27 | Medium | 已落实 | PRD §22；GOAL §3 | Python/Node/pnpm/uv 版本固定，提交 lockfiles。 | 文件存在检查；PENDING_AGENT。 |
| A28 | High | 已落实 | PRD §23；GOAL §16 | prompt injection、路径穿越、命令注入、API key 脱敏。 | 安全单测；PENDING_AGENT。 |
| A29 | Pass | 已落实 | PRD §7；GOAL §7 | CLI 含 `lj approve script|voice|visuals`。 | CLI help 检查；PENDING_AGENT。 |
| A30 | Pass | 已落实 | PRD §17.1、§19 | 4:3 定义为教程/演示通用比例，不绑定平台原生规格。 | preset 文档检查；PENDING_AGENT。 |
| A31 | Pass | 已落实 | PRD §16.3、§22；GOAL §5、§19.6 | Playwright 安装命令使用 `pip install playwright && playwright install`。 | doctor/troubleshooting 检查；PENDING_AGENT。 |
| A32 | Pass | 已落实 | PRD §18；GOAL §19.5 | bilingual 定义为双独立语言包和/或双行字幕。 | bilingual export 测试；PENDING_AGENT。 |
| A33 | High | 已落实 | PRD §3.3、§26、§27；GOAL §18 | ASR、富 motion、本地克隆、Remotion、桌面等全部移出 M1。 | 文档/范围扫描；PENDING_AGENT。 |
| A34 | Pass/Low | 已落实 | PRD §8；GOAL §14 | MCP 22 工具统一，M1 占位不冲突。 | MCP 清单检查；PENDING_AGENT。 |

## 2. Blocker 与 High 达成统计

| 类别 | 总数 | 文档层已落实 | 运行时待验证 |
|---|---:|---:|---:|
| Blocker | 6 | 6 | 6 |
| High | 12 | 12 | 12 |
| Medium | 10 | 10 | 10 |
| Pass/Low | 6 | 6 | 6 |

## 3. 仍需 Codex / Claude Code 执行的验证

文档层已完成优化，但以下必须在代码实现后运行：

- 审批 hash 绑定与 stale。
- 无 `--force` / 无隐藏绕过。
- `export --release` mock 硬失败。
- SQLite 删除后 `reindex`。
- import guard。
- `ffmpeg_card` scope freeze。
- Web smoke。
- 真实 provider release 包。
