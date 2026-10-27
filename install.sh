#!/usr/bin/env bash
# Install (or with --uninstall, remove) the consult skill and its rule blocks.
# Safe to run repeatedly. Touches only its own symlinks and marked blocks.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
BLOCKS=(python3 "$REPO/ai_rubric/blocks.py")
AGY_STATE="$HOME/.local/state/ai-rubric/agy-added.json"
status=0

# Preflight: change nothing unless every check passes.
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  echo "ERROR consult needs Python 3.11 or newer as python3; nothing was changed." >&2
  exit 2
fi
for spec in "$HOME/.claude/CLAUDE.md|md" "$HOME/.codex/AGENTS.md|md" \
            "$HOME/.gemini/GEMINI.md|md" "$HOME/.codex/rules/default.rules|hash"; do
  if ! "${BLOCKS[@]}" check "${spec%%|*}" "${spec##*|}"; then
    echo "ERROR fix the ai-rubric markers in ${spec%%|*} by hand; nothing was changed." >&2
    exit 2
  fi
done

LINKS=(
  "$HOME/.claude/skills/consult|$REPO/skills/consult"
  "$HOME/.codex/skills/consult|$REPO/skills/consult"
  "$HOME/.local/bin/consult|$REPO/bin/consult"
)

link() {
  local dest="$1" src="$2"
  mkdir -p "$(dirname "$dest")"
  if [ -L "$dest" ]; then
    local current; current="$(readlink "$dest")"
    if [ "$current" = "$src" ]; then echo "ok      $dest"; return; fi
    case "$current" in
      "$REPO"/*) ;;  # an older link into this repo: replace it
      *) echo "WARNING $dest links to $current; left alone"; status=1; return ;;
    esac
    rm "$dest"
  elif [ -e "$dest" ]; then
    echo "WARNING $dest exists and is not a link; left alone"; status=1; return
  fi
  ln -s "$src" "$dest" && echo "linked  $dest -> $src"
}

unlink_ours() {
  local dest="$1"
  if [ -L "$dest" ]; then
    case "$(readlink "$dest")" in
      "$REPO"/*) rm "$dest" && echo "removed $dest" ;;
    esac
  fi
}

codex_rules_fragment() {
  local tmp; tmp="$(mktemp)"
  sed "s|@HOME@|$HOME|g" "$REPO/install/codex.rules" > "$tmp"
  echo "$tmp"
}

if [ "${1:-}" = "--uninstall" ]; then
  for pair in "${LINKS[@]}"; do unlink_ours "${pair%%|*}"; done
  for f in "$HOME/.claude/CLAUDE.md" "$HOME/.codex/AGENTS.md" "$HOME/.gemini/GEMINI.md"; do
    "${BLOCKS[@]}" remove "$f" md || status=1
  done
  "${BLOCKS[@]}" remove "$HOME/.codex/rules/default.rules" hash || status=1
  python3 "$REPO/ai_rubric/agy_settings.py" remove "$HOME/.gemini/antigravity-cli/settings.json" "$AGY_STATE" || status=1
  echo "ai-rubric removed (only its own links and marked blocks)."
  exit $status
fi

for pair in "${LINKS[@]}"; do link "${pair%%|*}" "${pair##*|}"; done

for f in "$HOME/.claude/CLAUDE.md" "$HOME/.codex/AGENTS.md"; do
  "${BLOCKS[@]}" upsert "$f" md "$REPO/install/claude-rule.md" && echo "rules   $f" || status=1
done
"${BLOCKS[@]}" upsert "$HOME/.gemini/GEMINI.md" md "$REPO/install/gemini-rules.md" \
  && echo "rules   $HOME/.gemini/GEMINI.md" || status=1
frag="$(codex_rules_fragment)"
"${BLOCKS[@]}" upsert "$HOME/.codex/rules/default.rules" hash "$frag" \
  && echo "rules   $HOME/.codex/rules/default.rules" || status=1
rm -f "$frag"
python3 "$REPO/ai_rubric/agy_settings.py" add "$HOME/.gemini/antigravity-cli/settings.json" "$AGY_STATE" \
  && echo "rules   $HOME/.gemini/antigravity-cli/settings.json (read-only commands)" || status=1

echo
echo "Judge CLIs:"
for name in claude codex agy; do
  found="$(command -v "$name" 2>/dev/null || true)"
  [ -z "$found" ] && [ -x "$HOME/.local/bin/$name" ] && found="$HOME/.local/bin/$name"
  if [ -z "$found" ] && [ "$name" = codex ]; then
    app="/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
    [ -x "$app" ] && found="$app"
  fi
  if [ -n "$found" ]; then echo "  found   $name  $found"; else echo "  MISSING $name"; fi
done

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo; echo "WARNING $HOME/.local/bin is not on PATH; add it so 'consult' can be found." ;;
esac
exit $status
