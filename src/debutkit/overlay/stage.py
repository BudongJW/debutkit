"""방송 화면 미리보기(``/stage``): 채팅, 캐릭터, 알림, 추첨, 후원 벽, 뽑기판, 레이스를 OBS 장면과 같은 자리에 겹쳐 한 화면으로 본다.

- 시험 후원(``POST /stage/test``)은 플랫폼과 금액을 골라 시험 사건(플랫폼 demo)을 보낸다. 후원 하나가 알림, 추첨, 후원 벽, 뽑기판,
  참여 추첨에 함께 어떻게 보이는지 확인하는 용도. 시험 채팅(참가 명령 등)도 같은 방식
- 공통 화면 파일(ui.css, ui.js, theme.js)도 여기서 등록한다
"""

from __future__ import annotations

from typing import Any

from . import feature
from .events import OverlayEvent

#: 시험 후원 단위: 표시 이름, 사건 단위, 기본 금액
UNITS = {"won": ("원(치지직 치즈, YouTube 슈퍼챗)", "원", 1000), "balloon": ("SOOP 별풍선", "별풍선", 10), "adballoon": ("SOOP 애드벌룬", "애드벌룬", 100),
         "bits": ("Twitch 비트", "bits", 100)}
MAX_AMOUNT = 10_000_000


def make_feature(context: feature.Context) -> feature.Feature:
    def test(data: dict[str, Any]) -> dict[str, Any]:
        kind = data.get("kind", "donation")
        name = str(data.get("name") or "시험 시청자").strip()[:20] or "시험 시청자"
        if kind == "chat":
            text = str(data.get("text") or "").strip()[:200]
            if not text:
                raise feature.FeatureError("채팅 내용을 입력")
            context.publish(OverlayEvent("demo", "chat", name, (("text", text),)))
            return {"sent": "chat", "text": text}
        if kind == "member":
            context.publish(OverlayEvent("demo", "member", name, (("text", "구독"),)))
            return {"sent": "member"}
        unit = data.get("unit", "won")
        if unit not in UNITS:
            raise feature.FeatureError("단위는 " + ", ".join(UNITS))
        amount = data.get("amount", UNITS[unit][2])
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 < amount <= MAX_AMOUNT:
            raise feature.FeatureError("금액(개수)은 0보다 큰 숫자")
        message = str(data.get("text") or "시험 후원입니다").strip()[:200]
        context.publish(OverlayEvent("demo", "donation", name, (("text", message),), amount=float(amount), unit=UNITS[unit][1]))
        return {"sent": "donation", "amount": amount, "unit": UNITS[unit][1]}

    return feature.Feature(
        name="stage",
        static={"/stage": "stage.html", "/ui.css": "ui.css", "/ui.js": "ui.js", "/theme.js": "theme.js", "/live.js": "live.js",
                "/live-worker.js": "live-worker.js"},
        get={"/stage/units": lambda query: {key: {"name": name, "unit": unit, "amount": amount} for key, (name, unit, amount) in UNITS.items()}},
        post={"/stage/test": test},
    )
