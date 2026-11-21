"""Offline regression checks for the hosted CI matrix configuration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_matrix_does_not_cancel_other_platforms():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    strategy = ci.split("    strategy:", 1)[1].split("    runs-on:", 1)[0]
    assert "fail-fast: false" in strategy

def test_matrix_covers_three_operating_systems_and_python_versions():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for runner in ("ubuntu-latest", "windows-latest", "macos-latest"):
        assert runner in ci
    for version in ("3.10", "3.12", "3.13"):
        assert version in ci

def test_ci_keeps_real_tests_enabled():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q" in ci
    assert "continue-on-error: true" not in ci
