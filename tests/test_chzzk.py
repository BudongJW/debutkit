import pytest

pytest.importorskip("stream2clip.chzzk_api")

from debutkit import chzzk  # noqa: E402


@pytest.fixture
def token(monkeypatch, tmp_path):
    path = tmp_path / "chzzk-token.json"
    monkeypatch.setenv("STREAM2CLIP_CHZZK_TOKEN", str(path))
    for name in ("CHZZK_CLIENT_ID", "CHZZK_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    return path


def test_login_without_credentials_explains_in_korean(token):
    with pytest.raises(chzzk.ChzzkLoginError, match="Client ID와 Client Secret 필요"):
        chzzk.login(open_browser=lambda url: None)


def test_login_redirect_must_be_local(token):
    with pytest.raises(chzzk.ChzzkLoginError, match="이 PC 주소"):
        chzzk.login("id", "secret", "https://example.com/callback", open_browser=lambda url: None)


def test_signed_in_and_logout(token):
    assert not chzzk.signed_in() and chzzk.logout() is None
    token.write_text("{}", encoding="utf-8")
    assert chzzk.signed_in()
    assert chzzk.logout() == token and not token.exists()


def test_use_credentials_sets_process_environment(token, monkeypatch):
    import os

    monkeypatch.setenv("CHZZK_CLIENT_ID", "old")  # 테스트가 끝나면 monkeypatch가 되돌린다
    monkeypatch.setenv("CHZZK_CLIENT_SECRET", "old")
    chzzk.use_credentials("id", "")  # 빈 값은 바꾸지 않는다
    assert os.environ["CHZZK_CLIENT_ID"] == "id" and os.environ["CHZZK_CLIENT_SECRET"] == "old"


def test_api_source_without_credentials_is_reported(token):
    from debutkit.overlay.events import chzzk_api_source

    with pytest.raises(chzzk.ChzzkLoginError, match="Client ID"):
        chzzk_api_source()
