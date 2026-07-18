/*
 * 灵剪 · 分帧动效导演板（Director Board）· 数据驱动渲染器
 * ---------------------------------------------------------------
 * 灵剪的独家差异化能力：在每个关卡节点，把 AI 排好的分镜/动效/转场
 * 逐镜「明示」给用户，并让用户逐镜「点头确认」——不点头，不进渲染。
 *
 * 用法（产品运行时 / 预览均可）：
 *   renderDirectorBoard(document.getElementById('app'), BOARD_DATA);
 * 数据契约见 board.schema.json；示例见 examples/lingjian-intro.board.json。
 *
 * 自包含：首次调用自动注入样式，产品侧只需引本文件 + 传数据。
 * 确定性：不使用 Date.now / Math.random（渲染可复现）。
 */
(function (global) {
  'use strict';

  var BOARD_CSS = [
    ':root{',
    '--paper:#F0ECE5;--card:#F7F4EE;--ink:#1A1A18;--ink-soft:#6b665c;--ink-faint:#9a948a;',
    '--fire:#E85D26;--fire-deep:#C0361F;--muted:#D9D3C7;--line:#e2ddd2;',
    '--e1:#cfc8bb;--e2:#e6a07a;--e3:#ea7d4a;--e4:#e85d26;--e5:#c0361f;',
    "--f-disp:-apple-system,'SF Pro Display','Segoe UI',system-ui,sans-serif;",
    "--f-body:-apple-system,'SF Pro Text','Segoe UI',system-ui,sans-serif;",
    "--f-mono:'JetBrains Mono','SF Mono',ui-monospace,Menlo,monospace;",
    '--shadow:0 1px 2px rgba(26,26,24,.05),0 8px 24px rgba(26,26,24,.06);}',
    '@media (prefers-color-scheme:dark){:root{--paper:#171613;--card:#201e1a;--ink:#F0ECE5;--ink-soft:#a29b8d;--ink-faint:#6f685c;--muted:#2c2a24;--line:#2f2c26;--shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.35);}}',
    ':root[data-theme="dark"]{--paper:#171613;--card:#201e1a;--ink:#F0ECE5;--ink-soft:#a29b8d;--ink-faint:#6f685c;--muted:#2c2a24;--line:#2f2c26;--shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.35);}',
    ':root[data-theme="light"]{--paper:#F0ECE5;--card:#F7F4EE;--ink:#1A1A18;--ink-soft:#6b665c;--ink-faint:#9a948a;--muted:#D9D3C7;--line:#e2ddd2;--shadow:0 1px 2px rgba(26,26,24,.05),0 8px 24px rgba(26,26,24,.06);}',
    '.ljdb{background:var(--paper);color:var(--ink);font-family:var(--f-body);line-height:1.5;padding:40px clamp(16px,4vw,56px) 80px;min-height:100%;display:flex;flex-direction:column;align-items:center;background-image:radial-gradient(rgba(26,26,24,.05) 1px,transparent 1.4px);background-size:9px 9px;}',
    '.ljdb *{margin:0;box-sizing:border-box}',
    '.ljdb .hd,.ljdb .curvewrap,.ljdb .grid,.ljdb .footer{width:100%;max-width:1160px}',
    '.ljdb .hd{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;flex-wrap:wrap;border-bottom:2px solid var(--ink);padding-bottom:20px;margin-bottom:8px;}',
    '.ljdb .hd .bar{width:44px;height:6px;background:var(--fire);margin-bottom:14px}',
    '.ljdb .kick{font-family:var(--f-mono);font-size:13px;letter-spacing:.18em;text-transform:uppercase;color:var(--fire-deep);font-weight:600}',
    '.ljdb .h1{font-family:var(--f-disp);font-weight:800;font-size:clamp(30px,4.2vw,46px);letter-spacing:-.02em;line-height:1.02;margin-top:6px}',
    '.ljdb .h1 b{color:var(--fire)}',
    '.ljdb .sub{color:var(--ink-soft);font-size:15px;max-width:52ch;margin-top:10px}',
    '.ljdb .gate-legend{font-family:var(--f-mono);font-size:12px;color:var(--ink-soft);text-align:right;line-height:1.7}',
    '.ljdb .gate-legend b{color:var(--fire-deep)}',
    '.ljdb .curvewrap{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:22px 26px 14px;margin:26px 0 34px;overflow-x:auto}',
    '.ljdb .curvewrap h2{font-family:var(--f-mono);font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-soft);font-weight:600;margin-bottom:6px}',
    '.ljdb .curve{width:100%;min-width:720px;height:auto;display:block}',
    '.ljdb .curve .lbl{font-family:var(--f-mono);font-size:11px;fill:var(--ink-soft)}',
    '.ljdb .curve .cjk{font-family:var(--f-disp);font-weight:700;font-size:15px;fill:var(--ink)}',
    '.ljdb .curve .tname{font-family:var(--f-mono);font-size:10.5px;fill:var(--fire-deep);font-weight:600}',
    '.ljdb .grid{display:grid;gap:18px}',
    '.ljdb .shot{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);display:grid;grid-template-columns:132px 1fr 232px;overflow:hidden}',
    '@media(max-width:820px){.ljdb .shot{grid-template-columns:1fr}}',
    '.ljdb .col{padding:20px 22px}',
    '.ljdb .cL{background:linear-gradient(180deg,rgba(232,93,38,.05),transparent);border-right:1px solid var(--line)}',
    '.ljdb .cR{border-left:1px solid var(--line);background:rgba(26,26,24,.015)}',
    '@media(max-width:820px){.ljdb .cL,.ljdb .cR{border:none;border-top:1px solid var(--line)}}',
    '.ljdb .snum{font-family:var(--f-mono);font-size:12px;letter-spacing:.12em;color:var(--ink-soft);font-weight:600}',
    '.ljdb .sname{font-family:var(--f-disp);font-weight:800;font-size:30px;letter-spacing:-.01em;margin-top:4px;line-height:1}',
    '.ljdb .ebadge{margin-top:14px;font-family:var(--f-mono);font-size:11px;letter-spacing:.1em;color:var(--ink-soft)}',
    '.ljdb .ebar{height:8px;border-radius:5px;background:var(--muted);margin-top:6px;overflow:hidden}',
    '.ljdb .ebar i{display:block;height:100%;border-radius:5px}',
    '.ljdb .estar{font-size:13px;letter-spacing:2px;margin-top:6px;color:var(--fire)}',
    '.ljdb .role{font-family:var(--f-mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-faint);font-weight:600}',
    '.ljdb .script{font-size:17px;line-height:1.5;margin-top:6px;color:var(--ink)}',
    '.ljdb .script b{color:var(--fire-deep)}',
    '.ljdb .sig{margin-top:16px}',
    '.ljdb .sig .v{font-family:var(--f-disp);font-weight:700;font-size:16px;margin-top:5px}',
    '.ljdb .beats{margin-top:16px}',
    '.ljdb .beatline{display:flex;gap:0;margin-top:10px;align-items:stretch;flex-wrap:wrap}',
    '.ljdb .beat{flex:1 1 0;min-width:96px;position:relative;padding:0 4px}',
    '.ljdb .beat .dot{width:11px;height:11px;border-radius:50%;background:var(--fire);position:relative;z-index:2}',
    '.ljdb .beat .rail{position:absolute;top:5px;left:0;right:0;height:2px;background:var(--muted)}',
    '.ljdb .beat.first .rail{left:50%}',
    '.ljdb .beat.last .rail{right:50%}',
    '.ljdb .beat .bt{font-family:var(--f-mono);font-size:10.5px;color:var(--ink-faint);margin-top:8px}',
    '.ljdb .beat .bx{font-size:13px;line-height:1.35;margin-top:2px;color:var(--ink)}',
    '.ljdb .tchip{display:flex;align-items:center;gap:10px;padding:11px 13px;border-radius:10px;border:1px solid var(--line);background:var(--paper);margin-top:8px}',
    '.ljdb .tchip .ar{font-family:var(--f-mono);font-size:11px;color:var(--ink-faint);font-weight:600;flex:none;width:30px}',
    '.ljdb .tchip .tn{font-weight:700;font-size:14.5px;font-family:var(--f-disp)}',
    '.ljdb .tchip .tf{font-size:11.5px;color:var(--ink-soft);margin-top:1px}',
    '.ljdb .tchip .edot{width:9px;height:9px;border-radius:50%;flex:none;margin-left:auto}',
    '.ljdb .rlabel{font-family:var(--f-mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-faint);font-weight:600;margin-bottom:2px}',
    '.ljdb .status{display:flex;align-items:center;gap:10px;margin-top:16px}',
    '.ljdb .pill{font-family:var(--f-mono);font-size:11px;font-weight:600;letter-spacing:.08em;padding:5px 11px;border-radius:20px;text-transform:uppercase}',
    '.ljdb .pill.wait{background:var(--muted);color:var(--ink-soft)}',
    '.ljdb .pill.ok{background:var(--fire);color:#fff}',
    '.ljdb .btn{margin-top:12px;width:100%;font-family:var(--f-disp);font-weight:700;font-size:14px;padding:11px;border-radius:10px;border:2px solid var(--ink);background:transparent;color:var(--ink);cursor:pointer;transition:.15s}',
    '.ljdb .btn:hover{background:var(--ink);color:var(--paper)}',
    '.ljdb .btn.done{background:var(--fire);border-color:var(--fire);color:#fff}',
    '.ljdb .btn:focus-visible{outline:3px solid var(--fire);outline-offset:2px}',
    '.ljdb .footer{margin-top:34px;padding:22px 26px;background:var(--card);border:1px solid var(--line);border-radius:14px;display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap;box-shadow:var(--shadow)}',
    '.ljdb .prog{font-family:var(--f-mono);font-size:13px;color:var(--ink-soft)}',
    '.ljdb .prog b{color:var(--fire-deep);font-size:20px}',
    '.ljdb .note{font-size:13px;color:var(--ink-faint);max-width:44ch}',
    '@media(prefers-reduced-motion:reduce){.ljdb *{transition:none!important}}'
  ].join('');

  var EC = { 0: 'var(--e1)', 1: 'var(--e2)', 2: 'var(--e2)', 3: 'var(--e3)', 4: 'var(--e4)', 5: 'var(--e5)' };
  var EBAR = { 1: 'var(--e2)', 2: 'var(--e2)', 3: 'var(--e3)', 4: 'var(--e4)', 5: 'var(--e5)' };
  var ELABEL = { 1: 'calm', 2: 'calm→med', 3: 'medium', 4: 'high', 5: 'high · 顶峰' };
  var NS = 'http://www.w3.org/2000/svg';

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  // 台词/标题里的 **强调** → <b>，其余转义，防 XSS 与破版
  function emph(s) {
    var out = '', parts = String(s == null ? '' : s).split('**');
    for (var i = 0; i < parts.length; i++) out += (i % 2 ? '<b>' + esc(parts[i]) + '</b>' : esc(parts[i]));
    return out;
  }
  function stars(n, total) {
    total = total || 5; n = Math.max(0, Math.min(total, n | 0));
    var s = ''; for (var i = 0; i < total; i++) s += (i < n ? '★' : '☆'); return s;
  }
  function svgEl(t, a) { var e = document.createElementNS(NS, t); for (var k in a) e.setAttribute(k, a[k]); return e; }
  function injectStyle() {
    if (document.getElementById('ljdb-style')) return;
    var st = document.createElement('style'); st.id = 'ljdb-style'; st.textContent = BOARD_CSS;
    document.head.appendChild(st);
  }

  function buildCurve(svg, shots) {
    var pad = 54, W = 960, top = 30, bot = 150, n = shots.length;
    if (n < 1) return;
    var step = n > 1 ? (W - 2 * pad) / (n - 1) : 0;
    var xs = shots.map(function (s, i) { return pad + i * step; });
    var ys = shots.map(function (s) { return bot - (Math.max(1, Math.min(5, s.energy)) - 1) * ((bot - top) / 4); });
    var d = 'M' + xs[0] + ',' + ys[0];
    for (var i = 1; i < n; i++) { var mx = (xs[i - 1] + xs[i]) / 2; d += ' C' + mx + ',' + ys[i - 1] + ' ' + mx + ',' + ys[i] + ' ' + xs[i] + ',' + ys[i]; }
    svg.appendChild(svgEl('path', { d: d + ' L' + xs[n - 1] + ',' + bot + ' L' + xs[0] + ',' + bot + ' Z', fill: 'rgba(232,93,38,.10)' }));
    svg.appendChild(svgEl('path', { d: d, fill: 'none', stroke: 'var(--fire)', 'stroke-width': '3', 'stroke-linecap': 'round' }));
    shots.forEach(function (s, i) {
      if (i < n - 1) {
        var tx = (xs[i] + xs[i + 1]) / 2, ty = (ys[i] + ys[i + 1]) / 2;
        svg.appendChild(svgEl('circle', { cx: tx, cy: ty, r: 4, fill: 'var(--fire-deep)' }));
        var to = s.transitionOut || {};
        var tn = svgEl('text', { x: tx, y: ty - 10, 'text-anchor': 'middle', 'class': 'tname' });
        tn.textContent = String(to.name || '').split(' ')[0]; svg.appendChild(tn);
      }
      svg.appendChild(svgEl('circle', { cx: xs[i], cy: ys[i], r: 6.5, fill: 'var(--paper)', stroke: 'var(--fire)', 'stroke-width': '3' }));
      var c = svgEl('text', { x: xs[i], y: bot + 26, 'text-anchor': 'middle', 'class': 'cjk' }); c.textContent = s.name; svg.appendChild(c);
      var l = svgEl('text', { x: xs[i], y: bot + 42, 'text-anchor': 'middle', 'class': 'lbl' }); l.textContent = s.id; svg.appendChild(l);
      var st = svgEl('text', { x: xs[i], y: ys[i] - 14, 'text-anchor': 'middle', 'class': 'lbl', fill: 'var(--fire-deep)' });
      st.textContent = '★'.repeat(Math.max(1, Math.min(5, s.energy))); svg.appendChild(st);
    });
    svg.setAttribute('viewBox', '0 0 960 210');
  }

  function chipHTML(t) {
    t = t || {};
    var e = t.energy == null ? 0 : t.energy;
    return '<div class="tchip"><span class="ar">' + esc(t.type || '·') + '</span><div><div class="tn">' + esc(t.name || '') +
      '</div><div class="tf">' + esc(t.why || '') + '</div></div><span class="edot" style="background:' + (EC[e] || EC[0]) + '"></span></div>';
  }

  function buildCard(shot) {
    var beats = (shot.beats || []).map(function (b, i, arr) {
      var cls = 'beat' + (i === 0 ? ' first' : '') + (i === arr.length - 1 ? ' last' : '');
      return '<div class="' + cls + '"><div class="rail"></div><div class="dot"></div><div class="bt">' + esc(b.t) + '</div><div class="bx">' + esc(b.x) + '</div></div>';
    }).join('');
    var e = Math.max(1, Math.min(5, shot.energy));
    var card = document.createElement('article'); card.className = 'shot';
    card.innerHTML =
      '<div class="col cL"><div class="snum">SHOT ' + (shot.n < 10 ? '0' : '') + shot.n + ' · ' + esc(shot.id) + '</div><div class="sname">' + esc(shot.name) + '</div>' +
        '<div class="ebadge">能量 ' + (ELABEL[e] || '') + '</div><div class="ebar"><i style="width:' + (e / 5 * 100) + '%;background:' + (EBAR[e] || EBAR[3]) + '"></i></div>' +
        '<div class="estar">' + stars(e, 5) + '</div></div>' +
      '<div class="col"><div class="role">脚本 · 旁白</div><p class="script">' + emph(shot.script) + '</p>' +
        '<div class="sig"><div class="role">Signature 动效</div><div class="v">' + esc(shot.signature) + '</div></div>' +
        '<div class="beats"><div class="role">分帧 Beat</div><div class="beatline">' + beats + '</div></div></div>' +
      '<div class="col cR"><div class="rlabel">进场转场</div>' + chipHTML(shot.transitionIn) +
        '<div class="rlabel" style="margin-top:14px">出场转场</div>' + chipHTML(shot.transitionOut) +
        '<div class="status"><span class="pill wait">待确认</span></div>' +
        '<button class="btn" type="button">点头确认这一镜</button></div>';
    return card;
  }

  function renderDirectorBoard(root, data, opts) {
    if (!root) throw new Error('renderDirectorBoard: root 元素为空');
    data = data || {}; opts = opts || {};
    var meta = data.meta || {}, shots = (data.shots || []).slice();
    injectStyle();
    root.innerHTML = '';
    root.classList.add('ljdb');

    var total = shots.length, confirmed = 0;
    var kicker = meta.kicker || '灵剪 · 分镜 / 动效关';
    var title = meta.title || '分帧动效<b>导演板</b>';
    var subtitle = meta.subtitle || (total + ' 镜逐镜拆解：脚本 · 分帧 beat · signature 动效 · 进/出转场。每镜按能量曲线从转场库选配，请你逐镜确认——不点头，不进渲染。');
    var legend = meta.legend || '能量档 <b>■</b> high 强冲击<br>■ medium 中 · ■ calm 弱<br>转场取自<b>灵剪转场库</b>';

    var head = document.createElement('header'); head.className = 'hd';
    head.innerHTML = '<div><div class="bar"></div><div class="kick">' + esc(kicker) + '</div><h1 class="h1">' + emph(title) + '</h1><p class="sub">' + esc(subtitle) + '</p></div><div class="gate-legend">' + legend + '</div>';
    root.appendChild(head);

    var cw = document.createElement('section'); cw.className = 'curvewrap';
    cw.innerHTML = '<h2>' + esc(meta.curveTitle || '整片能量曲线 · 一条线看全片律动') + '</h2>';
    var svg = svgEl('svg', { 'class': 'curve', viewBox: '0 0 960 210' });
    cw.appendChild(svg); root.appendChild(cw);
    buildCurve(svg, shots);

    var grid = document.createElement('main'); grid.className = 'grid'; root.appendChild(grid);

    var foot = document.createElement('footer'); foot.className = 'footer';
    foot.innerHTML = '<div class="prog">已确认 <b class="pc">0</b> / ' + total + ' 镜 · 全部确认后方可进入下一步</div>' +
      '<div class="note">' + esc(meta.footNote || '这是灵剪「分镜/动效关」界面：转场是固化能力（库里选），不是临时挑；你是这一关的关主。') + '</div>';
    var pcEl = foot.querySelector('.pc');

    shots.forEach(function (shot) {
      var card = buildCard(shot);
      var btn = card.querySelector('.btn'), pill = card.querySelector('.pill');
      btn.addEventListener('click', function () {
        var ok = btn.classList.toggle('done');
        if (ok) { btn.textContent = '✓ 已确认（点此撤回）'; pill.className = 'pill ok'; pill.textContent = '已确认'; confirmed++; }
        else { btn.textContent = '点头确认这一镜'; pill.className = 'pill wait'; pill.textContent = '待确认'; confirmed--; }
        pcEl.textContent = confirmed;
        if (typeof opts.onConfirmChange === 'function') opts.onConfirmChange({ shot: shot, confirmed: ok, total: total, count: confirmed });
      });
      grid.appendChild(card);
    });
    root.appendChild(foot);

    return {
      get confirmedCount() { return confirmed; },
      allConfirmed: function () { return confirmed === total && total > 0; }
    };
  }

  global.renderDirectorBoard = renderDirectorBoard;
  if (typeof module !== 'undefined' && module.exports) module.exports = { renderDirectorBoard: renderDirectorBoard };
})(typeof window !== 'undefined' ? window : this);
