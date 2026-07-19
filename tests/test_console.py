"""lj console(本机导演控制台一键服务)回归测试。

锁死命根子:build_console 从流水线产物自动生成候选页;make_server 起本机服务 + /confirm 写回。
"""

import json
import threading
import urllib.request
from pathlib import Path

from packages.core.artifacts import write_artifact
from packages.core.console import build_console, detect_gate, make_server
from packages.core.project import ProjectRef, init_project


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    init_project(project, "console测试")
    write_artifact(
        ProjectRef(project, "console测试"),
        "script",
        {
            "id": "script",
            "style": "vox_cut",
            "ratio": "16:9",
            "target_duration_sec": 30,
            "profile": "open_source_project_intro",
            "style_lock": {"motion_language": "分帧逐层入场"},
            "scenes": [
                {"id": "s1", "narration_text": "第一镜钩子,一句话进去。"},
                {"id": "s2", "narration_text": "第二镜展开,把候选摆给你。"},
                {"id": "s3", "narration_text": "第三镜收尾,做你第一条片子。"},
            ],
        },
    )
    return project


def _voice_options(project: Path) -> None:
    art = project / "artifacts"
    vdir = art / "voice_options"
    vdir.mkdir(parents=True, exist_ok=True)
    for i in (1, 2, 3):
        (vdir / f"option_{i}.mp3").write_bytes(b"ID3fake-mp3-bytes")
    (art / "voice_options.json").write_text(
        json.dumps(
            {
                "options": [
                    {
                        "index": i,
                        "label_zh": f"音色{i}",
                        "voice_id": f"zh_test_{i}",
                        "audio_path": f"artifacts/voice_options/option_{i}.wav",
                        "duration_sec": 10.0,
                    }
                    for i in (1, 2, 3)
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_detect_gate_voice_then_script(tmp_path):
    project = _project(tmp_path)
    # 只有 script → 脚本关
    assert detect_gate(project) == "script"
    # 加 voice_options 且未审批 → 配音关
    _voice_options(project)
    assert detect_gate(project) == "voice"
    # 配音已审批后 → 不再停在配音关
    (project / "artifacts" / "approvals.json").write_text(
        json.dumps({"script": {}, "voice": {}}), encoding="utf-8"
    )
    assert detect_gate(project) == "script"


def test_build_voice_console(tmp_path):
    project = _project(tmp_path)
    _voice_options(project)
    serve_dir, gate = build_console(project, "voice")
    assert gate == "voice"
    html = (serve_dir / "index.html").read_text(encoding="utf-8")
    assert "配音关" in html and "音色确认" in html
    assert "zh_test_1" in html  # 候选真进了页面
    # mp3 被拷进服务目录(内联播放器要能取到)
    assert (serve_dir / "option_1.mp3").exists()
    # /confirm 写回脚本存在
    assert "/confirm" in html


def test_build_script_board_from_script(tmp_path):
    project = _project(tmp_path)
    serve_dir, gate = build_console(project, "script")
    assert gate == "script"
    board = json.loads((serve_dir / "board.json").read_text(encoding="utf-8"))
    assert board["schemaVersion"] == "1.0"
    assert len(board["shots"]) == 3  # 每场景一镜
    # 能量在 1–5、脚本=旁白原文、beats≥1(schema 要求)
    for shot, scene_text in zip(
        board["shots"],
        ["第一镜钩子", "第二镜展开", "第三镜收尾"],
    ):
        assert 1 <= shot["energy"] <= 5
        assert scene_text in shot["script"]
        assert len(shot["beats"]) >= 1
    # render.js + 装配入口都在
    assert (serve_dir / "render.js").exists()
    assert "renderDirectorBoard" in (serve_dir / "index.html").read_text(encoding="utf-8")


def test_server_serves_and_confirm_writes_back(tmp_path):
    project = _project(tmp_path)
    _voice_options(project)
    serve_dir, _ = build_console(project, "voice")
    httpd = make_server(serve_dir, project, 0)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        # 页面可取
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as r:
            assert r.status == 200
            assert "音色确认" in r.read().decode("utf-8")
        # POST /confirm → 写回 console_state.json
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/confirm",
            data=json.dumps({"gate": "voice", "selected_index": 3}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as r:
            assert r.status == 200
        state = json.loads(
            (project / "artifacts" / "console_state.json").read_text(encoding="utf-8")
        )
        assert state["selected_index"] == 3
    finally:
        httpd.shutdown()
        httpd.server_close()
