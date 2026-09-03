from pathlib import Path

from scripts.publication.audit_public_repo import audit_tree


def _internal_company_name() -> str:
    return "elar" + "tek"


def test_audit_rejects_company_name(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        f"{_internal_company_name()} POS Platform", encoding="utf-8"
    )
    findings = audit_tree(tmp_path)
    assert any(f.rule == "internal-company-name" for f in findings)


def test_audit_rejects_private_windows_and_wsl_paths(tmp_path: Path):
    user = "Fer" + "hat"
    sep = chr(92)
    windows_path = "C:" + sep + "Users" + sep + user + sep + "secret"
    wsl_path = "/mnt/" + "c" + "/Users/" + user + "/private"
    (tmp_path / "notes.md").write_text(
        windows_path + "\n" + wsl_path,
        encoding="utf-8",
    )
    findings = audit_tree(tmp_path)
    assert {f.rule for f in findings} >= {"private-host-path"}


def test_audit_rejects_secret_assignment_in_config(tmp_path: Path):
    (tmp_path / ".env.example").write_text("API_KEY=real-looking-value", encoding="utf-8")
    findings = audit_tree(tmp_path)
    assert any(f.rule == "secret-assignment" for f in findings)


def test_audit_does_not_treat_test_fixture_token_as_secret_config(tmp_path: Path):
    (tmp_path / "test_fixture.py").write_text('token="wrong-token"', encoding="utf-8")
    assert audit_tree(tmp_path) == []


def test_audit_accepts_production_inspired_language(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        "A production-inspired POS backend workload.", encoding="utf-8"
    )
    assert audit_tree(tmp_path) == []
