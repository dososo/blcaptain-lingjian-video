# ruff: noqa: E501

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

RENDER_TIMEOUT_SEC = 240
LAYOUTS = ("hook", "pain", "solution", "proof", "cta")
EVIDENCE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
EVIDENCE_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
CJK_FONT_SOURCES = (
    ("SourceHanSansSC-Medium.otf", "SourceHanSansSC-Medium.otf"),
    ("GlowSansSC-Compressed-ExtraBold.otf", "GlowSansSC-ExtraBold.otf"),
)
BLUEPRINT_LAYOUTS = {
    "hook_codex_prompt": "hook",
    "hook_ticker_takeover": "hook",
    "hook_product_flash": "hook",
    "pain_overwhelm_board": "pain",
    "pain_dataviz_cost": "pain",
    "pain_spatial_stations": "pain",
    "solution_three_gate_flow": "solution",
    "solution_cursor_demo": "solution",
    "solution_asset_pipeline": "solution",
    "proof_qa_evidence_wall": "proof",
    "proof_ffprobe_dashboard": "proof",
    "proof_manifest_timeline": "proof",
    "cta_repo_star_press": "cta",
    "cta_install_flow": "cta",
    "cta_brand_lockup": "cta",
}
RECIPE_LAYOUTS = {
    "codex_operation_capture": "solution",
    "ffprobe_terminal_capture": "proof",
    "github_repo_star_capture": "cta",
    "qa_report_capture": "proof",
    "readme_install_capture": "cta",
    "render_manifest_capture": "proof",
}
LAYOUT_LABELS = {
    "hook": "开场钩子",
    "pain": "痛点放大",
    "solution": "方案拆解",
    "proof": "证据聚焦",
    "cta": "行动收口",
}
ACCENT_LABELS = {
    "hook": "Codex 里一句话启动",
    "pain": "脚本 配音 画面 来回返工",
    "solution": "三审门禁把流程收拢",
    "proof": "QA 证据可复核",
    "cta": "开源项目 点 Star",
}
RECIPE_LABELS = {
    "codex_prompt_or_reconstructed_ui": "Codex 指令入口",
    "codex_operation_capture": "Codex 操作画面",
    "ffprobe_terminal_capture": "ffprobe 终端证据",
    "github_repo_star_capture": "GitHub Star 行动",
    "lingjian_artifact_flow": "灵剪产物流",
    "qa_report_capture": "QA 报告证据",
    "readme_install_capture": "README 安装入口",
    "render_manifest_capture": "render manifest 时间线",
    "visual_asset_generation_queue": "每镜视频资产队列",
}
PALETTES = {
    "hook": ("#08111f", "#2563eb", "#22d3ee", "#f8fafc"),
    "pain": ("#130f1f", "#f97316", "#f43f5e", "#fff7ed"),
    "solution": ("#071711", "#10b981", "#84cc16", "#ecfdf5"),
    "proof": ("#0b1020", "#8b5cf6", "#38bdf8", "#eef2ff"),
    "cta": ("#120b1f", "#facc15", "#fb7185", "#fffbeb"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="LingJian HyperFrames scene adapter")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.probe:
        return 0 if _hyperframes_available() else 1
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        expected, evidence_media = _render_scene(payload)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "asset_path": str(expected),
                "host_generation_contract": _adapter_contract(payload, evidence_media),
            },
            ensure_ascii=False,
        )
    )
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


def _render_scene(payload: dict[str, Any]) -> tuple[Path, list[dict[str, str]]]:
    expected = Path(str(payload.get("expected_asset_path") or "")).expanduser()
    if not expected.is_absolute():
        raise RuntimeError("expected_asset_path 必须是绝对路径。")
    expected.parent.mkdir(parents=True, exist_ok=True)
    duration = max(float(payload.get("duration_sec") or 1.0), 0.5)
    with tempfile.TemporaryDirectory() as temp_dir:
        project = Path(temp_dir)
        evidence_media = _write_project(project, payload, duration)
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
    return expected, evidence_media


def _write_project(project: Path, payload: dict[str, Any], duration: float) -> list[dict[str, str]]:
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
    _copy_project_fonts(project)
    evidence_media = _copy_evidence_media(project, payload)
    project.joinpath("index.html").write_text(
        _html(payload, duration, evidence_media=evidence_media),
        encoding="utf-8",
    )
    return evidence_media


def _copy_project_fonts(project: Path) -> None:
    source_dir = Path.home() / ".cache" / "blcaptain-fonts"
    target_dir = project / "assets" / "fonts"
    target_dir.mkdir(parents=True, exist_ok=True)
    for source_name, target_name in CJK_FONT_SOURCES:
        source = source_dir / source_name
        if source.exists():
            shutil.copyfile(source, target_dir / target_name)


def _canvas_dimensions(payload: dict[str, Any]) -> tuple[int, int, str]:
    ratio = _payload_ratio(payload)
    if ratio == "16:9":
        return 1920, 1080, "landscape"
    return 1080, 1920, "portrait"


def _payload_ratio(payload: dict[str, Any]) -> str:
    candidates: list[Any] = [payload.get("ratio"), payload.get("aspect")]
    brief = payload.get("brief")
    if isinstance(brief, dict):
        candidates.extend([brief.get("ratio"), brief.get("aspect")])
        profile = brief.get("profile")
        if isinstance(profile, dict):
            candidates.extend([profile.get("ratio"), profile.get("aspect")])
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text in {"16:9", "9:16"}:
            return text
    prompt = str(payload.get("visual_prompt") or "")
    if "16:9" in prompt or "横屏" in prompt:
        return "16:9"
    return "9:16"


def _html(
    payload: dict[str, Any],
    duration: float,
    evidence_media: list[dict[str, str]] | None = None,
) -> str:
    scene_id = html.escape(str(payload.get("scene_id") or "scene"))
    layout = _layout_for(payload)
    keyword = html.escape(_visual_keyword(payload))
    accent = html.escape(_accent_word(payload, layout))
    label = html.escape(LAYOUT_LABELS[layout])
    scene_no = html.escape(_scene_number(payload))
    motion_name = html.escape(f"director-{layout}")
    blueprint_id = html.escape(_safe_token(payload.get("blueprint_id") or payload.get("template_id")))
    asset_recipe_id = html.escape(_safe_token(payload.get("asset_recipe_id")))
    visual_archetype = html.escape(_safe_token(payload.get("visual_archetype")))
    transition_family = html.escape(_transition_family(payload))
    motion_rules = html.escape(",".join(_motion_rules(payload)))
    evidence_count = str(len(_evidence_labels(payload)))
    media_items = evidence_media or _inline_evidence_media(payload)
    hero_media = _primary_evidence_video(media_items)
    panel_items = _panel_evidence_media(media_items, hero_media)
    evidence_media_count = str(len(media_items))
    evidence_hero_kind = html.escape(hero_media.get("kind", "") if hero_media else "")
    bg, primary, secondary, surface = _palette_for(layout)
    safe_duration = f"{duration:.2f}"
    width, height, orientation = _canvas_dimensions(payload)
    landscape_css = _landscape_css() if orientation == "landscape" else ""
    timeline_script = _timeline_script(str(payload.get("scene_id") or "scene"), duration)
    return f"""<!doctype html>
<html lang="zh-CN" data-resolution="{orientation}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={width}, height={height}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      @font-face {{ font-family:'SourceHanSansSC'; src:url('assets/fonts/SourceHanSansSC-Medium.otf') format('opentype'); font-weight:500; font-display:block; }}
      @font-face {{ font-family:'GlowSansSC'; src:url('assets/fonts/GlowSansSC-ExtraBold.otf') format('opentype'); font-weight:800; font-display:block; }}
      * {{ box-sizing: border-box; }}
      html, body {{ margin: 0; width: {width}px; height: {height}px; overflow: hidden; background: #07111f; }}
      body {{ font-family:'SourceHanSansSC', sans-serif; }}
      #root {{ position: relative; width: {width}px; height: {height}px; overflow: hidden; }}
      .scene {{ --bg:{bg}; --primary:{primary}; --secondary:{secondary}; --surface:{surface}; --font-cjk:'SourceHanSansSC'; --font-display:'GlowSansSC'; --font-mono:'SourceHanSansSC'; position: relative; width: {width}px; height: {height}px; color: white; overflow: hidden; background: var(--bg); }}
      .scene::before {{ content:""; position:absolute; inset:0; background: linear-gradient(180deg, rgba(255,255,255,.05), transparent 42%, rgba(0,0,0,.28)); pointer-events:none; }}
      .stage-grid {{ position:absolute; inset:0; opacity:.18; background-image: linear-gradient(rgba(255,255,255,.16) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.16) 1px, transparent 1px); background-size: 96px 96px; animation: gridShift {safe_duration}s linear both; }}
      .wipe {{ position:absolute; inset:0; background: var(--primary); transform-origin:left; animation: wipe .55s cubic-bezier(.2,.8,.2,1) both; z-index:20; }}
      .scene-no {{ position:absolute; left:64px; top:72px; font-size:26px; font-weight:900; letter-spacing:0; opacity:.76; }}
      .tag {{ position:absolute; right:64px; top:72px; font-size:26px; font-weight:900; opacity:.78; }}
      .contract-rail {{ position:absolute; left:64px; right:64px; bottom:350px; display:flex; gap:14px; flex-wrap:wrap; z-index:9; }}
      .contract-pill {{ border-radius:999px; padding:10px 16px; font-size:22px; font-weight:900; color:var(--surface); background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.18); }}
      .evidence-hero {{ position:absolute; left:54px; right:54px; top:210px; height:890px; z-index:6; border-radius:46px; overflow:hidden; background:#020617; border:1px solid rgba(255,255,255,.22); box-shadow:0 48px 140px rgba(0,0,0,.42); animation:repoIn .85s ease-out both; }}
      .evidence-hero video {{ width:100%; height:100%; object-fit:cover; display:block; filter:saturate(1.08) contrast(1.04); }}
      .evidence-hero::after {{ content:""; position:absolute; inset:0; background:linear-gradient(180deg, rgba(2,6,23,.08), transparent 48%, rgba(2,6,23,.72)); pointer-events:none; }}
      .evidence-hero-label {{ position:absolute; left:28px; right:28px; bottom:28px; z-index:2; display:flex; align-items:center; justify-content:space-between; gap:18px; }}
      .evidence-hero-title {{ border-radius:999px; padding:14px 20px; font-size:26px; font-weight:950; color:var(--surface); background:rgba(2,6,23,.76); border:1px solid rgba(255,255,255,.18); backdrop-filter:blur(12px); }}
      .evidence-hero-badge {{ border-radius:999px; padding:12px 18px; font-size:22px; font-weight:950; color:#0f172a; background:var(--secondary); }}
      .evidence-story {{ position:absolute; left:64px; right:64px; top:1130px; z-index:7; display:grid; gap:22px; animation:cardRise .7s ease-out both; }}
      .evidence-story-main {{ border-radius:34px; padding:34px 38px; background:rgba(15,23,42,.76); border:1px solid rgba(255,255,255,.18); box-shadow:0 30px 90px rgba(0,0,0,.32); backdrop-filter:blur(16px); }}
      .evidence-story-title {{ font-size:46px; line-height:1.08; font-weight:950; letter-spacing:0; color:var(--surface); }}
      .evidence-story-copy {{ margin-top:14px; font-size:27px; line-height:1.34; font-weight:820; color:rgba(255,255,255,.78); }}
      .evidence-story-beats {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
      .evidence-story-beat {{ min-height:96px; border-radius:26px; padding:20px 18px; background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.14); font-size:23px; line-height:1.18; font-weight:900; color:var(--surface); animation:pop .55s ease-out both; }}
      .evidence-story-beat:nth-child(2) {{ animation-delay:.18s; }}
      .evidence-story-beat:nth-child(3) {{ animation-delay:.34s; }}
      .evidence-media-panel {{ position:absolute; left:64px; right:64px; top:1180px; min-height:250px; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; z-index:7; }}
      .evidence-media-card {{ position:relative; min-height:250px; border-radius:30px; overflow:hidden; background:rgba(15,23,42,.72); border:1px solid rgba(255,255,255,.18); box-shadow:0 28px 80px rgba(0,0,0,.28); animation:cardRise .7s ease-out both; }}
      .evidence-media-card:nth-child(2) {{ animation-delay:.18s; }}
      .evidence-media-card img, .evidence-media-card video {{ width:100%; height:250px; object-fit:cover; display:block; filter:saturate(1.08) contrast(1.02); }}
      .evidence-media-label {{ position:absolute; left:18px; right:18px; bottom:16px; border-radius:999px; padding:10px 14px; font-size:20px; font-weight:900; color:var(--surface); background:rgba(2,6,23,.72); backdrop-filter:blur(10px); }}
      .safe-band {{ position:absolute; left:0; right:0; bottom:0; height:330px; background:linear-gradient(transparent, rgba(0,0,0,.58)); z-index:8; }}
      .title {{ font-family:var(--font-display); font-size:86px; line-height:1.02; font-weight:950; letter-spacing:0; }}
      .small {{ font-size:28px; line-height:1.32; font-weight:760; color:rgba(255,255,255,.78); }}
      .label {{ color:var(--surface); background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.18); border-radius:999px; padding:12px 22px; font-size:26px; font-weight:900; display:inline-flex; width:max-content; }}
      .glass {{ background:rgba(255,255,255,.11); border:1px solid rgba(255,255,255,.18); box-shadow:0 32px 90px rgba(0,0,0,.28); backdrop-filter: blur(18px); }}
      .phone {{ position:absolute; right:72px; top:250px; width:430px; height:850px; border-radius:54px; padding:28px; background:#0f172a; box-shadow:0 50px 130px rgba(0,0,0,.42); animation: phoneIn .9s ease-out both, phoneDrift {max(duration - 1, .6):.2f}s ease-in-out .9s both; }}
      .phone-screen {{ width:100%; height:100%; border-radius:38px; background:#f8fafc; color:#0f172a; padding:34px 26px; overflow:hidden; }}
      .bubble {{ border-radius:26px; padding:22px 24px; margin-bottom:22px; font-size:30px; font-weight:800; line-height:1.2; animation: bubble .65s ease-out both; }}
      .bubble.user {{ background:#dbeafe; margin-left:40px; }}
      .bubble.agent {{ background:#dcfce7; margin-right:34px; animation-delay:.5s; }}
      .repo-card {{ position:absolute; left:72px; top:360px; width:500px; border-radius:38px; padding:42px; background:var(--surface); color:#0f172a; animation: cardRise .85s ease-out .18s both; }}
      .repo-card .repo {{ font-size:36px; font-weight:950; margin-top:18px; }}
      .spark-line {{ height:8px; border-radius:999px; background:linear-gradient(90deg,var(--primary),var(--secondary)); transform-origin:left; animation: grow {max(duration - .7, .6):.2f}s ease-out .7s both; }}
      .chaos-board {{ position:absolute; left:72px; right:72px; top:250px; height:830px; border-radius:42px; padding:44px; }}
      .task-stack {{ position:absolute; left:44px; top:140px; width:420px; display:grid; gap:24px; }}
      .task {{ height:118px; border-radius:28px; background:rgba(255,255,255,.92); color:#111827; padding:24px; font-size:34px; font-weight:950; animation: shakeIn .7s ease-out both; }}
      .task:nth-child(2) {{ animation-delay:.22s; transform:rotate(-1deg); }}
      .task:nth-child(3) {{ animation-delay:.42s; transform:rotate(1deg); }}
      .warning-panel {{ position:absolute; right:48px; top:170px; width:380px; height:450px; border-radius:34px; padding:34px; background:#111827; border:1px solid rgba(255,255,255,.16); animation: slideLeft .8s ease-out .2s both; }}
      .warning-row {{ height:52px; margin:22px 0; border-radius:14px; background:linear-gradient(90deg,var(--secondary),transparent); transform-origin:left; animation: grow .8s ease-out both; }}
      .workflow {{ position:absolute; left:64px; right:64px; top:250px; display:grid; gap:24px; }}
      .step {{ position:relative; min-height:170px; border-radius:34px; padding:34px 40px 34px 120px; background:var(--surface); color:#052e16; box-shadow:0 28px 72px rgba(0,0,0,.22); animation: stepIn .75s ease-out both; }}
      .step::before {{ content:attr(data-num); position:absolute; left:32px; top:34px; width:58px; height:58px; border-radius:18px; background:var(--primary); color:white; display:grid; place-items:center; font-weight:950; }}
      .step:nth-child(2) {{ animation-delay:.22s; }}
      .step:nth-child(3) {{ animation-delay:.42s; }}
      .step:nth-child(4) {{ animation-delay:.62s; }}
      .step-title {{ font-size:42px; font-weight:950; margin-bottom:10px; }}
      .step-copy {{ font-size:28px; font-weight:760; color:#14532d; }}
      .flow-line {{ position:absolute; left:132px; top:420px; bottom:360px; width:8px; border-radius:999px; background:var(--primary); transform-origin:top; animation: growY {max(duration - 1, .6):.2f}s ease-out .8s both; }}
      .dashboard {{ position:absolute; left:62px; right:62px; top:240px; bottom:360px; border-radius:44px; overflow:hidden; background:#0b1020; border:1px solid rgba(255,255,255,.18); box-shadow:0 40px 120px rgba(0,0,0,.38); animation: cardRise .85s ease-out both; }}
      .dash-top {{ height:92px; display:flex; align-items:center; gap:18px; padding:0 34px; background:rgba(255,255,255,.08); }}
      .dot {{ width:18px; height:18px; border-radius:999px; background:var(--secondary); }}
      .terminal {{ position:absolute; left:38px; right:38px; top:128px; height:360px; border-radius:28px; padding:34px; background:#020617; color:#e2e8f0; font-family:var(--font-mono); font-size:26px; line-height:1.55; overflow:hidden; }}
      .terminal .line {{ opacity:0; animation:typeLine .5s ease-out both; }}
      .terminal .line:nth-child(2) {{ animation-delay:.45s; }}
      .terminal .line:nth-child(3) {{ animation-delay:.9s; }}
      .qa-grid {{ position:absolute; left:38px; right:38px; top:540px; display:grid; grid-template-columns:repeat(2,1fr); gap:22px; }}
      .qa-card {{ min-height:150px; border-radius:28px; padding:26px; background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.14); animation: pop .65s ease-out both; }}
      .qa-card:nth-child(2) {{ animation-delay:.2s; }}
      .qa-card:nth-child(3) {{ animation-delay:.4s; }}
      .qa-card:nth-child(4) {{ animation-delay:.6s; }}
      .github {{ position:absolute; left:74px; right:74px; top:270px; border-radius:46px; background:#f8fafc; color:#0f172a; padding:46px; box-shadow:0 42px 120px rgba(0,0,0,.38); animation: repoIn .85s ease-out both; }}
      .github-head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:46px; }}
      .repo-name {{ font-size:46px; font-weight:950; }}
      .star {{ border-radius:999px; background:#0f172a; color:white; padding:24px 34px; font-size:34px; font-weight:950; animation:pulse 1s ease-in-out infinite alternate; }}
      .file-list {{ display:grid; gap:18px; }}
      .file {{ border-radius:22px; padding:22px 26px; background:#e2e8f0; font-size:30px; font-weight:820; transform-origin:left; animation: slideLeft .65s ease-out both; }}
      .file:nth-child(2) {{ animation-delay:.18s; }}
      .file:nth-child(3) {{ animation-delay:.34s; }}
      .cta-strip {{ position:absolute; left:140px; right:140px; top:1120px; height:108px; border-radius:999px; background:var(--primary); color:#0f172a; display:grid; place-items:center; font-size:42px; font-weight:950; animation: pop .65s ease-out .8s both; }}
      .stage-grid, .wipe, .phone, .bubble, .repo-card, .spark-line, .chaos-board, .task, .warning-panel, .warning-row, .workflow, .step, .flow-line, .dashboard, .terminal .line, .qa-card, .github, .file, .star, .cta-strip, .evidence-hero, .evidence-story, .evidence-story-beat, .evidence-media-card {{ animation: none !important; }}
      @keyframes wipe {{ 0% {{ transform:scaleX(1); }} 100% {{ transform:scaleX(0); }} }}
      @keyframes gridShift {{ from {{ transform:translate(0,0); }} to {{ transform:translate(-96px,-96px); }} }}
      @keyframes phoneIn {{ from {{ opacity:0; transform:translateX(120px) rotate(5deg); }} to {{ opacity:1; transform:translateX(0) rotate(0); }} }}
      @keyframes phoneDrift {{ from {{ transform:translateY(0); }} to {{ transform:translateY(-34px); }} }}
      @keyframes bubble {{ from {{ opacity:0; transform:translateY(40px) scale(.96); }} to {{ opacity:1; transform:translateY(0) scale(1); }} }}
      @keyframes cardRise {{ from {{ opacity:0; transform:translateY(90px) scale(.96); }} to {{ opacity:1; transform:translateY(0) scale(1); }} }}
      @keyframes shakeIn {{ from {{ opacity:0; transform:translateX(-70px) rotate(-4deg); }} to {{ opacity:1; transform:translateX(0) rotate(0); }} }}
      @keyframes slideLeft {{ from {{ opacity:0; transform:translateX(90px); }} to {{ opacity:1; transform:translateX(0); }} }}
      @keyframes stepIn {{ from {{ opacity:0; transform:translateY(56px); }} to {{ opacity:1; transform:translateY(0); }} }}
      @keyframes grow {{ from {{ transform:scaleX(.04); }} to {{ transform:scaleX(1); }} }}
      @keyframes growY {{ from {{ transform:scaleY(.03); }} to {{ transform:scaleY(1); }} }}
      @keyframes typeLine {{ from {{ opacity:0; transform:translateX(-20px); }} to {{ opacity:1; transform:translateX(0); }} }}
      @keyframes pop {{ from {{ opacity:0; transform:scale(.9); }} to {{ opacity:1; transform:scale(1); }} }}
      @keyframes repoIn {{ from {{ opacity:0; transform:perspective(900px) rotateX(10deg) translateY(90px); }} to {{ opacity:1; transform:perspective(900px) rotateX(0) translateY(0); }} }}
      @keyframes pulse {{ from {{ transform:scale(.97); }} to {{ transform:scale(1.04); }} }}
      {landscape_css}
    </style>
  </head>
  <body>
    <div id="root" class="scene layout-{layout}" data-composition-id="{scene_id}" data-layout="{layout}" data-motion="{motion_name}" data-blueprint-id="{blueprint_id}" data-asset-recipe-id="{asset_recipe_id}" data-visual-archetype="{visual_archetype}" data-transition-family="{transition_family}" data-motion-rules="{motion_rules}" data-evidence-count="{evidence_count}" data-evidence-media-count="{evidence_media_count}" data-evidence-hero-kind="{evidence_hero_kind}" data-start="0" data-duration="{safe_duration}" data-width="{width}" data-height="{height}">
      <div class="clip stage-grid" data-start="0" data-duration="{safe_duration}" data-track-index="0"></div>
      <div class="wipe" aria-hidden="true"></div>
      <div class="scene-no">SCENE {scene_no}</div>
      <div class="tag">LingJian Director</div>
      {_evidence_hero(hero_media)}
      {_evidence_focused_body(payload, keyword, accent, label) if hero_media else _layout_body(layout, keyword, accent, label, duration)}
      {_evidence_media_panel(panel_items)}
      {_contract_rail(payload)}
      <div class="safe-band" aria-hidden="true"></div>
    </div>
    {timeline_script}
  </body>
</html>
"""


def _timeline_script(scene_id: str, duration: float) -> str:
    scene_id_json = json.dumps(scene_id, ensure_ascii=False)
    duration_json = json.dumps(round(duration, 3))
    return f"""<script>
      window.__timelines = window.__timelines || {{}};
      const duration = {duration_json};
      const tl = gsap.timeline({{ paused: true, defaults: {{ ease: "power3.out" }} }});
      const mainTargets = ".repo-card,.phone,.chaos-board,.workflow,.dashboard,.github,.evidence-hero";
      const beatTargets = ".bubble,.task,.step,.qa-card,.file,.evidence-story-beat,.contract-pill";
      const lineTargets = ".spark-line,.warning-row,.flow-line";

      tl.fromTo(".wipe", {{ scaleX: 1 }}, {{ scaleX: 0, duration: 0.45 }}, 0);
      tl.fromTo(
        ".stage-grid",
        {{ x: 0, y: 0, opacity: 0.12 }},
        {{ x: -96, y: -72, opacity: 0.28, duration: duration, ease: "none" }},
        0
      );
      tl.fromTo(
        mainTargets,
        {{ opacity: 0, y: 84, scale: 0.96 }},
        {{ opacity: 1, y: 0, scale: 1, duration: 0.72, stagger: 0.08 }},
        0.12
      );
      tl.fromTo(
        ".title,.evidence-story-title",
        {{ opacity: 0, y: 36 }},
        {{ opacity: 1, y: 0, duration: 0.5, stagger: 0.06 }},
        0.28
      );
      tl.fromTo(
        lineTargets,
        {{ scaleX: 0.04, scaleY: 0.12, transformOrigin: "left center" }},
        {{ scaleX: 1, scaleY: 1, duration: Math.max(0.8, duration * 0.5), stagger: 0.08 }},
        0.48
      );
      tl.fromTo(
        beatTargets,
        {{ opacity: 0, y: 48, scale: 0.96 }},
        {{ opacity: 1, y: 0, scale: 1, duration: 0.48, stagger: 0.14 }},
        0.68
      );
      tl.to(
        mainTargets,
        {{ y: -28, duration: Math.max(0.7, duration - 1.2), ease: "power1.inOut" }},
        1.08
      );
      tl.fromTo(".safe-band", {{ opacity: 0.55 }}, {{ opacity: 1, duration: duration, ease: "none" }}, 0);
      window.__timelines[{scene_id_json}] = tl;
    </script>"""


def _landscape_css() -> str:
    return """
      .scene-no { left:72px; top:46px; font-size:22px; }
      .tag { right:72px; top:46px; font-size:22px; }
      .contract-rail { left:72px; right:72px; bottom:150px; }
      .contract-pill { font-size:20px; padding:8px 14px; }
      .safe-band { height:150px; }
      .repo-card { left:96px; top:170px; width:760px; padding:40px; }
      .repo-card .repo { font-size:34px; }
      .title { font-size:92px; line-height:1; }
      .small { font-size:26px; }
      .label { font-size:22px; padding:10px 18px; }
      .phone { right:116px; top:120px; width:520px; height:760px; border-radius:46px; }
      .phone-screen { border-radius:30px; padding:30px 24px; }
      .bubble { font-size:27px; margin-bottom:18px; }
      .chaos-board { left:96px; right:96px; top:124px; height:680px; padding:38px; }
      .task-stack { left:42px; top:126px; width:650px; grid-template-columns:1fr; gap:18px; }
      .task { height:92px; padding:20px 24px; font-size:30px; }
      .warning-panel { right:46px; top:116px; width:620px; height:390px; }
      .workflow { left:108px; right:108px; top:126px; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:22px; }
      .step { min-height:182px; padding:32px 36px 32px 118px; }
      .step-title { font-size:36px; }
      .step-copy { font-size:24px; }
      .flow-line { display:none; }
      .dashboard { left:96px; right:96px; top:112px; bottom:150px; border-radius:34px; }
      .dash-top { height:76px; }
      .terminal { left:34px; right:34px; top:104px; height:250px; font-size:23px; padding:28px; }
      .qa-grid { left:34px; right:34px; top:388px; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:16px; }
      .qa-card { min-height:130px; padding:22px; }
      .github { left:112px; right:112px; top:134px; padding:42px; border-radius:36px; }
      .repo-name { font-size:42px; }
      .star { font-size:28px; padding:18px 28px; }
      .file-list { grid-template-columns:repeat(3, minmax(0, 1fr)); }
      .file { min-height:112px; font-size:25px; padding:20px 22px; }
      .cta-strip { left:270px; right:270px; top:780px; height:88px; font-size:34px; }
      .evidence-hero { left:96px; right:860px; top:120px; height:620px; border-radius:34px; }
      .evidence-story { left:1120px; right:96px; top:142px; }
      .evidence-story-main { padding:30px 34px; border-radius:28px; }
      .evidence-story-title { font-size:42px; }
      .evidence-story-copy { font-size:24px; }
      .evidence-story-beats { grid-template-columns:1fr; }
      .evidence-story-beat { min-height:74px; font-size:22px; padding:18px; }
      .evidence-media-panel { left:1120px; right:96px; top:650px; min-height:160px; grid-template-columns:repeat(2, minmax(0, 1fr)); }
      .evidence-media-card { min-height:160px; border-radius:24px; }
      .evidence-media-card img, .evidence-media-card video { height:160px; }
    """


def _compact(text: str) -> str:
    return " ".join(text.split()).strip()


def _layout_for(payload: dict[str, Any]) -> str:
    blueprint = str(payload.get("blueprint_id") or payload.get("template_id") or "")
    if blueprint in BLUEPRINT_LAYOUTS:
        return BLUEPRINT_LAYOUTS[blueprint]
    recipe = str(payload.get("asset_recipe_id") or "")
    if recipe in RECIPE_LAYOUTS:
        return RECIPE_LAYOUTS[recipe]
    archetype = str(payload.get("visual_archetype") or "").lower()
    for keyword, layout in {
        "ffprobe": "proof",
        "qa": "proof",
        "manifest": "proof",
        "github": "cta",
        "repo": "cta",
        "install": "cta",
        "cursor": "solution",
        "pipeline": "solution",
        "workflow": "solution",
        "cost": "pain",
        "overwhelm": "pain",
        "pain": "pain",
        "ticker": "hook",
        "prompt": "hook",
        "flash": "hook",
    }.items():
        if keyword in archetype:
            return layout
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


def _palette_for(layout: str) -> tuple[str, str, str, str]:
    return PALETTES.get(layout, PALETTES["hook"])


def _layout_body(layout: str, keyword: str, accent: str, label: str, duration: float) -> str:
    if layout == "hook":
        return f"""
      <section class="repo-card">
        <div class="label">{label}</div>
        <div class="title">{keyword}</div>
        <div class="small">{accent}</div>
        <div class="spark-line"></div>
      </section>
      <section class="phone">
        <div class="phone-screen">
          <div class="bubble user">帮我做一条抖音短视频</div>
          <div class="bubble agent">灵剪开始:脚本→配音→画面→QA</div>
          <div class="bubble agent">先让你审,再生成成片</div>
        </div>
      </section>
"""
    if layout == "pain":
        return f"""
      <section class="chaos-board glass" data-start="0" data-duration="{duration:.2f}">
        <div class="label">{label}</div>
        <div class="task-stack">
          <div class="task">脚本反复改</div>
          <div class="task">配音不自然</div>
          <div class="task">画面像 PPT</div>
        </div>
        <div class="warning-panel">
          <div class="small">创作卡点</div>
          <div class="title">{keyword}</div>
          <div class="warning-row"></div>
          <div class="warning-row"></div>
          <div class="warning-row"></div>
        </div>
      </section>
"""
    if layout == "solution":
        return f"""
      <div class="flow-line"></div>
      <section class="workflow" data-start="0" data-duration="{duration:.2f}">
        <div class="step" data-num="1">
          <div class="step-title">脚本三审</div>
          <div class="step-copy">先看 Hook、痛点、方案和 CTA。</div>
        </div>
        <div class="step" data-num="2">
          <div class="step-title">配音试听</div>
          <div class="step-copy">固定音色,再进入正式合成。</div>
        </div>
        <div class="step" data-num="3">
          <div class="step-title">{keyword}</div>
          <div class="step-copy">每镜锁定画面、动效、字幕和验收点。</div>
        </div>
        <div class="step" data-num="4">
          <div class="step-title">渲染 QA</div>
          <div class="step-copy">ffprobe、抽帧和严格门一起检查。</div>
        </div>
      </section>
"""
    if layout == "proof":
        return f"""
      <section class="dashboard" data-start="0" data-duration="{duration:.2f}">
        <div class="dash-top"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="small">release 检查台</span></div>
        <div class="terminal">
          <div class="line">$ lj qa --release --strict</div>
          <div class="line">✓ h264 视频流  ✓ aac 音频流</div>
          <div class="line">✓ 底部字幕  ✓ 三审签名  ✓ 无 mock</div>
        </div>
        <div class="qa-grid">
          <div class="qa-card"><div class="label">{label}</div><div class="small">{accent}</div></div>
          <div class="qa-card"><div class="label">抽帧</div><div class="small">看画面不是看自评</div></div>
          <div class="qa-card"><div class="label">音轨</div><div class="small">自然中文配音</div></div>
          <div class="qa-card"><div class="label">导出</div><div class="small">发布包不带密钥</div></div>
        </div>
      </section>
"""
    return f"""
      <section class="github" data-start="0" data-duration="{duration:.2f}">
        <div class="github-head">
          <div>
            <div class="label">{label}</div>
            <div class="repo-name">dososo / blcaptain-lingjian-video</div>
          </div>
          <div class="star">★ Star</div>
        </div>
        <div class="file-list">
          <div class="file">SKILL.md  对话式工作流</div>
          <div class="file">README.md  普通用户上手</div>
          <div class="file">docs/  能力门诊与发布门</div>
        </div>
      </section>
      <div class="cta-strip">关注项目,点 Star,从一句话开始</div>
"""


def _scene_index(payload: dict[str, Any]) -> int:
    raw = str(payload.get("scene_id") or payload.get("id") or "1")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits:
        return max(int(digits), 1)
    return max(sum(ord(ch) for ch in raw), 1)


def _scene_number(payload: dict[str, Any]) -> str:
    return f"{_scene_index(payload):02d}"[-2:]


def _copy_evidence_media(project: Path, payload: dict[str, Any]) -> list[dict[str, str]]:
    source_root = _project_root(payload)
    if source_root is None:
        return []
    media_dir = project / "assets" / "evidence_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    for index, item in enumerate(_evidence_media_refs(payload), start=1):
        source = _safe_project_media_path(source_root, item["path"])
        if source is None:
            continue
        target = media_dir / f"evidence-{index}{source.suffix.lower()}"
        shutil.copyfile(source, target)
        copied.append(
            {
                "kind": item["kind"],
                "src": target.relative_to(project).as_posix(),
                "label": item["label"],
                "evidence_type": item["evidence_type"],
                "status": item["status"],
                "visual_source": item["visual_source"],
                "publish_grade": item["publish_grade"],
            }
        )
    return copied[:2]


def _project_root(payload: dict[str, Any]) -> Path | None:
    raw = str(payload.get("project_root") or "")
    if not raw:
        return None
    try:
        root = Path(raw).resolve()
    except OSError:
        return None
    return root if root.exists() and root.is_dir() else None


def _safe_project_media_path(project_root: Path, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(project_root)
    except (OSError, ValueError):
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    suffix = resolved.suffix.lower()
    if suffix not in EVIDENCE_IMAGE_EXTENSIONS and suffix not in EVIDENCE_VIDEO_EXTENSIONS:
        return None
    return resolved


def _evidence_media_refs(payload: dict[str, Any]) -> list[dict[str, str]]:
    refs = payload.get("evidence_asset_refs")
    if not isinstance(refs, list):
        return []
    media: list[dict[str, str]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        raw_path = str(
            ref.get("media_path")
            or ref.get("evidence_clip_path")
            or ref.get("path")
            or ""
        )
        suffix = Path(raw_path).suffix.lower()
        if suffix in EVIDENCE_VIDEO_EXTENSIONS:
            kind = "video"
        elif suffix in EVIDENCE_IMAGE_EXTENSIONS:
            kind = "image"
        else:
            continue
        media.append(
            {
                "kind": kind,
                "path": raw_path,
                "label": _evidence_ref_label(ref),
                "evidence_type": str(ref.get("evidence_type") or ref.get("type") or ""),
                "status": str(ref.get("evidence_clip_status") or ""),
                "visual_source": str(ref.get("evidence_visual_source") or ""),
                "publish_grade": "true" if bool(ref.get("publish_grade_evidence_video")) else "false",
            }
        )
    return media


def _evidence_ref_label(ref: dict[str, Any]) -> str:
    for key in ("label", "title", "evidence_type", "type", "id"):
        value = _compact_visual_text(str(ref.get(key) or ""))
        if value:
            return value[:14]
    return "证据素材"


def _inline_evidence_media(payload: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for ref in _evidence_media_refs(payload):
        items.append(
            {
                "kind": ref["kind"],
                "src": ref["path"],
                "label": ref["label"],
                "evidence_type": ref["evidence_type"],
                "status": ref["status"],
                "visual_source": ref["visual_source"],
                "publish_grade": ref["publish_grade"],
            }
        )
    return items[:2]


def _primary_evidence_video(items: list[dict[str, str]]) -> dict[str, str] | None:
    for item in items:
        if item.get("kind") == "video":
            return item
    return None


def _panel_evidence_media(
    items: list[dict[str, str]],
    hero: dict[str, str] | None,
) -> list[dict[str, str]]:
    if hero is None:
        return items[:2]
    return [item for item in items if item is not hero][:2]


def _evidence_hero(item: dict[str, str] | None) -> str:
    if item is None:
        return ""
    src = html.escape(item["src"])
    label = html.escape(item.get("label") or "真实动态证据")
    evidence_type = html.escape(item.get("evidence_type") or "")
    visual_source = html.escape(item.get("visual_source") or "video")
    return f"""
      <section class="evidence-hero" data-evidence-type="{evidence_type}" data-evidence-visual-source="{visual_source}" aria-label="真实动态证据主画面">
        <video src="{src}" autoplay muted playsinline loop></video>
        <div class="evidence-hero-label">
          <div class="evidence-hero-title">{label}</div>
          <div class="evidence-hero-badge">真实视频证据</div>
        </div>
      </section>
"""


def _evidence_focused_body(
    payload: dict[str, Any],
    keyword: str,
    accent: str,
    label: str,
) -> str:
    beats = _evidence_story_beats(payload)
    return f"""
      <section class="evidence-story" aria-label="真实证据导演说明">
        <div class="evidence-story-main">
          <div class="label">{label}</div>
          <div class="evidence-story-title">{keyword}</div>
          <div class="evidence-story-copy">{accent}</div>
        </div>
        <div class="evidence-story-beats">
          <div class="evidence-story-beat">{html.escape(beats[0])}</div>
          <div class="evidence-story-beat">{html.escape(beats[1])}</div>
          <div class="evidence-story-beat">{html.escape(beats[2])}</div>
        </div>
      </section>
"""


def _evidence_story_beats(payload: dict[str, Any]) -> tuple[str, str, str]:
    keyframes = _payload_keyframes(payload)
    states = [_compact_visual_text(_keyframe_state_text(item)) for item in keyframes]
    visible_states = [state[:14] for state in states if state]
    if len(visible_states) >= 3:
        return (visible_states[0], visible_states[1], visible_states[2])
    labels = _evidence_labels(payload)
    if labels:
        joined = " / ".join(labels[:2])
        return ("真实录屏为主", joined[:14], "字幕底部避让")
    return ("真实录屏为主", "导演契约执行", "字幕底部避让")


def _evidence_media_panel(items: list[dict[str, str]]) -> str:
    if not items:
        return ""
    cards: list[str] = []
    for item in items[:2]:
        src = html.escape(item["src"])
        label = html.escape(item.get("label") or "证据素材")
        if item.get("kind") == "video":
            media = f'<video src="{src}" autoplay muted playsinline loop></video>'
        else:
            media = f'<img src="{src}" alt="{label}" />'
        cards.append(
            f"""
        <article class="evidence-media-card" data-evidence-type="{html.escape(item.get("evidence_type") or "")}">
          {media}
          <div class="evidence-media-label">{label}</div>
        </article>"""
        )
    return f"""
      <section class="evidence-media-panel" aria-label="证据素材画面">
{"".join(cards)}
      </section>
"""


def _adapter_contract(
    payload: dict[str, Any],
    evidence_media: list[dict[str, str]],
) -> dict[str, Any]:
    transition_plan = payload.get("transition_plan")
    transition_family = (
        transition_plan.get("family")
        if isinstance(transition_plan, dict)
        else None
    )
    keyframes = _payload_keyframes(payload)
    keyframe_states = [_keyframe_state_text(item) for item in keyframes]
    return {
        "adapter": "lingjian_hyperframes_director",
        "blueprint_id": payload.get("blueprint_id") or payload.get("template_id"),
        "visual_archetype": payload.get("visual_archetype"),
        "asset_recipe_id": payload.get("asset_recipe_id"),
        "material_key": payload.get("material_key"),
        "layout_signature": _layout_for(payload),
        "transition_family": transition_family,
        "motion_rule_ids": _motion_rules(payload),
        "keyframe_count": len(keyframes),
        "keyframe_state_count": len({state for state in keyframe_states if state}),
        "evidence_ref_count": len(payload.get("evidence_asset_refs") or []),
        "evidence_media_count": len(evidence_media),
        "evidence_media_types": sorted({item["kind"] for item in evidence_media}),
        "evidence_media_hero_kind": (
            _primary_evidence_video(evidence_media) or {}
        ).get("kind", ""),
        "evidence_media_hero_role": (
            "primary_visual" if _primary_evidence_video(evidence_media) else ""
        ),
        "template_body_suppressed_for_evidence": bool(_primary_evidence_video(evidence_media)),
        "contract_confirmed_by_generator": True,
    }


def _payload_keyframes(payload: dict[str, Any]) -> list[Any]:
    direct = payload.get("keyframes") or payload.get("keyframe_beats")
    if isinstance(direct, list):
        return [item for item in direct if item is not None]
    board = payload.get("director_board")
    if isinstance(board, dict):
        board_keyframes = board.get("keyframes") or board.get("keyframe_beats")
        if isinstance(board_keyframes, list):
            return [item for item in board_keyframes if item is not None]
    for key in ("director_review_sheet_v2", "director_review_sheet"):
        sheet = payload.get(key)
        if isinstance(sheet, dict):
            sheet_keyframes = sheet.get("keyframes") or sheet.get("keyframe_beats")
            if isinstance(sheet_keyframes, list):
                return [item for item in sheet_keyframes if item is not None]
    return []


def _keyframe_state_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("state", "description", "visual_state", "action", "beat"):
            text = str(value.get(key) or "").strip()
            if text:
                return " ".join(text.lower().split())
    if isinstance(value, str):
        return " ".join(value.strip().lower().split())
    return ""


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
    board = payload.get("director_board")
    if isinstance(board, dict):
        for key in ("visual_content", "scene_goal", "focus"):
            value = _compact_visual_text(str(board.get(key) or ""))
            if value:
                return value[:18]
    recipe = str(payload.get("asset_recipe_id") or "")
    if recipe in RECIPE_LABELS:
        return RECIPE_LABELS[recipe]
    labels = _evidence_labels(payload)
    if labels:
        return "证据素材:" + " / ".join(labels[:2])
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


def _safe_token(value: Any) -> str:
    text = str(value or "").strip()
    keep = [char for char in text if char.isalnum() or char in {"_", "-", "."}]
    return "".join(keep)


def _transition_family(payload: dict[str, Any]) -> str:
    plan = payload.get("transition_plan")
    if isinstance(plan, dict):
        family = plan.get("family") or plan.get("transition_family")
        if family:
            return _safe_token(family)
    motion = payload.get("motion_intent")
    if isinstance(motion, dict) and motion.get("transition_family"):
        return _safe_token(motion.get("transition_family"))
    return ""


def _motion_rules(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("motion_rule_ids")
    if not isinstance(raw, list):
        motion = payload.get("motion_intent")
        raw = motion.get("motion_rule_ids") if isinstance(motion, dict) else []
    return [_safe_token(item) for item in raw if _safe_token(item)]


def _evidence_labels(payload: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for item in payload.get("expected_real_evidence") or []:
        label = _compact_visual_text(str(item))
        if label:
            labels.append(label[:10])
    for item in payload.get("evidence_asset_refs") or []:
        if isinstance(item, dict):
            label = _compact_visual_text(str(item.get("label") or item.get("type") or item.get("id") or ""))
        else:
            label = _compact_visual_text(str(item))
        if label:
            labels.append(label[:10])
    unique: list[str] = []
    for label in labels:
        if label not in unique:
            unique.append(label)
    return unique[:4]


def _contract_rail(payload: dict[str, Any]) -> str:
    pills: list[str] = []
    recipe = str(payload.get("asset_recipe_id") or "")
    if recipe in RECIPE_LABELS:
        pills.append(RECIPE_LABELS[recipe])
    transition = _transition_family(payload)
    if transition:
        pills.append("语义转场")
    evidence = _evidence_labels(payload)
    if evidence:
        pills.append("证据:" + " / ".join(evidence[:2]))
    if not pills:
        return ""
    items = "\n".join(
        f'        <span class="contract-pill">{html.escape(pill)}</span>'
        for pill in pills[:3]
    )
    return f"""
      <div class="contract-rail">
{items}
      </div>
"""


def _stderr_tail(stderr: str) -> str:
    lines = [line for line in (stderr or "").splitlines() if line.strip()]
    return "\n".join(lines[-8:]) or "HyperFrames 渲染失败。"


if __name__ == "__main__":
    raise SystemExit(main())
