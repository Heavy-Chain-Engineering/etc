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

# Convert a Git-Bash/MSYS2/Cygwin POSIX-style path to a Windows-native
# path when running under those shell environments. uname -s returns
# MINGW64_NT-* / MSYS_NT-* / CYGWIN_NT-* on Git-Bash / MSYS2 / Cygwin
# respectively; on macOS (Darwin), Linux, and WSL (Linux), the case
# statement falls through to the wildcard branch and the input is
# returned unchanged. cygpath ships with all three Windows shell
# environments by default.
_to_native_path() {
    local path="$1"
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*)
            if ! command -v cygpath &> /dev/null; then
                error "cygpath utility not found on Windows shell — Git Bash install may be incomplete"
                error "Install Git for Windows from https://git-scm.com/download/win"
                exit 1
            fi
            cygpath -w "$path"
            ;;
        *)
            printf '%s' "$path"
            ;;
    esac
}

# ── CLI argument parsing (F013) ──────────────────────────────────────────
# Accepts:
#   --client {claude|antigravity}   non-interactive client choice
#   --scope  {global|project}       global = ~/.claude (default); project = ./.claude in CWD
#   --help                          usage + exit 0
# Backward compatible: with no flags, falls through to interactive prompt.

CLIENT_FLAG=""
SCOPE_FLAG="global"

usage() {
    cat <<USAGE
etc — Engineering Team, Codified — installer

Usage: ./install.sh [OPTIONS]

Options:
  --client {claude|antigravity}   Skip interactive client prompt.
  --scope  {global|project}       Install scope. Defaults to 'global'.
                                  global  = \$HOME/.claude (or \$CLAUDE_CONFIG_DIR if set)
                                            or \$HOME/.gemini/antigravity for Antigravity
                                  project = ./.claude or ./.gemini/antigravity in current dir
  --help                          Show this help and exit.

Examples:
  ./install.sh                              # interactive, global scope
  ./install.sh --client claude              # non-interactive client, global
  ./install.sh --scope project              # interactive client, project scope
  ./install.sh --client claude --scope project  # fully non-interactive, per-project
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --client)
            CLIENT_FLAG="${2:-}"
            shift 2
            ;;
        --scope)
            SCOPE_FLAG="${2:-}"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown flag: $1" >&2
            echo "" >&2
            usage >&2
            exit 1
            ;;
    esac
done

# Validate flag values
case "$CLIENT_FLAG" in
    ""|claude|antigravity) ;;
    *)
        echo "ERROR: --client must be 'claude' or 'antigravity' (got: $CLIENT_FLAG)" >&2
        exit 1
        ;;
esac
case "$SCOPE_FLAG" in
    global|project) ;;
    *)
        echo "ERROR: --scope must be 'global' or 'project' (got: $SCOPE_FLAG)" >&2
        exit 1
        ;;
esac

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
# If --client was passed, skip the interactive prompt. Otherwise ask.
if [ -n "$CLIENT_FLAG" ]; then
    case "$CLIENT_FLAG" in
        claude)       CLIENT_CHOICE="1" ;;
        antigravity)  CLIENT_CHOICE="2" ;;
    esac
    info "Client: $CLIENT_FLAG (from --client)"
else
    echo -e "${BOLD}Select your AI coding assistant:${NC}"
    echo "  1) Claude Code"
    echo "  2) Antigravity / Gemini"
    read -p "Enter choice [1 or 2]: " CLIENT_CHOICE
    echo ""
fi

# Resolve $TARGET_DIR from (client, scope). Project-scope lands in CWD; global
# scope lands in $HOME (honoring $CLAUDE_CONFIG_DIR for Claude global).
if [ "$CLIENT_CHOICE" = "1" ]; then
    CLIENT_NAME="Claude Code"
    if [ "$SCOPE_FLAG" = "project" ]; then
        TARGET_DIR="$PWD/.claude"
    else
        TARGET_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    fi
elif [ "$CLIENT_CHOICE" = "2" ]; then
    CLIENT_NAME="Antigravity / Gemini"
    if [ "$SCOPE_FLAG" = "project" ]; then
        TARGET_DIR="$PWD/.gemini/antigravity"
    else
        TARGET_DIR="$HOME/.gemini/antigravity"
    fi
else
    error "Invalid choice. Please run the script again and select 1 or 2."
    exit 1
fi

info "Scope: $SCOPE_FLAG — installing into $TARGET_DIR"

# ── Preflight: gh-stack (F010 stacked-PR builds) ────────────────────────
# Non-blocking INFO check per F010 spec.md AC10/AC11 + BR-007. gh-stack
# is required only for multi-wave (total_waves > 1) builds; single-wave
# builds and the installer itself work without it. Uses POSIX-portable
# `command -v` so the check survives non-bash shells if the script is
# ever re-shebanged. The installer continues regardless of detection
# outcome — no abort, no non-zero termination, no early return.
if ! command -v gh-stack >/dev/null 2>&1; then
    echo "INFO: gh-stack not detected. Stacked-PR builds (etc F010+) require gh-stack. Install via: gh extension install jiazh/gh-stack (or equivalent). Single-wave builds work without it."
fi

# ── Preflight: impeccable (F011 /design phase wrap) ─────────────────────
# Non-blocking INFO check per F011 spec.md AC15 + BR-009. impeccable is
# required only for features that route through the /design phase; backend-
# only features and the installer itself work without it. Mirrors F010's
# gh-stack preflight pattern (POSIX-portable `command -v` AND a skill-
# directory existence fallback, since impeccable may be installed as a
# Claude Code skill at ~/.claude/skills/impeccable/ rather than as an
# executable on PATH). The installer continues regardless of detection
# outcome — no abort, no non-zero termination, no early return.
if ! command -v impeccable >/dev/null 2>&1 && [ ! -d "$HOME/.claude/skills/impeccable" ]; then
    echo "INFO: impeccable not detected. /design phase requires impeccable (etc F011+). Install via: npm install -g impeccable (or equivalent). Features without a /design phase work without it."
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

with open('$(_to_native_path "$SETTINGS")') as f:
    settings = json.load(f)
with open('$(_to_native_path "$HOOKS_TEMPLATE")') as f:
    template = json.load(f)

settings['hooks'] = template['hooks']

with open('$(_to_native_path "$SETTINGS")', 'w') as f:
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

# ── 10. Rewrite hardcoded ~/.claude/ paths to TARGET_DIR ─────────────────
# Skill instructions, hook commands, settings-hooks.json, and several
# agent definitions reference `~/.claude/` directly. These paths are baked
# at compile time and assume the default install location. When the
# harness lands somewhere else (e.g. ~/.claude-etc/ via CLAUDE_CONFIG_DIR),
# the strings must be rewritten in the installed copies so the runtime
# invocations resolve to files that actually exist.
#
# Uses a temp-file rewrite instead of `sed -i` so the script works under
# both BSD sed (macOS default) and GNU sed (Linux) without flavor checks.
# Writes the temp content back into the original file via `cat > "$f"`
# rather than `mv` so the destination's mode (notably the +x bit set in
# section 5 for hook scripts) is preserved.
if [ "$TARGET_DIR" != "$HOME/.claude" ]; then
    if [[ "$TARGET_DIR" == "$HOME/"* ]]; then
        TARGET_TILDE="~/${TARGET_DIR#$HOME/}"
    else
        TARGET_TILDE="$TARGET_DIR"
    fi

    REWRITTEN=0
    while IFS= read -r f; do
        sed "s|~/.claude/|${TARGET_TILDE}/|g" "$f" > "$f.tmp" \
            && cat "$f.tmp" > "$f" \
            && rm -f "$f.tmp"
        REWRITTEN=$((REWRITTEN + 1))
    done < <(grep -rl '~/.claude/' "$TARGET_DIR" 2>/dev/null || true)
    info "Rewrote ~/.claude/ → $TARGET_TILDE/ in $REWRITTEN file(s)"
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
with open('$(_to_native_path "$HOOKS_TEMPLATE")') as f:
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
