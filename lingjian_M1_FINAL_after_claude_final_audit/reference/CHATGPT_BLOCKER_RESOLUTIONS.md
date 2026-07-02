# Blocker Resolutions · 6 个阻断问题机制落定

## B-A01 审批绑定 artifact hash

### 机制

```python
class Approval(BaseModel):
    target: Literal["script", "voice", "visuals"]
    artifact_path: str
    artifact_sha256: str
    approved_by: str
    approved_at: datetime
    comment: str | None = None
```

hash 规则：

```text
artifact_sha256 = sha256(canonical_json(target_artifact))
```

canonical JSON：UTF-8、key 排序、去除 `generated_at` / 绝对路径 / 临时缓存 / 日志等非内容字段。voice 审批必须覆盖 `voice_plan.json` 与音频文件清单 `{path, sha256, duration_sec}`。

`render` 前：

```text
缺 script / voice / visuals 任一审批 → APPROVAL_REQUIRED
存在审批但 hash 不符 → APPROVAL_STALE，并将对应 target 回退到 *_review
```

### 验证

```bash
uv run lj approve script ./projects/m1_gate_test --approved-by tester --json
uv run lj script ./projects/m1_gate_test --type product --platform douyin --language zh-CN --ratio 9:16 --duration 45 --provider mock --json
uv run lj render ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --json
# 必须失败 APPROVAL_STALE
```

---

## B-A02 删除 `--force`，未审草稿走 preview

### 机制

- `lj render` 无 `--force` 参数。
- `lj export` 无 `--force` 参数。
- 不允许任何 `LINGJIAN_SKIP_APPROVAL` / `BYPASS_APPROVAL` 环境变量。
- 未审内容只能 `lj preview`，输出 `preview_only=true`，不能进入 release 包。

### 验证

```bash
uv run lj render --help | grep -i force && exit 1 || true
rg "force|SKIP_APPROVAL|BYPASS_APPROVAL" apps packages providers engines tests
```

扫描结果不得出现可用绕过路径。

---

## B-A03 release 禁 mock

### 机制

provider 必须有：

```python
is_mock: bool
```

`provider_manifest.json` 记录所有生成链路使用的 provider。`export --release` 前扫描：

```python
if release and any(p.is_mock for p in provider_manifest.providers):
    fail("MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE")
```

### 验证

```bash
uv run lj export ./projects/m1_gate_test --platform douyin --language zh-CN --ratio 9:16 --release --json
# 必须失败 MOCK_PROVIDER_NOT_ALLOWED_FOR_RELEASE
```

---

## B-A04 文件为真值，SQLite 为派生索引

### 机制

- 项目文件 artifact 是唯一事实源。
- SQLite 只存项目列表、搜索索引、最近状态缓存。
- 所有写操作先写 artifact，再更新 SQLite。
- SQLite 可删除，可由 `lj reindex` 从文件重建。

### 验证

```bash
rm -f ./projects/m1_gate_test/.lingjian/index.sqlite
uv run lj reindex ./projects/m1_gate_test --json
uv run lj status ./projects/m1_gate_test --json
```

`status` 必须与 `project.yaml / manifest.json / artifacts/*` 一致。

---

## B-A07 CI import guard

### 机制

CI 静态扫描：

- `packages/core/**` 禁止 import `remotion` / `hyperframes` / `playwright`。
- `providers/**` 禁止 import `remotion` / `hyperframes` / `playwright` SDK。M1 Playwright 通过 subprocess 调用 CLI。
- `engines/ffmpeg_card` 不 import HyperFrames / Remotion。
- M1 render path 只允许 `engines.ffmpeg_card`。

### 验证

```bash
python scripts/ci/check_forbidden_imports.py
python scripts/ci/check_render_engine_m1.py
```

必须通过。

---

## B-A11 `ffmpeg_card` SCOPE FREEZE

### 机制

M1 只实现：

```text
静态 PNG 卡片
帧内字幕
图片/截图摆放
scene 硬切
concat
FFmpeg finalizer
```

禁止：

```text
zoompan
Ken Burns
keyframe animation
shader
transition library
per-element timeline animation
```

### 验证

```bash
python scripts/ci/check_ffmpeg_card_scope.py
rg "zoompan|Ken Burns|keyframe|shader|transition" engines/ffmpeg_card tests
```

不得出现实际功能实现；文档中的禁止词可以白名单排除。
