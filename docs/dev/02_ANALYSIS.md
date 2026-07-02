# 02 分析

日期: 2026-07-01

## 架构边界

```text
apps/web ──HTTP──> apps/api ──调用──> packages/core
apps/cli ─────────────调用──> packages/core
packages/core ──通过注册表使用──> providers/*
packages/core ──通过渲染接口──> engines/ffmpeg_card
packages/schemas ──供──> CLI / API / Web / tests / MCP 占位
```

硬边界:

- `packages/core` 不 import FastAPI、Typer、Next.js、Remotion、HyperFrames、Playwright SDK。
- `providers` 不 import Remotion/HyperFrames/Playwright SDK;Playwright 只允许 subprocess/helper 路径。
- M1 只注册 `ffmpeg_card`;HyperFrames M2,Remotion M3 opt-in。
- Web 不维护第二套状态机,所有状态来自 API/core。
- 项目文件 artifact 是唯一事实源;SQLite 只是派生索引。

## 数据流

```text
init
→ project.yaml / manifest.json
→ ingest 写 assets/input_assets.json
→ extract 写 artifacts/extracted_content.json + source_map
→ script 写 artifacts/script.json + history
→ approve script 写 approvals.json(hash)
→ voice 写 voice_plan.json + voice_segments + history
→ approve voice 写 approvals.json(hash 覆盖音频清单)
→ visuals 写 visual_plan.json + history
→ approve visuals 写 approvals.json(hash)
→ render 检查三审 hash → renders/preview 或 renders/release + render_manifest.json
→ qa 写 qa_report.json/md
→ export 写 canonical package + export_manifest/provider_manifest/license_manifest
```

## 10 项精修落点

| 精修 | 落点 | Batch | 验证 |
|---|---|---:|---|
| R1 preview/release 物理隔离 | `engines/ffmpeg_card`, `packages/core/rendering.py`, `packages/core/exporting.py` | 2 | `V-REL-02` 引用 preview release 失败 |
| R2 extract 分类型路由 | `providers/web_extract`, `providers/ocr`, CLI extract 参数 | 1/2 | text 无 provider,url/ocr 分路由,OCR 缺失 warn |
| R3 artifact history | `packages/core/artifacts.py` | 1 | 覆盖前写 `history/<step>/<time>.json` |
| R4 ffmpeg_card 容差快照 | `tests/rendering`, `engines/ffmpeg_card` | 2 | 非全黑、分辨率、结构 hash/SSIM |
| R5 provider 错误分类 | `providers/errors.py`, LLM/TTS adapter | 2 | rate limit/quota/auth/invalid JSON 单测 |
| R6 exported 后可回环 | `packages/core/state_machine.py` | 1 | 导出后编辑上游进入 review 且下游 stale |
| R7 approval provenance 入发布包 | `packages/core/exporting.py` | 2 | `export_manifest.json.approvals` |
| R8 稀薄输入校验 | `packages/core/validation.py`, script/extract | 2 | `V-DEGRADE-01` warn 引导不崩 |
| R9 CJK 断行 | `engines/ffmpeg_card/text_layout.py` | 2 | 中文帧内非空且最多 2 行/安全区 |
| R10 doctor Agent 语义 | `apps/cli doctor`, `packages/core/doctor.py` | 1 | required 缺失 exit != 0,optional 缺失 exit 0 + warn |

## Provider 初始化判定

`doctor --json` 需要把 provider 能力拆成可被 Agent 使用的结构:

```json
{
  "ready": false,
  "required": [],
  "optional": [],
  "providers": {
    "llm": {
      "ready": false,
      "usable_real": false,
      "methods": [
        {"type": "cli", "configured": false, "safe_for_release": false},
        {"type": "openai_compatible", "configured": false, "safe_for_release": false},
        {"type": "codex_host", "configured": true, "safe_for_release": false}
      ]
    }
  }
}
```

规则:

- CLI provider 可用且非 mock 时,可以满足真实 provider 能力,不再强制 API key。
- API key provider 缺 key/base_url/model 时,返回 `PROVIDER_NOT_CONFIGURED` 类状态和配置引导。
- mock、模板、host-only 能力不能满足 `export --release` 的真实 provider 判定。
- 所有 key 只做存在性与脱敏校验,不写入 artifact、日志、release 包。

## 主要风险与处理

| 风险 | 等级 | 处理 |
|---|---:|---|
| 一次性全量实现导致半成品 | 高 | 严格 Batch 1→2→3,每批有可验收闭环 |
| 审批 hash 不严导致门禁失效 | 高 | canonical JSON + render 前重算 + stale 测试 |
| mock preview 混入 release | 高 | render 模式物理隔离 + export 只收 release render |
| `ffmpeg_card` 蔓延成小 Remotion | 高 | scope scan + 禁止词白名单仅文档 |
| 真实 provider 错误不可解释 | 中 | 稳定错误码、CLI/API key 分层状态与 provider_manifest 用量记录 |
| CJK 字体/断行跨平台差异 | 中 | doctor 字体缓存 + 结构断言而非逐像素 |
| Web 复制状态机 | 高 | API/core 单源,Web smoke 验证主路径 |
| license 漏洞 | 高 | license-notes + 依赖审查 + 禁入清单 |
| 默认 CI 依赖网络/key | 高 | mock provider + monkeypatch ffmpeg + integration 标记隔离 |

## 需要确认的点

- 是否允许我在当前目录直接初始化完整项目结构,把资产包留在同一仓库根目录下。
- 是否接受按 Batch 1 先交一轮可运行核心,再继续 Batch 2/3 的迭代节奏。
- 如果本机没有真实 LLM/TTS key,是否按要求将 `V-REAL-01` 置顶 `BLOCKED_ENV` 并继续离线验收其余项。
