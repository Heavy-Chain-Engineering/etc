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

# ── Optional third-party tool preflights (gh-stack, impeccable, Mergiraf) ─
# Pattern: detect missing tool → in INTERACTIVE mode (no --client flag),
# prompt the operator [y/N] whether to install + run the install command
# with their consent. In NON-INTERACTIVE mode (--client flag set), do NOT
# prompt — emit the INFO line listing how to install for the operator's
# later reference. The installer ALWAYS continues regardless of outcome;
# no third-party tool is a hard dependency for the etc core.
#
# Security posture: each install command is a single, well-known command
# (e.g. `brew install mergiraf`). The operator sees the exact command in
# the prompt before answering 'y'. Failures are surfaced as warnings, not
# errors — the installer keeps going.

# Verbatim INFO lines per F010/F011/F016 contract tests. These strings are
# the operator-facing surface AND the assertion targets for test_design_skill.py
# and test_build_stacked_prs.py. Modify with care — pinned in PRD ACs.
#
# F010 NOTE (corrected 2026-05-13): the F010 spec originally cited
# `gh extension install jiazh/gh-stack` — that namespace was wrong.
# The real tool is github/gh-stack (GitHub's official stacked-PR
# extension, currently in private preview; waitlist at
# https://github.github.com/gh-stack/). Install command + CLI shape
# (`gh stack ...`) match the F010 design.
F010_INFO_LINE="INFO: gh-stack not detected. Stacked-PR builds (etc F010+) require gh-stack (GitHub's official extension, currently in private preview at https://github.github.com/gh-stack/). Install via: gh extension install github/gh-stack (or equivalent). Single-wave builds work without it."
F011_INFO_LINE="INFO: impeccable not detected. /design phase requires impeccable (etc F011+). Install via: npm install -g impeccable (or equivalent). Features without a /design phase work without it."
F016_INFO_LINE="INFO: Mergiraf not detected. Semantic merge conflicts (etc F016+) are resolved manually without it. Install via: brew install mergiraf (macOS) | cargo install mergiraf | https://mergiraf.org for other platforms."
F018_INFO_LINE="INFO: @google/design.md not detected. /design phase output (etc F018+) validates against Google's DESIGN.md spec (https://github.com/google-labs-code/design.md). Install via: npm install -g @google/design.md (or run via npx). Features without /design work without it."

offer_install() {
    # Args:
    #   $1 = tool display name (e.g. "Mergiraf")
    #   $2 = verbatim INFO line (printed in non-interactive mode)
    #   $3 = install command (run with operator consent in interactive mode)
    local tool_name="$1"
    local info_line="$2"
    local install_cmd="$3"

    if [ -n "$CLIENT_FLAG" ]; then
        # Non-interactive (--client flag set): print verbatim INFO line; do
        # not prompt. Preserves F010/F011/F016 contract tests.
        echo "$info_line"
        return
    fi

    # Interactive: prompt operator before running anything third-party.
    echo ""
    echo "  $tool_name not detected."
    echo "  $info_line"
    read -r -p "  Install now via: $install_cmd ? [y/N]: " reply
    case "$reply" in
        [yY]|[yY][eE][sS])
            echo "  Running: $install_cmd"
            if eval "$install_cmd"; then
                info "$tool_name installed"
            else
                warn "$tool_name install failed (exit $?). Continuing without it."
            fi
            ;;
        *)
            echo "  Skipped. Install later via: $install_cmd"
            ;;
    esac
}

# gh-stack (F010 stacked-PR builds): GitHub's official extension.
# Currently in private preview at https://github.github.com/gh-stack/ —
# most operators (including HCE) don't have access yet, so we do NOT
# prompt to auto-install. INFO-only. Operators with waitlist access
# install via `gh extension install github/gh-stack` manually. Operators
# without access can use alternative stacking tools (ezyang/ghstack,
# Graphite, Sapling) OR ship single-wave builds, which need no tool.
if ! command -v gh-stack >/dev/null 2>&1; then
    echo "$F010_INFO_LINE"
fi

# impeccable (F011 /design phase wrap): required only for features routing
# through /design. Skip detection if the Claude Code skill version is
# already installed under ~/.claude/skills/impeccable/.
if ! command -v impeccable >/dev/null 2>&1 && [ ! -d "$HOME/.claude/skills/impeccable" ]; then
    offer_install "impeccable" "$F011_INFO_LINE" "npm install -g impeccable"
fi

# Mergiraf (F016 R3 — semantic merge for stacked-PR chains). On macOS we
# prefer brew (no Rust toolchain required); on Linux fall back to cargo.
if ! command -v mergiraf >/dev/null 2>&1; then
    case "$(uname -s)" in
        Darwin) mergiraf_cmd="brew install mergiraf" ;;
        *)      mergiraf_cmd="cargo install mergiraf" ;;
    esac
    offer_install "Mergiraf" "$F016_INFO_LINE" "$mergiraf_cmd"
fi

# @google/design.md (F018 — DESIGN.md compose + lint). Detected via npm
# package presence in either global node_modules OR by running `npx -y
# @google/design.md spec` as a probe (the spec subcommand is fast and
# only succeeds when the package is reachable). For install.sh we
# default to the npm-global probe; offline operators can run npx
# transparently. The fallback recommendation uses npm-global so the
# operator picks it up across projects without re-downloading per run.
if ! npm list -g --depth=0 @google/design.md >/dev/null 2>&1; then
    offer_install "@google/design.md" "$F018_INFO_LINE" "npm install -g @google/design.md"
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

# F020 — profiles/ subtree (detection.yaml + bindings + gate scripts) is
# nested deeper than the top-level *.md copy above. Use a recursive copy
# so per-profile assets land under TARGET_DIR/standards/code/profiles/.
if [ -d "$DIST_DIR/standards/code/profiles" ]; then
    mkdir -p "$TARGET_DIR/standards/code"
    cp -R "$DIST_DIR/standards/code/profiles" "$TARGET_DIR/standards/code/"
    # Make sure the gate scripts are executable (cp -R preserves mode on
    # most systems but is paranoid here).
    find "$TARGET_DIR/standards/code/profiles" -name '*.sh' -exec chmod +x {} \; 2>/dev/null || true
    PROFILE_COUNT=$(find "$TARGET_DIR/standards/code/profiles" -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ')
    info "Installed $PROFILE_COUNT language profile(s)"
fi

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

# ── 11. F020 profile detection ──────────────────────────────────────────
# Detect language profiles active in the install-time CWD and write
# `.etc_sdlc/profiles.lock`. Project-scope installs (--scope project) run
# from the target project root and produce a useful lock immediately;
# global-scope installs run from etc's own directory and produce a lock
# describing etc itself. SessionStart staleness checks re-detect later
# when the operator opens a different project.
if [ -f "$TARGET_DIR/scripts/detect_profiles.py" ] && command -v python3 &> /dev/null; then
    LOCK_DIR="$PWD/.etc_sdlc"
    mkdir -p "$LOCK_DIR"
    if python3 "$TARGET_DIR/scripts/detect_profiles.py" --repo-root "$PWD" --write-lock 2>/dev/null; then
        if [ -s "$LOCK_DIR/profiles.lock" ]; then
            DETECTED=$(tr '\n' ' ' < "$LOCK_DIR/profiles.lock")
            info "Detected profiles: $DETECTED"
        else
            info "No language profiles detected in $PWD (lock written empty)"
        fi
    else
        warn "Profile detection failed; skipping profiles.lock write"
    fi
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
