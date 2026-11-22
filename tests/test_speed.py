import pytest

from debutkit import speed
from debutkit.doctor import FAIL, OK, WARN


def fake_upload(mbps, sent):
    """``mbps`` 속도의 회선: 보낸 크기만큼 시계를 앞으로."""
    now = [0.0]

    def send(body):
        sent.append(len(body))
        now[0] += 0.05 + len(body) * 8 / (mbps * 1_000_000)  # 지연 50 ms

    return send, lambda: now[0]


def test_measure_stops_when_a_transfer_takes_long():
    sent = []
    send, clock = fake_upload(20, sent)
    mbps = speed.measure_upload(send=send, clock=clock)
    assert 18 < mbps < 20  # 큰 전송일수록 지연의 영향이 작다
    assert sent == [1_000_000, 2_000_000, 4_000_000, 8_000_000]  # 8 MB가 3초 넘게 걸려 멈춤


def test_measure_slow_line_stays_in_budget():
    sent = []
    send, clock = fake_upload(2, sent)
    speed.measure_upload(send=send, clock=clock, budget=12)
    assert clock() < 15 and sent[-1] <= 4_000_000


def test_measure_failure():
    with pytest.raises(RuntimeError, match="측정하지 못함"):
        speed.measure_upload(send=lambda body: None, clock=lambda: 0.0, sizes=(1000, 2000))


@pytest.mark.parametrize("mbps, kbps, level", [(70, 6000, "ok"), (9, 6000, "ok"), (7, 4500, "ok"), (5, 3000, "warn"), (3.2, 2000, "warn"), (2.5, 0, "fail")])
def test_advice_keeps_headroom(mbps, kbps, level):
    advice = speed.advise(mbps)
    assert (advice.video_kbps, advice.level) == (kbps, level)
    if kbps:
        assert kbps + speed.AUDIO_KBPS <= mbps * 1000 * speed.HEADROOM


def test_check_text():
    assert speed.check(69.4).status == OK and "1080p 60fps, 영상 6,000 kbps" in speed.check(69.4).detail
    assert speed.check(5).status == WARN and speed.check(5).hint
    assert speed.check(1).status == FAIL and "유선" in speed.check(1).hint
