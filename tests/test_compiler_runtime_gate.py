"""Source->dist parity guard for the Gap A behavioral-runtime-DoD artifacts.

The behavioral/runtime DoD gate (Gap A) ships four NEW artifacts that must
land in dist/ after compile, across three different sweep mechanisms:

  - standards/process/behavioral-runtime-dod.md   (compile_standards copytree)
  - standards/code/profiles/python/runtime-verify.sh (compile_standards copytree)
  - hooks/runtime-verify.sh                        (compile_dispatcher_hooks glob)
  - scripts/runtime_totalization_check.py          (compile_scripts iterdir)

#41/#18 precedent: non-`.md` and new-shape artifacts have been silently
dropped from dist/ before (the F020 verify-green.sh dispatcher; the
layer-rubrics.yaml installer narrowing). The hook `.sh`, the profile `.sh`,
and the gate `.py` each ride a different sweep — any one of which could be
narrowed back to a `.md`-only glob. This test compiles the REAL spec into an
isolated dist and asserts source->dist named-set equality for the four
artifacts, failing LOUDLY (naming the dropped file) if any is missing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

# (source path relative to repo root, dist path relative to the compiled dist)
GAP_A_ARTIFACTS: tuple[tuple[str, str], ...] = (
    (
        "standards/process/behavioral-runtime-dod.md",
        "standards/process/behavioral-runtime-dod.md",
    ),
    (
        "standards/code/profiles/python/runtime-verify.sh",
        "standards/code/profiles/python/runtime-verify.sh",
    ),
    ("hooks/runtime-verify.sh", "hooks/runtime-verify.sh"),
    (
        "scripts/runtime_totalization_check.py",
        "scripts/runtime_totalization_check.py",
    ),
)


def _load_compile_sdlc_module() -> Any:
    """Load compile-sdlc.py as a module (hyphenated filename needs importlib)."""
    module_path = REPO_ROOT / "compile-sdlc.py"
    spec = importlib.util.spec_from_file_location("compile_sdlc", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_real_spec() -> dict[str, Any]:
    """Load the real SDLC spec for the parity compile."""
    spec_path = REPO_ROOT / "spec" / "etc_sdlc.yaml"
    return yaml.safe_load(spec_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def compiled_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile the REAL Claude target into an isolated dist directory.

    Drives the same compile passes that produce the four Gap A artifacts:
    standards (copytree), dispatcher hooks (glob), and scripts (iterdir).
    """
    compile_sdlc = _load_compile_sdlc_module()
    dist_dir = tmp_path_factory.mktemp("dist")
    compile_sdlc.compile_standards(_load_real_spec(), dist_dir, REPO_ROOT)
    compile_sdlc.compile_dispatcher_hooks(dist_dir, REPO_ROOT)
    compile_sdlc.compile_scripts(dist_dir, REPO_ROOT)
    return dist_dir


def test_should_have_all_gap_a_sources_present_in_repo() -> None:
    """Precondition: every Gap A source artifact exists in the repo.

    Guards the parity test from passing vacuously — if a source artifact is
    deleted, the named-set equality below would otherwise trivially hold.
    """
    missing = [
        src for src, _dist in GAP_A_ARTIFACTS
        if not (REPO_ROOT / src).exists()
    ]
    assert not missing, (
        f"Gap A source artifacts missing from the repo: {sorted(missing)}. "
        f"Tasks 001/003/004/005 must land these before compile-wiring."
    )


def test_should_mirror_every_gap_a_artifact_into_dist(compiled_dist: Path) -> None:
    """Every Gap A source artifact must appear at its dist path after compile.

    Source->dist named-set equality for the four Gap A artifacts. Fails
    loudly NAMING any dropped artifact — the silent-drop failure mode from
    #41/#18 that this guard converts from 'caught downstream' to 'caught here'.
    """
    source_set = {dist_rel for _src, dist_rel in GAP_A_ARTIFACTS}
    dist_set = {
        dist_rel
        for _src, dist_rel in GAP_A_ARTIFACTS
        if (compiled_dist / dist_rel).exists()
    }
    missing = source_set - dist_set
    assert not missing, (
        f"Gap A artifacts dropped from dist/: {sorted(missing)}. "
        f"compile_standards / compile_dispatcher_hooks / compile_scripts "
        f"must mirror each one. Check the sweep was not narrowed to .md-only."
    )


def test_should_preserve_exec_bit_on_gap_a_shell_artifacts(
    compiled_dist: Path,
) -> None:
    """The dispatcher hook and profile primitive must be executable in dist/.

    Both are invoked as `bash <script>` by the conductor; a dropped exec bit
    is the same class of silent breakage as a dropped file.
    """
    shell_artifacts = (
        "hooks/runtime-verify.sh",
        "standards/code/profiles/python/runtime-verify.sh",
    )
    non_exec = [
        rel
        for rel in shell_artifacts
        if (compiled_dist / rel).stat().st_mode & 0o111 == 0
    ]
    assert not non_exec, (
        f"Gap A shell artifacts not executable in dist/: {sorted(non_exec)}."
    )
