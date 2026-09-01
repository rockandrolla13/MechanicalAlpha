import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BONDALPHA_SRC = ROOT / "src" / "bondalpha"
ALLOWED_BONDSIM_IMPORT_FILES = {BONDALPHA_SRC / "workflow.py"}


def test_bondalpha_does_not_import_bondsim_outside_compatibility_shim():
    violations = []
    for path in sorted(BONDALPHA_SRC.rglob("*.py")):
        if path in ALLOWED_BONDSIM_IMPORT_FILES:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "bondsim" or alias.name.startswith("bondsim."):
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "bondsim" or module.startswith("bondsim."):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert violations == []


def test_alpha_package_uses_neutral_public_primitives():
    expected = {
        ROOT / "src" / "mechanical_alpha" / "io.py",
        ROOT / "src" / "mechanical_alpha" / "hashing.py",
        ROOT / "src" / "mechanical_alpha" / "public_policy.py",
    }
    assert all(path.exists() for path in expected)
