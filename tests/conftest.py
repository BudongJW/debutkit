import pytest


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """모든 테스트에서 저장 설정 파일을 임시 폴더로: 실제 사용자 설정을 읽거나 쓰지 않는다."""
    monkeypatch.setenv("DEBUTKIT_SETTINGS", str(tmp_path / "debutkit-settings.json"))
