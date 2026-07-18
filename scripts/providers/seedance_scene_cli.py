# ruff: noqa: E501
"""LingJian Seedance 文生视频场景适配器。

契约与 hyperframes_scene_cli.py 对齐(灵剪 visuals 走 CLI 适配器 subprocess 调用):
- `--probe`          探测:有 ARK key 返回 0,否则 1。
- stdin JSON payload  生成:读 visual_prompt / duration_sec / ratio / expected_asset_path。
  - payload.probe=true 时只写一个极短占位 mp4 快速返回(capabilities 探测用,不烧云端额度)。
  - 否则真调火山方舟 Seedance(建任务→轮询 succeeded→下载 video_url 到 expected_asset_path)。
- stdout JSON         {"asset_path": ..., "host_generation_contract": {..., "contract_confirmed_by_generator": true}}。

ARK key 读取:环境变量 VOLCENGINE_ARK_API_KEY 优先,回落系统凭据库(macOS 钥匙串 / Linux secret-tool),
命名与灵剪约定一致:service=account=`lingjian:VOLCENGINE_ARK_API_KEY`。key 只在本进程读,不落盘、不进产物。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
ARK_MODEL = "doubao-seedance-2-0-mini-260615"
CREDENTIAL_NAME = "lingjian:VOLCENGINE_ARK_API_KEY"
ADAPTER_ID = "lingjian_seedance_generator"
POLL_INTERVAL_SEC = 8
POLL_MAX_TRIES = 40  # 最长约 5 分钟
CREATE_TIMEOUT_SEC = 60
DOWNLOAD_TIMEOUT_SEC = 180


def main() -> int:
    parser = argparse.ArgumentParser(description="LingJian Seedance scene adapter")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.probe:
        return 0 if _ark_key() else 1
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        expected = _resolve_expected(payload)
        if _is_probe(payload):
            _write_placeholder(expected)
        else:
            _generate(payload, expected)
        if not expected.exists() or expected.stat().st_size == 0:
            raise RuntimeError("Seedance 未写出预期 mp4。")
    except Exception as exc:  # noqa: BLE001 — 失败即非 0,交上游回落
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "asset_path": str(expected),
                "host_generation_contract": _adapter_contract(payload),
            },
            ensure_ascii=False,
        )
    )
    return 0


# ── ARK key ───────────────────────────────────────────────────────────────
def _ark_key() -> str:
    import os

    env_key = (os.environ.get("VOLCENGINE_ARK_API_KEY") or "").strip()
    if env_key:
        return env_key
    # macOS 钥匙串
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", CREDENTIAL_NAME, "-a", CREDENTIAL_NAME, "-w"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    # Linux Secret Service
    try:
        out = subprocess.run(
            ["secret-tool", "lookup", "service", "lingjian", "account", "VOLCENGINE_ARK_API_KEY"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


# ── payload 解析 ────────────────────────────────────────────────────────────
def _resolve_expected(payload: dict[str, Any]) -> Path:
    expected = Path(str(payload.get("expected_asset_path") or "")).expanduser()
    if not expected.is_absolute():
        raise RuntimeError("expected_asset_path 必须是绝对路径。")
    expected.parent.mkdir(parents=True, exist_ok=True)
    return expected


def _is_probe(payload: dict[str, Any]) -> bool:
    return bool(payload.get("probe")) or str(payload.get("task") or "") == "probe_visual_asset"


def _ratio(payload: dict[str, Any]) -> str:
    for key in ("ratio", "aspect"):
        val = str(payload.get(key) or "").strip()
        if val:
            return _norm_ratio(val)
    brief = payload.get("brief")
    if isinstance(brief, dict):
        val = str(brief.get("ratio") or "").strip()
        if val:
            return _norm_ratio(val)
        profile = brief.get("profile")
        if isinstance(profile, dict):
            val = str(profile.get("ratio") or "").strip()
            if val:
                return _norm_ratio(val)
    prompt = str(payload.get("visual_prompt") or "")
    if "16:9" in prompt or "横屏" in prompt or "横版" in prompt:
        return "16:9"
    return "9:16"


def _norm_ratio(val: str) -> str:
    val = val.replace("：", ":").strip()
    allowed = {"16:9", "9:16", "1:1", "4:3", "3:4", "21:9"}
    return val if val in allowed else "9:16"


def _duration(payload: dict[str, Any]) -> int:
    """吸附到 Seedance 2.0 mini 支持的时长集(实测 3s 报 InvalidParameter,仅支持 5/10s)。
    镜头短于支持时长时生成 5s,由下游渲染按镜头时长裁剪对齐。"""
    try:
        dur = float(payload.get("duration_sec") or 5.0)
    except (TypeError, ValueError):
        dur = 5.0
    return 5 if dur <= 7.5 else 10


# ── 生成 ────────────────────────────────────────────────────────────────────
def _generate(payload: dict[str, Any], expected: Path) -> None:
    key = _ark_key()
    if not key:
        raise RuntimeError("未找到 VOLCENGINE_ARK_API_KEY(环境变量或钥匙串)。")
    prompt = str(payload.get("visual_prompt") or payload.get("narration_text") or "").strip()
    if not prompt:
        raise RuntimeError("payload 缺 visual_prompt,无法生成。")
    prompt = f"{prompt} --ratio {_ratio(payload)} --duration {_duration(payload)} --watermark false"
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}

    body = {"model": ARK_MODEL, "content": [{"type": "text", "text": prompt}]}
    task = _post(ARK_BASE, body, headers)
    task_id = task.get("id")
    if not task_id:
        raise RuntimeError(f"Seedance 建任务无 id:{json.dumps(task, ensure_ascii=False)[:200]}")

    for _ in range(POLL_MAX_TRIES):
        time.sleep(POLL_INTERVAL_SEC)
        state = _get(f"{ARK_BASE}/{task_id}", headers)
        status = state.get("status")
        if status == "succeeded":
            url = (state.get("content") or {}).get("video_url")
            if not url:
                raise RuntimeError("Seedance succeeded 但无 video_url。")
            _download(url, expected)
            return
        if status in ("failed", "canceled"):
            raise RuntimeError(f"Seedance {status}:{json.dumps(state, ensure_ascii=False)[:200]}")
    raise RuntimeError("Seedance 轮询超时(约 5 分钟仍未 succeeded)。")


def _post(url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=CREATE_TIMEOUT_SEC) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Seedance HTTP {exc.code}:{exc.read().decode()[:200]}") from exc


def _get(url: str, headers: dict[str, str]) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=CREATE_TIMEOUT_SEC) as resp:
        return json.loads(resp.read())


def _download(url: str, expected: Path) -> None:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SEC) as resp:
        expected.write_bytes(resp.read())


def _write_placeholder(expected: Path) -> None:
    """capabilities 探测用:写一个极短占位 mp4,不烧云端额度。"""
    import shutil

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        subprocess.run(
            [ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=64x36:d=0.2:r=10",
             "-pix_fmt", "yuv420p", str(expected)],
            check=False,
            timeout=30,
        )
    if not expected.exists() or expected.stat().st_size == 0:
        # 无 ffmpeg 时写一个最小 mp4 头占位(仅证明适配器可写出;正式生成走真渲染)
        expected.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")


def _adapter_contract(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "adapter": ADAPTER_ID,
        "generator": "seedance",
        "model": ARK_MODEL,
        "blueprint_id": payload.get("blueprint_id") or payload.get("template_id"),
        "visual_archetype": payload.get("visual_archetype"),
        "asset_recipe_id": payload.get("asset_recipe_id"),
        "material_key": payload.get("material_key"),
        "ratio": _ratio(payload),
        "duration_sec": _duration(payload),
        "evidence_ref_count": len(payload.get("evidence_asset_refs") or []),
        "contract_confirmed_by_generator": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
