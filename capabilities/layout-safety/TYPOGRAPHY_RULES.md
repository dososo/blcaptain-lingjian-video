# 灵剪 · 版式安全规则（Typography Safety Rules）

> 灵剪固化的版式硬规则，防止用户生成视频时出现文字重叠 / 越界等版式事故。
> **HyperFrames inspect 查不出的字形级问题，由本规则 + 灵剪版式校验兜底。**

## R1 · 粗黑大字—标签垂直间距（07-11，用户实测反馈）

**问题**：GlowSans ExtraBold 等**粗黑 CJK 大字**，实际字形下沿超出其 CSS `line-height` box 约 **8–12%**（竖钩、走之、宝盖等笔画下延）。当其下方紧邻小标签 / 文字时，大字底部会**压住下方文字**——即使两者的 CSS 盒子并不重叠。

**实例**：`scene5-gates` 的 GATE 大字「脚本 / 配音 / 画面」（GlowSans ExtraBold 104px）压住下方 latin 标签 `SCRIPT / VOICE / VISUAL`。修复：大字缩到 92px + 标签下沉，净间距拉到 ≥18px。

**规则**：
- 粗黑大字与紧邻下方文字之间，**净间距 ≥ 18px**（或 ≥ 大字号的 15%，取大者）。
- 大字 `line-height ≥ 1.0`，不可压缩到 <1。
- 空间紧张时，**优先缩小大字号**（如 104→92）而非压间距。

**为什么 HyperFrames inspect 查不出**：inspect 的 `text_occluded` 只检测「文字被**不透明元素**遮挡」（跨层 z-index）；而这是「**同层字形溢出 line-box**」——完全不同的机制。所以这条必须靠本规则 + 下面的版式校验兜底。

**校验思路（可集成进灵剪 validate，伪代码）**：
```js
// 关键：用字形【实际下沿】actualBoundingBoxDescent，而非 CSS 盒子底(offsetHeight)
for (const E of bigBoldTexts) {              // font-weight≥700 且 font-size≥48px
  const glyphBottom = measureGlyphBottom(E); // canvas measureText 的 actualBoundingBoxDescent，或 Range 精确 bbox
  for (const F of textsBelowOverlapping(E)) { // 垂直投影与 E 重叠、位于其下方的文字元素
    const gap = F.top - glyphBottom;
    const need = Math.max(18, E.fontSize * 0.15);
    if (gap < need) report('typography_overlap', { E, F, gap, need });
  }
}
```
> `offsetHeight` / `getBoundingClientRect` 返回的是 CSS 盒子，**抓不到字形溢出**；必须用 `CanvasRenderingContext2D.measureText(...).actualBoundingBoxDescent` 或对文本节点建 `Range` 取精确 bbox。

**状态**：规则已入 SSOT（`MASTER_BLUEPRINT.md` §15）。校验器为 `spec`（伪代码已定，待实现为灵剪 validate 扩展 / HyperFrames 自定义 lint）。

---

## 规则扩展位（后续补）

- **R2 · 安全区**：竖屏 EBU 5% / 避顶 14% / 避底 20–35% / 侧 6%（见设计系统 §2）。
- **R3 · 行长 / 字阶 / 避头尾**：CJK 避头尾、字阶 ≤3 级、单一强调（见 `MASTER_BLUEPRINT.md` §15）。
- **R4 · 字幕遮挡**：带压字幕半透底 / 描边 ≥4px（matte occlusion，见设计系统 §2）。

> 新版式事故 → 补一条 R，并尽量给出「实际渲染」层面的校验思路（多数版式 bug 藏在 CSS 盒子与实际渲染的差异里）。
