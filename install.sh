#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"

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

# ── Preflight: dist/ must exist ──────────────────────────────────────────
if [ ! -d "$DIST_DIR" ]; then
    error "dist/ directory not found."
    echo ""
    echo "  Run the compiler first:"
    echo "    python3 compile-sdlc.py spec/etc_sdlc.yaml"
    echo ""
    echo "  The compiler reads the SDLC specification and generates"
    echo "  all artifacts in dist/. Then install.sh deploys them."
    exit 1
fi

if [ ! -f "$DIST_DIR/settings-hooks.json" ]; then
    error "dist/settings-hooks.json not found. Was the compilation successful?"
    exit 1
fi

# ── Client selection ─────────────────────────────────────────────────────
echo -e "${BOLD}Select your AI coding assistant:${NC}"
echo "  1) Claude Code"
echo "  2) Antigravity / Gemini"
read -p "Enter choice [1 or 2]: " CLIENT_CHOICE
echo ""

if [ "$CLIENT_CHOICE" = "1" ]; then
    TARGET_DIR="$HOME/.claude"
    CLIENT_NAME="Claude Code"
elif [ "$CLIENT_CHOICE" = "2" ]; then
    TARGET_DIR="$HOME/.gemini/antigravity"
    CLIENT_NAME="Antigravity / Gemini"
else
    error "Invalid choice. Please run the script again and select 1 or 2."
    exit 1
fi

# ── 1. Create directory structure ────────────────────────────────────────
# Standards subdirectories are discovered from the compiled dist/ rather
# than hardcoded — a hardcoded list silently drops any new category
# added in the spec (this happened with standards/git/ in v1.6).
mkdir -p "$TARGET_DIR"/{agents,skills,standards,hooks,sdlc,scripts,templates}
if [ -d "$DIST_DIR/standards" ]; then
    for src_dir in "$DIST_DIR/standards"/*/; do
        [ -d "$src_dir" ] || continue
        category=$(basename "$src_dir")
        mkdir -p "$TARGET_DIR/standards/$category"
    done
fi
info "Directory structure ready"

# ── 2. Install agents ───────────────────────────────────────────────────
AGENT_COUNT=0
if [ -d "$DIST_DIR/agents" ]; then
    for f in "$DIST_DIR"/agents/*.md; do
        [ -f "$f" ] || continue
        cp "$f" "$TARGET_DIR/agents/"
        AGENT_COUNT=$((AGENT_COUNT + 1))
    done
fi
info "Installed $AGENT_COUNT agents"

# ── 3. Install skills ───────────────────────────────────────────────────
# Copy entire skill directory trees, not just top-level files, so skills
# with templates/ subdirectories (e.g. init-project) install their
# supporting files alongside SKILL.md. Uses rsync if available (clean
# tree sync); otherwise falls back to cp -R.
SKILL_COUNT=0
if [ -d "$DIST_DIR/skills" ]; then
    for skill_dir in "$DIST_DIR"/skills/*/; do
        [ -d "$skill_dir" ] || continue
        skill_name=$(basename "$skill_dir")
        target_skill_dir="$TARGET_DIR/skills/$skill_name"
        mkdir -p "$target_skill_dir"
        if command -v rsync &> /dev/null; then
            rsync -a --delete "$skill_dir" "$target_skill_dir/"
        else
            # Portable fallback: clear target then copy tree contents
            find "$target_skill_dir" -mindepth 1 -delete 2>/dev/null || true
            cp -R "$skill_dir." "$target_skill_dir/"
        fi
        SKILL_COUNT=$((SKILL_COUNT + 1))
    done
fi
info "Installed $SKILL_COUNT skills"

# ── 4. Install standards ────────────────────────────────────────────────
STANDARD_COUNT=0
if [ -d "$DIST_DIR/standards" ]; then
    # Discover subdirectories dynamically rather than hardcoding a list.
    # See "directory structure" block above for why.
    for src_dir in "$DIST_DIR/standards"/*/; do
        [ -d "$src_dir" ] || continue
        category=$(basename "$src_dir")
        for f in "$src_dir"/*.md; do
            [ -f "$f" ] || continue
            cp "$f" "$TARGET_DIR/standards/$category/"
            STANDARD_COUNT=$((STANDARD_COUNT + 1))
        done
    done
fi
info "Installed $STANDARD_COUNT standards"

# ── 5. Install hooks ────────────────────────────────────────────────────
HOOK_COUNT=0
if [ -d "$DIST_DIR/hooks" ]; then
    for f in "$DIST_DIR"/hooks/*.sh; do
        [ -f "$f" ] || continue
        cp "$f" "$TARGET_DIR/hooks/"
        chmod +x "$TARGET_DIR/hooks/$(basename "$f")"
        HOOK_COUNT=$((HOOK_COUNT + 1))
    done
fi
info "Installed $HOOK_COUNT hooks (executable)"

# ── 6. Merge hook wiring into settings.json ──────────────────────────────
SETTINGS="$TARGET_DIR/settings.json"
HOOKS_TEMPLATE="$DIST_DIR/settings-hooks.json"

merge_settings() {
    if [ ! -f "$SETTINGS" ]; then
        cp "$HOOKS_TEMPLATE" "$SETTINGS"
        info "Created settings.json with hook wiring"
        return
    fi

    # Merge hooks into existing settings (replace hooks section)
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
    info "Merged hook wiring into settings.json (replaced hooks section)"
}

if command -v python3 &> /dev/null; then
    merge_settings
else
    warn "python3 not found — skipping settings.json merge"
    warn "Manually merge $HOOKS_TEMPLATE into $SETTINGS"
fi

# ── 7. Install SDLC tracker templates ───────────────────────────────────
if [ -d "$DIST_DIR/sdlc" ]; then
    cp "$DIST_DIR/sdlc/tracker.py" "$TARGET_DIR/sdlc/" 2>/dev/null && \
        chmod +x "$TARGET_DIR/sdlc/tracker.py" || true
    cp "$DIST_DIR/sdlc/dod-templates.json" "$TARGET_DIR/sdlc/" 2>/dev/null || true
    info "Installed SDLC tracker templates"
fi

# ── 8. Install templates ─────────────────────────────────────────────────
TEMPLATE_COUNT=0
if [ -d "$DIST_DIR/templates" ]; then
    for f in "$DIST_DIR"/templates/*.tmpl; do
        [ -f "$f" ] || continue
        cp "$f" "$TARGET_DIR/templates/"
        TEMPLATE_COUNT=$((TEMPLATE_COUNT + 1))
    done
fi
info "Installed $TEMPLATE_COUNT templates"

# ── 9. Install git hooks & scripts ──────────────────────────────────────
if [ -d "$DIST_DIR/hooks/git" ]; then
    mkdir -p "$TARGET_DIR/hooks/git"
    for f in "$DIST_DIR/hooks/git/"*; do
        [ -f "$f" ] || continue
        cp "$f" "$TARGET_DIR/hooks/git/"
        chmod +x "$TARGET_DIR/hooks/git/$(basename "$f")"
    done
    info "Installed git hook templates"
fi

if [ -d "$DIST_DIR/scripts" ]; then
    for f in "$DIST_DIR/scripts/"*; do
        [ -f "$f" ] || continue
        cp "$f" "$TARGET_DIR/scripts/"
        chmod +x "$TARGET_DIR/scripts/$(basename "$f")"
    done
    info "Installed utility scripts"
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Installation complete${NC}"
echo ""
echo "  Source:     $DIST_DIR"
echo "  Installed:  $TARGET_DIR"
echo ""
echo "    agents/     $AGENT_COUNT agent definitions"
echo "    skills/     $SKILL_COUNT skills (/implement)"
echo "    standards/  $STANDARD_COUNT engineering standards"
echo "    hooks/      $HOOK_COUNT hook scripts"
echo "    sdlc/       tracker + DoD templates"
echo ""
echo "  Hook events wired:"
HOOK_EVENTS=$(python3 -c "
import json
with open('$HOOKS_TEMPLATE') as f:
    hooks = json.load(f).get('hooks', {})
for event, groups in hooks.items():
    count = sum(len(g.get('hooks', [])) for g in groups)
    print(f'    {event}: {count} handler(s)')
" 2>/dev/null || echo "    (run python3 to see details)")
echo "$HOOK_EVENTS"
echo ""
echo "  Lifecycle:"
echo "    1. Edit spec/etc_sdlc.yaml (source of truth)"
echo "    2. python3 compile-sdlc.py spec/etc_sdlc.yaml"
echo "    3. ./install.sh"
echo ""
echo "  Quick start:"
echo "    /implement spec/your-prd.md"
echo ""
