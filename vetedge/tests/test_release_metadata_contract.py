from __future__ import annotations

import ast
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPOSITORY_ROOT / "pyproject.toml"
PACKAGE_INIT_PATH = REPOSITORY_ROOT / "vetedge" / "__init__.py"


def _package_version() -> str:
	tree = ast.parse(PACKAGE_INIT_PATH.read_text(encoding="utf-8"))
	for node in tree.body:
		if not isinstance(node, ast.Assign):
			continue
		if not any(
			isinstance(target, ast.Name) and target.id == "__version__"
			for target in node.targets
		):
			continue
		value = ast.literal_eval(node.value)
		assert isinstance(value, str)
		return value
	raise AssertionError("__version__ is not declared in vetedge/__init__.py")


def test_vetedge_2_release_version():
	assert _package_version() == "2.0.0"


def test_frappe_cloud_dependency_range_targets_v16_only():
	metadata = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
	frappe_dependencies = metadata["tool"]["bench"]["frappe-dependencies"]

	assert frappe_dependencies == {"frappe": ">=16.0.0-dev,<17.0.0"}
