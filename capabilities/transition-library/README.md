# 转场动效库（Transition Library）· 灵剪能力模块

> **转场是灵剪固化能力，不是临时挑的花活。** 分镜关按用户内容从本库匹配 → 在分帧动效导演板明示 → 用户逐镜确认。这是「按内容匹配对应效果」的落点。

## 文件

| 文件 | 作用 |
|---|---|
| `transitions.json` | 机读库：**42 个**转场 × 全字段（v1.1；象限/能量/feel/motivated/HF-GSAP 实现/ffmpeg-gl 映射/廉价陷阱/本片用处/状态）。导演板 `transitionIn/Out.ref` 指向这里的 `id`。 |
| `_expansion_draft.md` | 扩充来源存档：ffmpeg xfade 58 项全名单 + gl-transitions 125 shader 来源 + 24 新增项（已合并进 transitions.json）。 |
| `TRANSITION_LIBRARY.md` | 人读谱系：四象限 + 每转场卡 + 内容匹配规则 + 反廉价护栏。团队/用户读。 |
| `match.js` | **内容匹配器**：按能量差 + 语义关系 + 母题 + 风格荐转场，并强制强转场稀缺配额。产出直接喂导演板。 |
| `test/match.test.js` | 回归测试：喂本片能量+语义 → 重现导演板 6 编排。`node test/match.test.js`。 |

## 用法

```js
const lib = require('./transitions.json');
const { planTransitions, matchTransition } = require('./match.js');

// 整片规划（推荐）：逐对匹配 + 强转场稀缺守卫
const plan = planTransitions(shots, {
  library: lib,
  relations: ['转折', undefined, '递进', undefined, undefined, '收束'], // 上游语义标注（可选）
  motifLinks: [false, true, false, false, false, false],              // 母题承接（可选）
  style: '编辑风',
  maxStrong: 3            // 全片强转场配额
});
// plan[i] = { fromN, toN, ref, name, why, energy, downgraded }

// 单对：matchTransition(shotA, shotB, { library, relation, motifLink, style })
```

`shots` 至少含 `{ n, energy }`；可选 `{ relationToNext, motifToNext }`。语义关系词：`转折 / 递进 / 并列 / 对比 / 收束 / 呼应`（缺省时按能量差自动推断，但语义标注更准）。

## 与导演板的接口

匹配器产出的 `ref` 写进 board data 的 `transitionIn/Out.ref`（见 `../director-board/board.schema.json`）。导演板据此渲染转场 chip；用户在关卡可改，改动回写 board data。**一条数据链：内容 → 匹配器 → board.json → 导演板 → 用户确认。**

## 实现后端（须核）

主引擎 = **HyperFrames + GSAP**（`transitions.json` 的 `impl` 字段）。ffmpeg xfade / gl-transitions 映射标『待核』者，须对照官方核实后再用（多数材质/甩镜类无通用 xfade 现成项）。

## 状态（诚实）

- 匹配逻辑：**已用 node 测试验证自洽**（编排复现 + 稀缺守卫生效）。
- 42 个转场（v1.1，ffmpeg xfade / gl-transitions 官方核实）的跨镜实现：**`spec`（已规格化，跨镜成片实现随主线画面执行集成）**。默认以硬切 concat 兜底,强转场按能量差稀缺使用。
