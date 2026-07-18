# 分帧动效导演板（Director Board）· 灵剪本地关卡控制台

> **灵剪的独家差异化能力。** 在每个关卡节点，把 AI 排好的分镜 / 动效 / 转场逐镜「明示」给用户，并让用户逐镜「点头确认」——不点头，不进渲染。市面 AI 视频工具「一句话出片」是黑箱；灵剪把黑箱打开成**可读、可审、可交互的本地导演板**，这是脱颖而出的关键。
>
> **本地服务红线：导演板只在本机 `localhost` / 本地静态服务打开，绝不使用任何远程或云端地址。**

## 它解决什么

AI 逐镜独立生成 = 各自为政、凌乱、无整片律动（这是「AI 做视频做大」的通病）。导演板用两层对治：

1. **整片能量曲线**（顶部）：一条线看全片起伏（hook→turn→…→cta 的能量峰谷 + 镜间转场），把「只可意会」的律动画成「可看」的谱。
2. **逐镜卡片**：每镜摆出脚本台词、能量档、分帧 beat 时序、signature 动效、进/出转场，一个「确认」按钮。用户是关主。

## 在工作流里的位置

- 它是**画面关「导演分镜确认单」的可视化实现**。
- 设计为**横切每个关卡的交互确认台**：同一渲染器，换 `meta` 文案与卡片字段，即可用于风格关 / 脚本关 / 配音关 / 画面关的逐项确认。
- 每一关：AI 产出候选 → 导演板本地展示 → 用户逐项确认 → 全部齐绿才放行下一关。确认状态通过 `onConfirmChange` 钩子暴露；把它接进 `lj` 工作流状态机是集成目标（见 SKILL.md / Roadmap），当前尚未接线。

## 文件

| 文件 | 作用 |
|---|---|
| `render.js` | 数据驱动渲染器（单一真相）。自包含：首次调用自动注入样式。暴露全局 `renderDirectorBoard`。 |
| `board.schema.json` | 分镜数据契约（JSON Schema draft-07）。上游产出须符合它。 |
| `examples/lingjian-intro.board.json` | 7 镜数据（契约实例、source of truth）。 |
| `standalone.html` | 可跑入口：读示例数据渲染，供预览 / 演示。 |

## 用法

### 本地打开（关卡控制台）

```bash
cd director-board
python3 -m http.server 8080
# 浏览器打开 http://localhost:8080/standalone.html
```

（`standalone.html` 用 `fetch` 读 JSON，故需本地静态服务，不能直接双击 `file://` 打开。这也保证了控制台只在本机地址运行。）

### 产品集成

```html
<div id="app"></div>
<script src="render.js"></script>
<script>
  const handle = renderDirectorBoard(document.getElementById('app'), boardData, {
    onConfirmChange: (s) => {
      // s = { shot, confirmed, total, count }
      // 例：全部确认后才启用「进入渲染」
      renderBtn.disabled = !(s.count === s.total);
    }
  });
  // handle.allConfirmed() → boolean；handle.confirmedCount → number
</script>
```

`boardData` 必须符合 `board.schema.json`。台词与标题里的 `**双星**` 片段渲染为朱砂强调。

## 数据从哪来（内容 → 导演板）

上游链路产出 `board.json`：**脚本**（台词 + signature）→ **分镜**（每镜 beats，元素依次入场，≥3 拍）→ **转场匹配**（相邻镜的能量差 + 语义关系 → 选转场，填 `transitionIn/Out`）。

## 设计原则

- **确定性**：不使用 `Date.now` / `Math.random`，渲染可复现。
- **自包含 / 无依赖**：纯原生 JS + SVG，无第三方库、无网络请求（数据除外），无 emoji 当图标。
- **双主题**：`prefers-color-scheme` + `:root[data-theme]` 双向覆盖，明暗都经校验。
- **无障碍**：按钮 `:focus-visible` 可见焦点；`prefers-reduced-motion` 降级。
- **本地优先**：只连本机地址，不发外部请求，不嵌远程资源。
