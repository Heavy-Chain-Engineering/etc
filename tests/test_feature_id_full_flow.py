"""Integration tests for the full F023 allocate-temp → resolve-final-id flow.

Coverage targets:
- AC-010 (overall): integration test in tmp_path with fresh `git init` exercises
  the full flow — allocate-temp creates Ftmp-<hex>-<slug>/; test writes a fake
  spec.md + 1 ADR under temp form; resolve-final-id renames dir + ADR +
  appends id_history[final]; the release tag at Step 7a is etc/feature/F<NNN>
  /release (NOT etc/feature/Ftmp-<hex>/release).
- AC-007 (BR-007): simulate a phase tag write at
  etc/feature/Ftmp-<hex>/build/phase-0/start BEFORE resolve-final-id; assert
  post-rename that the original phase tag still exists at its original SHA
  (F021 BR-008 append-only discipline preserved verbatim).
- AC-008 (BR-008): state.yaml.id_history contains TWO entries (temp + final),
  each with form/value/written_at fields, ISO-8601 UTC timestamps.
- EC-006: state.yaml without pre-existing id_history field gets the field
  CREATED during resolve-final-id (legacy state.yaml files without the field
  are not migrated; this exercises the field-creation path).

The test exercises the integration boundary — it does NOT re-implement helper
functions. Calls `feature_id.allocate_temp(...)` and `feature_id.resolve_final_id(...)`
directly via Python import.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import feature_id  # pyright: ignore[reportMissingImports]  # noqa: E402, I001  — sys.path inserted above

_FINAL_ID_PATTERN = re.compile(r"^F\d{3}$")
_TEMP_ID_PATTERN = re.compile(r"^Ftmp-[0-9a-f]{8}$")
_ISO_8601_UTC_SUFFIXES = ("Z", "+00:00")


# ── helpers ─────────────────────────────────────────────────────────────


def _init_git_repo(repo_root: Path) -> None:
    """Initialize a fresh git repo at `repo_root` with an initial commit.

    Mirrors the helper in tests/test_feature_id_resolve_final.py so the
    integration test does not depend on cross-file fixtures.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    # An initial empty commit so HEAD exists for tag writes + git mv.
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "initial"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )


def _git_rev_parse(repo_root: Path, ref: str) -> str:
    """Return the SHA of `ref` in `repo_root` (raises CalledProcessError on miss)."""
    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_tag_list(repo_root: Path, pattern: str) -> list[str]:
    """Return matching git tag names under `pattern` (empty list on no match)."""
    result = subprocess.run(
        ["git", "tag", "--list", pattern],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _git_commit_empty(repo_root: Path, message: str) -> None:
    """Create an empty commit (advances HEAD without touching the working tree)."""
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", message],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )


def _is_iso_8601_utc(value: str) -> bool:
    """True iff `value` parses as ISO-8601 with a UTC offset (Z or +00:00)."""
    if "T" not in value:
        return False
    if not value.endswith(_ISO_8601_UTC_SUFFIXES):
        return False
    # datetime.fromisoformat accepts +00:00 directly; Python 3.11+ accepts Z.
    from datetime import datetime

    try:
        # Normalize trailing Z to +00:00 so fromisoformat parses pre-3.11 too.
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


# ── AC-010: full flow happy path ────────────────────────────────────────


class TestFullFlowHappyPath:
    def test_should_rename_dir_and_adr_and_emit_final_release_tag_when_full_flow_runs(
        self, tmp_path: Path
    ) -> None:
        # AC-010: full integration. allocate-temp → write spec.md + 1 ADR
        # under temp form → resolve-final-id → assert dir renamed, ADR
        # renamed, release tag uses the FINAL F<NNN> (not the temp form).
        _init_git_repo(tmp_path)
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        # Step 1: allocate-temp creates the active dir + initial state.yaml.
        temp_id, feature_path = feature_id.allocate_temp("test-feature", etc_sdlc_root)

        assert _TEMP_ID_PATTERN.match(temp_id), f"allocate_temp returned malformed id: {temp_id!r}"
        assert feature_path.is_dir()

        # Step 2: write a fake spec.md (inside the temp feature dir).
        (feature_path / "spec.md").write_text("# fake spec\n")

        # Step 3: write 1 ADR under docs/adrs/ in temp form + git-commit it.
        adr_dir = tmp_path / "docs" / "adrs"
        adr_dir.mkdir(parents=True)
        adr_temp_name = f"{temp_id}-001-foo.md"
        adr_temp_path = adr_dir / adr_temp_name
        adr_temp_path.write_text("# ADR foo\n")
        subprocess.run(
            ["git", "add", str(adr_temp_path)],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", f"add {adr_temp_name}"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Step 4: resolve-final-id renames the dir + ADR + appends id_history.
        final_id = feature_id.resolve_final_id(feature_path.name, etc_sdlc_root, repo_root=tmp_path)

        # Assertion 1: final_id matches F<NNN>.
        assert _FINAL_ID_PATTERN.match(final_id), f"final_id malformed: {final_id!r}"

        # Assertion 2: dir renamed to F<NNN>-test-feature/.
        new_dir = etc_sdlc_root / "features" / "active" / f"{final_id}-test-feature"
        assert new_dir.is_dir()
        assert not feature_path.exists()

        # Assertion 3: ADR renamed to F<NNN>-001-foo.md.
        new_adr = adr_dir / f"{final_id}-001-foo.md"
        assert new_adr.is_file()
        assert not adr_temp_path.exists()

        # Assertion 4: simulate the Step 7a release-tag write — it MUST use
        # the final F<NNN>, never the temp form. (Per AC-010, the test
        # simulates the tag write itself.)
        release_tag = f"etc/feature/{final_id}/release"
        subprocess.run(
            ["git", "tag", release_tag],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        release_tags = _git_tag_list(tmp_path, "etc/feature/F[0-9][0-9][0-9]/release")
        assert release_tag in release_tags, (
            f"release tag {release_tag} not present in {release_tags}"
        )
        # And no release tag exists under the temp form (BR-006 contract).
        temp_release_tags = _git_tag_list(tmp_path, "etc/feature/Ftmp-*/release")
        assert temp_release_tags == [], f"unexpected temp-form release tags: {temp_release_tags}"


# ── AC-007: phase-tag preservation across resolve-final-id ──────────────


class TestPhaseTagPreservation:
    def test_should_preserve_temp_form_phase_tag_at_original_sha_after_resolve(
        self, tmp_path: Path
    ) -> None:
        # AC-007 (BR-007): phase tags written under Ftmp-<hex> form during
        # /build waves MUST survive resolve-final-id unchanged — same name,
        # same SHA. F021 BR-008 append-only discipline preserved verbatim.
        _init_git_repo(tmp_path)
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        temp_id, feature_path = feature_id.allocate_temp("phase-tag-feature", etc_sdlc_root)
        (feature_path / "spec.md").write_text("# fake spec\n")

        # Stage one ADR under temp form so resolve-final-id exercises git mv.
        adr_dir = tmp_path / "docs" / "adrs"
        adr_dir.mkdir(parents=True)
        adr_path = adr_dir / f"{temp_id}-001-decision.md"
        adr_path.write_text("# ADR\n")
        subprocess.run(
            ["git", "add", str(adr_path)],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        _git_commit_empty(tmp_path, "stage ADR")  # advances HEAD irrelevant
        subprocess.run(
            ["git", "commit", "-q", "--amend", "--no-edit"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Write the phase tag at the CURRENT HEAD (simulates a /build wave
        # tag write under the temp form, per F021 + F023 design).
        phase_tag = f"etc/feature/{temp_id}/build/phase-0/start"
        subprocess.run(
            ["git", "tag", phase_tag],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        phase_sha_before = _git_rev_parse(tmp_path, phase_tag)

        # Advance HEAD via an empty commit BEFORE resolve-final-id so that
        # any naive "retag at current HEAD" implementation would surface a
        # different SHA on the phase tag. (BR-007 demands the original SHA
        # is preserved unconditionally — append-only.)
        _git_commit_empty(tmp_path, "advance HEAD post-phase-tag")

        # Step: run resolve-final-id.
        final_id = feature_id.resolve_final_id(feature_path.name, etc_sdlc_root, repo_root=tmp_path)

        # Assertion 1: the original Ftmp-<hex> phase tag still exists.
        preserved = _git_tag_list(tmp_path, f"etc/feature/{temp_id}/*")
        assert preserved, (
            "temp-form phase tags lost after resolve-final-id; git tag --list returned empty"
        )
        assert phase_tag in preserved, f"expected {phase_tag} in {preserved}"

        # Assertion 2: the phase tag points at its ORIGINAL SHA.
        phase_sha_after = _git_rev_parse(tmp_path, phase_tag)
        assert phase_sha_after == phase_sha_before, (
            f"phase tag SHA mutated by resolve-final-id: {phase_sha_before} -> {phase_sha_after}"
        )

        # Assertion 3: no retag under the final form was written by the
        # harness (F023 BR-007 — harness never retags Ftmp- phase tags).
        final_phase_tags = _git_tag_list(tmp_path, f"etc/feature/{final_id}/build/phase-*")
        assert final_phase_tags == [], f"unexpected retag under final form: {final_phase_tags}"


# ── AC-008: state.yaml.id_history shape after resolve-final-id ──────────


class TestStateYamlIdHistoryShape:
    def test_should_produce_two_id_history_entries_with_iso_8601_utc_written_at(
        self, tmp_path: Path
    ) -> None:
        # AC-008: state.yaml.id_history after resolve-final-id contains
        # exactly TWO entries — entry 0 form=temp, entry 1 form=final —
        # each with form/value/written_at fields; both written_at parse as
        # ISO-8601 UTC.
        _init_git_repo(tmp_path)
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        temp_id, feature_path = feature_id.allocate_temp("state-shape", etc_sdlc_root)

        final_id = feature_id.resolve_final_id(feature_path.name, etc_sdlc_root, repo_root=tmp_path)

        new_dir = etc_sdlc_root / "features" / "active" / f"{final_id}-state-shape"
        loaded: dict[str, Any] = yaml.safe_load((new_dir / "state.yaml").read_text())
        history = loaded["id_history"]

        assert isinstance(history, list)
        assert len(history) == 2, (
            f"expected exactly 2 id_history entries; got {len(history)}: {history!r}"
        )

        entry_temp = history[0]
        assert entry_temp["form"] == "temp"
        assert entry_temp["value"] == temp_id
        assert _is_iso_8601_utc(entry_temp["written_at"]), (
            f"entry 0 written_at not ISO-8601 UTC: {entry_temp['written_at']!r}"
        )

        entry_final = history[1]
        assert entry_final["form"] == "final"
        assert entry_final["value"] == final_id
        assert _is_iso_8601_utc(entry_final["written_at"]), (
            f"entry 1 written_at not ISO-8601 UTC: {entry_final['written_at']!r}"
        )


# ── EC-006: legacy state.yaml without id_history gets the field created ─


class TestLegacyStateYamlMissingIdHistory:
    def test_should_create_id_history_field_when_state_yaml_lacks_it(self, tmp_path: Path) -> None:
        # EC-006: simulating a legacy/pre-F023 feature whose state.yaml
        # does NOT contain id_history. resolve-final-id MUST CREATE the
        # field with both temp + final entries (NOT migrate it from
        # absent — legacy state.yaml files without the field aren't
        # migrated; this exercises the creation path on a newly-built
        # feature whose state.yaml happened to be authored without the
        # field).
        _init_git_repo(tmp_path)
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        # Hand-construct the temp feature dir (bypass allocate_temp so we
        # control the state.yaml shape — EC-006 + EC-008 acceptable bypass).
        temp_hex = "feed1ace"
        slug = "legacy-no-history"
        feature_dir = etc_sdlc_root / "features" / "active" / f"Ftmp-{temp_hex}-{slug}"
        feature_dir.mkdir(parents=True)
        # state.yaml present but WITHOUT id_history (e.g., only carries
        # an unrelated field).
        (feature_dir / "state.yaml").write_text(yaml.safe_dump({"unrelated_field": "value"}))

        final_id = feature_id.resolve_final_id(feature_dir.name, etc_sdlc_root, repo_root=tmp_path)

        new_dir = etc_sdlc_root / "features" / "active" / f"{final_id}-{slug}"
        loaded: dict[str, Any] = yaml.safe_load((new_dir / "state.yaml").read_text())

        # Assertion 1: id_history field was CREATED.
        assert "id_history" in loaded, (
            "id_history field not created on legacy-no-history state.yaml"
        )

        # Assertion 2: it carries both the temp and final entries.
        history = loaded["id_history"]
        assert isinstance(history, list)
        assert len(history) == 2
        assert history[0]["form"] == "temp"
        assert history[0]["value"] == f"Ftmp-{temp_hex}"
        assert history[1]["form"] == "final"
        assert history[1]["value"] == final_id

        # Assertion 3: pre-existing unrelated_field preserved (no migration
        # erases extant fields).
        assert loaded.get("unrelated_field") == "value", (
            "unrelated field clobbered by resolve-final-id; id_history bootstrap should be additive"
        )


# ── AC-007 (sub-cases): parametrize over phase positions ────────────────


@pytest.mark.parametrize(
    "phase_name",
    [
        "build/phase-0/start",
        "build/phase-0/done",
        "build/phase-1/start",
    ],
)
class TestPhaseTagPreservationSubCases:
    def test_should_preserve_each_phase_tag_form_at_original_sha(
        self, tmp_path: Path, phase_name: str
    ) -> None:
        # AC-007 sub-cases: BR-007 covers ALL phase-N {start,done} tags
        # written under the temp form, not just phase-0/start. Parametrize
        # to cover the three most common positions.
        _init_git_repo(tmp_path)
        etc_sdlc_root = tmp_path / ".etc_sdlc"

        temp_id, feature_path = feature_id.allocate_temp("phase-sub-cases", etc_sdlc_root)

        tag_ref = f"etc/feature/{temp_id}/{phase_name}"
        subprocess.run(
            ["git", "tag", tag_ref],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        sha_before = _git_rev_parse(tmp_path, tag_ref)

        # Advance HEAD before resolve to make any silent retag observable.
        _git_commit_empty(tmp_path, f"advance HEAD before resolve for {phase_name}")

        feature_id.resolve_final_id(feature_path.name, etc_sdlc_root, repo_root=tmp_path)

        assert tag_ref in _git_tag_list(tmp_path, f"etc/feature/{temp_id}/*"), (
            f"phase tag {tag_ref} lost after resolve-final-id"
        )
        assert _git_rev_parse(tmp_path, tag_ref) == sha_before, (
            f"phase tag {tag_ref} SHA mutated by resolve-final-id"
        )
