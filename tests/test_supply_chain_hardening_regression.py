"""Regression checks for the production dependency and CI trust boundary."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"
SETUP_PYTHON_SHA = "a26af69be951a213d495a4c3e4e4022e16d87065"
SETUP_NODE_SHA = "49933ea5288caeca8642d1e84afbd3f7d6820020"


# Regression: SECURITY-003 — production Python dependencies floated without hashes.
# Found by /cso on 2026-08-12.
# Report: .gstack/security-reports/2026-08-12-155000.json
def test_production_lock_pins_every_requirement_with_hashes() -> None:
    lock = (ROOT / "requirements-fastapi.lock").read_text(encoding="utf-8")
    requirement_lines = [
        line for line in lock.splitlines() if line and not line.startswith((" ", "#", "--"))
    ]

    assert "--python-version 3.12" in lock
    assert "--python-platform x86_64-manylinux_2_28" in lock
    assert requirement_lines
    assert all(re.match(r"^[A-Za-z0-9_.-]+==[^ ;\\]+ \\?$", line) for line in requirement_lines)
    assert lock.count("--hash=sha256:") >= len(requirement_lines)


# Regression: SECURITY-006 — the production API container ran as root.
# Found by /cso on 2026-08-12.
# Report: .gstack/security-reports/2026-08-12-155000.json
def test_docker_uses_hashed_lock_and_runs_as_non_root() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "COPY requirements-fastapi.lock /workspace/test7/" in dockerfile
    assert (
        "pip install --no-cache-dir --require-hashes "
        "-r /workspace/test7/requirements-fastapi.lock"
    ) in dockerfile
    assert "install -d -o alloy -g alloy -m 0750 /workspace/test7/.cache/ai" in dockerfile
    assert re.search(r"(?m)^USER alloy$", dockerfile)
    assert re.search(r"(?m)^\.cache/?$", dockerignore)


# Regression: SECURITY-005 — CI executed mutable action release tags.
# Found by /cso on 2026-08-12.
# Report: .gstack/security-reports/2026-08-12-155000.json
def test_ci_actions_are_sha_pinned_with_read_only_contents() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    ci_lock = (ROOT / "requirements-ci.lock").read_text(encoding="utf-8")

    assert "permissions:\n  contents: read" in workflow
    assert workflow.count(f"actions/checkout@{CHECKOUT_SHA}") == 2
    assert f"actions/setup-python@{SETUP_PYTHON_SHA}" in workflow
    assert f"actions/setup-node@{SETUP_NODE_SHA}" in workflow
    assert not re.search(r"uses:\s+actions/[^@\s]+@v\d+", workflow)
    assert "cache-dependency-path: requirements-ci.lock" in workflow
    assert "pip install --require-hashes -r requirements-ci.lock" in workflow
    assert "run: python -m pytest tests -q" in workflow
    assert "pytest==" in ci_lock
    assert "--hash=sha256:" in ci_lock


# Regression: SECURITY-008 — workflow changes had no repository owner rule.
# Found by /cso on 2026-08-12.
# Report: .gstack/security-reports/2026-08-12-155000.json
def test_workflow_changes_require_repository_owner_review() -> None:
    codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")

    assert "/.github/workflows/ @Ttime-taek" in codeowners.splitlines()
