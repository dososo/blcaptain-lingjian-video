# 伪成功扫描报告

日期: 2026-07-02

命令:

```bash
uv run python scripts/ci/check_false_success.py
uv run python scripts/ci/check_no_force.py
uv run python scripts/ci/check_forbidden_imports.py
uv run python scripts/ci/check_render_engine_m1.py
uv run python scripts/ci/check_ffmpeg_card_scope.py
```

证据:

- `verification/false_success_scan.json`
- `verification/evidence/V-FORBID-01.log`
- `verification/evidence/V-FORBID-02.log`
- `verification/evidence/V-FORBID-03.log`
- `verification/evidence/V-FORBID-04.log`
- `verification/evidence/V-FORBID-05.log`

## 13 项结果

| ID | 扫描项 | 结果 |
| --- | --- | --- |
| FS-01 | 无强制跳过入口 | 未发现 |
| FS-02 | release 遇 mock 有稳定错误码 | 未发现 |
| FS-03 | preview 产物不能被 release 引用 | 未发现 |
| FS-04 | core/provider 无禁用引擎 SDK import | 未发现 |
| FS-05 | M1 渲染引擎范围冻结 | 未发现 |
| FS-06 | ffmpeg_card 无越界动效能力 | 未发现 |
| FS-07 | render/export 无平台名控制流;静态 dict 为受控例外 | 未发现 |
| FS-08 | 离线测试不依赖网络或真实 key | 未发现 |
| FS-09 | SQLite 为派生索引且可重建 | 未发现 |
| FS-10 | 审批 stale 与 reindex 有测试覆盖 | 未发现 |
| FS-11 | 未引入高风险第三方项目代码名 | 未发现 |
| FS-12 | 默认路径未引入视频下载器 | 未发现 |
| FS-13 | doctor 区分真实发布 provider | 未发现 |

说明: `packages/core/exporting.py` 的 `PLATFORM_EXTRA_FILES` 是静态字符串 dict,作为数据驱动受控例外;扫描会校验它不含动态调用或逻辑分支。

iter_8 复核: 新增 skill 打包、`lj run` 引导主线与 V-REAL-01 provenance 后,5 个扫描器仍全部 exit=0;未引入 yt-dlp、youtube-dl、Remotion、HyperFrames、Playwright 到 core/provider/engine 主路径,未增加 release 绕过入口。

结论: 13 项均在代码路径上真跑,当前无发现项。
