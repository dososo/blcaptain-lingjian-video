"""灵剪本地导演控制台(director console)一键服务。

命根子:每一关在本机 localhost 把候选逐项摆给用户审、点头才往下走。
`lj console <项目>` 会:
  1. auto 检测当前关(voice / script / 分镜);
  2. 从流水线产物(voice_options.json / script.json / board.json)自动生成候选页;
  3. 起一个**本机 localhost** 静态服务(带 /confirm 写回,把确认落到 artifacts/console_state.json);
  4. 打印 URL,由宿主 agent 在右侧浏览器打开。

绝不云端 / 隧道 / artifact —— 永远是用户自己机器上的 localhost 页。
渲染确定性:无 Date.now / 未播种 random;纯静态 + 本地数据。
"""
# ruff: noqa: E501 — 本模块含内联 HTML/CSS/JS 模板,长行不可避免。

from __future__ import annotations

import json
import math
import shutil
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DIRECTOR_BOARD = _REPO_ROOT / "director-board"

# ── 风格锁(VOX 清爽科技默认色板;控制台外观全风格通用,换风格只换文案)──
_INK = "#1B1B19"
_PAPER = "#F7F1E4"
_PAPER2 = "#EFE7D5"
_CINNABAR = "#E0402A"

_STEPS = [
    ("00", "环境预检"),
    ("01", "内容+比例"),
    ("02", "风格"),
    ("03", "脚本"),
    ("05", "配音"),
    ("06", "画面"),
    ("08", "配乐"),
    ("10", "成片QA"),
]


def detect_gate(project: Path) -> str:
    """按已有产物自动判断当前关。voice_options → 配音关;visual_plan/board → 分镜关;否则脚本关。"""
    art = project / "artifacts"
    if (art / "voice_options.json").exists() and not _approved(project, "voice"):
        return "voice"
    if (art / "board.json").exists() or (
        (art / "visual_plan.json").exists() and not _approved(project, "visuals")
    ):
        return "board"
    return "script"


def _approved(project: Path, target: str) -> bool:
    """审批是否已存在(主线把审批存在 artifacts/approvals.json;不存在按未审批处理)。"""
    p = project / "artifacts" / "approvals.json"
    if not p.exists():
        return False
    try:
        return target in json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ────────────────────────────────────────────────────────── 能量曲线推断
def _infer_energy(i: int, n: int) -> int:
    """脚本关无 energy 时,按叙事位置推断一条 1–5 的能量曲线(钩子高→早段落→拱到中后峰→CTA 收)。
    确定性:纯位置函数,无随机。仅作脚本关预览,分镜关再由用户细化。"""
    if n <= 1:
        return 4
    p = i / (n - 1)
    e = 3 + 2 * math.sin(math.pi * p)  # 3 → 5 → 3 的拱形
    if i == 0:
        e = 4  # 钩子有劲
    elif i == n - 1:
        e = 3  # CTA 收
    elif p < 0.4:
        e = min(e, 2.6)  # 早段落低谷
    return max(1, min(5, round(e)))


def _scene_role(i: int, n: int) -> tuple[str, str]:
    """给脚本镜位一个通用 id/中文名(仅展示用)。"""
    if i == 0:
        return "HOOK", "钩子"
    if i == n - 1:
        return "CTA", "收尾"
    seq = [("TURN", "转折"), ("WHAT", "是什么"), ("PROOF", "证明"), ("BUILD", "递进")]
    return seq[(i - 1) % len(seq)]


def _script_to_board(script: dict[str, Any], project_name: str) -> dict[str, Any]:
    """script.json → board.json(render.js 可渲染)。能量/beat/转场为脚本关自动预览,标注清楚。"""
    scenes = script.get("scenes", [])
    n = len(scenes)
    style_lock = script.get("style_lock", {}) or {}
    motion = style_lock.get("motion_language") or "分帧逐层入场(不匀速推拉)"
    shots = []
    for i, sc in enumerate(scenes):
        sid, sname = _scene_role(i, n)
        energy = _infer_energy(i, n)
        text = str(sc.get("narration_text", "")).strip()
        shots.append(
            {
                "n": i + 1,
                "id": sid,
                "name": sname,
                "energy": energy,
                "script": text,
                "signature": f"按 {script.get('style', 'VOX')} 风格：{motion}",
                "beats": [
                    {"t": "0.0s", "x": "入场 · 主体/大字进"},
                    {"t": "中段", "x": "旁白展开 · 逐句揭示"},
                    {"t": "收束", "x": "落点 · 甩向下一镜"},
                ],
                "transitionOut": (
                    {"type": "■", "name": "收束", "why": "末镜收尾", "energy": 0, "ref": None}
                    if i == n - 1
                    else {"type": "→", "name": "硬切", "why": "默认隐形硬切(强转场稀缺)", "energy": 1, "ref": None}
                ),
            }
        )
    return {
        "schemaVersion": "1.0",
        "meta": {
            "gate": "脚本关 · 预览",
            "project": project_name,
            "profile": script.get("profile", ""),
            "style": script.get("style", ""),
            "ratio": script.get("ratio", ""),
            "motif": style_lock.get("label_zh") or "",
            "kicker": "灵剪 · 本机导演控制台 · localhost",
            "title": "脚本关 · **逐镜确认**",
            "subtitle": (
                f"{n} 镜 · 目标 {script.get('target_duration_sec', '?')}s。"
                "能量曲线为按叙事位置自动推断的预览，分帧 beat / 转场在分镜关再细化——逐镜点头才往下走。"
            ),
            "curveTitle": "整片能量曲线 · 一条线看全片律动",
            "legend": "能量档 <b>high</b> 强 / medium 中 / calm 弱",
            "footNote": "本页由本机静态服务打开（lj console），非云端、非 artifact。确认写回 artifacts/console_state.json。",
        },
        "shots": shots,
    }


# ────────────────────────────────────────────────────────── HTML 生成
_SHARED_CSS = f"""
  :root{{ --ink:{_INK}; --paper:{_PAPER}; --paper2:{_PAPER2}; --cinnabar:{_CINNABAR}; --mute:#8A8375 }}
  *{{ box-sizing:border-box; margin:0; padding:0 }}
  body{{ background:var(--paper); color:var(--ink); font-family:"PingFang SC","Source Han Sans SC","Hiragino Sans GB",system-ui,sans-serif; line-height:1.55; -webkit-font-smoothing:antialiased }}
  .wrap{{ max-width:960px; margin:0 auto; padding:34px 26px 64px }}
  .kicker{{ font-size:13px; letter-spacing:.2em; color:var(--cinnabar); font-weight:700 }}
  h1{{ font-size:34px; font-weight:800; margin:6px 0 4px; letter-spacing:-.01em }}
  h1 b{{ color:var(--cinnabar) }}
  .sub{{ color:var(--mute); font-size:15px; margin-bottom:4px; max-width:760px }}
  .rule{{ height:3px; width:54px; background:var(--cinnabar); margin:16px 0 22px; border-radius:2px }}
  .steps{{ display:flex; gap:6px; flex-wrap:wrap; margin:22px 0 6px }}
  .step{{ font-size:12px; padding:6px 11px; border-radius:7px; background:#EDE6D6; color:var(--mute); font-weight:600 }}
  .step.done{{ color:#2f7d4f }} .step.now{{ background:var(--ink); color:var(--paper); font-weight:800 }}
  .bar{{ position:sticky; bottom:0; background:var(--paper2); border:1px solid #E0D7C4; border-radius:12px; padding:14px 18px; margin-top:22px; display:flex; align-items:center; gap:12px; flex-wrap:wrap }}
  .bar b{{ color:var(--cinnabar) }}
  .note{{ font-size:12.5px; color:var(--mute); margin-top:16px; line-height:1.6 }}
  .btn{{ appearance:none; border:1.5px solid var(--ink); background:transparent; color:var(--ink); font-weight:800; font-size:14px; padding:9px 20px; border-radius:9px; cursor:pointer; font-family:inherit; transition:.12s }}
  .btn:hover{{ background:var(--ink); color:var(--paper) }}
  .btn.go{{ background:var(--cinnabar); border-color:var(--cinnabar); color:#fff; margin-left:auto }}
  .btn.go[disabled]{{ opacity:.4; cursor:not-allowed }}
"""

_POST_JS = """
  async function ljConfirm(payload){
    try{ await fetch('/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); }
    catch(e){ console.warn('confirm 写回失败(不影响选择)', e); }
  }
"""


def _steps_html(current: str) -> str:
    order = ["00", "01", "02", "03", "05", "06", "08", "10"]
    now_idx = {"script": 3, "voice": 4, "board": 5}.get(current, 3)
    out = []
    for k, label in _STEPS:
        idx = order.index(k)
        cls = "step done" if idx < now_idx else ("step now" if idx == now_idx else "step")
        mark = " ✓" if idx < now_idx else (" ← 你在这" if idx == now_idx else "")
        out.append(f'<span class="{cls}">{k} {label}{mark}</span>')
    return '<div class="steps">' + "".join(out) + "</div>"


def _voice_html(voice_options: dict[str, Any], project_name: str) -> str:
    options = voice_options.get("options", [])
    data = [
        {
            "i": o.get("index"),
            "name": o.get("label_zh", f"音色{o.get('index')}"),
            "vid": o.get("voice_id", ""),
            "src": Path(str(o.get("audio_path", ""))).name.replace(".wav", ".mp3"),
            "dur": round(float(o.get("duration_sec", 0)), 1),
        }
        for o in options
    ]
    data_json = json.dumps(data, ensure_ascii=False)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>灵剪 · 配音关 · 音色确认</title><style>{_SHARED_CSS}
  .card{{ background:#fff; border:1px solid #E7DFCF; border-radius:14px; padding:18px 20px; margin-bottom:14px; position:relative }}
  .card.sel{{ border-color:var(--cinnabar); box-shadow:0 0 0 2px rgba(224,64,42,.14) }}
  .row{{ display:flex; align-items:center; gap:12px; flex-wrap:wrap }}
  .name{{ font-size:19px; font-weight:800 }}
  .vid{{ margin-left:auto; font-family:ui-monospace,Menlo,monospace; font-size:12px; color:var(--mute) }}
  audio{{ width:100%; height:38px; margin:10px 0 12px }}
  .badge{{ display:none; position:absolute; top:16px; right:20px; background:var(--cinnabar); color:#fff; font-size:12px; font-weight:800; padding:4px 11px; border-radius:20px }}
  .card.sel .badge{{ display:block }} .card.sel .vid{{ margin-right:64px }}
</style></head><body><div class="wrap">
  <div class="kicker">灵剪 · 本机导演控制台 · localhost</div>
  <h1>配音关 · <b>音色确认</b></h1>
  <div class="sub">{project_name} · 同一段全文，火山豆包音色真合成试听 —— 逐个听，选你要的那一个。</div>
  <div class="rule"></div>
  <div id="list"></div>
  <div class="bar"><span>当前选择：<b id="chosen">未选</b></span>
    <button class="btn go" id="go" disabled>确认此音色 · 进配音导演确认</button></div>
  {_steps_html("voice")}
  <div class="note">命根子：每一关在<b>你自己电脑的 localhost</b> 把候选逐项摆给你审，不是把文件甩进对话。选择会写回 <code>artifacts/console_state.json</code>。</div>
</div><script>{_POST_JS}
  var VOICES={data_json}, chosen=null;
  var list=document.getElementById('list'), chosenEl=document.getElementById('chosen'), go=document.getElementById('go');
  function choose(i){{
    chosen=i;
    document.querySelectorAll('.card').forEach(function(c){{ c.classList.toggle('sel', +c.dataset.i===i); }});
    var v=VOICES.find(function(x){{return x.i===i;}});
    chosenEl.textContent=i+' 号 · '+v.name; go.disabled=false;
    ljConfirm({{gate:'voice', selected_index:i, voice_id:v.vid, name:v.name}});
  }}
  VOICES.forEach(function(v){{
    var el=document.createElement('div'); el.className='card'; el.dataset.i=v.i;
    el.innerHTML='<div class="badge">已选</div><div class="row"><span class="name">'+v.i+' · '+v.name+'</span>'+
      '<span class="vid">'+v.vid+'</span></div>'+
      '<audio controls preload="none" src="'+v.src+'"></audio>'+
      '<div><button class="btn">选这个</button></div>';
    el.querySelector('.btn').addEventListener('click', function(){{ choose(v.i); }});
    list.appendChild(el);
  }});
  go.addEventListener('click', function(){{
    if(chosen==null) return;
    ljConfirm({{gate:'voice', confirmed:true, selected_index:chosen}});
    go.textContent='已确认 ✓ 音色 '+chosen+' 号 —— 回对话说「配音确认单」继续';
    go.disabled=true;
  }});
</script></body></html>"""


def _board_index_html(project_name: str) -> str:
    """render.js 的装配入口(读同目录 board.json → renderDirectorBoard)。"""
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>灵剪 · 导演板 · {project_name}</title></head>
<body><div id="app"></div>
<script src="render.js"></script>
<script>{_POST_JS}
  fetch('board.json').then(function(r){{return r.json();}}).then(function(data){{
    var handle=renderDirectorBoard(document.getElementById('app'), data, {{
      onConfirmChange:function(s){{
        ljConfirm({{gate:'board', confirmed:s.count, total:s.total, all:s.count===s.total}});
      }}
    }});
    window.__ljboard=handle;
  }}).catch(function(e){{
    document.getElementById('app').innerHTML='<p style="font-family:sans-serif;padding:40px">需通过本机服务打开（lj console 已起服务）。'+e.message+'</p>';
  }});
</script></body></html>"""


# ────────────────────────────────────────────────────────── 组装 + 服务
def build_console(project: Path, gate: str) -> tuple[Path, str]:
    """生成本关控制台的可服务目录,返回 (serve_dir, 实际 gate)。"""
    project = project.resolve()
    art = project / "artifacts"
    if gate == "auto":
        gate = detect_gate(project)
    serve_dir = project / ".lj-console"
    if serve_dir.exists():
        shutil.rmtree(serve_dir)
    serve_dir.mkdir(parents=True, exist_ok=True)
    name = project.name

    if gate == "voice":
        vo = _read_json(art / "voice_options.json")
        (serve_dir / "index.html").write_text(_voice_html(vo, name), encoding="utf-8")
        # 拷贝试听音频(优先 mp3,回落 wav)到服务目录
        vdir = art / "voice_options"
        if vdir.exists():
            for f in list(vdir.glob("*.mp3")) or list(vdir.glob("*.wav")):
                shutil.copy2(f, serve_dir / f.name)
        return serve_dir, gate

    # board / script:render.js + board.json
    if (art / "board.json").exists():
        board = _read_json(art / "board.json")
    else:
        board = _script_to_board(_read_json(art / "script.json"), name)
    render_js = _DIRECTOR_BOARD / "render.js"
    if render_js.exists():
        shutil.copy2(render_js, serve_dir / "render.js")
    (serve_dir / "board.json").write_text(
        json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (serve_dir / "index.html").write_text(_board_index_html(name), encoding="utf-8")
    return serve_dir, gate


class _ConsoleHandler(SimpleHTTPRequestHandler):
    project_path: Path = Path(".")

    def log_message(self, *args: Any) -> None:  # 静音访问日志
        return

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/confirm":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = {"raw": raw.decode("utf-8", "replace")}
        state_path = self.project_path / "artifacts" / "console_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')


def make_server(serve_dir: Path, project: Path, port: int) -> ThreadingHTTPServer:
    """在 127.0.0.1 起服务(只绑本机,永不对外)。port=0 由系统分配空闲端口。"""

    def _factory(*args: Any, **kwargs: Any) -> _ConsoleHandler:
        return _ConsoleHandler(*args, directory=str(serve_dir), **kwargs)

    _ConsoleHandler.project_path = project.resolve()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _factory)
    return httpd
