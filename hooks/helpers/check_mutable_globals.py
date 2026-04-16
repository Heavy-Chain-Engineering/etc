#!/usr/bin/env python3
"""CQ-001: Detect module-level mutable state assignments.

Parses a Python file using the ast module and reports module-level
assignments of mutable types: list(), [], dict(), {}, set(),
defaultdict(), deque().

Exemptions:
  - __init__.py files (legitimate re-export patterns)
  - Assignments with Final type annotation
  - Assignments inside if TYPE_CHECKING: blocks
  - Lines with # cq-exempt: CQ-001 comment

Exit codes:
  0 = no violations
  1 = violations found

Output format (one per line):
  CQ-001:{line}:{col}: Module-level mutable assignment: {name} = {type}
"""

import ast
import sys
from pathlib import Path

# Mutable constructor call names
MUTABLE_CALLS = frozenset({
    "list", "dict", "set", "defaultdict", "deque",
    "OrderedDict", "Counter",
})

# Mutable literal AST node types
MUTABLE_LITERALS = (ast.List, ast.Dict, ast.Set)


def _is_final_annotation(_target: ast.AST, node: ast.AST) -> bool:
    """Check if an assignment has a Final type annotation."""
    if isinstance(node, ast.AnnAssign) and node.annotation is not None:
        ann = node.annotation
        # Final or typing.Final
        if isinstance(ann, ast.Name) and ann.id == "Final":
            return True
        if isinstance(ann, ast.Attribute) and ann.attr == "Final":
            return True
        # Final[type]
        if isinstance(ann, ast.Subscript):
            value = ann.value
            if isinstance(value, ast.Name) and value.id == "Final":
                return True
            if isinstance(value, ast.Attribute) and value.attr == "Final":
                return True
    return False


def _is_type_checking_block(node: ast.AST) -> bool:
    """Check if a node is inside an if TYPE_CHECKING: block."""
    if isinstance(node, ast.If):
        test = node.test
        if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
            return True
        if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
            return True
    return False


def _get_mutable_type(value: ast.AST) -> str | None:
    """Return the mutable type name if value is a mutable constructor/literal."""
    if isinstance(value, MUTABLE_LITERALS):
        return type(value).__name__.lower()
    if isinstance(value, ast.Call):
        func = value.func
        if isinstance(func, ast.Name) and func.id in MUTABLE_CALLS:
            return func.id
        if isinstance(func, ast.Attribute) and func.attr in MUTABLE_CALLS:
            return func.attr
    return None


def _get_target_name(target: ast.AST) -> str | None:
    """Extract variable name from an assignment target."""
    if isinstance(target, ast.Name):
        return target.id
    return None


def _has_exempt_comment(line: str) -> bool:
    """Check if a source line has a cq-exempt: CQ-001 comment."""
    return "# cq-exempt: CQ-001" in line


def check_file(filepath: str) -> list[str]:
    """Check a Python file for module-level mutable state assignments.

    Returns a list of violation strings.
    """
    path = Path(filepath)

    # Exempt __init__.py files
    if path.name == "__init__.py":
        return []

    try:
        source = path.read_text()
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        # Pass silently on unparseable files (EC-006)
        return []

    source_lines = source.splitlines()
    violations = []

    for node in ast.iter_child_nodes(tree):
        # Skip if TYPE_CHECKING: blocks
        if _is_type_checking_block(node):
            continue

        # Check regular assignments: x = []
        if isinstance(node, ast.Assign):
            for target in node.targets:
                name = _get_target_name(target)
                if name is None:
                    continue
                mtype = _get_mutable_type(node.value)
                if mtype is None:
                    continue
                # Check for exempt comment
                line_idx = node.lineno - 1
                if line_idx < len(source_lines) and _has_exempt_comment(source_lines[line_idx]):
                    continue
                violations.append(
                    f"CQ-001:{node.lineno}:{node.col_offset}: "
                    f"Module-level mutable assignment: {name} = {mtype}"
                )

        # Check annotated assignments: x: list[str] = []
        elif isinstance(node, ast.AnnAssign):
            if node.value is None:
                continue
            target = node.target
            name = _get_target_name(target)
            if name is None:
                continue
            if _is_final_annotation(target, node):
                continue
            mtype = _get_mutable_type(node.value)
            if mtype is None:
                continue
            # Check for exempt comment
            line_idx = node.lineno - 1
            if line_idx < len(source_lines) and _has_exempt_comment(source_lines[line_idx]):
                continue
            violations.append(
                f"CQ-001:{node.lineno}:{node.col_offset}: "
                f"Module-level mutable assignment: {name} = {mtype}"
            )

    return violations


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <file.py>", file=sys.stderr)
        return 2

    violations = check_file(sys.argv[1])
    for v in violations:
        print(v)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
