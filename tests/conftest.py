import pytest


@pytest.fixture(autouse=True)
def isolated_support_state(tmp_path, monkeypatch):
    """Ticket database, uploads and operator login never touch the working directory during tests."""
    monkeypatch.setenv('GRAND_DB_PATH', str(tmp_path / 'support.sqlite3'))
    monkeypatch.setenv('GRAND_UPLOAD_DIR', str(tmp_path / 'uploads'))
    monkeypatch.delenv('GRAND_OPERATOR_CONFIG', raising=False)
    monkeypatch.delenv('GRAND_ADMIN_PASSWORD', raising=False)
    monkeypatch.delenv('GRAND_SESSION_SECRET', raising=False)
