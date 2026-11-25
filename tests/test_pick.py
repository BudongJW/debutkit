"""뽑기판: 설정 확인, 배치와 수량, 비밀 유지, 되돌리기와 섞기, 저장, 시청자 참여 규칙, 공정성 확인 값, 서버 주소."""

import http.client
import json
import random
from collections import Counter

import pytest

from debutkit import pick, settings
from debutkit.overlay import feature
from debutkit.overlay.events import OverlayEvent, system_event
from debutkit.overlay.server import OverlayServer

PRIZES = [{"name": "비밀상품", "count": 1, "rare": True}, {"name": "노래 한 곡", "count": 2}]


def board(**changes):
    found = pick.PickBoard(rng=random.Random(5), load=False)
    if changes:
        found.update(changes)
    return found


def chat(text, name="시청자", platform="chzzk", role=""):
    return OverlayEvent(platform, "chat", name, (("text", text),), role=role)


def donation(amount, unit="원", text="", name="후원자", platform="soop"):
    return OverlayEvent(platform, "donation", name, (("text", text),), amount=float(amount), unit=unit)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


# --------------------------------------------------------------------------- 설정


def test_defaults_palette_and_options():
    config = pick.Config()
    assert config.cells == 20 and config.blank == "꽝" and sum(prize.count for prize in config.prizes) == 8
    assert len(pick.COLORS) == 13 and len(pick.THEMES) >= 6  # 방송 색(channel) + 12색 and len(pick.COVERS) >= 8 and len(pick.EFFECTS) - 2 >= 8
    for key, (_, hex_) in pick.COLORS.items():  # 고른 색 하나에서 나머지 색, 글자 색은 대비가 큰 쪽
        colors = pick.palette(key)
        assert colors["cover"] == hex_ and colors["on_cover"] in (pick.INK, pick.PAPER)
        assert pick.contrast(colors["cover"], colors["on_cover"]) >= 3.0, key
        assert pick.contrast(colors["board"], colors["text"]) >= 4.5, key
    custom = pick.palette("pink", {"cover": "#000000", "win": "#ffffff"})
    assert custom["cover"] == "#000000" and custom["on_cover"] == pick.PAPER and custom["on_win"] == pick.INK
    assert pick.palette("#123456")["base"] == "#123456"
    loaded = pick.parse_config({"color": "#AABBCC", "colors": {"board": "#FFFFFF", "text": ""}, "styles": {"title": {"size": 80}}})
    assert loaded.color == "#aabbcc" and loaded.colors == {"board": "#ffffff"} and loaded.styles["title"]["size"] == 80
    assert loaded.styles["caption"] == pick.DEFAULT_STYLES["caption"]
    # 방송 색(channel)은 설정 화면에서 고른 색을 따른다
    from debutkit.overlay import theme

    assert pick.palette("channel")["base"] == "#ff4f8b" and pick.Config().color == "channel"
    settings.save_data(theme.DATA, {"primary": "#3557d6", "highlight": "#ffd84d"})
    assert pick.palette("channel")["base"] == "#3557d6" and pick.options()["colors"]["channel"]["hex"] == "#3557d6"
    assert pick.parse_config({"caption": " 첫 줄 \n\n 둘째   줄 "}).caption == "첫 줄\n둘째 줄"


@pytest.mark.parametrize("changes, message", [
    ({"prizes": []}, "상품을 1개 이상 입력"),
    ({"prizes": [{"name": " ", "count": 1}]}, "상품 이름이 비어 있음"),
    ({"prizes": [{"name": "가" * 25}]}, "24자 이내"),
    ({"prizes": [{"name": "a"}, {"name": "a"}]}, "같은 이름의 상품이 2개: a"),
    ({"prizes": [{"name": "a", "count": 0}]}, "수량은 1에서 100 사이의 정수: a"),
    ({"prizes": [{"name": "a", "count": 1.5}]}, "수량은 1에서 100"),
    ({"prizes": [{"name": "a", "count": True}]}, "수량은 1에서 100"),
    ({"prizes": [{"name": f"p{i}"} for i in range(31)]}, "30종류까지"),
    ({"cells": 3}, "칸 수는 4에서 100 사이"),
    ({"cells": 101}, "칸 수는 4에서 100 사이"),
    ({"cells": 4, "prizes": [{"name": "a", "count": 5}]}, r"상품 수\(5\)가 칸 수\(4\)보다 많음"),
    ({"columns": 21}, "열 수는 0"),
    ({"title": "가" * 31}, "제목은 30자 이내"),
    ({"caption": "가\n나\n다\n라"}, "3줄 이내"),
    ({"blank": "가" * 25}, "빈칸 이름은 24자 이내"),
    ({"theme": "slot"}, "디자인은 card"),
    ({"color": "rainbow"}, "테마 색은 channel, pink"),
    ({"colors": {"cover": "red"}}, "덮개 색은 #RRGGBB"),
    ({"cover": "plaid"}, "덮개 무늬는"),
    ({"font": "comic"}, "글꼴은"),
    ({"effect": "glow"}, "당첨 효과는"),
    ({"miss_effect": "boom"}, "꽝 효과는"),
    ({"win_sound": "x"}, "당첨 소리는"),
    ({"miss_sound": "x"}, "꽝 소리는"),
    ({"seconds": 1}, "결과 표시 시간은 2초에서 30초 사이"),
    ({"scale": 200}, "크기는 40%에서 130% 사이"),
    ({"volume": -1}, "음량은 0에서 100 사이"),
    ({"position": "top"}, "위치는"),
    ({"styles": {"title": {"size": 10}}}, "제목 크기는 24px에서 120px 사이"),
    ({"styles": {"caption": {"line": 300}}}, "설명 줄 간격는 100%에서 220% 사이"),
    ({"styles": {"result": {"size": 200}}}, "결과 카드 크기는 60%에서 160% 사이"),
    ({"styles": {"title": {"align": "justify"}}}, "제목 정렬은"),
    ({"styles": {"result": {"color": "#12"}}}, "결과 카드 색은 #RRGGBB"),
    ({"viewers": {"command": "뽑기"}}, "참여 명령은 !로 시작"),
    ({"viewers": {"command": "!뽑 기"}}, "참여 명령은 !로 시작"),
    ({"viewers": {"command": "!추첨"}}, "다른 기능이 쓰는 명령"),
    ({"viewers": {"who": "anyone"}}, "열 수 있는 사람은"),
    ({"viewers": {"who": "donors", "donation_min": None}}, "후원 최소 금액"),
    ({"viewers": {"donation_min": -5}}, "0 이상의 정수"),
    ({"viewers": {"cooldown": 4000}}, "대기 시간은 0초에서 3600초 사이"),
    ({"viewers": {"per_viewer": 101}}, "시청자별 횟수는"),
    ({"viewers": {"platforms": []}}, "플랫폼을 1개 이상"),
    ({"viewers": {"platforms": ["afreeca"]}}, "플랫폼을 1개 이상"),
])
def test_invalid_settings_are_explained(changes, message):
    with pytest.raises(pick.PickError, match=message):
        pick.parse_config({"prizes": PRIZES, **changes})
    with pytest.raises(pick.PickError, match="설정 형식"):
        pick.parse_config(["not", "a", "dict"])


# --------------------------------------------------------------------------- 배치, 비밀, 조작


def test_layout_counts_quantities_and_system_random():
    assert isinstance(pick.PickBoard()._rng, random.SystemRandom)
    found = board(cells=10, prizes=[{"name": "노래 한 곡", "count": 2}, {"name": "소원", "count": 1}], blank="다음 기회에")
    layout = [cell["prize"] for cell in found.secret()["layout"]]
    assert Counter(layout) == {"노래 한 곡": 2, "소원": 1, "다음 기회에": 7}
    config = found.secret()["config"]
    assert config["cells"] == 10 and config["blank"] == "다음 기회에"
    tiers = {cell["prize"]: cell["tier"] for cell in found.secret()["layout"]}
    assert tiers == {"노래 한 곡": "win", "소원": "win", "다음 기회에": "miss"}
    assert pick.parse_config({"prizes": [{"name": "꽝 아님 꽝", "count": 1}, {"name": "금", "rare": True}]}).tier("꽝 아님 꽝") == "miss"
    orders = {tuple(pick.contents(pick.parse_config({"cells": 8, "prizes": PRIZES})))}
    assert orders == {("비밀상품", "노래 한 곡", "노래 한 곡", "꽝", "꽝", "꽝", "꽝", "꽝")}


def test_public_state_and_feed_never_leak_unopened_prizes():
    found = board(cells=12, prizes=PRIZES)
    subscriber, current = found.channel.subscribe()
    secret_cell = next(cell["n"] for cell in found.secret()["layout"] if cell["prize"] == "비밀상품")
    for value in (current, found.status(), found.proof()):
        assert "비밀상품" not in json.dumps(value, ensure_ascii=False)
    other = next(cell["n"] for cell in found.secret()["layout"] if cell["prize"] != "비밀상품")
    entry = found.open(other, by="고양이집사")
    published = subscriber.get_nowait()
    text = json.dumps(published, ensure_ascii=False)
    assert "비밀상품" not in text and published["event"]["entry"]["cell"] == other and "index" not in published["event"]["entry"]
    assert [cell for cell in published["cells"] if "prize" in cell] == [{"n": other, "open": True, "prize": entry["prize"], "tier": entry["tier"], "by": "고양이집사"}]
    assert "비밀상품" in json.dumps(found.secret(), ensure_ascii=False)  # 조작 화면 전용 조회에만
    found.update({"show_remaining": True})  # 남은 상품 요약을 켜면 이름과 개수만(위치 없음)
    state = found.status()
    assert {item["name"]: item["left"] for item in state["remaining"]} == {"비밀상품": 1, "노래 한 곡": 2 - (entry["prize"] == "노래 한 곡")}
    assert all("prize" not in cell for cell in state["cells"] if not cell["open"])
    found.open(secret_cell)
    assert any(cell.get("prize") == "비밀상품" for cell in found.status()["cells"])


def test_open_undo_reshuffle_reset_finish():
    found = board(cells=6, prizes=PRIZES)
    with pytest.raises(pick.PickError, match="칸 번호는 1에서 6 사이의 정수"):
        found.open(7)
    with pytest.raises(pick.PickError, match="칸 번호"):
        found.open(True)
    with pytest.raises(pick.PickError, match="되돌릴 칸 없음"):
        found.undo()
    entry = found.open(2, by="고양이집사")
    assert entry["cell"] == 2 and entry["source"] == "control" and entry["script"].startswith("고양이집사 님 2번 ")
    with pytest.raises(pick.PickError, match="이미 열린 칸: 2번"):
        found.open(2)
    third = found.open()  # 남은 칸 중 무작위
    assert third["cell"] != 2 and found.status()["opened"] == 2
    found.undo()
    log = found.secret()["log"]
    assert log[0]["undone"] and log[0]["cell"] == third["cell"] and found.status()["opened"] == 1
    before = found.secret()
    opened_prize = before["layout"][1]["prize"]
    after = found.reshuffle()
    assert after["layout"][1] == {**before["layout"][1]} and after["layout"][1]["prize"] == opened_prize  # 열린 칸은 그대로
    assert Counter(cell["prize"] for cell in after["layout"]) == Counter(cell["prize"] for cell in before["layout"])
    assert after["commit"]["round"] == before["commit"]["round"] + 1 and after["commit"]["hash"] != before["commit"]["hash"]
    assert len(after["rounds"]) == len(before["rounds"]) + 1
    reset = found.reset()
    assert reset["opened"] == 0 and not reset["finished"] and reset["commit"]["round"] == before["commit"]["round"] + 2 and len(reset["log"]) == 2  # 기록은 남김
    for _ in range(6):
        found.open()
    assert found.status()["finished"] and found.status()["commit"]["revealed"]  # 모두 열면 끝나고 공개
    with pytest.raises(pick.PickError, match="끝난 판"):
        found.open()
    with pytest.raises(pick.PickError, match="끝난 판"):
        found.reshuffle()
    found.undo()  # 모두 연 판은 마지막 칸 되돌리기 가능
    assert not found.status()["finished"]
    found.finish()
    with pytest.raises(pick.PickError, match="끝내고 공개한 판은 되돌릴 수 없음"):
        found.undo()
    with pytest.raises(pick.PickError, match="이미 끝난 판"):
        found.finish()
    finished = found.status()
    assert all("prize" in cell for cell in finished["cells"]) and sum(cell["open"] for cell in finished["cells"]) == 5


def test_visible_replay_and_log():
    found = board(cells=5, prizes=PRIZES)
    with pytest.raises(pick.PickError, match="다시 보일 결과 없음"):
        found.replay()
    found.open(1, by="a")
    subscriber, _ = found.channel.subscribe()
    replay = found.replay()
    sent = subscriber.get_nowait()
    assert sent["event"]["type"] == "replay" and sent["event"]["entry"]["cell"] == 1 and replay["entry"]["cell"] == 1
    assert found.channel.subscribe()[1]["event"]["type"] == "open"  # 다시 보이기는 새로 연결한 화면에 보내지 않음
    assert found.set_visible(False)["visible"] is False and found.status()["visible"] is False
    assert found.clear_log()["log"] == [] and found.status()["opened"] == 1


def test_live_prize_edit_keeps_opened_cells():
    found = board(cells=8, prizes=[{"name": "노래", "count": 2}, {"name": "소원", "count": 1}])
    round_before = found.status()["commit"]["round"]
    found.update({"title": "새 제목", "color": "mint"})  # 표시만 바꾸면 배치 그대로
    assert found.status()["commit"]["round"] == round_before and found.status()["display"]["title"] == "새 제목"
    song = next(cell["n"] for cell in found.secret()["layout"] if cell["prize"] == "노래")
    found.open(song)
    found.update({"prizes": [{"name": "노래", "count": 2}, {"name": "춤", "count": 3}]})
    layout = found.secret()["layout"]
    assert layout[song - 1] == {"n": song, "prize": "노래", "tier": "win", "open": True}
    assert Counter(cell["prize"] for cell in layout) == {"노래": 2, "춤": 3, "꽝": 3}
    assert found.status()["commit"]["round"] == round_before + 1
    with pytest.raises(pick.PickError, match="칸 수를 바꿀 수 없음"):
        found.update({"cells": 9})
    with pytest.raises(pick.PickError, match=r"남은 상품\(8\)이 남은 칸\(7\)보다 많음"):
        found.update({"prizes": [{"name": "춤", "count": 8}]})


def test_saved_boards():
    found = board(cells=6, prizes=PRIZES)
    first = found.secret()["board"]["id"]
    made = found.create_board("벌칙 판")
    assert made["board"]["name"] == "벌칙 판" and made["config"]["cells"] == 6 and len(made["boards"]) == 2
    empty = found.create_board(copy=False)
    assert empty["config"]["cells"] == 20 and empty["board"]["name"] == "판 3"
    found.switch_board(first)
    assert found.status()["board"]["id"] == first
    found.rename_board(first, "첫 판")
    with pytest.raises(pick.PickError, match="판 이름은 1자에서 20자"):
        found.rename_board(first, " ")
    with pytest.raises(pick.PickError, match="없는 판") as missing:
        found.switch_board("b00000000")
    assert missing.value.status == 404
    found.delete_board(first)
    assert found.status()["board"]["id"] != first and len(found.secret()["boards"]) == 2
    while len(found.secret()["boards"]) < pick.MAX_BOARDS:
        found.create_board()
    with pytest.raises(pick.PickError, match="12개까지"):
        found.create_board()
    for item in found.secret()["boards"][1:]:
        found.delete_board(item["id"])
    with pytest.raises(pick.PickError, match="마지막 판은 지울 수 없음"):
        found.delete_board(found.secret()["board"]["id"])


def test_state_persists_across_new_board_objects():
    first = pick.PickBoard()
    assert settings.load_data("pick.json") == {} and first.secret()["stored"] is False  # 처음 예시 판은 바꿀 때 저장
    first.update({"cells": 9, "prizes": PRIZES, "title": "저장 확인"})
    entry = first.open(4, by="고양이집사")
    first.create_board("둘째 판")
    first.switch_board(first.secret()["boards"][0]["id"])
    second = pick.PickBoard()
    assert second.secret()["layout"] == first.secret()["layout"] and second.status()["commit"] == first.status()["commit"]
    assert second.status()["display"]["title"] == "저장 확인" and second.secret()["log"][0]["script"] == entry["script"]
    assert [item["name"] for item in second.secret()["boards"]] == ["기본 판", "둘째 판"]
    assert second.status()["cells"][3]["by"] == "고양이집사"
    saved = settings.load_data("pick.json")
    saved["boards"][0]["layout"] = ["가짜"] * 9  # 설정과 맞지 않는 배치는 새로 섞음(열린 칸 없이)
    saved["boards"][1]["config"] = {"cells": "많이"}
    settings.save_data("pick.json", saved)
    third = pick.PickBoard()
    assert Counter(cell["prize"] for cell in third.secret()["layout"]) == {"비밀상품": 1, "노래 한 곡": 2, "꽝": 6}
    assert third.status()["opened"] == 0 and third.secret()["boards"][1]["total"] == 20


# --------------------------------------------------------------------------- 공정성 확인


def test_fairness_commitment_reveals_and_verifies():
    found = board(cells=6, prizes=PRIZES)
    published = found.status()["commit"]
    assert set(published) == {"round", "hash", "revealed"} and not published["revealed"]
    found.open(1)
    found.finish()
    revealed = found.status()["commit"]
    assert revealed["hash"] == published["hash"] and pick.verify(revealed["text"], published["hash"])
    lines = revealed["text"].split("\n")
    assert len(lines[0]) == 32 and lines[1:] == [f"{cell['n']}:{cell['prize']}" for cell in found.secret()["layout"]]
    assert not pick.verify(revealed["text"].replace("1:", "2:", 1), published["hash"])
    assert pick.commitment([cell["prize"] for cell in found.secret()["layout"]], revealed["salt"]) == published["hash"]
    again = board(cells=6, prizes=PRIZES)
    first_hash = again.status()["commit"]["hash"]
    again.reshuffle()  # 섞으면 지난 배치는 공개하고 새 값
    old = again.proof()["rounds"][-1]
    assert old["hash"] == first_hash and pick.verify(old["text"], first_hash) and old["reason"] == "reshuffle"
    assert again.proof()["current"]["hash"] != first_hash and "text" not in again.proof()["current"]


# --------------------------------------------------------------------------- 시청자 참여


def test_command_and_donation_number_parsing():
    assert pick.parse_command("!뽑기 7", "!뽑기") == (True, 7)
    assert pick.parse_command("!뽑기 7번 주세요", "!뽑기") == (True, 7)
    assert pick.parse_command("!뽑기", "!뽑기") == (True, None)
    assert pick.parse_command("!뽑기 아무거나", "!뽑기") == (True, None)
    assert pick.parse_command("!PICK 3", "!pick") == (True, 3)
    assert pick.parse_command("뽑기 7", "!뽑기") == (False, None) and pick.parse_command("!뽑기7", "!뽑기") == (False, None)
    assert pick.donation_numbers("!뽑기 3 7번", "!뽑기") == [3, 7]
    assert pick.donation_numbers("12", "!뽑기") == [12] and pick.donation_numbers("3, 5", "!뽑기") == [3, 5]
    assert pick.donation_numbers("3번째 후원인데 12번 열어 주세요", "!뽑기") == [12]
    assert pick.donation_numbers("응원합니다", "!뽑기") == []


def test_chat_opening_rules_permissions_cooldown_and_platforms():
    clock = Clock()
    found = pick.PickBoard(rng=random.Random(2), monotonic=clock)
    found.update({"cells": 10, "prizes": PRIZES})
    assert found.viewer_open(chat("!뽑기 3"))[1] == "시청자 참여 꺼짐"
    found.handle(chat("!뽑기 3"))
    assert found.status()["opened"] == 0
    found.update({"viewers": {"enabled": True, "cooldown": 30, "platforms": ["chzzk", "youtube"]}})
    opened, reason = found.viewer_open(chat("!뽑기 3", name="고양이집사"))
    assert reason == "" and opened[0]["cell"] == 3 and opened[0]["source"] == "chat" and opened[0]["by"] == "고양이집사"
    assert opened[0]["script"].startswith("고양이집사 님 3번 ")
    assert found.viewer_open(chat("!뽑기 4", name="고양이집사"))[1] == "대기 시간 남음(30초)"
    assert found.viewer_open(chat("!뽑기 4", name="고양이집사", platform="youtube"))[0]  # 다른 플랫폼은 다른 시청자
    assert found.viewer_open(chat("!뽑기 5", platform="soop"))[1] == "허용하지 않은 플랫폼"
    assert found.viewer_open(chat("!뽑기 3", name="새벽감성"))[1] == "이미 열린 칸: 3번"
    assert found.viewer_open(chat("!뽑기 11", name="새벽감성"))[1] == "없는 칸: 11번"
    assert found.viewer_open(chat("안녕하세요", name="새벽감성"))[1] == "참여 명령이 아님"
    clock.now += 31
    opened, _ = found.viewer_open(chat("!뽑기", name="고양이집사"))  # 번호 없으면 남은 칸 중 무작위
    assert opened and opened[0]["cell"] not in (3, 4)
    assert found.viewer_open(chat("!뽑기 9", name="매니저", role="moderator"))[0]  # 매니저는 대기 시간 없음
    assert found.viewer_open(chat("!뽑기 10", name="매니저", role="moderator"))[0]
    found.update({"viewers": {"per_viewer": 2}})
    clock.now += 100
    assert found.viewer_open(chat("!뽑기", name="고양이집사"))[1] == "이 판에서 2번까지"
    found.update({"viewers": {"who": "staff"}})
    assert found.viewer_open(chat("!뽑기", name="새 시청자"))[1] == "스트리머와 매니저만"
    assert found.viewer_open(chat("!뽑기", name="스트리머", role="owner"))[0]
    found.update({"viewers": {"who": "donors", "donation_min": 1000}})
    assert found.viewer_open(chat("!뽑기", name="새 시청자"))[1] == "후원으로만 열기"
    found.set_visible(False)
    assert found.viewer_open(chat("!뽑기", role="owner"))[1] == "판을 숨긴 상태"
    found.handle(system_event("!뽑기 1"))
    assert all(entry["platform"] != "system" for entry in found.secret()["log"])


def test_donation_opening_min_amount_units_numbers_and_repeat():
    found = pick.PickBoard(rng=random.Random(4))
    found.update({"cells": 12, "prizes": PRIZES, "viewers": {"enabled": True, "who": "all"}})
    assert found.viewer_open(donation(5000))[1] == "후원으로 열기 꺼짐"
    found.update({"viewers": {"donation_min": 1000}})
    assert found.viewer_open(donation(999))[1] == "최소 금액 미달(1,000원)"
    assert found.viewer_open(donation(9, "별풍선"))[1] == "최소 금액 미달(1,000원)"  # 별풍선 1개 100원
    assert found.viewer_open(donation(500, "bits", platform="twitch"))[1] == "최소 금액 미달(1,000원)"  # 원으로 환산 못 하는 단위
    opened, _ = found.viewer_open(donation(10, "별풍선", text="7번 열어 주세요", name="풍선 시청자"))
    assert [entry["cell"] for entry in opened] == [7] and opened[0]["source"] == "donation"
    assert opened[0]["script"] == f"풍선 시청자 님 별풍선 10개 후원 감사합니다. 7번 {opened[0]['prize']}{'' if opened[0]['tier'] == 'miss' else ' 당첨'}"
    again, _ = found.viewer_open(donation(1000, text="7"))  # 이미 열린 번호는 무작위
    assert len(again) == 1 and again[0]["cell"] != 7
    found.update({"viewers": {"repeat": True}})
    many, _ = found.viewer_open(donation(3500, text="!뽑기 1 2"))
    assert [entry["cell"] for entry in many][:2] == [1, 2] and len(many) == 3
    found.update({"viewers": {"donation_min": 0, "repeat": False}})
    assert len(found.viewer_open(donation(100, "bits", platform="twitch"))[0]) == 1  # 최소 0원이면 모든 후원
    found.update({"viewers": {"who": "staff"}})
    assert found.viewer_open(donation(50000))[1] == "후원으로 열기 꺼짐"
    found.update({"viewers": {"who": "donors", "donation_min": 1000, "repeat": True}})
    while not found.status()["finished"]:
        found.viewer_open(donation(100000))
    assert found.viewer_open(donation(100000))[1] == "끝난 판"


def test_test_event_from_control_page():
    found = pick.PickBoard(rng=random.Random(1))
    found.update({"cells": 6, "prizes": PRIZES, "viewers": {"enabled": True, "platforms": ["soop"], "donation_min": 1000}})
    answer = found.test_event({"kind": "chat", "name": "시험", "text": "!뽑기 2"})  # 시험 플랫폼은 항상 허용
    assert answer["reason"] == "" and answer["opened"][0]["cell"] == 2 and answer["opened"][0]["platform"] == "demo"
    assert found.test_event({"kind": "donation", "amount": 500})["reason"] == "최소 금액 미달(1,000원)"
    with pytest.raises(pick.PickError, match="시험 금액"):
        found.test_event({"kind": "donation", "amount": "많이"})


# --------------------------------------------------------------------------- 오버레이 서버


@pytest.fixture
def server():
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def request(srv, method, path, body=None, raw=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    payload = raw if raw is not None else json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    return response.status, response.getheader("Content-Type"), response.read()


def call(srv, path, body=None):
    status, _, raw = request(srv, "POST", path, body or {})
    return status, json.loads(raw)


def test_feature_is_registered():
    parts = feature.default_features(feature.Context(notify=print))
    found = next(part for part in parts if part.name == "pick")
    assert "pick" in found.feeds and found.taps[0].__self__.__class__ is pick.PickBoard
    assert set(found.static) == {"/pick", "/pick.js", "/pick.css", "/pick/control"}


def test_pages_and_routes(server):
    for path, marker in (("/pick", b"/pick.js"), ("/pick/control", "뽑기판".encode()), ("/pick.js", b"feeds=pick"), ("/pick.css", b".pk-cell")):
        status, _, body = request(server, "GET", path)
        assert status == 200 and marker in body, path
    status, body = call(server, "/pick/config", {"config": {"cells": 8, "prizes": PRIZES}})
    assert status == 200 and body["config"]["cells"] == 8
    secret = json.loads(request(server, "GET", "/pick/secret")[2])
    hidden = next(cell["n"] for cell in secret["layout"] if cell["prize"] == "비밀상품")
    for path in ("/pick/state", "/pick/proof"):
        status, kind, raw = request(server, "GET", path)
        assert status == 200 and kind == "application/json" and "비밀상품".encode() not in raw, path
    other = next(cell["n"] for cell in secret["layout"] if cell["n"] != hidden)
    status, body = call(server, "/pick/open", {"cell": other, "by": "고양이집사"})
    assert status == 200 and body["entry"]["cell"] == other
    status, body = call(server, "/pick/open", {"cell": other})
    assert status == 400 and body["error"] == f"이미 열린 칸: {other}번"
    assert call(server, "/pick/open", {"cell": 99})[0] == 400
    assert call(server, "/pick/open", {})[0] == 200
    assert call(server, "/pick/undo")[1]["opened"] == 1
    assert call(server, "/pick/replay")[0] == 200
    assert call(server, "/pick/reshuffle")[1]["commit"]["round"] > secret["commit"]["round"]
    assert call(server, "/pick/visible", {"visible": False})[1]["visible"] is False
    assert call(server, "/pick/visible", {"visible": True})[1]["visible"] is True
    status, body = call(server, "/pick/config", {"cells": 2})
    assert status == 400 and "칸 수는 4에서 100" in body["error"]
    status, _, raw = request(server, "POST", "/pick/config", raw=b"not json")
    assert status == 400 and json.loads(raw)["error"] == "바꿀 설정이 없음"
    big = {"config": {"cells": 100, "prizes": [{"name": f"상품 이름 {i:02d}번 조금 길게", "count": 3} for i in range(30)]}}
    status, body = call(server, "/pick/config", big)
    assert status == 400 and "칸 수를 바꿀 수 없음" in body["error"]  # 열린 칸이 있는 판
    call(server, "/pick/reset")
    assert call(server, "/pick/config", big)[0] == 200  # 긴 상품표(4096 바이트 이상)
    new = call(server, "/pick/board/new", {"name": "둘째 판", "copy": False})[1]
    assert new["board"]["name"] == "둘째 판" and len(new["boards"]) == 2
    assert call(server, "/pick/board/rename", {"id": new["board"]["id"], "name": "벌칙"})[1]["board"]["name"] == "벌칙"
    assert call(server, "/pick/board/switch", {"id": "b12345678"})[0] == 404
    assert call(server, "/pick/board/delete", {"id": new["board"]["id"]})[0] == 200
    assert call(server, "/pick/reset")[1]["opened"] == 0
    assert call(server, "/pick/finish")[1]["commit"]["revealed"] is True
    assert call(server, "/pick/log/clear")[1]["log"] == []
    assert call(server, "/pick/test", {"kind": "chat", "text": "!뽑기"})[1]["reason"] == "시청자 참여 꺼짐"


def test_live_feed_and_chat_tap(server):
    call(server, "/pick/config", {"cells": 6, "prizes": PRIZES, "viewers": {"enabled": True}})
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/live?feeds=pick")
    stream = conn.getresponse()

    def event():
        name = stream.fp.readline().decode().strip().removeprefix("event: ")
        data = json.loads(stream.fp.readline().decode().removeprefix("data: "))
        stream.fp.readline()
        return name, data

    name, first = event()
    assert name == "pick" and first["total"] == 6 and all("prize" not in cell for cell in first["cells"])
    server.hub.publish(OverlayEvent("chzzk", "chat", "고양이집사", (("text", "!뽑기 5"),)))
    name, opened = event()
    assert opened["event"]["type"] == "open" and opened["event"]["entry"]["cell"] == 5 and opened["event"]["entry"]["by"] == "고양이집사"
    assert "비밀상품" not in json.dumps(opened, ensure_ascii=False) or opened["event"]["entry"]["prize"] == "비밀상품"
    stream.close()
    conn.close()


def test_state_survives_server_restart():
    srv = OverlayServer([], port=0).start()
    try:
        call(srv, "/pick/config", {"cells": 9, "prizes": PRIZES, "title": "다시 시작"})
        call(srv, "/pick/open", {"cell": 3, "by": "고양이집사"})
        before = json.loads(request(srv, "GET", "/pick/secret")[2])
    finally:
        srv.stop()
    srv = OverlayServer([], port=0).start()
    try:
        after = json.loads(request(srv, "GET", "/pick/secret")[2])
        state = json.loads(request(srv, "GET", "/pick/state")[2])
    finally:
        srv.stop()
    assert after["layout"] == before["layout"] and after["commit"]["hash"] == before["commit"]["hash"]
    assert state["display"]["title"] == "다시 시작" and state["cells"][2]["open"] and state["cells"][2]["by"] == "고양이집사"
