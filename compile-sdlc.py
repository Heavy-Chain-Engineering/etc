#!/usr/bin/env python3
"""
compile-sdlc.py — Compiles the SDLC specification into deployable artifacts.

Reads spec/etc_sdlc.yaml (the single source of truth) and emits:
  dist/
  ├── settings-hooks.json    (Claude Code hook wiring)
  ├── hooks/                 (command hook scripts)
  ├── agents/                (agent .md definitions)
  ├── skills/                (skill .md definitions)
  ├── standards/             (engineering standards, passed through)
  └── sdlc/                  (tracker templates)

Usage:
  python3 compile-sdlc.py [spec-file]
  python3 compile-sdlc.py spec/etc_sdlc.yaml
"""

import argparse
import contextlib
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

import yaml

try:
    from filelock import FileLock
except ImportError:  # pragma: no cover - minimal installer envs may lack filelock
    FileLock = None  # type: ignore[assignment,misc]

# Windows ships cp1252 as the default stdio encoding; force utf-8 so prints of
# box-drawing chars and other non-ASCII content don't crash on Windows. No-op
# on macOS/Linux (which default to utf-8 already).
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


CODEX_COMMAND_EVENTS = frozenset({
    "PreToolUse",
    "PostToolUse",
    "SessionStart",
    "Stop",
    "SubagentStart",
})

CODEX_RESULT_PARITY_BUCKETS: Final = {
    "TaskCreated": "skill-artifact-readiness",
    "TaskCompleted": "subagent-artifact-completion",
    "SubagentStop": "subagent-artifact-review",
    "ConfigChange": "edit-bash-ci-guard",
}

CODEX_ARTIFACT_SCHEMAS: Final = {
    "readiness": [
        "schema_version",
        "task_id",
        "client",
        "created_at",
        "updated_at",
        "source_commit",
        "changed_files",
        "status",
        "checks",
        "notes",
        "phase",
        "risk_tier",
        "files_in_scope",
        "acceptance_criteria",
        "required_reading",
        "test_strategy",
        "dependencies",
        "ready",
    ],
    "reading-ledger": [
        "schema_version",
        "task_id",
        "client",
        "created_at",
        "updated_at",
        "source_commit",
        "changed_files",
        "status",
        "checks",
        "notes",
        "required_reading",
        "read_entries",
        "coverage",
        "missing",
        "fresh",
    ],
    "review": [
        "schema_version",
        "task_id",
        "client",
        "created_at",
        "updated_at",
        "source_commit",
        "changed_files",
        "status",
        "checks",
        "notes",
        "reviewer",
        "review_type",
        "findings",
        "required_fixes",
        "verdict",
        "fresh_for_changed_files",
    ],
    "completion": [
        "schema_version",
        "task_id",
        "client",
        "created_at",
        "updated_at",
        "source_commit",
        "changed_files",
        "status",
        "checks",
        "notes",
        "test_evidence",
        "review_evidence",
        "acceptance_criteria_results",
        "unresolved_risks",
        "final_status",
    ],
}

CODEX_PLUGIN_NAME = "etc-sdlc"
CODEX_PLUGIN_BUNDLED_SURFACES = ("skills", "hooks")
CODEX_PLUGIN_INSTALLER_OWNED_SURFACES = (
    "AGENTS.md",
    ".codex/agents",
    ".codex/scripts",
    ".codex/schemas",
    "gate-classification.json",
    "project-local Codex config",
)

CODEX_SOURCE_SNAPSHOT_PATHS = (
    "compile-sdlc.py",
    "spec",
    "agents",
    "hooks",
    "skills",
    "standards",
    "scripts",
)

CODEX_EXPECTED_SNAPSHOT_PATHS = (
    "AGENTS.md",
    "gate-classification.json",
    "standards",
    ".codex/hooks.json",
    ".codex/hooks",
    ".codex/agents",
    ".codex/scripts",
    ".codex/schemas",
    ".codex/standards",
    ".agents/skills",
)


def load_spec(spec_path: str) -> dict:
    """Load and validate the SDLC specification."""
    with open(spec_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    required_sections = ["version", "defaults", "gates"]
    missing = [s for s in required_sections if s not in spec]
    if missing:
        print(f"ERROR: Missing required sections in spec: {missing}", file=sys.stderr)
        sys.exit(1)

    return spec


def compile_gates(spec: dict, dist_dir: Path, repo_root: Path) -> dict:
    """Compile gates into settings-hooks.json and copy/generate hook scripts."""
    gates = spec.get("gates", {})
    defaults = spec.get("defaults", {})
    hooks_dir = dist_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Group gates by event and matcher for settings-hooks.json
    # Intermediate: { event: { matcher_key: [handler, ...] } }
    events: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for gate in gates.values():
        event = gate["event"]
        gate_type = gate["type"]
        matcher = gate.get("matcher", "")

        handler: dict = {"type": gate_type}

        if gate_type == "command":
            # Copy the script to dist/hooks/ and reference it
            script_name = gate["script"]
            src_script = repo_root / "hooks" / script_name
            dst_script = hooks_dir / script_name

            if src_script.exists():
                shutil.copy2(src_script, dst_script)
                dst_script.chmod(0o755)
            else:
                print(f"WARNING: Script not found: {src_script}", file=sys.stderr)

            # Placeholder substituted at install time (see
            # etc_installer.settings_merge.substitute_hooks_dir). The
            # compiler does NOT know the install target — the installer
            # resolves --target-dir / CLAUDE_CONFIG_DIR and rewrites the
            # placeholder accordingly.
            handler["command"] = f"{{{{ETC_HOOKS_DIR}}}}/{script_name}"
            timeout = gate.get("timeout")
            if timeout:
                handler["timeout"] = timeout * 1000  # Convert seconds to milliseconds

        elif gate_type in ("prompt", "agent"):
            # Build the full prompt with role prefix
            role = gate.get("role", "")
            prompt = gate.get("prompt", "")

            if role:
                full_prompt = f"{role.strip()}\n\n{prompt.strip()}"
            else:
                full_prompt = prompt.strip()

            handler["prompt"] = full_prompt
            handler["model"] = gate.get("model", defaults.get("model", "sonnet"))

            timeout = gate.get("timeout")
            if timeout:
                handler["timeout"] = timeout

            if gate_type == "agent":
                max_turns = gate.get("max_turns")
                if max_turns:
                    handler["maxTurns"] = max_turns

        # Add status message
        description = gate.get("description", "")
        if description:
            # Take first sentence as status message
            first_sentence = description.strip().split(".")[0].strip()
            if len(first_sentence) < 80:
                handler["statusMessage"] = f"{first_sentence}..."

        # Add the if field for tool-specific filtering
        if_filter = gate.get("if")
        if if_filter:
            handler["if"] = if_filter

        # Group by event + matcher
        if event not in events:
            events[event] = {}

        matcher_key = matcher or "__no_matcher__"
        if matcher_key not in events[event]:
            events[event][matcher_key] = []

        events[event][matcher_key].append(handler)

    helpers_src = repo_root / "hooks" / "helpers"
    if helpers_src.exists():
        # Filter caches like the codex copy path (is_generated_cache_path)
        # does — this site shipped __pycache__/*.pyc into dist (audit init 8).
        shutil.copytree(
            helpers_src,
            hooks_dir / "helpers",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    # Build the final settings-hooks.json structure
    hooks_config: dict[str, list] = {}

    for event, matcher_groups in events.items():
        hooks_config[event] = []
        for matcher_key, handlers in matcher_groups.items():
            entry: dict = {"hooks": handlers}
            if matcher_key != "__no_matcher__":
                entry["matcher"] = matcher_key
            hooks_config[event].append(entry)

    return {"hooks": hooks_config}


def compile_agents(spec: dict, dist_dir: Path, repo_root: Path) -> None:
    """Copy agent definitions to dist/agents/."""
    agents = spec.get("agents", {})
    agents_dir = dist_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    for agent_name, agent_def in agents.items():
        source = agent_def.get("source")
        if source:
            src_path = repo_root / source
            if src_path.exists():
                shutil.copy2(src_path, agents_dir / src_path.name)
            else:
                print(f"WARNING: Agent source not found: {src_path}", file=sys.stderr)
                # Generate a minimal agent definition
                generate_agent_md(agent_def, agent_name, agents_dir)
        else:
            generate_agent_md(agent_def, agent_name, agents_dir)


def generate_agent_md(agent_def: dict, agent_name: str, agents_dir: Path) -> None:
    """Generate an agent .md file from the DSL definition."""
    name = agent_def.get("name", agent_name)
    description = agent_def.get("description", "")
    tools = agent_def.get("tools", [])
    constraints = agent_def.get("constraints", [])

    content = f"""---
name: {agent_name}
description: {description.strip()}
tools: [{', '.join(tools)}]
---

# {name}

{description.strip()}
"""

    if constraints:
        content += "\n## Constraints\n\n"
        for c in constraints:
            content += f"- {c}\n"

    out_path = agents_dir / f"{agent_name}.md"
    out_path.write_text(content, encoding="utf-8")


def compile_skills(dist_dir: Path, repo_root: Path) -> None:
    """Compile skill definitions to dist/skills/.

    All skills are hand-authored under repo_root/skills/<name>/. Each skill
    directory is copied to dist/skills/<name>/ recursively, so templates and
    other support files ride along with SKILL.md.
    """
    skills_dir = dist_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    # All skills are hand-authored in repo_root/skills/.
    # DSL skill declarations are metadata only (description, flow) — not templates.
    # The compiler passes through the hand-authored SKILL.md files as-is.
    hand_authored_dir = repo_root / "skills"
    if hand_authored_dir.is_dir():
        for skill_path in hand_authored_dir.iterdir():
            if skill_path.is_dir() and (skill_path / "SKILL.md").exists():
                dst = skills_dir / skill_path.name
                shutil.copytree(skill_path, dst, dirs_exist_ok=True)


def _disk_skill_names(repo_root: Path) -> set[str]:
    """Names of on-disk skill dirs (those holding a SKILL.md)."""
    skills_src = repo_root / "skills"
    if not skills_src.is_dir():
        return set()
    return {
        d.name
        for d in skills_src.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    }


def _disk_agent_names(repo_root: Path) -> set[str]:
    """Stems of on-disk agent .md files."""
    agents_src = repo_root / "agents"
    if not agents_src.is_dir():
        return set()
    return {p.stem for p in agents_src.glob("*.md")}


def _declared_agent_stems(spec: dict) -> set[str]:
    """Agent stems the spec declares (derived from each agent's source path)."""
    stems: set[str] = set()
    for agent_name, agent_def in spec.get("agents", {}).items():
        source = agent_def.get("source")
        stems.add(Path(source).stem if source else agent_name)
    return stems


def check_disk_parity(spec: dict, repo_root: Path) -> list[str]:
    """Return parity violations between the spec registry and on-disk surface.

    Enforces three rules so the spec stays the honest single source of truth:
      (a) every on-disk skill dir must be declared in `skills:`;
      (b) every on-disk agent .md must be declared in `agents:` or parked in
          the `unregistered_agents:` allowlist;
      (c) anything declared (skill or agent) must exist on disk.
    """
    declared_skills = set(spec.get("skills", {}).keys())
    disk_skills = _disk_skill_names(repo_root)
    allowed_agents = set(spec.get("unregistered_agents", {}).keys())
    declared_agents = _declared_agent_stems(spec)
    disk_agents = _disk_agent_names(repo_root)

    violations: list[str] = []
    for name in sorted(disk_skills - declared_skills):
        violations.append(f"undeclared skill on disk: skills/{name}/ (add it to skills:)")
    for name in sorted(declared_skills - disk_skills):
        violations.append(f"declared skill missing on disk: skills/{name}/ (declared but no dir)")
    for name in sorted(disk_agents - declared_agents - allowed_agents):
        violations.append(
            f"undeclared agent on disk: agents/{name}.md "
            f"(add it to agents: or list it under unregistered_agents:)"
        )
    for name in sorted(declared_agents - disk_agents):
        violations.append(
            f"declared agent missing on disk: agents/{name}.md (declared but no file)"
        )
    return violations


def enforce_disk_parity(spec: dict, repo_root: Path) -> None:
    """Fail the compile (exit 1) if the registry and disk have drifted."""
    violations = check_disk_parity(spec, repo_root)
    if violations:
        print("ERROR: declared-vs-disk parity check failed:", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        sys.exit(1)


def generate_implement_skill(skill_def: dict, skills_dir: Path, spec: dict) -> None:
    """Generate the /implement skill — the primary user-facing entry point."""
    defaults = spec.get("defaults", {})
    coverage = defaults.get("coverage_threshold", 98)

    content = f"""---
name: implement
description: {skill_def.get('description', 'Spec-based implementation workflow').strip()}
---

# /implement — Spec-Based Implementation

You are the orchestrator for a disciplined engineering team. Your job is to take
a specification or PRD, validate it, decompose it into tasks, dispatch those tasks
to subagents, and deliver verified, tested, production-ready code.

You NEVER write code yourself. You delegate to specialized agents.

## Usage

```
/implement <path-to-spec-or-prd>
/implement spec/prd-authentication.md
```

## Workflow

### Step 1: Validate the Specification

Read the spec file provided by the user. Evaluate whether it meets the Definition
of Ready:

- [ ] Has specific, measurable acceptance criteria
- [ ] Names concrete entities, endpoints, modules, or components
- [ ] Defines scope boundaries (what's IN and what's NOT)
- [ ] Does not require unstated domain knowledge
- [ ] Is detailed enough for a developer to implement without guessing

**If the spec does NOT meet Definition of Ready:** STOP IMMEDIATELY. Tell the user
exactly what's missing. Do not proceed until the spec is adequate.

```
"This spec needs work before I can implement it. Missing:
- [specific gap 1]
- [specific gap 2]
Please refine the spec and try again."
```

### Step 2: Decompose into Tasks

Parse the validated spec into a task graph. For each task, create a YAML file
in `.etc_sdlc/tasks/` with this structure:

```yaml
task_id: "NNN"
title: "Clear, actionable task title"
assigned_agent: backend-developer  # or frontend-developer, devops-engineer, etc.
status: pending
requires_reading:
  - path/to/relevant/spec.md
  - path/to/existing/code.py
files_in_scope:
  - src/module/file.py
  - tests/test_module_file.py
acceptance_criteria:
  - "Specific, measurable criterion 1"
  - "Specific, measurable criterion 2"
dependencies: []  # task IDs that must complete first
context: |
  Additional context from the PRD relevant to this task.
```

**Rules for decomposition:**
- Each task must be implementable by a single agent in a single session
- Tasks with overlapping `files_in_scope` MUST be serialized (not parallel)
- Every task must have at least one acceptance criterion
- Test files must be included in `files_in_scope`
- `requires_reading` must include the spec and any existing code being modified

Create the `.etc_sdlc/tasks/` directory if it doesn't exist.

### Step 3: Dispatch to Subagents

For each task, respecting dependency order:

1. Update the task file: `status: in_progress`
2. Spawn a subagent with the appropriate `assigned_agent` type
3. The subagent receives:
   - The task file as its primary instruction
   - Engineering standards via the SubagentStart hook
   - Project invariants and context
4. The subagent's work is gated by:
   - `check-required-reading.sh` — must read requires_reading files first
   - `check-test-exists.sh` — must write tests before implementation
   - `check-invariants.sh` — must not violate project invariants
5. On subagent completion, update task file: `status: completed`

**Parallelization rule:** Before dispatching parallel tasks, verify their
`files_in_scope` lists do not overlap. If any two tasks share a file, they
MUST run sequentially. File-set isolation, not branch isolation.

**Escalation:** If a subagent fails and cannot self-correct (the hook escalates
with `continue: false`), mark the task `status: escalated` and report the
failure to the user. Do not retry indefinitely.

### Step 4: Verify and Report

After all tasks complete:

1. Run the full CI pipeline (tests, types, lint, invariants)
2. Verify all acceptance criteria from the original spec
3. Report to the user:

```
## Implementation Complete

**Spec:** [spec file path]
**Tasks:** N completed, M total

### What Was Built
- [summary of each task's deliverable]

### Test Coverage
- Coverage: NN% (threshold: {coverage}%)

### Verification
- [ ] All tests pass
- [ ] Type checking clean
- [ ] Lint clean
- [ ] Invariants hold

### Deferred Items
- [anything that was out of scope or requires follow-up]
```

## Constraints

- You NEVER write code — you delegate to specialized agents
- You NEVER skip the spec validation step — reject inadequate specs immediately
- You NEVER dispatch parallel tasks with overlapping file scopes
- You ALWAYS create task files before dispatching work
- You ALWAYS report results to the user, including failures
- If anything fails loudly (hook escalation), surface it to the user immediately
"""

    skill_dir = skills_dir / "implement"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def generate_generic_skill(skill_def: dict[str, Any], skill_name: str, skills_dir: Path) -> None:
    """Generate a generic skill .md file."""
    content = f"""---
name: {skill_name}
description: {skill_def.get('description', '').strip()}
---

# /{skill_name}

{skill_def.get('description', '').strip()}
"""
    skill_dir = skills_dir / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def compile_standards(spec: dict, dist_dir: Path, repo_root: Path) -> None:
    """Copy engineering standards to dist/standards/."""
    standards = spec.get("standards", {})
    source_dir = repo_root / standards.get("source_dir", "standards")
    dist_standards = dist_dir / "standards"

    if source_dir.exists():
        if dist_standards.exists():
            shutil.rmtree(dist_standards)
        shutil.copytree(source_dir, dist_standards)
    else:
        print(f"WARNING: Standards source not found: {source_dir}", file=sys.stderr)


def compile_sdlc_tracker(spec: dict, dist_dir: Path, repo_root: Path) -> None:
    """Compile SDLC phase definitions into tracker templates."""
    phases = spec.get("phases", {})
    sdlc_dir = dist_dir / "sdlc"
    sdlc_dir.mkdir(parents=True, exist_ok=True)

    # Copy existing tracker
    tracker_src = repo_root / ".sdlc" / "tracker.py"
    if tracker_src.exists():
        shutil.copy2(tracker_src, sdlc_dir / "tracker.py")
        (sdlc_dir / "tracker.py").chmod(0o755)

    # Generate DoD templates from the spec
    dod_templates = {}
    for phase_name, phase_def in phases.items():
        dod_items = phase_def.get("definition_of_done", [])
        dod_templates[phase_name] = {
            "description": phase_def.get("description", ""),
            "team": phase_def.get("team", []),
            "watchdogs": phase_def.get("watchdogs", []),
            "dod": [{"item": item, "done": False} for item in dod_items],
        }

    with open(sdlc_dir / "dod-templates.json", "w", encoding="utf-8") as f:
        json.dump(dod_templates, f, indent=2)
        f.write("\n")


def compile_templates(dist_dir: Path, repo_root: Path) -> None:
    """Copy artifact templates to dist/templates/."""
    templates_src = repo_root / "templates"
    templates_dst = dist_dir / "templates"

    if templates_src.exists():
        templates_dst.mkdir(parents=True, exist_ok=True)
        for tmpl in templates_src.iterdir():
            if tmpl.is_file() and tmpl.suffix == ".tmpl":
                shutil.copy2(tmpl, templates_dst / tmpl.name)


def compile_git_hooks(dist_dir: Path, repo_root: Path) -> None:
    """Copy git hook templates."""
    git_hooks_src = repo_root / "hooks" / "git"
    git_hooks_dst = dist_dir / "hooks" / "git"

    if git_hooks_src.exists():
        git_hooks_dst.mkdir(parents=True, exist_ok=True)
        for hook_file in git_hooks_src.iterdir():
            if hook_file.is_file():
                shutil.copy2(hook_file, git_hooks_dst / hook_file.name)
                (git_hooks_dst / hook_file.name).chmod(0o755)


def compile_dispatcher_hooks(dist_dir: Path, repo_root: Path) -> None:
    """Mirror top-level dispatcher hooks (and helpers/) into dist/hooks/.

    compile_gates only copies gate-referenced ``script:`` entries; dispatcher
    hooks invoked from SKILL prose (e.g. hooks/verify-green.sh, the F020
    profile-aware test dispatcher) are not registered as gates and were being
    silently dropped from dist/. This mirrors EVERY repo_root/hooks/*.sh into
    dist_dir/hooks/ with 0o755, then recursively copies repo_root/hooks/helpers/
    (.py modules, no exec bit). hooks/git/ is excluded — compile_git_hooks owns
    it. Idempotent and graceful when hooks/ is absent.
    """
    hooks_src = repo_root / "hooks"
    if not hooks_src.is_dir():
        return

    hooks_dst = dist_dir / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)

    for script in sorted(hooks_src.glob("*.sh")):
        dst_script = hooks_dst / script.name
        shutil.copy2(script, dst_script)
        dst_script.chmod(0o755)

    helpers_src = hooks_src / "helpers"
    if helpers_src.is_dir():
        helpers_dst = hooks_dst / "helpers"
        shutil.copytree(
            helpers_src,
            helpers_dst,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )


def compile_scripts(dist_dir: Path, repo_root: Path) -> None:
    """Copy utility scripts."""
    scripts_src = repo_root / "scripts"
    scripts_dst = dist_dir / "scripts"

    if scripts_src.exists():
        scripts_dst.mkdir(parents=True, exist_ok=True)
        for script in scripts_src.iterdir():
            if script.is_file():
                shutil.copy2(script, scripts_dst / script.name)
                (scripts_dst / script.name).chmod(0o755)


def _compile_lock(repo_root: Path) -> contextlib.AbstractContextManager[Any]:
    """Serialize concurrent compiles so parallel invocations don't race.

    reset_output_dir() rmtree+rebuilds the shared output tree, so two compiles
    running at once (xdist test workers, CI) can have one rmtree while another
    writes — a non-atomic-reset race that surfaces as a spurious non-zero exit.
    This lock serializes them. Best-effort: when filelock is unavailable (a
    minimal installer env) compile proceeds unlocked, since install-time
    compiles are single-invocation and never race. The lock lives in the system
    temp dir (keyed by repo path) so it survives the dist/ rmtree and never
    pollutes the repo tree.
    """
    if FileLock is None:
        return contextlib.nullcontext()
    key = hashlib.sha1(str(repo_root).encode("utf-8")).hexdigest()[:12]
    lock_path = Path(tempfile.gettempdir()) / f"etc-compile-sdlc-{key}.lock"
    return FileLock(str(lock_path))


def _clear_dir_contents(directory: Path) -> None:
    """Remove every child of ``directory`` without removing the dir itself."""
    for child in directory.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def reset_output_dir(output_dir: Path) -> None:
    """Create a clean compiler output directory.

    Normally removes and recreates ``output_dir``. When ``output_dir`` is a
    bind-mount, the mountpoint itself cannot be unlinked — ``shutil.rmtree``
    raises ``OSError`` (errno EBUSY/16, "Device or resource busy") on the
    final ``rmdir``. In that case we clear the directory's CONTENTS in place
    so the mountpoint survives and the compile still gets a clean tree (#62).
    """
    if not output_dir.exists():
        output_dir.mkdir(parents=True)
        return
    try:
        shutil.rmtree(output_dir)
    except OSError:
        # output_dir itself can't be removed (e.g. a bind-mount point).
        # rmtree clears children before failing on the mountpoint rmdir;
        # clear any stragglers in place and keep the existing directory.
        _clear_dir_contents(output_dir)
        return
    output_dir.mkdir(parents=True)


def apply_codex_replacements(text: str) -> str:
    """Rewrite Claude install-root references for Codex artifacts."""
    replacements = (
        ("~/.claude/scripts/", ".codex/scripts/"),
        ("~/.claude/scripts", ".codex/scripts"),
        ("~/.codex/scripts/", ".codex/scripts/"),
        ("~/.codex/scripts", ".codex/scripts"),
        ("~/.Codex/scripts/", ".codex/scripts/"),
        ("~/.Codex/scripts", ".codex/scripts"),
        ("AskUserQuestion's automatic escape hatch", "request_user_input's free-form option"),
        ("AskUserQuestion's automatic Other", "request_user_input's free-form option"),
        ("AskUserQuestion tool", "request_user_input tool"),
        ("AskUserQuestion invocations", "request_user_input invocations"),
        ("AskUserQuestion invocation", "request_user_input invocation"),
        ("AskUserQuestion call shapes", "request_user_input call shapes"),
        ("AskUserQuestion calls", "request_user_input calls"),
        ("AskUserQuestion call", "request_user_input call"),
        ("AskUserQuestion below", "request_user_input prompt below"),
        ("AskUserQuestion(", "request_user_input("),
        ("AskUserQuestion", "request_user_input"),
        ("Agent({", "spawn_agent({"),
        ("Task({", "spawn_agent({"),
        ("Agent(", "spawn_agent("),
        ("Task(", "spawn_agent("),
        ("Agent-tool", "subagent-dispatch"),
        ("Agent tool", "Codex subagent dispatch tool"),
        ("Task tool", "Codex subagent dispatch tool"),
        ("subagent_type", "agent_type"),
        ("Anthropic's `/goal` feature", "Codex goal-tracking tools"),
        ("Claude Code's evaluator", "the Codex goal evaluator"),
        ("Haiku evaluator", "goal evaluator"),
        ("`/goal <condition>`", "`create_goal(objective=<condition>)`"),
        (
            "`/goal --clear`",
            "`update_goal(status=complete)` when the objective is satisfied",
        ),
        ("`/goal` feature", "Codex goal-tracking tools"),
        ("`/goal` is unavailable", "Codex goal tooling is unavailable"),
        ("/goal evaluator", "Codex goal evaluator"),
        ("~/.claude", "~/.codex"),
        (".claude/", ".codex/"),
    )
    rewritten = text
    for source, target in replacements:
        rewritten = rewritten.replace(source, target)
    rewritten = re.sub(
        r"the helpers are installed under\s+`\.codex/scripts/`, not the user's project",
        "the helpers are installed under project-local `.codex/scripts/`",
        rewritten,
    )
    rewritten = re.sub(
        r"helpers live at\s+`\.codex/scripts/`, not the user's\s+project",
        "helpers live under project-local `.codex/scripts/`",
        rewritten,
    )
    rewritten = re.sub(
        r"the helper lives at\s+`\.codex/scripts/`, not the user's\s+project",
        "the helper lives under project-local `.codex/scripts/`",
        rewritten,
    )
    rewritten = re.sub(
        r"helpers live at\s+`\.codex/scripts/`, not in",
        "helpers live under project-local `.codex/scripts/`, not in",
        rewritten,
    )
    rewritten = rewritten.replace("an request_user_input", "a request_user_input")
    return rewritten


def copy_codex_path(src_path: Path, dst_path: Path) -> None:
    """Copy a file or tree while rewriting client-specific text references."""
    if is_generated_cache_path(src_path):
        return

    if src_path.is_dir():
        for child in src_path.rglob("*"):
            if is_generated_cache_path(child):
                continue
            target = dst_path / child.relative_to(src_path)
            if child.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                copy_codex_path(child, target)
        return

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        content = src_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        shutil.copy2(src_path, dst_path)
    else:
        rewritten = apply_codex_replacements(content)
        dst_path.write_text(rewritten, encoding="utf-8")
        shutil.copystat(src_path, dst_path)


def is_generated_cache_path(path: Path) -> bool:
    """Return true for local interpreter cache files that must not ship."""
    return "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}


def compile_codex_gates(
    spec: dict,
    dist_dir: Path,
    repo_root: Path,
) -> tuple[dict, dict]:
    """Compile Codex command hooks and classify every YAML gate."""
    gates = spec.get("gates", {})
    hooks_dir = dist_dir / ".codex" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    events: dict[str, dict[str, list[dict[str, Any]]]] = {}
    classifications: dict[str, dict[str, Any]] = {}

    for gate_name, gate in gates.items():
        classification = classify_codex_gate(gate_name, gate)
        classifications[gate_name] = classification

        if not classification["active_hook"]:
            continue

        handler = codex_command_handler(gate, hooks_dir, repo_root)
        event = gate["event"]
        matcher_key = gate.get("matcher", "") or "__no_matcher__"
        events.setdefault(event, {}).setdefault(matcher_key, []).append(handler)

    helpers_src = repo_root / "hooks" / "helpers"
    if helpers_src.exists():
        copy_codex_path(helpers_src, hooks_dir / "helpers")

    hooks_config: dict[str, list[dict[str, Any]]] = {}
    for event, matcher_groups in events.items():
        hooks_config[event] = []
        for matcher_key, handlers in matcher_groups.items():
            entry: dict[str, Any] = {"hooks": handlers}
            if matcher_key != "__no_matcher__":
                entry["matcher"] = matcher_key
            hooks_config[event].append(entry)

    classification_config = {
        "client": "codex",
        "gates": classifications,
    }
    return {"hooks": hooks_config}, classification_config


def classify_codex_gate(gate_name: str, gate: dict[str, Any]) -> dict[str, Any]:
    """Classify one YAML gate for Codex result parity."""
    event = gate["event"]
    gate_type = gate["type"]

    if gate_name == "concept-check":
        bucket = "stop-ci-verification"
        active_hook = False
    elif event in CODEX_RESULT_PARITY_BUCKETS:
        bucket = CODEX_RESULT_PARITY_BUCKETS[event]
        active_hook = False
    elif gate_type == "command" and event in CODEX_COMMAND_EVENTS:
        bucket = "command-hook"
        active_hook = True
    elif gate_type in ("prompt", "agent"):
        bucket = f"{gate_type}-artifact-workflow"
        active_hook = False
    else:
        bucket = "unsupported-command-workaround"
        active_hook = False

    return {
        "event": event,
        "type": gate_type,
        "matcher": gate.get("matcher", ""),
        "codex_bucket": bucket,
        "active_hook": active_hook,
        "result_parity": codex_result_parity(gate_name, bucket),
    }


def codex_result_parity(gate_name: str, bucket: str) -> str:
    """Return concise operator-facing classification detail."""
    parity = {
        "task-readiness": "Skill workflow writes and validates readiness.json.",
        "task-completion": "Verifier subagent writes and validates completion.json.",
        "adversarial-review": "Reviewer subagent writes and validates review.json.",
        "change-control": "Edit/Bash guards and CI diff validation replace ConfigChange.",
        "concept-check": "Completion and CI validation replace PostToolUse Task lifecycle.",
    }
    return parity.get(gate_name, f"Mapped to Codex {bucket}.")


def codex_command_handler(
    gate: dict[str, Any],
    hooks_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Build one Codex command hook handler and copy its script."""
    script_name = gate["script"]
    src_script = repo_root / "hooks" / script_name
    dst_script = hooks_dir / script_name

    if src_script.exists():
        copy_codex_path(src_script, dst_script)
        dst_script.chmod(0o755)
    else:
        print(f"WARNING: Script not found: {src_script}", file=sys.stderr)

    handler: dict[str, Any] = {
        "type": "command",
        "command": f'bash "$(git rev-parse --show-toplevel)/.codex/hooks/{script_name}"',
    }
    timeout = gate.get("timeout")
    if timeout:
        handler["timeout"] = timeout

    description = gate.get("description", "")
    if description:
        first_sentence = description.strip().split(".")[0].strip()
        if len(first_sentence) < 80:
            handler["statusMessage"] = f"{first_sentence}..."

    return handler


def compile_codex_agents(spec: dict, dist_dir: Path, repo_root: Path) -> None:
    """Generate Codex custom-agent TOML files from YAML agent declarations."""
    agents_dir = dist_dir / ".codex" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    for agent_name, agent_def in spec.get("agents", {}).items():
        source = agent_def.get("source")
        source_text = ""
        if source:
            src_path = repo_root / source
            if src_path.exists():
                source_text = src_path.read_text(encoding="utf-8")
            else:
                print(f"WARNING: Agent source not found: {src_path}", file=sys.stderr)

        instructions = source_text or generated_agent_instructions(agent_name, agent_def)
        content = "\n".join(
            [
                f"name = {toml_string(agent_name)}",
                f"description = {toml_string(agent_def.get('description', '').strip())}",
                f"developer_instructions = {toml_string(apply_codex_replacements(instructions))}",
                "",
            ]
        )
        (agents_dir / f"{agent_name}.toml").write_text(content, encoding="utf-8")


def generated_agent_instructions(agent_name: str, agent_def: dict[str, Any]) -> str:
    """Build fallback instructions when an agent source file is unavailable."""
    constraints = "\n".join(f"- {item}" for item in agent_def.get("constraints", []))
    return f"# {agent_def.get('name', agent_name)}\n\n{agent_def.get('description', '')}\n\n{constraints}\n"


def toml_string(value: str) -> str:
    """Serialize a Python string as a TOML-compatible basic string."""
    return json.dumps(value, ensure_ascii=False)


def compile_codex_skills(dist_dir: Path, repo_root: Path) -> None:
    """Copy skills into the Codex repository-local skills layout."""
    skills_src = repo_root / "skills"
    skills_dst = dist_dir / ".agents" / "skills"
    if skills_src.exists():
        copy_codex_path(skills_src, skills_dst)


def compile_codex_standards(spec: dict, dist_dir: Path, repo_root: Path) -> None:
    """Copy standards into the Codex install surfaces.

    Generated skills cite repo-root ``standards/...`` paths. The
    ``.codex/standards`` copy remains the managed harness backing store.
    """
    standards = spec.get("standards", {})
    source_dir = repo_root / standards.get("source_dir", "standards")
    if source_dir.exists():
        copy_codex_path(source_dir, dist_dir / "standards")
        copy_codex_path(source_dir, dist_dir / ".codex" / "standards")


def compile_codex_scripts(dist_dir: Path, repo_root: Path) -> None:
    """Copy runtime scripts into the Codex install surface."""
    scripts_src = repo_root / "scripts"
    scripts_dst = dist_dir / ".codex" / "scripts"
    if not scripts_src.exists():
        return

    scripts_dst.mkdir(parents=True, exist_ok=True)
    for script in scripts_src.iterdir():
        if script.is_file():
            copy_codex_path(script, scripts_dst / script.name)
            (scripts_dst / script.name).chmod(0o755)


def compile_codex_artifact_schemas(dist_dir: Path) -> None:
    """Generate task-proof JSON schemas for Codex result parity."""
    schemas_dir = dist_dir / ".codex" / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)
    for artifact_name, required_fields in CODEX_ARTIFACT_SCHEMAS.items():
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"ETC {artifact_name} artifact",
            "type": "object",
            "required": required_fields,
            "properties": {
                field_name: {} for field_name in required_fields
            },
            "additionalProperties": True,
        }
        with open(
            schemas_dir / f"{artifact_name}.schema.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(schema, f, indent=2)
            f.write("\n")


def write_codex_agents_md(dist_dir: Path) -> None:
    """Write repository instructions for Codex installs."""
    content = """# ETC Codex Harness

Follow the ETC SDLC workflow from the generated skills in `.agents/skills`.
Use `.codex/agents` for specialized subagents and write task proof artifacts
under `.etc_sdlc/tasks/<task-id>/`.

Command hooks live under `.codex/hooks` and deterministic runtime helpers live
under `.codex/scripts`. Prompt and agent lifecycle gates are represented by
task-scoped artifacts, not active prompt hooks.
"""
    (dist_dir / "AGENTS.md").write_text(content, encoding="utf-8")


def compile_codex_source_snapshot(dist_dir: Path, repo_root: Path) -> None:
    """Copy the source needed for installed drift checks."""
    source_root = dist_dir / ".codex" / "source"
    source_root.mkdir(parents=True, exist_ok=True)

    for relative_path in CODEX_SOURCE_SNAPSHOT_PATHS:
        src_path = repo_root / relative_path
        if src_path.exists():
            copy_codex_path(src_path, source_root / relative_path)


def compile_codex_expected_snapshot(dist_dir: Path) -> None:
    """Copy compiled outputs for installed drift checks without source deps."""
    expected_root = dist_dir / ".codex" / "expected"
    expected_root.mkdir(parents=True, exist_ok=True)

    for relative_path in CODEX_EXPECTED_SNAPSHOT_PATHS:
        src_path = dist_dir / relative_path
        if src_path.exists():
            copy_codex_path(src_path, expected_root / relative_path)


def compile_codex_plugin_package(spec: dict, dist_dir: Path) -> None:
    """Generate a Codex plugin convenience bundle from compiled artifacts."""
    plugin_root = dist_dir / "plugins" / CODEX_PLUGIN_NAME
    manifest_dir = plugin_root / ".codex-plugin"
    hooks_dir = plugin_root / "hooks"

    manifest_dir.mkdir(parents=True, exist_ok=True)
    hooks_dir.mkdir(parents=True, exist_ok=True)

    write_json_file(manifest_dir / "plugin.json", codex_plugin_manifest(spec))
    copy_codex_plugin_skills(dist_dir, plugin_root)
    copy_codex_plugin_hooks(dist_dir, hooks_dir)
    write_json_file(
        plugin_root / "codex-plugin-classification.json",
        codex_plugin_classification(),
    )


def codex_plugin_manifest(spec: dict) -> dict[str, object]:
    """Build the plugin manifest for documented plugin surfaces."""
    return {
        "name": CODEX_PLUGIN_NAME,
        "version": codex_plugin_version(spec),
        "description": "ETC Codex SDLC skills and hooks convenience package.",
        "author": {
            "name": "ETC",
        },
        "license": "MIT",
        "keywords": ["codex", "sdlc", "harness"],
        "skills": "./skills/",
        "interface": {
            "displayName": "ETC SDLC",
            "shortDescription": "Codex skills and hooks for ETC SDLC workflows.",
            "longDescription": (
                "Convenience package for supported Codex plugin surfaces. "
                "Use install.sh --client codex for complete harness setup."
            ),
            "developerName": "ETC",
            "category": "Productivity",
            "capabilities": ["Write"],
            "defaultPrompt": [
                "Start an ETC spec workflow.",
                "Run ETC task readiness checks.",
                "Review ETC completion proof.",
            ],
        },
    }


def codex_plugin_version(spec: dict) -> str:
    """Return a semver-compatible plugin version derived from the SDLC spec."""
    version = str(spec.get("version", "0.1.0")).strip().removeprefix("v")
    parts = version.split(".")
    if len(parts) == 1:
        return f"{parts[0]}.0.0"
    if len(parts) == 2:
        return f"{parts[0]}.{parts[1]}.0"
    return ".".join(parts[:3])


def copy_codex_plugin_skills(dist_dir: Path, plugin_root: Path) -> None:
    """Copy compiled skills into the plugin root."""
    skills_src = dist_dir / ".agents" / "skills"
    if skills_src.exists():
        copy_codex_path(skills_src, plugin_root / "skills")


def copy_codex_plugin_hooks(dist_dir: Path, hooks_dir: Path) -> None:
    """Copy compiled hook config and scripts into the plugin root."""
    hooks_config = dist_dir / ".codex" / "hooks.json"
    hook_scripts = dist_dir / ".codex" / "hooks"

    if hooks_config.exists():
        copy_codex_path(hooks_config, hooks_dir / "hooks.json")
    if hook_scripts.exists():
        copy_codex_path(hook_scripts, hooks_dir)


def codex_plugin_classification() -> dict[str, object]:
    """Describe what the plugin bundle does and does not own."""
    return {
        "schema_version": 1,
        "plugin_name": CODEX_PLUGIN_NAME,
        "installer_authoritative": True,
        "bundled_surfaces": list(CODEX_PLUGIN_BUNDLED_SURFACES),
        "installer_owned_surfaces": list(CODEX_PLUGIN_INSTALLER_OWNED_SURFACES),
        "custom_agents_bundled": False,
        "reason": (
            "Custom agents remain installer-owned because this plugin bundle is "
            "limited to Codex plugin surfaces verified for convenience packaging."
        ),
    }


def write_json_file(path: Path, payload: dict[str, object]) -> None:
    """Write a stable JSON object."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def validate_concepts(repo_root: Path) -> int:
    """Validate CONCEPT entries in INVARIANTS.md files.

    Checks that every CONCEPT-NNN entry has the required fields:
    - Contexts (required for cross-boundary concepts)
    - Precondition, Postcondition, Invariant (DbC fields)
    - Verify (with a non-empty command)
    - Fail action

    Returns the number of validation errors found.
    """
    import re

    errors = 0
    invariant_files = list(repo_root.rglob("INVARIANTS.md"))

    for inv_file in invariant_files:
        text = inv_file.read_text(encoding="utf-8")
        # Find all CONCEPT entries
        concept_pattern = re.compile(
            r"^##\s+(CONCEPT-\d+):\s*(.+)$", re.MULTILINE
        )

        for match in concept_pattern.finditer(text):
            concept_id = match.group(1)
            # Extract the section text (from this heading to the next ## heading)
            start = match.end()
            next_heading = re.search(r"^##\s+", text[start:], re.MULTILINE)
            section = text[start : start + next_heading.start()] if next_heading else text[start:]

            rel_path = inv_file.relative_to(repo_root)

            # Check required fields
            required_fields = {
                "Contexts": r"\*\*Contexts:\*\*",
                "Precondition": r"\*\*Precondition:\*\*",
                "Postcondition": r"\*\*Postcondition:\*\*",
                "Invariant": r"\*\*Invariant:\*\*",
                "Verify": r"\*\*Verify:\*\*\s*`[^`]+`",
                "Fail action": r"\*\*Fail action:\*\*",
            }

            for field_name, pattern in required_fields.items():
                if not re.search(pattern, section):
                    print(
                        f"ERROR: {rel_path}: {concept_id} missing required "
                        f"field: {field_name}",
                        file=sys.stderr,
                    )
                    errors += 1

    return errors


def audit_enforcement(repo_root: Path) -> int:
    """Audit enforcement annotations against the ruff reference config.

    Scans all .md files in standards/code/ and standards/testing/,
    extracts Enforce: annotations, and cross-references ruff rule
    codes against the reference config's select list.

    Returns exit code: 0 = clean, 1 = errors found.
    """
    import re
    import tomllib

    standards_dirs = [
        repo_root / "standards" / "code",
        repo_root / "standards" / "testing",
    ]

    # Parse the ruff reference config
    ruff_toml_path = repo_root / "standards" / "code" / "ruff-reference.toml"
    if not ruff_toml_path.exists():
        print("ERROR: standards/code/ruff-reference.toml not found", file=sys.stderr)
        return 1

    with open(ruff_toml_path, "rb") as f:
        ruff_config = tomllib.load(f)

    select_list = ruff_config.get("tool", {}).get("ruff", {}).get("lint", {}).get("select", [])
    if not select_list:
        print("ERROR: No select list found in ruff-reference.toml", file=sys.stderr)
        return 1

    # Expand rule set prefixes to a set for matching
    # Each prefix (e.g., "N") matches any rule starting with that prefix
    rule_prefixes = set(select_list)

    def rule_is_covered(rule_code: str) -> bool:
        """Check if a specific rule code is covered by the select list."""
        for prefix in rule_prefixes:
            if rule_code == prefix or rule_code.startswith(prefix):
                return True
        return False

    # Scan standards docs for Enforce: annotations
    enforce_pattern = re.compile(r"\*\*Enforce:\*\*\s*(.+?)$", re.MULTILINE)
    ruff_rule_pattern = re.compile(r"ruff\(([^)]+)\)")

    errors = 0
    warnings = 0
    ruff_count = 0
    hook_count = 0
    none_count = 0
    total_rules = 0
    referenced_rules: set[str] = set()
    docs_with_annotations: set[str] = set()
    all_md_files: list[Path] = []

    for standards_dir in standards_dirs:
        if not standards_dir.exists():
            continue
        for md_file in sorted(standards_dir.glob("*.md")):
            all_md_files.append(md_file)
            content = md_file.read_text(encoding="utf-8")
            file_has_annotation = False

            for match in enforce_pattern.finditer(content):
                annotation = match.group(1).strip()
                total_rules += 1
                file_has_annotation = True

                # Extract ruff rules
                ruff_match = ruff_rule_pattern.search(annotation)
                if ruff_match:
                    rules_str = ruff_match.group(1)
                    rules = [r.strip() for r in rules_str.split(",")]
                    for rule in rules:
                        referenced_rules.add(rule)
                        if not rule_is_covered(rule):
                            print(
                                f"ERROR: {md_file.relative_to(repo_root)}: "
                                f"ruff({rule}) not in ruff-reference.toml select list",
                                file=sys.stderr,
                            )
                            errors += 1
                        else:
                            ruff_count += 1

                elif "hook(" in annotation:
                    hook_count += 1
                elif annotation.startswith("none"):
                    none_count += 1

            if file_has_annotation:
                docs_with_annotations.add(str(md_file.relative_to(repo_root)))

    # Warn about docs with no annotations (exclude ruff-audit.md itself)
    for md_file in all_md_files:
        rel = str(md_file.relative_to(repo_root))
        if rel not in docs_with_annotations and "ruff-audit" not in rel:
            print(f"WARNING: {rel} has no Enforce: annotations", file=sys.stderr)
            warnings += 1

    # Warn about rule prefixes in config not referenced by any standard
    for prefix in rule_prefixes:
        found = False
        for rule in referenced_rules:
            if rule == prefix or rule.startswith(prefix):
                found = True
                break
        if not found:
            print(
                f"WARNING: Rule set '{prefix}' in ruff-reference.toml "
                f"not referenced by any standard",
                file=sys.stderr,
            )
            warnings += 1

    # Summary
    print()
    print("Enforcement Audit Summary")
    print("=" * 40)
    print(f"  Rules enforced by ruff:  {ruff_count}")
    print(f"  Rules enforced by hook:  {hook_count}")
    print(f"  Rules guidance-only:     {none_count}")
    print(f"  Total annotated rules:   {total_rules}")
    print(f"  Errors:                  {errors}")
    print(f"  Warnings:                {warnings}")
    print()

    if errors > 0:
        print(f"FAILED: {errors} enforcement error(s) found.", file=sys.stderr)
        return 1

    print("PASSED: All ruff annotations reference rules in the reference config.")
    return 0


def compile_claude_target(spec: dict, dist_dir: Path, repo_root: Path) -> None:
    """Compile the existing Claude artifact tree."""
    reset_output_dir(dist_dir)

    print(f"Output directory: {dist_dir}")
    print()
    print(f"  Spec version: {spec['version']}")

    print("  Checking declared-vs-disk parity...")
    enforce_disk_parity(spec, repo_root)

    print("  Compiling gates → settings-hooks.json + hook scripts...")
    hooks_config = compile_gates(spec, dist_dir, repo_root)
    with open(dist_dir / "settings-hooks.json", "w", encoding="utf-8") as f:
        json.dump(hooks_config, f, indent=2)
        f.write("\n")

    gate_count = sum(len(g) for g in hooks_config.get("hooks", {}).values())
    print(f"    {len(spec.get('gates', {}))} gates → {gate_count} hook entries")

    print("  Mirroring dispatcher hooks → dist/hooks/...")
    compile_dispatcher_hooks(dist_dir, repo_root)
    dispatcher_count = len(list((dist_dir / "hooks").glob("*.sh")))
    helper_count = (
        len(list((dist_dir / "hooks" / "helpers").glob("*.py")))
        if (dist_dir / "hooks" / "helpers").exists()
        else 0
    )
    print(f"    {dispatcher_count} hook scripts, {helper_count} helpers")

    print("  Compiling agents → dist/agents/...")
    compile_agents(spec, dist_dir, repo_root)
    agent_count = len(list((dist_dir / "agents").glob("*.md")))
    print(f"    {agent_count} agent definitions")

    print("  Compiling skills → dist/skills/...")
    compile_skills(dist_dir, repo_root)
    skill_count = len([
        d
        for d in (dist_dir / "skills").iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    ])
    print(f"    {skill_count} skill definitions")

    print("  Copying standards → dist/standards/...")
    compile_standards(spec, dist_dir, repo_root)
    standards_count = count_markdown_files(dist_dir / "standards")
    print(f"    {standards_count} standard documents")

    print("  Compiling SDLC phases → dist/sdlc/...")
    compile_sdlc_tracker(spec, dist_dir, repo_root)
    phase_count = len(spec.get("phases", {}))
    print(f"    {phase_count} phases with DoD templates")

    print("  Copying templates → dist/templates/...")
    compile_templates(dist_dir, repo_root)
    tmpl_count = len(list((dist_dir / "templates").glob("*.tmpl"))) if (
        dist_dir / "templates"
    ).exists() else 0
    print(f"    {tmpl_count} templates")

    print("  Copying git hooks → dist/hooks/git/...")
    compile_git_hooks(dist_dir, repo_root)

    print("  Copying scripts → dist/scripts/...")
    compile_scripts(dist_dir, repo_root)

    validate_concept_entries(repo_root)

    print()
    print("Compilation complete.")
    print()
    print("  dist/")
    print(f"  ├── settings-hooks.json    ({len(spec.get('gates', {}))} gates)")
    print(f"  ├── hooks/                 ({len(list((dist_dir / 'hooks').glob('*.sh')))} scripts, {helper_count} helpers)")
    print(f"  ├── agents/                ({agent_count} definitions)")
    print(f"  ├── skills/                ({skill_count} definitions)")
    print(f"  ├── standards/             ({standards_count} documents)")
    print(f"  └── sdlc/                  ({phase_count} phase templates)")
    print()
    print("Next: ./install.sh to deploy the harness.")


def compile_codex_target(spec: dict, dist_dir: Path, repo_root: Path) -> None:
    """Compile a Codex-native artifact tree."""
    reset_output_dir(dist_dir)

    print(f"Output directory: {dist_dir}")
    print()
    print(f"  Spec version: {spec['version']}")

    print("  Checking declared-vs-disk parity...")
    enforce_disk_parity(spec, repo_root)

    print("  Compiling Codex gates → .codex/hooks.json + classification...")
    hooks_config, classifications = compile_codex_gates(spec, dist_dir, repo_root)
    codex_dir = dist_dir / ".codex"
    with open(codex_dir / "hooks.json", "w", encoding="utf-8") as f:
        json.dump(hooks_config, f, indent=2)
        f.write("\n")
    with open(dist_dir / "gate-classification.json", "w", encoding="utf-8") as f:
        json.dump(classifications, f, indent=2)
        f.write("\n")
    active_count = len(_all_codex_hook_handlers(hooks_config))
    print(f"    {len(spec.get('gates', {}))} gates classified, {active_count} active hooks")

    print("  Compiling Codex agents → .codex/agents/...")
    compile_codex_agents(spec, dist_dir, repo_root)
    agent_count = len(list((codex_dir / "agents").glob("*.toml")))
    print(f"    {agent_count} custom-agent definitions")

    print("  Compiling Codex skills → .agents/skills/...")
    compile_codex_skills(dist_dir, repo_root)
    skill_count = len([
        d
        for d in (dist_dir / ".agents" / "skills").iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    ])
    print(f"    {skill_count} skill definitions")

    print("  Copying Codex standards, scripts, and schemas...")
    compile_codex_standards(spec, dist_dir, repo_root)
    compile_codex_scripts(dist_dir, repo_root)
    compile_codex_artifact_schemas(dist_dir)
    write_codex_agents_md(dist_dir)
    compile_codex_expected_snapshot(dist_dir)
    compile_codex_source_snapshot(dist_dir, repo_root)
    compile_codex_plugin_package(spec, dist_dir)

    print()
    print("Codex compilation complete.")
    print()
    print("  codex/")
    print("  ├── AGENTS.md")
    print(f"  ├── .codex/hooks.json      ({active_count} active hooks)")
    print(f"  ├── .codex/agents/         ({agent_count} definitions)")
    print(f"  ├── .agents/skills/        ({skill_count} definitions)")
    print("  ├── standards/             (repo-root compatibility surface)")
    print(f"  ├── gate-classification.json ({len(spec.get('gates', {}))} gates)")
    print(f"  └── plugins/{CODEX_PLUGIN_NAME}/")
    print()
    print("Next: ./install.sh --client codex to deploy the harness.")


def validate_concept_entries(repo_root: Path) -> None:
    """Validate CONCEPT entries and exit consistently with the legacy compiler."""
    print("  Validating CONCEPT entries in INVARIANTS.md files...")
    concept_errors = validate_concepts(repo_root)
    if concept_errors > 0:
        print(f"    {concept_errors} CONCEPT validation error(s) found", file=sys.stderr)
        sys.exit(1)

    concept_count = count_concept_entries(repo_root)
    print(f"    {concept_count} CONCEPT entries validated")


def count_concept_entries(repo_root: Path) -> int:
    """Count concept entries in invariant files."""
    import re

    concept_count = 0
    for inv_file in repo_root.rglob("INVARIANTS.md"):
        concept_count += len(
            re.findall(
                r"^##\s+CONCEPT-\d+:",
                inv_file.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        )
    return concept_count


def count_markdown_files(path: Path) -> int:
    """Count Markdown files under a path if it exists."""
    return sum(1 for _ in path.rglob("*.md")) if path.exists() else 0


def _all_codex_hook_handlers(hooks_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten Codex hook handlers for summaries."""
    handlers: list[dict[str, Any]] = []
    for entries in hooks_config.get("hooks", {}).values():
        for entry in entries:
            handlers.extend(entry.get("hooks", []))
    return handlers


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse compiler CLI arguments."""
    parser = argparse.ArgumentParser(description="Compile ETC SDLC artifacts.")
    parser.add_argument("spec_path", nargs="?", default="spec/etc_sdlc.yaml")
    parser.add_argument(
        "--client",
        choices=("claude", "codex", "all"),
        default="claude",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit-enforcement", action="store_true")
    return parser.parse_args(argv)


def main() -> None:
    repo_root = Path(__file__).parent.resolve()
    args = parse_args(sys.argv[1:])

    if args.audit_enforcement:
        exit_code = audit_enforcement(repo_root)
        sys.exit(exit_code)

    spec = load_spec(args.spec_path)
    print(f"Compiling SDLC spec: {args.spec_path}")
    print(f"Client target: {args.client}")

    # Serialize concurrent compiles (xdist test workers / CI) — reset_output_dir
    # rmtree+rebuilds the shared dist tree and is not atomic across processes.
    with _compile_lock(repo_root):
        if args.client == "all":
            output_dir = args.output or repo_root / "dist"
            reset_output_dir(output_dir)
            compile_claude_target(spec, output_dir / "claude", repo_root)
            compile_codex_target(spec, output_dir / "codex", repo_root)
            return

        if args.client == "codex":
            output_dir = args.output or repo_root / "dist" / "codex"
            compile_codex_target(spec, output_dir, repo_root)
            return

        output_dir = args.output or repo_root / "dist"
        compile_claude_target(spec, output_dir, repo_root)


if __name__ == "__main__":
    main()
