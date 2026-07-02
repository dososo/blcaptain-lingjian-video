# 08 · 最终实现准备度(FINAL IMPLEMENTATION READINESS)

## 能否交给 Codex/Claude Code 一次实现:**有条件**

不建议一次全量(core+CLI+API+Web+真实 provider+渲染+QA+export 超出单次可靠上限,且 provider 接口不刚性会自由发挥)。**先落 6 个 Blocker 硬约束,再按 3 个真实增量批次实现。** 每批都交付真东西、不是 demo,且不取消 M1 主干,不把门禁/release 判定/ffmpeg_card/canonical export 推迟。

## 先修什么(进 Batch 1 前)
1. 审批 artifact hash 绑定 + `APPROVAL_STALE` 回退(A01)。
2. 移除 `--force`,预览走 `lj preview`(A02)。
3. `export --release` mock 硬失败码(A03)。
4. 文件=真值、SQLite=派生索引 + `lj reindex`(A04)。
5. CI import guard(禁引擎 SDK 进 core)+ 渲染路径断言(A07)。
6. `ffmpeg_card` SCOPE FREEZE(A11)。
(这 6 条是设计/约束,不产功能面,应在 Batch 1 一并落地。)

---

## 推荐实现批次

### Batch 1 — 核心状态机 + schemas + CLI + provider mock/doctor + approvals + artifact hash
真实交付物:
- `packages/schemas`(Pydantic 权威 + JSON Schema 导出,含 `Approval`)。
- `packages/core`:状态机 `apply_event`、artifact 读写、**三审门禁 + hash 绑定**、文件=真值/SQLite=派生索引 + `reindex`。
- `apps/cli`:全命令骨架(非交互 + `--json` + 稳定错误码),含 `approve script|voice|visuals`;`preview`(草稿)。
- `providers/*`:ABC 生命周期 + **mock 实现**(LLM/TTS/OCR/web_extract)+ `doctor`;`is_mock=True`。
- `apps/api`:薄封装(与 CLI 同 core)。
- doctor:FFmpeg/字体/Playwright/provider/**Remotion 提示**/trafilatura 版本+license 检测。
- CI:离线;import guard;schema round-trip;CLI `--json` golden;provider 契约测试。

真实价值:**Agent 可驱动全链路并被强制停审;项目状态可信、可复跑;门禁不可绕。**

验收命令:
```bash
uv sync && uv run pytest && uv run ruff check .
uv run lj doctor --json
rm -rf ./projects/b1
uv run lj init ./projects/b1 --name "批次1" --json
uv run lj ingest text ./projects/b1 --file examples/product_intro_zh.txt --json
uv run lj extract ./projects/b1 --provider mock --json
uv run lj script ./projects/b1 --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj render ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --json   # 必失败 APPROVAL_REQUIRED
uv run lj approve script ./projects/b1 --approved-by tester --json
# 改脚本后审批应失效:
uv run lj script ./projects/b1 --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj render ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --json   # 必失败 APPROVAL_STALE
uv run lj reindex ./projects/b1 --json && uv run lj status ./projects/b1 --json          # DB 可从文件重建、状态一致
```

### Batch 2 — 真实 LLM/TTS + ffmpeg_card + QA + export(含 release/mock 判定)
真实交付物:
- `providers/llm`:`openai_compatible`(自定义 base_url)+ `anthropic`(JSON mode + Pydantic 校验 + 重试 + 回退骨架)。
- `providers/tts`:`edge`(在线,标注)+ 一个 `openai_compatible` 云 TTS(**同步**);`synthesize` 返回 ffprobe 实测逐段时长。
- `providers/ocr`:`rapidocr`(**可选 extras**);`providers/web_extract`:`trafilatura(>=1.8)` + `playwright`(opt-in 截图,默认不下载视频)。
- `engines/ffmpeg_card`:静态帧(Pillow/HTML)+ **帧内字幕** + concat + FFmpeg finalizer(响度/尺寸/封面/metadata);SCOPE FREEZE。
- 五平台 preset(纯配置);9:16/16:9 手调 + 3:4/4:3 盒模型;zh/en;bilingual(双包/双字幕)。
- QA(分级 hard/warn/info,含音画字 ffprobe 复核、source_map、敏感信息、平台风险、mock/release 检查)。
- export:canonical 结构 + `provider_manifest`/`license_manifest`;**release 禁 mock**。

真实价值:**能产出可播放、结构合规、可发布的多平台 MP4 发布包(真实 provider 路径)。**

验收命令(mock 结构路径 + 真实 provider 路径见 §13):
```bash
# 三审后渲染出片(mock provider,验证结构/门禁/渲染,不做 release)
uv run lj voice ./projects/b1 --provider mock --voice test-voice --json
uv run lj approve voice ./projects/b1 --approved-by tester --json
uv run lj visuals ./projects/b1 --engine ffmpeg_card --template product --json
uv run lj approve visuals ./projects/b1 --approved-by tester --json
uv run lj render ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --json
uv run lj qa ./projects/b1 --json                                   # 音画字一致、分级结果
uv run lj export ./projects/b1 --platform douyin --language zh-CN --ratio 9:16 --release --json  # 必失败 MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE
```

### Batch 3 — Next.js Web 控制台(5 页)+ provider 配置页 + 跨平台 polish + docs
真实交付物:
- `apps/web`(Next.js+TS+Tailwind+shadcn/ui)5 页:①新建向导 ②提取+文案审 ③语音审 ④画面审 ⑤渲染+发布(doctor/provider 设置抽屉);3 主按钮(批准/重新生成/手动编辑);右侧低清预览;`awaiting_review` 驱动。
- provider 配置页(API key 状态/base_url/模型/测试连通)。
- 跨平台 polish:Windows/中文路径 e2e;字体下载;`docker-compose`。
- docs:README/installation/providers/render-engines/platform-presets/skill-and-mcp(占位)/license-notes/troubleshooting + AGENTS.md/CLAUDE.md/DISCLAIMER.md。
- Web Playwright smoke(对 mock 后端跑通主路径)。

真实价值:**非开发者可在 Web 完成同一主干:输入→审文案/语音/画面→渲染→下载发布包。**

验收命令:
```bash
cd apps/web && pnpm install && pnpm lint && pnpm build
# e2e smoke(对 mock 后端):新建→提取→审文案→审语音→审画面→渲染→发布包页可下载
uv run pytest -m web_smoke
```

---

## 不允许出现的伪成功(任一出现即判不通过)
1. `render` 在三审未齐/审批失效时"成功"出片。
2. 存在任何 `--force`/环境变量绕过门禁。
3. `export --release` 用 mock provider 却成功产包。
4. `uv sync` 核心拉入 onnxruntime/torch/playwright(应在 extras)。
5. Python `core`/`providers` 直接 import remotion/hyperframes/playwright SDK。
6. `ffmpeg_card` 出现 zoompan/逐帧动画/转场(超 SCOPE FREEZE)。
7. 字幕/画面与配音不同步(ffprobe 复核未通过)却判 QA pass。
8. 中文帧内文字为空/方块(字体缺失未 fail)。
9. CI 依赖网络/GPU/真实 key。
10. 渲染/导出代码出现 `if platform == '...'` 平台特化分支。
11. 用"自然/高质量/智能"等不可测词作为自动验收判据。
12. SQLite 与文件 artifact 状态不一致且无法 `reindex` 修复。

---

## 最终 M1 验收命令全集

### 13.1 基础质量
```bash
uv sync
uv run pytest
uv run ruff check .
uv run pyright || true        # M1 建议 pyright 只在 packages/core+schemas 严格(basic 全仓、strict 核心),第三方 stub 缺失不 block
uv run lj doctor --json

cd apps/web
pnpm install
pnpm lint
pnpm build
```

### 13.2 审批门禁
```bash
rm -rf ./projects/m1_gate_test
uv run lj init ./projects/m1_gate_test --name "门禁测试" --json
uv run lj ingest text ./projects/m1_gate_test --file examples/product_intro_zh.txt --json
uv run lj extract ./projects/m1_gate_test --provider mock --json
uv run lj script ./projects/m1_gate_test --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj render ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --json
# ↑ 必失败,返回 {"error_code":"APPROVAL_REQUIRED"}

uv run lj approve script ./projects/m1_gate_test --approved-by tester --json
uv run lj voice ./projects/m1_gate_test --provider mock --voice test-voice --json
uv run lj approve voice ./projects/m1_gate_test --approved-by tester --json
uv run lj visuals ./projects/m1_gate_test --engine ffmpeg_card --template product --json
uv run lj approve visuals ./projects/m1_gate_test --approved-by tester --json
uv run lj render ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --json   # 此时成功
uv run lj qa ./projects/m1_gate_test --json
# 附加:改脚本后审批失效
uv run lj script ./projects/m1_gate_test --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj render ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --json   # 必失败 APPROVAL_STALE
```

### 13.3 mock 不能 release
```bash
uv run lj export ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --release --json
# ↑ 必失败,返回 {"error_code":"MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE"}
```

### 13.4 canonical export 结构(非 release 结构校验)
```bash
uv run lj export ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --json   # 非 release,允许 mock,provider_manifest 标 mock=true
test -d "exports/m1_gate_test/douyin/zh-CN/9x16"
# 必存在:video.mp4 + metadata(publish.md) + captions(subtitles.srt/.vtt/.ass) + source_map.json + qa_report.md + provider_manifest.json + license_manifest.md + cover.png
# YouTube 版另验:thumbnail.png + description.md + chapters.md
```

### 13.5 真实 provider 路径(配置后,产 release 包)
```bash
export LINGJIAN_LLM_PROVIDER=openai_compatible
export OPENAI_BASE_URL=...        # 可指向 DeepSeek/Qwen/Moonshot/Ollama/vLLM
export OPENAI_API_KEY=...
export OPENAI_MODEL=...
export LINGJIAN_TTS_PROVIDER=edge_tts   # 或 openai_compatible 云 TTS(生产推荐)

rm -rf ./projects/m1_real_test
uv run lj init ./projects/m1_real_test --name "真实链路测试" --json
uv run lj ingest text ./projects/m1_real_test --file examples/product_intro_zh.txt --json
uv run lj extract ./projects/m1_real_test --provider local --json
uv run lj script ./projects/m1_real_test --provider openai_compatible --platform douyin --language zh-CN --ratio 9:16 --duration 45 --json
uv run lj approve script ./projects/m1_real_test --approved-by human --json
uv run lj voice ./projects/m1_real_test --provider edge_tts --voice zh-CN-XiaoxiaoNeural --json
uv run lj approve voice ./projects/m1_real_test --approved-by human --json
uv run lj visuals ./projects/m1_real_test --engine ffmpeg_card --template product --json
uv run lj approve visuals ./projects/m1_real_test --approved-by human --json
uv run lj render ./projects/m1_real_test --platform douyin --language zh-CN --ratio 9:16 --json
uv run lj qa ./projects/m1_real_test --json
uv run lj export ./projects/m1_real_test --platform douyin --language zh-CN --ratio 9:16 --release --json   # 必成功,产 release 包
# 多平台/多语言抽验:
uv run lj export ./projects/m1_real_test --platform youtube --language en-US --ratio 16:9 --release --json
```

真实可用判据(全过才算 M1 达标):门禁失败/失效正确触发 → 三审后出**可播 MP4(中文不乱码、音画字对齐、有封面)** → mock 无法 release、真实 provider 可 release → canonical 结构 + provider/license manifest 完整 → 五平台×zh/en 可导 → CLI 全 `--json` 可被 Agent 编排 → CI 离线全绿。

### EdgeTTS 稳定性/条款替代
EdgeTTS 为非官方逆向微软在线服务(ToS 灰区 + 可能变动)。生产替代:**OpenAI-compatible 云 TTS(默认生产)**、国内云 TTS(火山/阿里/腾讯/Minimax,作可配置 provider)、本地 CosyVoice/IndexTTS(M3,外部服务)。doctor 须将 EdgeTTS 标注为"体验用、在线、非官方"。

### pyright/lint 配置说明
建议 `pyright` 对 `packages/core` + `packages/schemas` 用 strict(业务真值区要强类型),全仓用 basic;第三方无 stub 的子进程 adapter 允许 `# type: ignore` 且不阻塞。`ruff` 全仓开 E/F/I;`ruff format` 统一风格。前端 `pnpm lint`(eslint)+ `tsc --noEmit` 类型检查。
