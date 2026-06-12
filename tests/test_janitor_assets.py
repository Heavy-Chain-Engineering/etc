"""Tests for scripts/janitor_assets.py — published-asset deletion guard.

These tests are hermetic: every `gh` invocation is routed through an
injectable runner seam (`gh_runner`) so no test touches a real GitHub
remote. The seam takes an argv list and returns captured stdout (str)
exactly as `subprocess.run(...).stdout` would, or raises to simulate a
gh-boundary failure (binary absent / non-zero exit / rate-limit) — the
same fake-runner pattern as tests/test_janitor_trust.py.

Coverage targets (per task 001 acceptance criteria):
    AC-1 classify(path)
        - public/**, static/**, www/**          → PUBLISHED_ASSET
        - any other path                         → OTHER (pass-through)
    AC-2 consumer_search(filename) via injected runner
        - org derived from the repo remote owner
        - a consumer hit  → blocked verdict, consumers named
        - zero hits       → cleared verdict + evidence
                            {query, org_scope, searched_at, hit_count}
    AC-3 fail-closed degrade (mirrors the janitor_trust degrade suite)
        - gh absent / CalledProcessError / unparseable output
                          → fail-closed verdict (NOT cleared, distinct)
        - non-boundary error                     → propagates (crashes loud)
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "janitor_assets.py"


def _load_janitor_assets() -> ModuleType:
    """Load scripts/janitor_assets.py without requiring scripts to be a package.

    Mirrors the importlib loader pattern used by test_janitor_trust.py and
    test_value_hypothesis.py elsewhere in this suite. The module is registered
    in ``sys.modules`` before ``exec_module`` so the stdlib ``dataclasses``
    machinery (which resolves the defining module by name to check for
    ``KW_ONLY``) can find it during ``@dataclass`` processing at import time.
    """
    spec = importlib.util.spec_from_file_location("janitor_assets", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


janitor_assets = _load_janitor_assets()


# ── Fakes / fixtures ────────────────────────────────────────────────────


def _gh_runner_from(
    *,
    owner: str = "acme",
    code_hits: list[dict[str, Any]] | None = None,
    absent: bool = False,
    repo_view_raises: BaseException | None = None,
    search_raises: BaseException | None = None,
    search_returns: str | None = None,
) -> Callable[[list[str]], str]:
    """Build a fake gh runner for the two gh crossings this module makes.

    `gh repo view --json owner` → derives the org (`owner`).
    `gh search code <query> --owner <org> --json repository,path`
        → returns `code_hits` (each a {repository, path} record).

    Failure-injection hooks (degrade-path tests):
    `absent` — raise FileNotFoundError on any call (gh binary missing).
    `repo_view_raises` — raised on the `gh repo view` call.
    `search_raises` — raised on the `gh search code` call (e.g. a non-zero
    exit surfacing as subprocess.CalledProcessError, or a rate-limit).
    `search_returns` — overrides search stdout with a raw string (e.g.
    garbage that fails JSON parse).
    """
    code_hits = code_hits or []

    def runner(argv: list[str]) -> str:
        if absent:
            raise FileNotFoundError(argv[0])
        if argv[:3] == ["gh", "repo", "view"]:
            if repo_view_raises is not None:
                raise repo_view_raises
            return json.dumps({"owner": {"login": owner}})
        if argv[:3] == ["gh", "search", "code"]:
            if search_raises is not None:
                raise search_raises
            if search_returns is not None:
                return search_returns
            return json.dumps(code_hits)
        raise AssertionError(f"unexpected gh argv: {argv}")

    return runner


def _hit(repository: str, path: str) -> dict[str, Any]:
    return {"repository": {"nameWithOwner": repository}, "path": path}


# ── AC-1: classify ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "public/logo.png",
        "public/img/nested/deep/favicon.ico",
        "static/css/site.css",
        "www/index.html",
    ],
)
def test_should_classify_published_asset_when_path_under_deploy_root(
    path: str,
) -> None:
    assert janitor_assets.classify(path) == janitor_assets.PUBLISHED_ASSET


@pytest.mark.parametrize(
    "path",
    [
        "src/helper.py",
        "tests/test_helper.py",
        "docs/public.md",
        "README.md",
        "publicity/note.txt",
        "my-public/logo.png",
        "app/public/logo.png",
    ],
)
def test_should_classify_other_when_path_outside_deploy_roots(
    path: str,
) -> None:
    # Closed glob set anchored at the path root: substring/suffix matches
    # (publicity/, my-public/) and nested deploy roots (app/public/) are
    # NOT v1 published-asset surface — they pass through untouched.
    assert janitor_assets.classify(path) == janitor_assets.OTHER


def test_should_normalize_leading_dot_slash_when_classifying() -> None:
    assert janitor_assets.classify("./public/logo.png") == (janitor_assets.PUBLISHED_ASSET)


def test_should_expose_published_roots_as_module_constant() -> None:
    # The closed glob set is a module constant (load-bearing for the skill
    # wiring): the three documented roots, nothing more.
    assert janitor_assets.PUBLISHED_ROOTS == ("public", "static", "www")


# ── AC-2: consumer_search — hit and zero-hit verdicts ───────────────────


def test_should_block_deletion_when_consumer_hit_found() -> None:
    runner = _gh_runner_from(
        owner="acme",
        code_hits=[_hit("acme/email-templates", "emails/welcome.html")],
    )

    verdict = janitor_assets.consumer_search("logo.png", gh_runner=runner)

    assert verdict.status == janitor_assets.BLOCKED
    assert verdict.consumers == ["acme/email-templates:emails/welcome.html"]


def test_should_name_every_consumer_when_multiple_hits() -> None:
    runner = _gh_runner_from(
        owner="acme",
        code_hits=[
            _hit("acme/email-templates", "emails/welcome.html"),
            _hit("acme/marketing-site", "src/footer.tsx"),
        ],
    )

    verdict = janitor_assets.consumer_search("logo.png", gh_runner=runner)

    assert verdict.status == janitor_assets.BLOCKED
    assert verdict.consumers == [
        "acme/email-templates:emails/welcome.html",
        "acme/marketing-site:src/footer.tsx",
    ]


def test_should_clear_deletion_when_zero_consumer_hits() -> None:
    runner = _gh_runner_from(owner="acme", code_hits=[])

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    assert verdict.status == janitor_assets.CLEARED
    assert verdict.consumers == []


def test_should_record_evidence_dict_when_cleared() -> None:
    runner = _gh_runner_from(owner="acme", code_hits=[])

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    evidence = verdict.evidence
    assert evidence is not None
    assert set(evidence) == {"query", "org_scope", "searched_at", "hit_count"}
    assert evidence["org_scope"] == "acme"
    assert evidence["hit_count"] == 0
    assert "orphan.png" in evidence["query"]


def test_should_record_iso8601_searched_at_when_cleared() -> None:
    from datetime import datetime

    runner = _gh_runner_from(owner="acme", code_hits=[])

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    searched_at = verdict.evidence["searched_at"]  # type: ignore[index]
    # Round-trips as ISO-8601 with a trailing Z (UTC).
    assert searched_at.endswith("Z")
    parsed = datetime.fromisoformat(searched_at.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_should_record_hit_count_in_evidence_even_when_blocked() -> None:
    # Edge 2 (generic filename floods with hits): the evidence records the
    # hit count so the operator sees the false-positive cost.
    runner = _gh_runner_from(
        owner="acme",
        code_hits=[
            _hit("acme/a", "x.html"),
            _hit("acme/b", "y.html"),
        ],
    )

    verdict = janitor_assets.consumer_search("logo.png", gh_runner=runner)

    assert verdict.evidence is not None
    assert verdict.evidence["hit_count"] == 2


def test_should_derive_org_from_repo_remote_owner() -> None:
    captured: list[list[str]] = []
    base = _gh_runner_from(owner="globex", code_hits=[])

    def recording_runner(argv: list[str]) -> str:
        captured.append(argv)
        return base(argv)

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=recording_runner)

    assert verdict.evidence is not None
    assert verdict.evidence["org_scope"] == "globex"
    search_calls = [a for a in captured if a[:3] == ["gh", "search", "code"]]
    assert search_calls, "expected a gh search code call"
    assert "--owner" in search_calls[0]
    assert search_calls[0][search_calls[0].index("--owner") + 1] == "globex"


# ── AC-3: fail-closed degrade (mirrors janitor_trust degrade suite) ──────


def test_should_fail_closed_when_gh_absent() -> None:
    runner = _gh_runner_from(absent=True)

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    assert verdict.status == janitor_assets.FAIL_CLOSED
    assert verdict.status != janitor_assets.CLEARED


def test_should_fail_closed_when_search_exits_nonzero() -> None:
    runner = _gh_runner_from(
        search_raises=subprocess.CalledProcessError(1, ["gh", "search", "code"])
    )

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    assert verdict.status == janitor_assets.FAIL_CLOSED


def test_should_fail_closed_when_repo_view_exits_nonzero() -> None:
    # Org derivation itself can fail (no remote / auth scope) — that is also
    # a gh-boundary failure and must fail closed, never repo-local fallback.
    runner = _gh_runner_from(
        repo_view_raises=subprocess.CalledProcessError(1, ["gh", "repo", "view"])
    )

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    assert verdict.status == janitor_assets.FAIL_CLOSED


def test_should_fail_closed_when_search_returns_garbage_json() -> None:
    runner = _gh_runner_from(search_returns="not json at all <<<")

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    assert verdict.status == janitor_assets.FAIL_CLOSED


def test_should_carry_failure_reason_when_fail_closed() -> None:
    # The fail-closed verdict names the boundary failure class so the run
    # record and the operator-confirm prompt can surface WHY.
    runner = _gh_runner_from(absent=True)

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    assert verdict.reason is not None
    assert "FileNotFoundError" in verdict.reason


def test_should_not_clear_or_name_consumers_when_fail_closed() -> None:
    # A fail-closed verdict is distinct from zero-hits: never cleared, no
    # evidence dict, no repo-local fallback.
    runner = _gh_runner_from(absent=True)

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    assert verdict.status == janitor_assets.FAIL_CLOSED
    assert verdict.consumers == []
    assert verdict.evidence is None


def test_should_propagate_unexpected_error_not_at_gh_boundary() -> None:
    # A real bug in our own code (non-gh-boundary failure) must still crash
    # loudly — the fix must not widen to a bare `except Exception`.
    def _boom(argv: list[str]) -> str:
        raise ZeroDivisionError("not a gh-boundary failure")

    with pytest.raises(ZeroDivisionError, match="not a gh-boundary failure"):
        janitor_assets.consumer_search("orphan.png", gh_runner=_boom)


def test_should_fail_closed_when_org_owner_missing_from_repo_view() -> None:
    # gh repo view returns a mapping without a usable owner.login → cannot
    # derive the org → fail closed (cannot attest to an unknown scope).
    def runner(argv: list[str]) -> str:
        if argv[:3] == ["gh", "repo", "view"]:
            return json.dumps({"owner": {}})
        raise AssertionError(f"unexpected gh argv: {argv}")

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    assert verdict.status == janitor_assets.FAIL_CLOSED


# ── CLI surfaces ─────────────────────────────────────────────────────────


def test_should_print_published_asset_token_via_classify_cli(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = janitor_assets.main(["classify", "public/logo.png"])

    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == janitor_assets.PUBLISHED_ASSET


def test_should_print_other_token_via_classify_cli(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = janitor_assets.main(["classify", "src/helper.py"])

    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == janitor_assets.OTHER


def test_should_exit_nonzero_on_unknown_subcommand() -> None:
    with pytest.raises(SystemExit) as excinfo:
        janitor_assets.main(["bogus"])

    assert excinfo.value.code != 0
