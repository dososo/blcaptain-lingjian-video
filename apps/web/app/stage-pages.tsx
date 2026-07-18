const stageCopy = {
  new: {
    title: "新建向导",
    status: "degraded",
    body: "粘贴文本、URL 或截图前先运行 doctor,确认 FFmpeg、字体、CLI provider 与 key 状态。",
    action: "创建项目",
  },
  "script-review": {
    title: "提取 + 文案审核",
    status: "awaiting_review",
    body: "核对 source_map、脚本、平台发布文案和稀薄输入提示。改稿后下游审批会变为 stale。",
    action: "批准文案",
  },
  "voice-review": {
    title: "语音审核",
    status: "empty",
    body: "生成语音后核对 provider、voice、逐段音频路径和实测时长。mock 语音不能 release。",
    action: "批准语音",
  },
  "visuals-review": {
    title: "画面审核",
    status: "empty",
    body: "核对 visual_plan、比例安全区、CJK 断行和低清 preview。M1 仅允许 ffmpeg_card。",
    action: "批准画面",
  },
  export: {
    title: "渲染 + 发布包",
    status: "blocked",
    body: "三审通过后生成 preview。正式 release 必须使用真实 provider 和 release render。",
    action: "导出发布包",
  },
};

type StageKey = keyof typeof stageCopy;

export function StageWorkflowPage({ stage }: { stage: StageKey }) {
  const item = stageCopy[stage];

  return (
    <main className="route-shell">
      <nav className="route-nav" aria-label="主流程">
        <a href="/">总览</a>
        <a href="/new">新建</a>
        <a href="/script-review">文案</a>
        <a href="/voice-review">语音</a>
        <a href="/visuals-review">画面</a>
        <a href="/export">导出</a>
      </nav>
      <section className="route-main">
        <span className={`status ${item.status}`}>{item.status}</span>
        <h1>{item.title}</h1>
        <p>{item.body}</p>
        <div className="actions">
          <button className="primary">{item.action}</button>
          <button>重新生成</button>
          <button>手动编辑</button>
        </div>
      </section>
      <aside className="route-preview">
        <span>低清预览</span>
        <div className="phone-frame">
          <div className="caption">审批状态清晰可见</div>
        </div>
      </aside>
    </main>
  );
}
