#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SKILL_NAME="lingjian-video"

if [ ! -f "$ROOT_DIR/SKILL.md" ]; then
  echo "未找到 $ROOT_DIR/SKILL.md" >&2
  exit 1
fi

mkdir -p "$HOME/.agents/skills" "$HOME/.claude/skills"
ln -sfn "$ROOT_DIR" "$HOME/.agents/skills/$SKILL_NAME"
ln -sfn "$ROOT_DIR" "$HOME/.claude/skills/$SKILL_NAME"

test -f "$HOME/.agents/skills/$SKILL_NAME/SKILL.md"
test -f "$HOME/.claude/skills/$SKILL_NAME/SKILL.md"

echo "已安装 skill 软链:"
echo "- $HOME/.agents/skills/$SKILL_NAME -> $ROOT_DIR"
echo "- $HOME/.claude/skills/$SKILL_NAME -> $ROOT_DIR"
