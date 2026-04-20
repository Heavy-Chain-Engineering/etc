"""Tests for the code quality enforcement pipeline.

Covers:
  - hooks/helpers/check_mutable_globals.py (CQ-001)
  - hooks/helpers/check_noop_functions.py (CQ-002)
  - hooks/check-code-quality.sh (shell hook)
  - Enforcement annotation validation
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPERS_DIR = REPO_ROOT / "hooks" / "helpers"

# Import the helper modules for direct testing
sys.path.insert(0, str(HELPERS_DIR))
import check_mutable_globals  # noqa: E402
import check_noop_functions  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════
# CQ-001: Global mutable state detection
# ═══════════════════════════════════════════════════════════════════════════


class TestCQ001MutableGlobals:
    """Tests for check_mutable_globals.py (CQ-001)."""

    def test_should_detect_list_literal_when_module_level(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("handlers = []\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 1
        assert "CQ-001" in violations[0]
        assert "handlers" in violations[0]

    def test_should_detect_dict_literal_when_module_level(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("registry = {}\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 1
        assert "registry" in violations[0]

    def test_should_detect_set_call_when_module_level(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("seen = set()\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 1
        assert "seen" in violations[0]

    def test_should_detect_list_call_when_module_level(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("items = list()\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 1
        assert "items" in violations[0]

    def test_should_detect_dict_call_when_module_level(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("cache = dict()\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 1

    def test_should_detect_defaultdict_when_module_level(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("from collections import defaultdict\n_handlers = defaultdict(list)\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 1
        assert "_handlers" in violations[0]
        assert "defaultdict" in violations[0]

    def test_should_detect_deque_when_module_level(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("from collections import deque\nbuffer = deque()\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 1
        assert "buffer" in violations[0]

    def test_should_exempt_init_py_when_checked(self, tmp_path: Path) -> None:
        f = tmp_path / "__init__.py"
        f.write_text("handlers = []\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 0

    def test_should_exempt_final_annotation_when_present(self, tmp_path: Path) -> None:
        f = tmp_path / "config.py"
        f.write_text("from typing import Final\nDEFAULTS: Final = [1, 2, 3]\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 0

    def test_should_exempt_final_subscript_when_present(self, tmp_path: Path) -> None:
        f = tmp_path / "config.py"
        f.write_text("from typing import Final\nDEFAULTS: Final[list[int]] = [1, 2, 3]\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 0

    def test_should_exempt_type_checking_block_when_present(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    stubs = []\n"
            "\n"
            "x = 42\n"
        )
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 0

    def test_should_exempt_cq_exempt_comment_when_present(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("handlers = []  # cq-exempt: CQ-001 -- legitimate registry\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 0

    def test_should_pass_silently_when_syntax_error(self, tmp_path: Path) -> None:
        f = tmp_path / "broken.py"
        f.write_text("def foo(\n")  # Incomplete syntax
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 0

    def test_should_pass_when_no_mutables(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.py"
        f.write_text("MAX_RETRIES = 3\nNAME = 'hello'\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 0

    def test_should_ignore_function_level_mutables(self, tmp_path: Path) -> None:
        f = tmp_path / "ok.py"
        f.write_text("def foo():\n    items = []\n    return items\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 0

    def test_should_detect_annotated_mutable_when_not_final(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("items: list[str] = []\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 1
        assert "items" in violations[0]

    def test_should_detect_multiple_violations(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("a = []\nb = {}\nc = set()\n")
        violations = check_mutable_globals.check_file(str(f))
        assert len(violations) == 3


# ═══════════════════════════════════════════════════════════════════════════
# CQ-002: No-op function detection
# ═══════════════════════════════════════════════════════════════════════════


class TestCQ002NoopFunctions:
    """Tests for check_noop_functions.py (CQ-002)."""

    def test_should_detect_pass_only_function(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("def do_nothing():\n    pass\n")
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 1
        assert "CQ-002" in violations[0]
        assert "do_nothing" in violations[0]

    def test_should_detect_docstring_pass_function(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text('def do_nothing():\n    """Does nothing."""\n    pass\n')
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 1

    def test_should_detect_logger_only_function(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("def register_handlers():\n    logger.info('Registering handlers')\n")
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 1
        assert "register_handlers" in violations[0]

    def test_should_detect_docstring_logger_function(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text(
            'def register_handlers():\n'
            '    """Register all handlers."""\n'
            '    logger.info("Registering")\n'
            '    logger.debug("Done")\n'
        )
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 1

    def test_should_exempt_abstractmethod_when_decorated(self, tmp_path: Path) -> None:
        f = tmp_path / "base.py"
        f.write_text(
            "from abc import abstractmethod\n"
            "class Base:\n"
            "    @abstractmethod\n"
            "    def process(self):\n"
            "        pass\n"
        )
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 0

    def test_should_exempt_protocol_method_when_in_protocol_class(self, tmp_path: Path) -> None:
        f = tmp_path / "proto.py"
        f.write_text(
            "from typing import Protocol\n"
            "class Handler(Protocol):\n"
            "    def handle(self) -> None:\n"
            "        ...\n"
        )
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 0

    def test_should_exempt_init_when_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "cls.py"
        f.write_text(
            "class MyClass:\n"
            "    def __init__(self):\n"
            "        pass\n"
        )
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 0

    def test_should_exempt_pytest_fixture_when_decorated(self, tmp_path: Path) -> None:
        f = tmp_path / "conftest.py"
        f.write_text(
            "import pytest\n"
            "@pytest.fixture\n"
            "def empty_fixture():\n"
            "    pass\n"
        )
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 0

    def test_should_exempt_cq_exempt_comment_when_present(self, tmp_path: Path) -> None:
        f = tmp_path / "audit.py"
        f.write_text(
            "def emit_audit_event():  # cq-exempt: CQ-002 -- audit trail\n"
            "    logger.info('audit event')\n"
        )
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 0

    def test_should_pass_when_function_has_real_logic(self, tmp_path: Path) -> None:
        f = tmp_path / "good.py"
        f.write_text("def compute(x):\n    return x * 2\n")
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 0

    def test_should_pass_when_function_has_logger_and_logic(self, tmp_path: Path) -> None:
        f = tmp_path / "good.py"
        f.write_text(
            "def process(x):\n"
            "    logger.info('processing')\n"
            "    return x * 2\n"
        )
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 0

    def test_should_pass_silently_when_syntax_error(self, tmp_path: Path) -> None:
        f = tmp_path / "broken.py"
        f.write_text("def foo(\n")
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 0

    def test_should_detect_async_noop_function(self, tmp_path: Path) -> None:
        f = tmp_path / "async_bad.py"
        f.write_text("async def do_nothing():\n    pass\n")
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 1

    def test_should_detect_docstring_only_function(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text('def placeholder():\n    """TODO: implement this."""\n')
        violations = check_noop_functions.check_file(str(f))
        assert len(violations) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Shell hook: check-code-quality.sh
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckCodeQualityHook:
    """Tests for the check-code-quality.sh shell hook."""

    def _run_hook(self, hook_input: dict, cwd: str | None = None) -> subprocess.CompletedProcess:
        import json

        hook_path = REPO_ROOT / "hooks" / "check-code-quality.sh"
        return subprocess.run(
            ["bash", str(hook_path)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd,
        )

    def test_should_pass_when_non_python_file(self, tmp_path: Path) -> None:
        result = self._run_hook({
            "tool_input": {"file_path": "README.md"},
            "cwd": str(tmp_path),
        })
        assert result.returncode == 0

    def test_should_pass_when_no_file_path(self) -> None:
        result = self._run_hook({"tool_input": {}, "cwd": "."})
        assert result.returncode == 0

    def test_should_pass_when_file_does_not_exist(self, tmp_path: Path) -> None:
        result = self._run_hook({
            "tool_input": {"file_path": "new_module.py"},
            "cwd": str(tmp_path),
        })
        assert result.returncode == 0

    def test_should_block_when_mutable_global_found(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("handlers = []\n")
        result = self._run_hook({
            "tool_input": {"file_path": "bad.py"},
            "cwd": str(tmp_path),
        })
        assert result.returncode == 2
        assert "CQ-001" in result.stderr

    def test_should_block_when_noop_function_found(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def placeholder():\n    pass\n")
        result = self._run_hook({
            "tool_input": {"file_path": "bad.py"},
            "cwd": str(tmp_path),
        })
        assert result.returncode == 2
        assert "CQ-002" in result.stderr

    def test_should_pass_when_clean_python_file(self, tmp_path: Path) -> None:
        good_file = tmp_path / "good.py"
        good_file.write_text("MAX_RETRIES = 3\n\ndef compute(x):\n    return x * 2\n")
        result = self._run_hook({
            "tool_input": {"file_path": "good.py"},
            "cwd": str(tmp_path),
        })
        assert result.returncode == 0

    def test_should_block_path_traversal_when_dotdot_present(self, tmp_path: Path) -> None:
        result = self._run_hook({
            "tool_input": {"file_path": "../../../etc/passwd.py"},
            "cwd": str(tmp_path),
        })
        assert result.returncode == 2
        assert "Suspicious" in result.stderr


# ═══════════════════════════════════════════════════════════════════════════
# Enforcement annotation validation
# ═══════════════════════════════════════════════════════════════════════════


class TestEnforcementAnnotations:
    """Validate that all standards docs have Enforce: annotations."""

    STANDARDS_CODE_DIR = REPO_ROOT / "standards" / "code"
    STANDARDS_TESTING_DIR = REPO_ROOT / "standards" / "testing"

    # Standards docs that must have enforcement annotations per the spec
    CODE_DOCS = [
        "clean-code.md",
        "error-handling.md",
        "python-conventions.md",
        "typing-standards.md",
    ]

    TESTING_DOCS = [
        "testing-standards.md",
        "test-naming.md",
        "llm-evaluation.md",
    ]

    def test_should_have_enforce_annotation_in_clean_code(self) -> None:
        content = (self.STANDARDS_CODE_DIR / "clean-code.md").read_text()
        assert "**Enforce:**" in content

    def test_should_have_enforce_annotation_in_error_handling(self) -> None:
        content = (self.STANDARDS_CODE_DIR / "error-handling.md").read_text()
        assert "**Enforce:**" in content

    def test_should_have_enforce_annotation_in_python_conventions(self) -> None:
        content = (self.STANDARDS_CODE_DIR / "python-conventions.md").read_text()
        assert "**Enforce:**" in content

    def test_should_have_enforce_annotation_in_typing_standards(self) -> None:
        content = (self.STANDARDS_CODE_DIR / "typing-standards.md").read_text()
        assert "**Enforce:**" in content

    def test_should_have_enforce_annotation_in_testing_standards(self) -> None:
        content = (self.STANDARDS_TESTING_DIR / "testing-standards.md").read_text()
        assert "**Enforce:**" in content

    def test_should_have_enforce_annotation_in_test_naming(self) -> None:
        content = (self.STANDARDS_TESTING_DIR / "test-naming.md").read_text()
        assert "**Enforce:**" in content

    def test_should_have_enforce_annotation_in_llm_evaluation(self) -> None:
        content = (self.STANDARDS_TESTING_DIR / "llm-evaluation.md").read_text()
        assert "**Enforce:**" in content

    def test_should_exist_ruff_reference_toml(self) -> None:
        assert (self.STANDARDS_CODE_DIR / "ruff-reference.toml").exists()

    def test_should_exist_ruff_audit_md(self) -> None:
        assert (self.STANDARDS_CODE_DIR / "ruff-audit.md").exists()

    def test_should_exist_import_discipline_md(self) -> None:
        assert (self.STANDARDS_CODE_DIR / "import-discipline.md").exists()

    def test_should_exist_test_isolation_md(self) -> None:
        assert (self.STANDARDS_TESTING_DIR / "test-isolation.md").exists()

    def test_should_exist_fixture_fidelity_md(self) -> None:
        assert (self.STANDARDS_TESTING_DIR / "fixture-fidelity.md").exists()

    def test_should_include_required_ruff_rule_sets(self) -> None:
        """Verify ruff-reference.toml contains all required rule set prefixes."""
        content = (self.STANDARDS_CODE_DIR / "ruff-reference.toml").read_text()
        required_sets = [
            '"E"', '"F"', '"I"', '"W"', '"N"', '"UP"', '"B"',
            '"C90"', '"ERA"', '"SIM"', '"T20"', '"PLR"', '"ANN"',
            '"BLE"', '"TRY"', '"TCH"',
        ]
        for rule_set in required_sets:
            assert rule_set in content, f"Missing rule set {rule_set} in ruff-reference.toml"

    def test_should_set_mccabe_max_complexity(self) -> None:
        content = (self.STANDARDS_CODE_DIR / "ruff-reference.toml").read_text()
        assert "max-complexity = 10" in content

    def test_should_set_pylint_max_args(self) -> None:
        content = (self.STANDARDS_CODE_DIR / "ruff-reference.toml").read_text()
        assert "max-args = 5" in content

    def test_should_have_per_file_ignores_for_tests(self) -> None:
        content = (self.STANDARDS_CODE_DIR / "ruff-reference.toml").read_text()
        assert '"tests/**/*.py"' in content
        assert '"ANN"' in content
        assert '"PLR0913"' in content
