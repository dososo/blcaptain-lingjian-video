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
    prompt = _compact(str(payload.get("visual_prompt") or payload.get("narration_text") or "灵剪"))
    main_motion = ""
    motion = payload.get("motion_spec") if isinstance(payload.get("motion_spec"), dict) else {}
    if isinstance(motion, dict):
        main_motion = str(motion.get("main") or "")
    title = html.escape(prompt[:28] or "灵剪短视频")
    subtitle = html.escape(main_motion or "零 key 动态画面")
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
      .bg {{
        position: absolute; inset: -160px;
        background:
          radial-gradient(circle at 24% 22%, rgba(255, 214, 102, .96), transparent 23%),
          radial-gradient(circle at 78% 28%, rgba(72, 187, 255, .92), transparent 24%),
          radial-gradient(circle at 52% 82%, rgba(34, 197, 94, .8), transparent 28%),
          linear-gradient(145deg, #07111f 0%, #0f766e 48%, #ef4444 100%);
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
        position: absolute; left: 74px; right: 74px; top: 350px;
        padding: 58px 62px; border-radius: 36px;
        background: rgba(255,255,255,.9); color: #0f172a;
        box-shadow: 0 34px 90px rgba(0,0,0,.3);
        animation: panelIn .9s ease-out both, float {max(duration - 1, 0.5):.2f}s ease-in-out .9s both;
      }}
      .eyebrow {{ font-size: 32px; color: #0f766e; font-weight: 800; margin-bottom: 28px; }}
      .title {{ font-size: 72px; line-height: 1.12; font-weight: 900; letter-spacing: 0; }}
      .sub {{ margin-top: 32px; font-size: 38px; line-height: 1.35; color: #334155; font-weight: 650; }}
      .bars {{ position: absolute; left: 86px; right: 86px; bottom: 340px; display: grid; gap: 22px; }}
      .bar {{ height: 42px; border-radius: 999px; background: rgba(255,255,255,.82); transform-origin: left; animation: grow 1.2s ease-out both; }}
      .bar:nth-child(2) {{ width: 78%; animation-delay: .2s; }}
      .bar:nth-child(3) {{ width: 58%; animation-delay: .4s; }}
      .tag {{ position: absolute; right: 84px; top: 118px; color: white; font-size: 30px; font-weight: 800; opacity: .88; }}
      @keyframes drift {{ from {{ transform: scale(1) rotate(0deg); }} to {{ transform: scale(1.08) rotate(2deg); }} }}
      @keyframes mesh {{ from {{ transform: translate(0,0); }} to {{ transform: translate(-78px,-78px); }} }}
      @keyframes panelIn {{ from {{ opacity: 0; transform: translateY(86px) scale(.96); }} to {{ opacity: 1; transform: translateY(0) scale(1); }} }}
      @keyframes float {{ from {{ transform: translateY(0); }} to {{ transform: translateY(-28px); }} }}
      @keyframes grow {{ from {{ transform: scaleX(.08); opacity: .35; }} to {{ transform: scaleX(1); opacity: .9; }} }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="{scene_id}" data-start="0" data-duration="{safe_duration}" data-width="1080" data-height="1920">
      <div class="bg" data-start="0" data-duration="{safe_duration}"></div>
      <div class="mesh" data-start="0" data-duration="{safe_duration}"></div>
      <div class="tag" data-start="0" data-duration="{safe_duration}">LingJian × HyperFrames</div>
      <section class="panel" data-start="0" data-duration="{safe_duration}">
        <div class="eyebrow">发布级动态镜头</div>
        <div class="title">{title}</div>
        <div class="sub">{subtitle}</div>
      </section>
      <div class="bars" data-start=".8" data-duration="{max(duration - .8, .5):.2f}">
        <div class="bar"></div><div class="bar"></div><div class="bar"></div>
      </div>
    </div>
  </body>
</html>
"""


def _compact(text: str) -> str:
    return " ".join(text.split()).strip()


def _stderr_tail(stderr: str) -> str:
    lines = [line for line in (stderr or "").splitlines() if line.strip()]
    return "\n".join(lines[-8:]) or "HyperFrames 渲染失败。"


if __name__ == "__main__":
    raise SystemExit(main())
