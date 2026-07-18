const stages = [
  "created",
  "input_ready",
  "script_review",
  "voice_review",
  "visuals_review",
  "rendered",
  "exported",
];

const panels = [
  {
    title: "新建向导",
    status: "degraded",
    body: "粘贴文本、URL 或截图开始。doctor 会先检查 FFmpeg、字体、CLI provider 与 key 状态。",
  },
  {
    title: "提取 + 文案审核",
    status: "awaiting_review",
    body: "展示提取正文、source_map、分镜脚本和平台发布文案。",
  },
  {
    title: "语音审核",
    status: "empty",
    body: "生成后展示 provider、voice、逐段实测时长和试听入口。",
  },
  {
    title: "画面审核",
    status: "empty",
    body: "展示 visual_plan、比例安全区、CJK 字体状态和低清草稿。",
  },
  {
    title: "渲染 + 发布包",
    status: "blocked",
    body: "三审缺失、QA hard fail 或 mock provider 都会阻止 release。",
  },
];

const approvals = [
  { label: "文案", state: "待审核", hash: "script.json" },
  { label: "语音", state: "未生成", hash: "voice_plan.json" },
  { label: "画面", state: "未生成", hash: "visual_plan.json" },
];

export default function HomePage() {
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="mark">灵</span>
          <div>
            <strong>灵剪</strong>
            <small>Video Studio M1</small>
          </div>
        </div>
        <button className="primary">新建项目</button>
        <nav>
          <a className="active" href="/script-review">
            批次1 · 门禁测试
          </a>
          <a href="/new">产品介绍模板</a>
          <a href="/export">教程演示模板</a>
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>批次1 · 门禁测试</h1>
            <p>Agent 生成即停,等待人工审批后再继续。</p>
          </div>
          <button className="primary">批准当前步骤</button>
        </header>

        <ol className="pipeline" aria-label="项目管线">
          {stages.map((stage, index) => (
            <li key={stage} className={index < 3 ? "done" : index === 3 ? "current" : ""}>
              {stage}
            </li>
          ))}
        </ol>

        <div className="content-grid">
          <section className="stage-panel">
            <div className="panel-heading">
              <span>当前步骤</span>
              <strong>提取 + 文案审核</strong>
            </div>
            <div className="script">
              <h2>灵剪把一段中文产品文案变成可审核视频包</h2>
              <p>
                source_map 已记录输入来源。脚本修改会让语音与画面审批失效,render
                前会返回 APPROVAL_STALE。
              </p>
            </div>
            <div className="actions">
              <button className="primary">批准</button>
              <button>重新生成</button>
              <button>手动编辑</button>
            </div>
          </section>

          <aside className="preview">
            <span>草稿预览</span>
            <div className="phone-frame">
              <div className="caption">中文帧内字幕不乱码</div>
            </div>
          </aside>
        </div>

        <section className="review-grid">
          {panels.map((panel) => (
            <article key={panel.title}>
              <span className={`status ${panel.status}`}>{panel.status}</span>
              <h3>{panel.title}</h3>
              <p>{panel.body}</p>
            </article>
          ))}
        </section>
      </section>

      <aside className="inspector">
        <h2>Doctor</h2>
        <p className="blocked">缺 FFmpeg / ffprobe / 真实 LLM / 真实 TTS</p>
        <p>可优先配置 CLI provider；必须使用 key 时只做脱敏检测,不写入日志或发布包。</p>

        <h2>审批</h2>
        <ul>
          {approvals.map((approval) => (
            <li key={approval.label}>
              <span>{approval.label}</span>
              <strong>{approval.state}</strong>
              <small>{approval.hash}</small>
            </li>
          ))}
        </ul>
      </aside>
    </main>
  );
}
