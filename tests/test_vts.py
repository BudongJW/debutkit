"""VTube Studio 연동: 이 PC의 시험용 WebSocket 서버(tests/vts_fake.py)와 실제 프로토콜로 통신해 확인한다."""

import base64
import time

import pytest

pytest.importorskip("websocket")

from vts_fake import FakeVts  # noqa: E402

from debutkit import settings, vts  # noqa: E402
from debutkit.overlay.events import OverlayEvent  # noqa: E402


@pytest.fixture
def fake():
    server = FakeVts()
    yield server
    server.close()


def test_login_saves_token_and_reuses_it(fake):
    prompts = []
    client = vts.connect(fake.url, request_new=True, on_prompt=lambda: prompts.append(1))
    client.close()
    assert prompts == [1] and vts.load_token() == "new-token"
    assert vts.token_path().parent == settings.settings_path().parent and "new-token" not in str(settings.load())
    icon = base64.b64decode(fake.icons[0])
    assert icon.startswith(b"\x89PNG") and icon[16:24] == b"\x00\x00\x00\x80\x00\x00\x00\x80"  # 128x128
    with vts.connect(fake.url) as again:  # 저장한 토큰으로 바로 인증
        assert [model.name for model in again.models()] == ["Hiyori", "Neko Mio"]
    assert len(fake.icons) == 1
    assert vts.forget_token() and vts.load_token() is None


def test_missing_or_denied_token(fake):
    with pytest.raises(vts.VtsError, match="연결 전"):
        vts.connect(fake.url)
    vts.save_token("stale")
    with pytest.raises(vts.VtsError, match="더 이상 유효하지 않음"):
        vts.connect(fake.url)
    fake.deny = True
    with pytest.raises(vts.VtsError, match="허용하지 않음"):
        vts.connect(fake.url, request_new=True)


def test_models_load_hotkeys_and_trigger(fake):
    vts.save_token("good-token")
    with vts.connect(fake.url) as client:
        model = vts.find_model(client.models(), "neko")
        client.load_model(model.id)
        assert fake.loaded == ["m2"]
        assert [(hotkey.name, hotkey.kind) for hotkey in client.hotkeys()] == [("Heart", "ToggleExpression"), ("Clap", "TriggerAnimation")]
        client.trigger("Heart")
        assert fake.triggered == ["Heart"]
        with pytest.raises(vts.VtsError, match="VTube Studio 오류 202"):
            client.trigger("없는 단축키")
    with pytest.raises(vts.VtsError, match="다시 시작해야 표시"):
        vts.find_model([vts.Model("m1", "Hiyori", True)], "새 모델")


def test_unreachable_vts():
    with pytest.raises(vts.VtsError, match="연결하지 못함"):
        vts.VtsClient("ws://127.0.0.1:9", timeout=1)


def test_reaction_rules_and_units():
    rules = vts.parse_reactions(["0:Clap", "1000:Heart", "bad", "x:y", "5000: Big "])
    assert [(rule.min_won, rule.hotkey) for rule in rules] == [(5000, "Big"), (1000, "Heart"), (0, "Clap")]
    assert vts.pick_reaction(rules, 1000, "원").hotkey == "Heart"
    assert vts.pick_reaction(rules, 50, "별풍선").hotkey == "Big"  # 50개 = 5,000원
    assert vts.pick_reaction(rules, 999, "원").hotkey == "Clap"
    assert vts.pick_reaction(rules, 500, "bits").hotkey == "Clap"  # 환산하지 않는 단위는 최소 금액 0 규칙만
    assert vts.pick_reaction(vts.parse_reactions(["1000:Heart"]), 500, "bits") is None


def test_reactor_triggers_hotkeys_for_donations(fake):
    vts.save_token("good-token")
    notes = []
    reactor = vts.VtsReactor(vts.parse_reactions(["1000:Heart", "0:Clap"]), url=fake.url, notify=notes.append).start()
    try:
        reactor(OverlayEvent("chzzk", "chat", "a", (("text", "안녕"),)))
        reactor(OverlayEvent("chzzk", "donation", "b", (), amount=2000, unit="원"))
        reactor(OverlayEvent("youtube", "member", "c", ()))
        reactor(OverlayEvent("soop", "donation", "d", (), amount=1, unit="별풍선"))
        deadline = time.monotonic() + 5
        while len(fake.triggered) < 3 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert fake.triggered == ["Heart", "Clap", "Clap"] and notes == []
        fake.hotkeys.clear()  # 모델이 바뀌어 단축키가 없어진 경우
        reactor(OverlayEvent("chzzk", "donation", "e", (), amount=5000, unit="원"))
        deadline = time.monotonic() + 5
        while not notes and time.monotonic() < deadline:
            time.sleep(0.05)
        assert notes and "후원 반응 실패(Heart)" in notes[0]
    finally:
        reactor.stop()


def test_cli_vts_commands(fake, capsys):
    from debutkit import cli

    assert cli.main(["vts", "--url", fake.url, "models"]) == 1 and "연결 전" in capsys.readouterr().err
    assert cli.main(["vts", "--url", fake.url, "login"]) == 0 and "허용을 누르십시오" in capsys.readouterr().out
    assert cli.main(["vts", "--url", fake.url, "models"]) == 0 and "* Hiyori" in capsys.readouterr().out
    assert cli.main(["vts", "--url", fake.url, "load", "neko"]) == 0 and fake.loaded == ["m2"]
    assert cli.main(["vts", "--url", fake.url, "hotkeys"]) == 0 and "Heart" in capsys.readouterr().out
    assert cli.main(["vts", "--url", fake.url, "trigger", "Clap"]) == 0 and fake.triggered == ["Clap"]
    assert cli.main(["vts", "logout"]) == 0 and vts.load_token() is None


def test_overlay_saves_and_reads_reactions(tmp_path, capsys):
    from debutkit import cli

    args = cli.build_parser().parse_args(["overlay", "--save", "--vts-reaction", "1000:Heart", "--vts-reaction", "0:Clap"])
    cli._overlay_settings(args)
    assert settings.load()["vts_reactions"] == ["1000:Heart", "0:Clap"]
    later = cli.build_parser().parse_args(["overlay", "--saved"])
    cli._overlay_settings(later)
    assert later.vts_reaction == ["1000:Heart", "0:Clap"]

    class Server:
        hub = type("Hub", (), {"taps": []})()
        attached = []

        def attach(self, part):
            self.attached.append(part)

    cli._start_vts_reactions(Server(), later)
    assert "연결 전" in capsys.readouterr().out and not Server.attached
