# F022 Audit — Language Coupling in the etc Harness

**Date:** 2026-05-15
**Author:** etc internal audit
**Status:** Research artifact — informs the eventual `/spec F022` session
**Repository state at audit:** `internal/main` @ `cae8e9c`

## Why this audit exists

etc was built by a Python programmer for a Python codebase. Many of its enforcement gates, standards, agent manifests, and skill flows assume Python tooling (`pytest`, `mypy`, `ruff`, `uv`). The harness is positioned as "engineering team, codified" — but today it codifies a *Python* engineering team. Customers with TypeScript / Go / Rust / Java / Swift / Ruby / Terraform / Kubernetes / documentation surfaces get partial-to-no enforcement.

This audit inventories every Python-coupling point so the /spec session for F022 (language-agnostic redesign) can work from evidence, not from gut feel.

**Out of scope of THIS document:** the redesign itself. This is the inventory. The proposed profile architecture is sketched at the end but the binding decisions happen in /spec.

## Methodology

Three passes over the repository at `cae8e9c`:

1. Recursive grep for Python tooling markers (`pytest`, `mypy`, `ruff`, `uv run`, `pyproject.toml`, `.py` file extension) across `hooks/`, `standards/`, `agents/`, `skills/`.
2. Targeted reads of each hit to determine coupling severity.
3. Classification of each finding into one of three buckets:

| Bucket | Definition | Implication |
|---|---|---|
| **HARD** | Forces the target codebase to be Python; non-Python projects get no enforcement or get spurious failures | Must generalize for F022 to ship |
| **SOFT** | Detects Python-ness with weak fallback; non-Python projects get silently skipped | Should generalize; tolerable degradation today |
| **OUT-OF-SCOPE** | Harness internal tooling (the helpers happen to be Python); does not affect the target codebase | No change needed |

## Findings — hooks

### HARD coupling

| File | Line(s) | What it does | Why it's hard-coupled |
|---|---|---|---|
| `hooks/verify-green.sh` | 22, 33, 44 | Runs `uv run pytest --cov --cov-fail-under=98 -x --tb=short -q`, `uv run mypy src/`, `uv run ruff check src/ tests/` | Hardcoded Python toolchain. No detection. Non-Python projects: this hook either no-ops or errors. Verifier agent's BLOCKED message lists `pytest, jest, vitest` but the gate itself does not branch. |
| `hooks/check-completion-discipline.sh` | 70-105 | Runs pytest + mypy + ruff conditionally on `pyproject.toml` / `uv.lock` / `pytest.ini` presence | Detection exists but only for Python; absence of these files = no gate fires (silent skip). |
| `hooks/check-seam-evidence.sh` | 151-153 | Greps test files for `@pytest.mark.integration` markers | Hardcoded pytest marker. TS/JS uses `describe.integration`, Go uses build tags, etc. |
| `hooks/check-test-exists.sh` | 25-37 | Only enforces TDD on `*.py` files; looks for `tests/**/test_<module>.py` | Hard-skips non-Python source. TDD gate is silently off for TS/Go/Rust/etc. |
| `hooks/check-code-quality.sh` | 24-25, 54-65 | Hard-filter to `.py` files; invokes Python AST helpers (`check_mutable_globals.py`, `check_noop_functions.py`) | Silent skip on non-Python. Quality gate is effectively absent for non-Python work. |

### OUT-OF-SCOPE (mentions of Python but not coupling)

| File | Note |
|---|---|
| `hooks/block-dangerous-commands.sh` | Lists `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache` in the dirs-not-to-`rm` set. Defensive, not coupling. |
| `hooks/chief-efficiency-officer.sh` | Mentions `py-spy` / `pytest-timeout` in a help-text suggestion. Cosmetic. |
| `hooks/check-value-hypothesis-schema.sh` | Invokes harness-internal `scripts/value_hypothesis.py`. Internal tooling; OK. |

## Findings — standards

### HARD coupling (Python-named or Python-only-content)

| File | What it claims to standardize | Coupling |
|---|---|---|
| `standards/code/python-conventions.md` | "Python conventions" | Python-only by title and content |
| `standards/code/typing-standards.md` | mypy configuration + Python type system rules | mypy-specific |
| `standards/code/ruff-audit.md` | "ruff rule audit" with per-rule rationale | ruff-specific tool |
| `standards/code/ruff-reference.toml` | Reference ruff config | ruff-specific (but legitimately so — it's a CONFIG, not a STANDARD) |
| `standards/code/clean-code.md` | Function size / parameter count / complexity limits | Rules ARE language-agnostic, but each rule is anchored to a ruff rule code (PLR0915, PLR0913, C901). Other languages need different enforcers (eslint, golangci-lint, clippy) |
| `standards/code/error-handling.md` | `raise/except/try` patterns, `from e` chaining, domain exceptions | Python-vocabulary; TS uses `throw/catch`, Go uses error returns, Rust uses Result. Same SHAPE, different syntax. |
| `standards/code/import-discipline.md` | "All imports at top of file"; references E402, `__future__`, relative-vs-absolute Python imports | Python-vocabulary; concept generalizes but text doesn't |
| `standards/testing/testing-standards.md` | `pytest-asyncio`, `@pytest.fixture`, mode="auto" | Python-only |
| `standards/testing/test-isolation.md` | `pytest-randomly`, `@pytest.fixture` | Python-only |
| `standards/testing/seam-evidence.md` | `@pytest.mark.integration` markers | Python-only |
| `standards/testing/llm-evaluation.md` | `@pytest.mark.llm_eval`, pytest-as-eval-runner | Python-only |
| `standards/process/definition-of-done.md` | "mypy strict passes with zero errors" in the Code section | mypy-named in a checklist that should be language-agnostic |
| `standards/quality/guardrail-rules.md` | "coverage output from pytest-cov or coverage.py" | pytest-named |
| `standards/quality/metrics.md` | "mypy error count (threshold: 0)" | mypy-named |

### Note: which of these are concepts vs. vocabulary?

A useful distinction surfaces here. Several standards have **language-agnostic concepts** wrapped in **Python vocabulary**:

- `clean-code.md` — size/complexity limits are universal; the ruff rule names are not
- `error-handling.md` — the rules (never silently swallow, catch specific, errors-are-values) are universal; the `raise/except` syntax examples are not
- `import-discipline.md` — "deps visible at top, no circular imports" is universal; E402 and `__future__` are not
- `testing-standards.md` Section on async — async test patterns exist in every language; pytest-asyncio is one binding

These are the **highest-value standards to generalize**: the rule survives the migration, only the binding changes.

By contrast `python-conventions.md`, `ruff-audit.md`, `typing-standards.md` are Python-binding documents and probably stay as "Python profile" sub-standards rather than being generalized.

## Findings — agents

### HARD coupling (frontmatter or body)

| Agent | Where | What |
|---|---|---|
| `agents/backend-developer.md` | line 74-84 + 94 + 169 | Frontmatter: "writes Python conformant to `python-conventions.md`". Body lists FastAPI + Pydantic + SQLAlchemy + LlamaIndex + pytest as "ecosystem"; hard `uv run pytest` test command; conservative defaults section names "pytest for tests" as a fallback. |
| `agents/verifier.md` | line 38-64 + 111-115 | Reads `pyproject.toml [tool.pytest]`, `pytest.ini`, `jest.config.*`, `vitest.config.*` for detection (good — partially language-aware) BUT execution paths default to `uv run pytest/mypy/ruff` (Python). Error messages name only Python tools. |
| `agents/code-simplifier.md` | Required reading items 3-4 | "if the project is Python" — conditional Python references, but no analogous TS/Go entries |
| `agents/devops-engineer.md` | line 123 | One sentence: "If the project uses types (TypeScript, mypy), enforce in CI" — actually language-aware. |

### SOFT coupling

| Agent | What |
|---|---|
| `agents/code-reviewer.md` | Required-reading entry 3-4 reference python-conventions + typing-standards via tier-0 standards. Inherits coupling from standards. |
| `agents/architect-reviewer.md`, `agents/process-evaluator.md`, `agents/sem.md`, `agents/multi-tenant-auditor.md`, `agents/hotfix-responder.md`, `agents/project-bootstrapper.md`, `agents/frontend-dashboard-refactorer.md` | Mention .py / pytest / mypy in passing — cosmetic references in examples, not load-bearing logic |

### Frontend coverage assessment

`agents/frontend-developer.md` exists and is TS/React-coded. `agents/frontend-dashboard-refactorer.md` exists. Frontend has its own dedicated agents. They use TS conventions. **Frontend is the proof case that multi-language agents already work in etc** — the architecture supports it. The gap is that the HOOKS and STANDARDS don't.

## Findings — skills

### HARD coupling (assumes Python in the body)

| Skill | Where | What |
|---|---|---|
| `skills/build/SKILL.md` | line 49-50, 112, 152-154 | "running verification commands (pytest, compile, invariant checks)". Step 7 verify text says "pytest reports 0 failures". Task YAML examples use `src/shared.py` / `tests/test_shared.py`. |
| `skills/implement/SKILL.md` | line 58, 198, 220, 297 | Same pattern — "pytest" named as the verification command; example task files use `.py` paths |

### OUT-OF-SCOPE

| Skill | Why |
|---|---|
| `skills/init-project/SKILL.md` | References `.py` only for harness internals (`compile-sdlc.py`); the project bootstrapped IS arbitrary |
| `skills/spec/SKILL.md`, `/architect`, `/journey`, `/design`, `/discovery`, `/efficiency`, `/postmortem`, `/hotfix`, `/metrics`, `/checkpoint`, `/decompose`, `/retrospective`, `/tasks`, `/pull-tickets`, `/roadmap`, `/harness-feedback` | No Python coupling found |

## Quantified coupling

| Surface | Files surveyed | HARD-coupled | SOFT-coupled | Out-of-scope |
|---|---|---|---|---|
| Hooks | 18 | **5** | 0 | 3 |
| Standards | 43 | **14** | 0 | 29 |
| Agents | 23 | **3** | 7 | 13 |
| Skills | 19 | **2** | 0 | 17 |
| **Total** | **103** | **24** | **7** | **62** |

24 hard-coupled surfaces. Roughly 23% of the harness. The rest is either already language-agnostic or legitimately Python-internal.

## Proposed generalization architecture (sketch, for /spec input)

This section is **not a commitment** — it's the shape the audit suggests so /spec has a starting point.

### Profile system

```
standards/code/profiles/
  python.md           — current python-conventions.md content
  typescript.md       — TS/JS, strictNullChecks, no any, eslint anchors
  go.md               — gofmt, golangci-lint anchors, error-as-value norms
  rust.md             — clippy anchors, Result-everywhere, no .unwrap() in lib code
  terraform.md        — tflint, hashicorp style, module structure
  markdown.md         — markdownlint + Vale/proselint for prose
```

Each profile declares its TOOLING + RULES bindings:

```yaml
# standards/code/profiles/python.yaml (sibling to .md)
language: python
detect:
  - pyproject.toml
  - setup.py
  - "*.py"
test_runner: uv run pytest
type_checker: uv run mypy
linter: uv run ruff check
formatter: uv run ruff format
coverage_tool: pytest-cov
file_extensions: [.py]
test_glob: "tests/**/test_*.py"
quality_helpers:
  - check_mutable_globals.py
  - check_noop_functions.py
```

### Project detection

`scripts/detect_language_profile.py` walks the repo root in priority order: `pyproject.toml` → `package.json` → `go.mod` → `Cargo.toml` → `pom.xml` → `Package.swift` → `Gemfile` → `*.tf` → fallback. Returns active profile name. Multi-language projects return a list; gates run all detected profiles' checks.

### Hook generalization pattern

```bash
# hooks/verify-green.sh (generalized)
PROFILE=$(detect_language_profile)
case "$PROFILE" in
  python)     TESTER="uv run pytest --cov --cov-fail-under=98 -x" ;;
  typescript) TESTER="npm test -- --coverage" ;;
  go)         TESTER="go test ./... -cover" ;;
  rust)       TESTER="cargo test" ;;
  *)          echo "No profile detected; skipping verify-green"; exit 0 ;;
esac
$TESTER || exit 2
```

`hooks/check-test-exists.sh`, `hooks/check-code-quality.sh`, `hooks/check-seam-evidence.sh` all follow the same shape.

### Standards generalization pattern

Tier-0 standards (rules everyone follows) split from tier-1 (language-specific bindings):

```
standards/code/
  clean-code.md                 ← rules (language-agnostic)
  error-handling.md             ← rules (language-agnostic)
  import-discipline.md          ← rules (language-agnostic)
  profiles/
    python.md                   ← bindings: ruff rule codes, mypy syntax
    typescript.md               ← bindings: eslint rule names, tsconfig
    go.md                       ← bindings: golangci-lint, govet
    ...
```

Agent manifests reference the rule set; the active profile injects the bindings.

### Beyond code

| Surface | Profile category |
|---|---|
| Frontend (CSS, HTML, components) | `typescript` profile owns the JS/TS side; CSS would need its own (stylelint) |
| Infra-as-code | `terraform` profile (tflint), `kubernetes` profile (kubeval, kube-score) |
| DevOps / CI | `docker` profile (hadolint), `github-actions` profile (actionlint) |
| Documentation | `markdown` profile (markdownlint, Vale), `adoc` profile (asciidoctor) |
| Technical writing | sibling to markdown profile — adds style guide + glossary checks |

## Migration sequencing proposal

| Phase | Scope | Cost |
|---|---|---|
| **Phase 0: this audit** | DONE | shipped 2026-05-15 |
| **Phase 1: profile architecture** | /spec + /architect for the profile system. ADR for detection order. Probably a single F-feature. | 1 day |
| **Phase 2: python profile (baseline)** | Move existing Python content into `profiles/python.md` + `python.yaml`. Generalize the 5 hooks. NO regression on etc itself. | 1-2 days |
| **Phase 3: typescript profile (proof case)** | Build the typescript profile end-to-end; dogfood on a sample TS repo. Validates the architecture. | 2-3 days |
| **Phase 4: go + rust profiles** | Once TS works, the third + fourth languages are mostly copy-pattern. | 1 day each |
| **Phase 5: beyond-code profiles** | Terraform, markdown, k8s — each their own small F-feature | 0.5-1 day each |
| **Phase 6: README + customer comms** | Reposition etc as language-agnostic. Update marketing surface. | 0.5 day |

Total: ~10-14 working days for the full sequence. Phase 2 alone is the minimum viable improvement (existing Python stays working; the architecture is in place for others).

## Open questions for /spec

1. **Naming.** `profile` vs `language` vs `stack`? `profile` is broadest (covers non-code surfaces like terraform + markdown).
2. **Detection precedence.** A repo with both `pyproject.toml` and `package.json` (backend + frontend monorepo) — run both profiles or pick one? Probably both; need a multi-profile config syntax.
3. **Customer override.** Should `.etc_sdlc/profile-config.yaml` let the operator pin profiles instead of auto-detect? Yes, for monorepos.
4. **Tier-0 (rules) vs tier-1 (bindings) line.** Where exactly does it land? `clean-code.md` clearly rules + bindings; the bindings get extracted. Less clear for `error-handling.md` whose examples are deeply Python-flavored.
5. **Hook fallback.** When no profile is detected (greenfield repo, mixed unrecognized stack), do hooks silently skip or hard-block until a profile is declared? Silent skip is friendlier; hard-block is safer. Probably configurable.
6. **Coverage threshold portability.** 98% line+branch is a Python+pytest number. Should it be per-profile (98% python, 80% TS, 70% rust)?
7. **`agents/backend-developer.md` ownership.** Does it stay Python-named and become one of many sibling agents (`backend-developer-python`, `backend-developer-typescript`, `backend-developer-go`)? Or does it become profile-aware? Probably profile-aware; the agent reads the active profile in its required-reading list.
8. **Migration safety.** Can we ship Phase 2 (python profile) without breaking the 1014 current tests? The tests reference specific tool invocations; they'll need profile-awareness. Likely produces ~50-100 new test cases per profile.

## Recommendation

**Greenlight a Phase-1 /spec session for F022 within the next 1-2 sessions.** The audit is now complete enough for the Socratic loop to anchor on:

- The 24 hard-coupled surfaces give /spec a concrete scope artifact.
- The 8 open questions above are the gray-area resolution candidates.
- The Migration sequencing proposal gives /architect a phased plan to refine.
- The fact that frontend-developer + frontend-dashboard-refactorer already work proves the architecture supports multi-language; what's missing is hooks + standards, not the agent pattern.

**Do NOT start coding profiles before /spec runs.** Phase 1 needs explicit decisions on naming, detection precedence, override mechanism, and the rules-vs-bindings line before any file moves. Without those decisions, Phase 2 will produce a profile structure that needs rework.

---

**End of audit.**
