#!/usr/bin/env python3
"""CQ-002: Detect no-op functions whose body is only logging or pass.

Parses a Python file using the ast module and reports functions whose
body consists entirely of:
  - Only logger.*() calls (any logging method)
  - Only pass statements
  - Only docstring + pass
  - Only docstring + logger.*() calls

Exemptions:
  - Abstract methods (@abstractmethod)
  - Protocol methods (in classes inheriting Protocol)
  - __init__ methods
  - Functions decorated with @pytest.fixture
  - Lines with # cq-exempt: CQ-002 comment

Exit codes:
  0 = no violations
  1 = violations found

Output format (one per line):
  CQ-002:{line}:{col}: No-op function (body is only logging): {name}
"""

import ast
import sys
from pathlib import Path


def _is_abstractmethod(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function is decorated with @abstractmethod."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
            return True
        if isinstance(decorator, ast.Attribute) and decorator.attr == "abstractmethod":
            return True
    return False


def _is_pytest_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function is decorated with @pytest.fixture."""
    for decorator in node.decorator_list:
        # @pytest.fixture
        if isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
            if isinstance(decorator.value, ast.Name) and decorator.value.id == "pytest":
                return True
        # @fixture (bare import)
        if isinstance(decorator, ast.Name) and decorator.id == "fixture":
            return True
        # @pytest.fixture(...)
        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Attribute) and func.attr == "fixture":
                if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                    return True
    return False


def _is_protocol_class(class_node: ast.ClassDef) -> bool:
    """Check if a class inherits from Protocol."""
    for base in class_node.bases:
        if isinstance(base, ast.Name) and base.id == "Protocol":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "Protocol":
            return True
    return False


def _is_docstring(node: ast.AST) -> bool:
    """Check if a node is a docstring (Expr containing a Constant string)."""
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
        return isinstance(node.value.value, str)
    return False


def _is_pass(node: ast.AST) -> bool:
    """Check if a node is a pass statement."""
    return isinstance(node, ast.Pass)


def _is_logger_call(node: ast.AST) -> bool:
    """Check if a node is a logger.*() call."""
    if not isinstance(node, ast.Expr):
        return False
    if not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    # logger.info(), logger.debug(), log.warning(), etc.
    if isinstance(func, ast.Attribute):
        obj = func.value
        if isinstance(obj, ast.Name) and obj.id in ("logger", "log", "logging", "self.logger", "self.log"):
            return True
        # self.logger.info()
        if isinstance(obj, ast.Attribute) and obj.attr in ("logger", "log"):
            return True
    return False


def _is_noop_body(body: list[ast.AST]) -> bool:
    """Check if a function body is a no-op (only docstring, pass, logger calls)."""
    if not body:
        return True

    meaningful_stmts = []
    for stmt in body:
        if _is_docstring(stmt):
            continue  # Docstrings don't count
        meaningful_stmts.append(stmt)

    if not meaningful_stmts:
        # Body is only a docstring
        return True

    # All meaningful statements must be pass or logger calls
    for stmt in meaningful_stmts:
        if _is_pass(stmt):
            continue
        if _is_logger_call(stmt):
            continue
        return False

    return True


def _has_exempt_comment(source_lines: list[str], lineno: int) -> bool:
    """Check if the function def line has a cq-exempt: CQ-002 comment."""
    idx = lineno - 1
    if 0 <= idx < len(source_lines):
        return "# cq-exempt: CQ-002" in source_lines[idx]
    return False


def check_file(filepath: str) -> list[str]:
    """Check a Python file for no-op functions.

    Returns a list of violation strings.
    """
    path = Path(filepath)

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

    def _check_functions(nodes: list[ast.AST], in_protocol: bool = False) -> None:
        for node in nodes:
            # Handle class definitions
            if isinstance(node, ast.ClassDef):
                is_protocol = _is_protocol_class(node)
                _check_functions(node.body, in_protocol=is_protocol)
                continue

            # Handle function definitions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Exemptions
                if node.name == "__init__":
                    continue
                if _is_abstractmethod(node):
                    continue
                if in_protocol:
                    continue
                if _is_pytest_fixture(node):
                    continue
                if _has_exempt_comment(source_lines, node.lineno):
                    continue

                if _is_noop_body(node.body):
                    violations.append(
                        f"CQ-002:{node.lineno}:{node.col_offset}: "
                        f"No-op function (body is only logging): {node.name}"
                    )

                # Check nested functions
                _check_functions(node.body, in_protocol=in_protocol)

    _check_functions(tree.body)
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
