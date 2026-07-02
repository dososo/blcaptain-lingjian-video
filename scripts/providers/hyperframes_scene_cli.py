# ruff: noqa: E501

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

RENDER_TIMEOUT_SEC = 120
LAYOUTS = ("hook", "pain", "solution", "proof", "cta")
LAYOUT_LABELS = {
    "hook": "开场钩子",
    "pain": "痛点放大",
    "solution": "方案拆解",
    "proof": "证据聚焦",
    "cta": "行动收口",
}
ACCENT_LABELS = {
    "hook": "注意力拉满",
    "pain": "流程卡点",
    "solution": "一条主线",
    "proof": "可复核",
    "cta": "马上试用",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="LingJian HyperFrames scene adapter")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.probe:
        return 0 if _hyperframes_available() else 1
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        expected = _render_scene(payload)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"asset_path": str(expected)}, ensure_ascii=False))
    return 0


def _hyperframes_available() -> bool:
    try:
        completed = subprocess.run(
            ["npx", "hyperframes", "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _render_scene(payload: dict[str, Any]) -> Path:
    expected = Path(str(payload.get("expected_asset_path") or "")).expanduser()
    if not expected.is_absolute():
        raise RuntimeError("expected_asset_path 必须是绝对路径。")
    expected.parent.mkdir(parents=True, exist_ok=True)
    duration = max(float(payload.get("duration_sec") or 1.0), 0.5)
    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        _write_project(project, payload, duration)
        completed = subprocess.run(
            [
                "npx",
                "hyperframes",
                "render",
                "--output",
                str(expected),
                "--quality",
                "draft",
            ],
            cwd=project,
            text=True,
            capture_output=True,
            check=False,
            timeout=RENDER_TIMEOUT_SEC,
        )
        if completed.returncode != 0:
            raise RuntimeError(_stderr_tail(completed.stderr))
    if not expected.exists() or expected.stat().st_size == 0:
        raise RuntimeError("HyperFrames 未写出预期 mp4。")
    return expected


def _write_project(project: Path, payload: dict[str, Any], duration: float) -> None:
    project.joinpath("package.json").write_text(
        json.dumps(
            {
                "name": "lingjian-hyperframes-scene",
                "private": True,
                "type": "module",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    project.joinpath("hyperframes.json").write_text(
        json.dumps(
            {
                "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
                "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    project.joinpath("index.html").write_text(_html(payload, duration), encoding="utf-8")


def _html(payload: dict[str, Any], duration: float) -> str:
    scene_id = html.escape(str(payload.get("scene_id") or "scene"))
    layout = _layout_for(payload)
    keyword = html.escape(_visual_keyword(payload))
    accent = html.escape(_accent_word(payload, layout))
    label = html.escape(LAYOUT_LABELS[layout])
    scene_no = html.escape(_scene_number(payload))
    motion_name = html.escape(f"layout-{layout}")
    safe_duration = f"{duration:.2f}"
    return f"""<!doctype html>
<html lang="zh-CN" data-resolution="portrait">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <style>
      * {{ box-sizing: border-box; }}
      html, body {{ margin: 0; width: 1080px; height: 1920px; overflow: hidden; background: #07111f; }}
      body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Noto Sans CJK SC", sans-serif; }}
      #root {{ position: relative; width: 1080px; height: 1920px; overflow: hidden; }}
      .scene {{ position: relative; width: 1080px; height: 1920px; color: white; overflow: hidden; }}
      .bg {{
        position: absolute; inset: -160px;
        background:
          radial-gradient(circle at 18% 20%, rgba(20, 184, 166, .92), transparent 22%),
          radial-gradient(circle at 82% 28%, rgba(251, 191, 36, .88), transparent 24%),
          radial-gradient(circle at 50% 88%, rgba(244, 63, 94, .82), transparent 27%),
          linear-gradient(145deg, #07111f 0%, #155e75 46%, #7c2d12 100%);
        animation: drift {safe_duration}s linear both;
      }}
      .mesh {{
        position: absolute; inset: 0; opacity: .24;
        background-image:
          linear-gradient(rgba(255,255,255,.16) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255,255,255,.16) 1px, transparent 1px);
        background-size: 78px 78px;
        animation: mesh {safe_duration}s linear both;
      }}
      .panel {{
        position: absolute;
        padding: 58px 62px; border-radius: 36px;
        background: rgba(255,255,255,.9); color: #0f172a;
        box-shadow: 0 34px 90px rgba(0,0,0,.3);
        animation: panelIn .9s ease-out both, float {max(duration - 1, 0.5):.2f}s ease-in-out .9s both;
      }}
      .eyebrow {{ font-size: 30px; color: #0f766e; font-weight: 800; margin-bottom: 22px; }}
      .keyword {{ font-size: 104px; line-height: .98; font-weight: 950; letter-spacing: 0; }}
      .sub {{ margin-top: 28px; font-size: 34px; line-height: 1.25; color: #334155; font-weight: 650; }}
      .tag {{ position: absolute; right: 76px; top: 100px; color: white; font-size: 28px; font-weight: 800; opacity: .86; }}
      .scene-no {{ position: absolute; left: 76px; top: 100px; font-size: 28px; font-weight: 900; opacity: .74; }}
      .safe-band {{ position: absolute; left: 0; right: 0; bottom: 0; height: 310px; background: linear-gradient(transparent, rgba(0,0,0,.42)); }}
      .layout-hook .keyword {{ position: absolute; left: 72px; right: 72px; top: 500px; color: white; font-size: 142px; text-shadow: 0 22px 70px rgba(0,0,0,.35); animation: hookText .9s cubic-bezier(.2,.8,.2,1) both; }}
      .layout-hook .ring {{ position: absolute; border: 4px solid rgba(255,255,255,.35); border-radius: 999px; animation: ring {safe_duration}s ease-in-out both; }}
      .layout-hook .ring.one {{ width: 760px; height: 760px; left: 160px; top: 390px; }}
      .layout-hook .ring.two {{ width: 560px; height: 560px; left: 260px; top: 490px; animation-delay: .2s; }}
      .layout-pain .panel {{ left: 64px; top: 350px; width: 450px; min-height: 640px; }}
      .layout-pain .alert-stack {{ position: absolute; right: 68px; top: 430px; width: 416px; display: grid; gap: 30px; }}
      .layout-pain .alert {{ height: 142px; border-radius: 28px; background: rgba(15,23,42,.76); border: 1px solid rgba(255,255,255,.18); transform-origin: right; animation: slideCard .8s ease-out both; }}
      .layout-pain .alert:nth-child(2) {{ animation-delay: .18s; }}
      .layout-pain .alert:nth-child(3) {{ animation-delay: .32s; }}
      .layout-solution .panel {{ left: 90px; right: 90px; top: 280px; }}
      .layout-solution .cards {{ position: absolute; left: 90px; right: 90px; top: 820px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }}
      .layout-solution .card {{ height: 300px; border-radius: 34px; background: rgba(255,255,255,.86); box-shadow: 0 22px 60px rgba(0,0,0,.22); animation: rise .9s ease-out both; }}
      .layout-solution .card:nth-child(2) {{ animation-delay: .18s; }}
      .layout-solution .card:nth-child(3) {{ animation-delay: .34s; }}
      .layout-proof .metric {{ position: absolute; left: 86px; top: 300px; font-size: 230px; line-height: .86; font-weight: 950; color: #fef3c7; animation: metric .9s ease-out both; }}
      .layout-proof .panel {{ right: 76px; left: 420px; top: 690px; padding: 42px; }}
      .layout-proof .bars {{ position: absolute; left: 86px; right: 86px; bottom: 380px; display: grid; gap: 24px; }}
      .bar {{ height: 42px; border-radius: 999px; background: rgba(255,255,255,.82); transform-origin: left; animation: grow 1.2s ease-out both; }}
      .bar:nth-child(2) {{ width: 78%; animation-delay: .2s; }}
      .bar:nth-child(3) {{ width: 58%; animation-delay: .4s; }}
      .layout-cta .panel {{ left: 78px; right: 78px; top: 400px; text-align: center; }}
      .layout-cta .button {{ position: absolute; left: 210px; right: 210px; top: 930px; height: 120px; border-radius: 999px; background: #fef3c7; color: #0f172a; display: grid; place-items: center; font-size: 44px; font-weight: 950; animation: pulse 1.2s ease-in-out infinite alternate; }}
      .layout-cta .grid {{ position: absolute; left: 96px; right: 96px; bottom: 380px; display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px; }}
      .layout-cta .tile {{ height: 170px; border-radius: 30px; background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.22); animation: rise .8s ease-out both; }}
      @keyframes drift {{ from {{ transform: scale(1) rotate(0deg); }} to {{ transform: scale(1.08) rotate(2deg); }} }}
      @keyframes mesh {{ from {{ transform: translate(0,0); }} to {{ transform: translate(-78px,-78px); }} }}
      @keyframes panelIn {{ from {{ opacity: 0; transform: translateY(86px) scale(.96); }} to {{ opacity: 1; transform: translateY(0) scale(1); }} }}
      @keyframes float {{ from {{ transform: translateY(0); }} to {{ transform: translateY(-28px); }} }}
      @keyframes grow {{ from {{ transform: scaleX(.08); opacity: .35; }} to {{ transform: scaleX(1); opacity: .9; }} }}
      @keyframes hookText {{ from {{ opacity: 0; transform: translateY(70px) scale(.92); }} to {{ opacity: 1; transform: translateY(0) scale(1); }} }}
      @keyframes ring {{ from {{ transform: scale(.72); opacity: .1; }} to {{ transform: scale(1.1); opacity: .72; }} }}
      @keyframes slideCard {{ from {{ opacity: 0; transform: translateX(90px); }} to {{ opacity: 1; transform: translateX(0); }} }}
      @keyframes rise {{ from {{ opacity: 0; transform: translateY(70px); }} to {{ opacity: 1; transform: translateY(0); }} }}
      @keyframes metric {{ from {{ opacity: 0; transform: scale(.78); }} to {{ opacity: 1; transform: scale(1); }} }}
      @keyframes pulse {{ from {{ transform: scale(.96); }} to {{ transform: scale(1.03); }} }}
    </style>
  </head>
  <body>
    <div id="root" class="scene layout-{layout}" data-composition-id="{scene_id}" data-layout="{layout}" data-motion="{motion_name}" data-start="0" data-duration="{safe_duration}" data-width="1080" data-height="1920">
      <div class="bg" data-start="0" data-duration="{safe_duration}"></div>
      <div class="mesh" data-start="0" data-duration="{safe_duration}"></div>
      <div class="scene-no">SCENE {scene_no}</div>
      <div class="tag">LingJian × HyperFrames</div>
      {_layout_body(layout, keyword, accent, label, duration)}
      <div class="safe-band" aria-hidden="true"></div>
    </div>
  </body>
</html>
"""


def _compact(text: str) -> str:
    return " ".join(text.split()).strip()


def _layout_for(payload: dict[str, Any]) -> str:
    role = str(payload.get("role") or payload.get("roll_type") or payload.get("rollType") or "").lower()
    for keyword, layout in {
        "hook": "hook",
        "opening": "hook",
        "pain": "pain",
        "problem": "pain",
        "solution": "solution",
        "feature": "hook",
        "benefit": "hook",
        "proof": "proof",
        "data": "proof",
        "cta": "cta",
        "close": "cta",
    }.items():
        if keyword in role:
            return layout
    return LAYOUTS[(_scene_index(payload) - 1) % len(LAYOUTS)]


def _layout_body(layout: str, keyword: str, accent: str, label: str, duration: float) -> str:
    safe_tail = f"{max(duration - .8, .5):.2f}"
    if layout == "hook":
        return f"""
      <div class="ring one"></div><div class="ring two"></div>
      <div class="keyword">{keyword}</div>
"""
    if layout == "pain":
        return f"""
      <section class="panel" data-start="0" data-duration="{duration:.2f}">
        <div class="eyebrow">{label}</div>
        <div class="keyword">{keyword}</div>
        <div class="sub">{accent}</div>
      </section>
      <div class="alert-stack"><div class="alert"></div><div class="alert"></div><div class="alert"></div></div>
"""
    if layout == "solution":
        return f"""
      <section class="panel" data-start="0" data-duration="{duration:.2f}">
        <div class="eyebrow">{label}</div>
        <div class="keyword">{keyword}</div>
        <div class="sub">{accent}</div>
      </section>
      <div class="cards"><div class="card"></div><div class="card"></div><div class="card"></div></div>
"""
    if layout == "proof":
        return f"""
      <div class="metric">3×</div>
      <section class="panel" data-start="0" data-duration="{duration:.2f}">
        <div class="eyebrow">{label}</div>
        <div class="keyword">{keyword}</div>
      </section>
      <div class="bars" data-start=".8" data-duration="{safe_tail}">
        <div class="bar"></div><div class="bar"></div><div class="bar"></div>
      </div>
"""
    return f"""
      <section class="panel" data-start="0" data-duration="{duration:.2f}">
        <div class="eyebrow">{label}</div>
        <div class="keyword">{keyword}</div>
        <div class="sub">{accent}</div>
      </section>
      <div class="button">开始发布</div>
      <div class="grid"><div class="tile"></div><div class="tile"></div><div class="tile"></div><div class="tile"></div></div>
"""


def _scene_index(payload: dict[str, Any]) -> int:
    raw = str(payload.get("scene_id") or payload.get("id") or "1")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits:
        return max(int(digits), 1)
    return max(sum(ord(ch) for ch in raw), 1)


def _scene_number(payload: dict[str, Any]) -> str:
    return f"{_scene_index(payload):02d}"[-2:]


def _visual_keyword(payload: dict[str, Any]) -> str:
    on_screen_text = _compact_visual_text(str(payload.get("on_screen_text") or ""))
    if on_screen_text:
        return on_screen_text[:8]
    source = str(payload.get("visual_prompt") or payload.get("narration_text") or "灵剪")
    narration = str(payload.get("narration_text") or "")
    text = source
    if "视觉关键词:" in text:
        text = text.split("视觉关键词:", 1)[1]
        if "。" in text:
            text = text.split("。", 1)[0]
    if "旁白/画面信息:" in text:
        text = text.split("旁白/画面信息:", 1)[1]
    text = _remove_redundant_words(text)
    if narration:
        text = text.replace(narration, "")
    text = _compact_visual_text(text) or _compact_visual_text(narration)
    if not text:
        return "灵剪"
    return text[:8]


def _accent_word(payload: dict[str, Any], layout: str) -> str:
    return ACCENT_LABELS[layout]


def _remove_redundant_words(text: str) -> str:
    replacements = [
        "为竖屏短视频生成一镜画面",
        "画幅 9:16",
        "风格为干净的中文产品说明动态图形",
        "主体清晰",
        "背景简洁",
        "旁白",
        "画面信息",
        "生成一张",
        "生成",
        "一镜",
        "画面",
        "短视频",
        "动态",
        "动态图形",
    ]
    compact = text
    for item in replacements:
        compact = compact.replace(item, " ")
    return compact


def _compact_visual_text(text: str) -> str:
    keep: list[str] = []
    for char in text:
        if "\u4e00" <= char <= "\u9fff" or char.isalnum():
            keep.append(char)
        elif keep and keep[-1] != " ":
            keep.append(" ")
    words = [part for part in "".join(keep).split() if part]
    if not words:
        return ""
    joined = "".join(words)
    for prefix in ("现在", "已经", "可以", "一个", "一条", "用户", "我们", "它会"):
        if joined.startswith(prefix) and len(joined) > len(prefix) + 2:
            joined = joined[len(prefix) :]
    return joined.strip()


def _stderr_tail(stderr: str) -> str:
    lines = [line for line in (stderr or "").splitlines() if line.strip()]
    return "\n".join(lines[-8:]) or "HyperFrames 渲染失败。"


if __name__ == "__main__":
    raise SystemExit(main())
