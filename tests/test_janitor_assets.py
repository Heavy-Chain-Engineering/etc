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
    AC-6 evaluate_candidate composition (regression pin)
        - OTHER path        → cleared-other, runner NEVER invoked
        - PUBLISHED_ASSET   → delegates to consumer_search
    Security hardening
        - option-like filename (-...)            → fail-closed, no runner call
        - argv `--` sentinel before the filename positional
        - malformed/whitespace org login         → fail-closed
        - traversal path (public/../../etc)      → classify OTHER
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

    evidence = verdict.evidence
    assert evidence is not None
    searched_at = evidence["searched_at"]
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


# ── AC-6: evaluate_candidate composition (regression pin) ───────────────


def _exploding_runner(argv: list[str]) -> str:
    """A runner that fails the test if it is EVER called.

    Wired into evaluate_candidate for an OTHER path to prove the gh crossing
    is never reached (AC-6: a plain dead-code deletion flows as today).
    """
    raise AssertionError(f"runner must not be invoked for an OTHER path: {argv}")


@pytest.mark.parametrize(
    "path",
    ["src/helper.py", "tests/test_helper.py", "README.md", "app/public/logo.png"],
)
def test_should_clear_other_without_invoking_runner_when_path_not_published(
    path: str,
) -> None:
    # AC-6 regression pin: an OTHER-classified path is cleared by
    # classification alone — consumer_search is NEVER reached, so the
    # exploding runner is never called.
    verdict = janitor_assets.evaluate_candidate(path, gh_runner=_exploding_runner)

    assert verdict.status == janitor_assets.CLEARED_OTHER
    assert verdict.consumers == []
    assert verdict.evidence is None


def test_should_delegate_to_consumer_search_when_path_published() -> None:
    # The PUBLISHED_ASSET branch DOES cross to gh: a zero-hit search clears
    # it with recorded evidence (same shape consumer_search returns).
    runner = _gh_runner_from(owner="acme", code_hits=[])

    verdict = janitor_assets.evaluate_candidate("public/orphan.png", gh_runner=runner)

    assert verdict.status == janitor_assets.CLEARED
    assert verdict.evidence is not None
    assert "orphan.png" in verdict.evidence["query"]


def test_should_block_via_evaluate_candidate_when_published_asset_consumed() -> None:
    runner = _gh_runner_from(
        owner="acme",
        code_hits=[_hit("acme/email-templates", "emails/welcome.html")],
    )

    verdict = janitor_assets.evaluate_candidate("public/img/logo.png", gh_runner=runner)

    assert verdict.status == janitor_assets.BLOCKED
    assert verdict.consumers == ["acme/email-templates:emails/welcome.html"]


def test_should_search_basename_not_full_path_via_evaluate_candidate() -> None:
    # The org search is by basename (the asset's filename), not the repo
    # path — the consumer hotlinks the deployed URL's leaf, not the repo path.
    captured: list[list[str]] = []
    base = _gh_runner_from(owner="acme", code_hits=[])

    def recording_runner(argv: list[str]) -> str:
        captured.append(argv)
        return base(argv)

    janitor_assets.evaluate_candidate("public/img/nested/logo.png", gh_runner=recording_runner)

    search_calls = [a for a in captured if a[:3] == ["gh", "search", "code"]]
    assert search_calls, "expected a gh search code call"
    # filename positional sits after the `--` sentinel; it is the basename.
    assert search_calls[0][-1] == "logo.png"


# ── Security hardening: argv-option injection (item 4) ───────────────────


def test_should_place_end_of_options_sentinel_before_filename() -> None:
    captured: list[list[str]] = []
    base = _gh_runner_from(owner="acme", code_hits=[])

    def recording_runner(argv: list[str]) -> str:
        captured.append(argv)
        return base(argv)

    janitor_assets.consumer_search("logo.png", gh_runner=recording_runner)

    search_calls = [a for a in captured if a[:3] == ["gh", "search", "code"]]
    assert search_calls
    argv = search_calls[0]
    assert "--" in argv
    # The filename positional is the LAST token, immediately after `--`.
    assert argv[argv.index("--") + 1] == "logo.png"
    assert argv[-1] == "logo.png"


def test_should_fail_closed_when_filename_looks_like_an_option() -> None:
    # An option-like filename must NEVER clear: it is rejected before any
    # runner call (argv-option-injection defense).
    verdict = janitor_assets.consumer_search("--limit", gh_runner=_exploding_runner)

    assert verdict.status == janitor_assets.FAIL_CLOSED
    assert verdict.status != janitor_assets.CLEARED
    assert verdict.reason is not None
    assert "--limit" in verdict.reason


def test_should_reject_option_like_filename_before_any_runner_call() -> None:
    # Belt-and-braces on the "before any runner call" guarantee: the
    # exploding runner proves no gh crossing happens for a `-`-prefixed name.
    verdict = janitor_assets.consumer_search("-rf", gh_runner=_exploding_runner)

    assert verdict.status == janitor_assets.FAIL_CLOSED


# ── Security hardening: org-login validation (item 5) ────────────────────


@pytest.mark.parametrize(
    "bad_login",
    ["acme\n", " acme", "acme corp", "-acme", "acme/../../etc", ""],
)
def test_should_fail_closed_when_org_login_is_malformed(bad_login: str) -> None:
    # A login carrying whitespace, newlines, or otherwise outside GitHub's
    # org charset is a malformed/hostile remote → fail closed, never search.
    def runner(argv: list[str]) -> str:
        if argv[:3] == ["gh", "repo", "view"]:
            return json.dumps({"owner": {"login": bad_login}})
        raise AssertionError(f"unexpected gh argv after bad org: {argv}")

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    assert verdict.status == janitor_assets.FAIL_CLOSED


def test_should_accept_hyphenated_org_login() -> None:
    # A valid hyphenated org (GitHub's charset) clears the search normally.
    runner = _gh_runner_from(owner="Heavy-Chain-Engineering", code_hits=[])

    verdict = janitor_assets.consumer_search("orphan.png", gh_runner=runner)

    assert verdict.status == janitor_assets.CLEARED
    assert verdict.evidence is not None
    assert verdict.evidence["org_scope"] == "Heavy-Chain-Engineering"


# ── Security hardening: classify traversal canonicalization (item 6) ─────


@pytest.mark.parametrize(
    "path",
    [
        "public/../../../etc/passwd",
        "public/../secret",
        "static/../../outside.txt",
        "../public/logo.png",
        "/public/logo.png",
        "www/../..",
    ],
)
def test_should_classify_other_when_path_uses_traversal_or_escapes_root(
    path: str,
) -> None:
    # A traversal-laden string must not spoof a published root; anything that
    # normalizes to escape the repo root (leading .. or absolute /) is OTHER.
    assert janitor_assets.classify(path) == janitor_assets.OTHER


def test_should_classify_published_when_inner_traversal_stays_under_root() -> None:
    # public/img/../logo.png normalizes to public/logo.png — still a genuine
    # published-asset path; canonicalization must not over-reject.
    assert janitor_assets.classify("public/img/../logo.png") == (janitor_assets.PUBLISHED_ASSET)


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
