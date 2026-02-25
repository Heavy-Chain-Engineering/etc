#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
error() { echo -e "  ${RED}✗${NC} $1"; }

echo ""
echo -e "${BOLD}etc — Engineering Team, Codified${NC}"
echo "Installing coding harness..."
echo ""

# Preflight checks
if [ ! -d "$SCRIPT_DIR/agents" ] || [ ! -d "$SCRIPT_DIR/standards" ] || [ ! -d "$SCRIPT_DIR/hooks" ]; then
    error "Missing agents/, standards/, or hooks/ in $SCRIPT_DIR"
    error "Are you running this from the etc-system-engineering repo root?"
    exit 1
fi

# 1. Create directory structure
mkdir -p "$CLAUDE_DIR"/{agents,standards/{process,code,testing,architecture,security,quality},hooks}
info "Directory structure ready"

# 2. Install agents
AGENT_COUNT=0
for f in "$SCRIPT_DIR"/agents/*.md; do
    cp "$f" "$CLAUDE_DIR/agents/"
    AGENT_COUNT=$((AGENT_COUNT + 1))
done
info "Installed $AGENT_COUNT agents"

# 3. Install standards
STANDARD_COUNT=0
for dir in process code testing architecture security quality; do
    if [ -d "$SCRIPT_DIR/standards/$dir" ]; then
        for f in "$SCRIPT_DIR/standards/$dir"/*.md; do
            [ -f "$f" ] || continue
            cp "$f" "$CLAUDE_DIR/standards/$dir/"
            STANDARD_COUNT=$((STANDARD_COUNT + 1))
        done
    fi
done
info "Installed $STANDARD_COUNT standards"

# 4. Install hooks
HOOK_COUNT=0
for f in "$SCRIPT_DIR"/hooks/*.sh; do
    cp "$f" "$CLAUDE_DIR/hooks/"
    chmod +x "$CLAUDE_DIR/hooks/$(basename "$f")"
    HOOK_COUNT=$((HOOK_COUNT + 1))
done
info "Installed $HOOK_COUNT hooks (executable)"

# 5. Merge hook wiring into settings.json
SETTINGS="$CLAUDE_DIR/settings.json"
HOOKS_TEMPLATE="$SCRIPT_DIR/settings-hooks.json"

merge_settings() {
    if [ ! -f "$SETTINGS" ]; then
        cp "$HOOKS_TEMPLATE" "$SETTINGS"
        info "Created settings.json with hook wiring"
        return
    fi

    # Check if hooks are already configured
    if python3 -c "
import json, sys
with open('$SETTINGS') as f:
    d = json.load(f)
sys.exit(0 if 'hooks' not in d else 1)
" 2>/dev/null; then
        # No hooks yet — merge them in
        python3 -c "
import json
with open('$SETTINGS') as f:
    settings = json.load(f)
with open('$HOOKS_TEMPLATE') as f:
    template = json.load(f)
settings['hooks'] = template['hooks']
with open('$SETTINGS', 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')
"
        info "Merged hook wiring into existing settings.json"
    else
        warn "settings.json already has hooks — skipping (review manually if needed)"
    fi
}

if command -v python3 &> /dev/null; then
    merge_settings
else
    warn "python3 not found — skipping settings.json merge"
    warn "Manually add hook wiring from settings-hooks.json"
fi

# 6. Install SDLC tracker templates
mkdir -p "$CLAUDE_DIR/sdlc"
cp "$SCRIPT_DIR/.sdlc/tracker.py" "$CLAUDE_DIR/sdlc/"
cp "$SCRIPT_DIR/.sdlc/dod-templates.json" "$CLAUDE_DIR/sdlc/"
chmod +x "$CLAUDE_DIR/sdlc/tracker.py"
info "Installed SDLC tracker templates (run 'python3 .sdlc/tracker.py init' per project)"

# 7. Install .meta/ reconciliation tools
mkdir -p "$CLAUDE_DIR/scripts"
cp "$SCRIPT_DIR/scripts/meta-reconcile.py" "$CLAUDE_DIR/scripts/"
chmod +x "$CLAUDE_DIR/scripts/meta-reconcile.py"
# Git hooks are per-project — copy templates to a reference location
mkdir -p "$CLAUDE_DIR/hooks/git"
cp "$SCRIPT_DIR/hooks/git/post-commit" "$CLAUDE_DIR/hooks/git/"
cp "$SCRIPT_DIR/hooks/git/pre-push" "$CLAUDE_DIR/hooks/git/"
chmod +x "$CLAUDE_DIR/hooks/git/"*
info "Installed .meta/ reconciliation tools (git hooks in ~/.claude/hooks/git/)"

# Summary
echo ""
echo -e "${BOLD}Installation complete${NC}"
echo ""
echo "  Installed to: $CLAUDE_DIR"
echo "    agents/    $(ls "$CLAUDE_DIR/agents/"*.md 2>/dev/null | wc -l | tr -d ' ') agent definitions"
echo "    standards/ $(find "$CLAUDE_DIR/standards" -name '*.md' 2>/dev/null | wc -l | tr -d ' ') engineering standards"
echo "    hooks/     $(ls "$CLAUDE_DIR/hooks/"*.sh 2>/dev/null | wc -l | tr -d ' ') Claude Code hooks"
echo "    hooks/git/ post-commit + pre-push (.meta/ reconciliation)"
echo "    scripts/   meta-reconcile.py"
echo "    sdlc/      tracker.py + dod-templates.json"
echo ""
echo "  Next steps:"
echo "    1. Verify ~/.claude/settings.json has hook wiring"
echo "    2. Add a .claude/CLAUDE.md to your project repos"
echo "    3. Per-project: cp ~/.claude/hooks/git/* .git/hooks/ to enable .meta/ tracking"
echo "    4. Launch Claude Code — the harness is active"
echo ""
