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

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml


def load_spec(spec_path: str) -> dict:
    """Load and validate the SDLC specification."""
    with open(spec_path) as f:
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

    for _gate_name, gate in gates.items():
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

            handler["command"] = f"~/.claude/hooks/{script_name}"
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
    out_path.write_text(content)


def compile_skills(spec: dict, dist_dir: Path, repo_root: Path) -> None:
    """Compile skill definitions to dist/skills/.

    Two sources:
    1. DSL-declared skills (spec.skills) — generated from the YAML definition
    2. Hand-authored skills (repo_root/skills/**/SKILL.md) — passed through as-is
    """
    skills = spec.get("skills", {})
    skills_dir = dist_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate DSL-declared skills
    for skill_name, skill_def in skills.items():
        if skill_name == "implement":
            generate_implement_skill(skill_def, skills_dir, spec)
        else:
            generate_generic_skill(skill_def, skill_name, skills_dir)

    # 2. Pass through hand-authored skills from repo_root/skills/
    hand_authored_dir = repo_root / "skills"
    if hand_authored_dir.is_dir():
        for skill_path in hand_authored_dir.iterdir():
            if skill_path.is_dir() and (skill_path / "SKILL.md").exists():
                dst = skills_dir / skill_path.name
                if not dst.exists():  # Don't overwrite DSL-generated skills
                    dst.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(skill_path / "SKILL.md", dst / "SKILL.md")


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
    (skill_dir / "SKILL.md").write_text(content)


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
    (skill_dir / "SKILL.md").write_text(content)


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

    with open(sdlc_dir / "dod-templates.json", "w") as f:
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


def main() -> None:
    # Determine paths
    spec_path = sys.argv[1] if len(sys.argv) > 1 else "spec/etc_sdlc.yaml"
    repo_root = Path(__file__).parent.resolve()
    dist_dir = repo_root / "dist"

    # Clean dist/
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir()

    print(f"Compiling SDLC spec: {spec_path}")
    print(f"Output directory: {dist_dir}")
    print()

    # Load the spec
    spec = load_spec(spec_path)
    print(f"  Spec version: {spec['version']}")

    # Compile each section
    print("  Compiling gates → settings-hooks.json + hook scripts...")
    hooks_config = compile_gates(spec, dist_dir, repo_root)
    with open(dist_dir / "settings-hooks.json", "w") as f:
        json.dump(hooks_config, f, indent=2)
        f.write("\n")

    gate_count = sum(len(g) for g in hooks_config.get("hooks", {}).values())
    print(f"    {len(spec.get('gates', {}))} gates → {gate_count} hook entries")

    print("  Compiling agents → dist/agents/...")
    compile_agents(spec, dist_dir, repo_root)
    agent_count = len(list((dist_dir / "agents").glob("*.md")))
    print(f"    {agent_count} agent definitions")

    print("  Compiling skills ��� dist/skills/...")
    compile_skills(spec, dist_dir, repo_root)
    skill_count = len([d for d in (dist_dir / "skills").iterdir() if d.is_dir() and (d / "SKILL.md").exists()])
    print(f"    {skill_count} skill definitions")

    print("  Copying standards → dist/standards/...")
    compile_standards(spec, dist_dir, repo_root)
    standards_count = sum(1 for _ in (dist_dir / "standards").rglob("*.md")) if (dist_dir / "standards").exists() else 0
    print(f"    {standards_count} standard documents")

    print("  Compiling SDLC phases → dist/sdlc/...")
    compile_sdlc_tracker(spec, dist_dir, repo_root)
    phase_count = len(spec.get("phases", {}))
    print(f"    {phase_count} phases with DoD templates")

    print("  Copying templates → dist/templates/...")
    compile_templates(dist_dir, repo_root)
    tmpl_count = len(list((dist_dir / "templates").glob("*.tmpl"))) if (dist_dir / "templates").exists() else 0
    print(f"    {tmpl_count} templates")

    print("  Copying git hooks → dist/hooks/git/...")
    compile_git_hooks(dist_dir, repo_root)

    print("  Copying scripts → dist/scripts/...")
    compile_scripts(dist_dir, repo_root)

    # Summary
    print()
    print("Compilation complete.")
    print()
    print(f"  dist/")
    print(f"  ├── settings-hooks.json    ({len(spec.get('gates', {}))} gates)")
    print(f"  ├── hooks/                 ({len(list((dist_dir / 'hooks').glob('*.sh')))} scripts)")
    print(f"  ├── agents/                ({agent_count} definitions)")
    print(f"  ├── skills/                ({skill_count} definitions)")
    print(f"  ├─��� standards/             ({standards_count} documents)")
    print(f"  └── sdlc/                  ({phase_count} phase templates)")
    print()
    print("Next: ./install.sh to deploy the harness.")


if __name__ == "__main__":
    main()
