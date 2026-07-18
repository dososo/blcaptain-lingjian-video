import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_skill_file_and_readme_install_prompt_are_packaged():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert skill.startswith("---\nname: lingjian-video")
    assert "帮我做一条短视频" in skill
    assert "doctor 未 ready 时不要继续 release" in skill
    assert "MCP 尚未实现" in skill
    assert "--voice-audio-file" in skill
    assert "scripts/install_skill_links.sh" in readme
    assert "uv run lj run" in readme
    assert "codex plugin marketplace add dososo/blcaptain-lingjian-video" in readme


def test_install_skill_script_and_mcp_boundary_are_honest():
    script = ROOT / "scripts" / "install_skill_links.sh"
    mcp_readme = (ROOT / "packages" / "mcp_server" / "README.md").read_text(encoding="utf-8")
    skill_doc = (ROOT / "docs" / "skill-and-mcp.md").read_text(encoding="utf-8")
    install_script = script.read_text(encoding="utf-8")

    assert script.exists()
    assert "ln -sfn" in install_script
    assert "$HOME/.agents/skills/$SKILL_NAME" in install_script
    assert "$HOME/.codex/skills" not in install_script
    assert "M1 不交付完整 MCP server" in mcp_readme
    assert "MCP 为后续里程碑" in skill_doc
    assert "MCP 可用" not in mcp_readme


def test_creator_onboarding_docs_name_plugins_and_user_audio_path():
    quickstart = (ROOT / "docs" / "CREATOR_QUICKSTART.md").read_text(encoding="utf-8")
    matrix = (ROOT / "docs" / "CAPABILITY_MATRIX.md").read_text(encoding="utf-8")

    assert "npx skills add heygen-com/hyperframes" in quickstart
    assert "npx skills add remotion-dev/skills" in quickstart
    assert "--voice-audio-file" in quickstart
    assert "provider_id=user_audio" in quickstart
    assert "MCP 未实现" in matrix
    assert "灵剪核心不 import、不 bundle Remotion/HyperFrames SDK" in matrix
    assert "Node.js 22+" in quickstart
    assert "商用 license" in quickstart


def test_codex_plugin_manifest_and_marketplace_are_packaged():
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads(
        (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
    )
    plugin_skill = ROOT / "skills" / "lingjian-video" / "SKILL.md"

    assert manifest["name"] == "lingjian-video"
    assert manifest["skills"] == "./skills/"
    assert plugin_skill.exists()
    assert plugin_skill.read_text(encoding="utf-8").startswith("---\nname: lingjian-video")
    assert marketplace["plugins"][0]["name"] == "lingjian-video"
    assert marketplace["plugins"][0]["source"]["path"] == "./"
