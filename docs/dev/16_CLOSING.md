# 16 收官说明

日期:2026-07-02

## 结论

本轮按收官一键执行包完成 P0/P1/P2:

- P0:默认 PATH 已持久使用带 `drawtext/libfreetype` 的 FFmpeg;主 `verification/results.json` 可复现为 52 PASS / 0 FAIL;真实 PASS 与离线回落两份快照均已归档。
- P1:根目录 `SKILL.md` 已落盘;README 顶部已放对话式安装提示词;安装软链脚本已可运行;MCP 表述已收敛为后续里程碑,不宣称可用。
- P2:`lj run <project>` 已实现引导主线,默认三审暂停,`--yes` 仅作为显式 CI 自动审批,render 后自动 QA 再 export。

## 文件落点

- `SKILL.md`:宿主 agent 的 skill 入口,frontmatter 含灵剪、短视频、抖音、小红书、YouTube、三审、导出等触发词。
- `README.md`:顶部新增“30 秒上手:对话式安装提示词”,保留 `<REPO_URL>` 发布占位,并给出本地 `scripts/install_skill_links.sh` 路径。
- `scripts/install_skill_links.sh`:用 `ln -sfn` 把整个仓库目录软链到 `~/.codex/skills/lingjian-video` 与 `~/.claude/skills/lingjian-video`。
- `docs/skill-and-mcp.md`:明确 MCP 为后续里程碑。
- `packages/mcp_server/README.md`:继续明确 M1 不交付完整 MCP server。
- `apps/cli/lingjian_cli/main.py:52`:新增 `lj run` 审批暂停辅助与 artifact 写入辅助。
- `apps/cli/lingjian_cli/main.py:704`:新增 `lj run <project>` 命令。
- `scripts/ci/run_verification.py:231`:V-REAL-01 在真实链路前记录 ffmpeg 路径、版本、ffprobe 版本、drawtext 与 OS provenance。

## `lj run` 行为

- 默认模式:首次运行会 init / ingest / extract / script,然后停在 `status=awaiting_approval,current_step=script`,给出查看、批准、驳回命令。
- 用户批准 script 后再次运行,进入 voice 并停在 voice 审批点。
- 用户批准 voice 后再次运行,进入 visuals 并停在 visuals 审批点。
- 三审全部通过后再次运行,执行 render -> qa -> export。
- `--yes`:仅在用户显式传入时写入真实 approval 记录并完成预览链,用于 CI 或明确授权的非交互场景。
- `--release`:先跑 doctor;doctor 不 ready 时返回 `DOCTOR_NOT_READY`,不会硬闯 release。

## 证据对齐

| 文件 | 环境 | 结果 |
| --- | --- | --- |
| `verification/results.json` | 默认 PATH,`/opt/homebrew/bin/ffmpeg` 已链接到 `ffmpeg-full`;可继承 `claude_cli`;TTS 为 `macos_say` | 52 PASS / 0 FAIL |
| `verification/results.real_pass_20260702.json` | 真实 PASS 快照 | 52 PASS / 0 FAIL |
| `verification/results.offline_fallback_20260702.json` | 隐藏 `claude/codex`,清空 provider env | 51 PASS / 1 BLOCKED_ENV / 0 FAIL |

`verification/evidence/V-REAL-01.log` 已包含:

- `which ffmpeg` -> `/opt/homebrew/bin/ffmpeg`
- `ffmpeg -version` -> 配置含 `--enable-libfreetype`
- `ffprobe -version`
- `ffmpeg -hide_banner -filters | grep drawtext`
- OS 信息
- release 视频 ffprobe 输出 `h264` 视频流与 `aac` 音频流

## 新增测试

- `tests/test_cli_contract.py::test_lj_run_pauses_at_script_review_without_yes`
- `tests/test_cli_contract.py::test_lj_run_yes_completes_preview_flow_with_real_approvals`
- `tests/test_skill_packaging.py::test_skill_file_and_readme_install_prompt_are_packaged`
- `tests/test_skill_packaging.py::test_install_skill_script_and_mcp_boundary_are_honest`
- `tests/test_capability_onboarding.py::test_setup_text_names_preview_and_release_modes`
- `tests/test_run_verification.py::test_real_release_verification_runs_release_chain_when_ready` 已扩展 provenance 断言

## 已知边界

- Web 控制台仍是静态骨架,不能宣称已接 API。
- MCP 未实现,不能宣称 MCP 可用。
- skills.sh 的 `npx skills add <REPO_URL> --skill lingjian-video` 仅作为发布后路径,当前真实可用路径是 clone + `scripts/install_skill_links.sh`。
- mock 仅用于预览档;正式 release 必须 doctor ready 且真实 provider 可用。
