"""방송 로고 만들기(logo.py, secret.py): 입력 확인, 외부 SVG 정리, 기본 도형, 글꼴 윤곽선, 배치, AI 생성 표시,
OpenAI와 Recraft 요청 형식과 오류 안내(가짜 응답), API 키 보관, 생성 기록, 서버 요청, 명령줄."""

from __future__ import annotations

import base64
import http.client
import io
import json
import urllib.error
import xml.etree.ElementTree as ET

import pytest

from debutkit import logo
from debutkit.secret import KeyBox

pytest.importorskip("fontTools")
pytest.importorskip("brotli")

SVG = "{http://www.w3.org/2000/svg}"
KEY = "sk-test-abcdef123456"
EVIL = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 64 64" onload="steal()">'
        '<script>alert(1)</script><defs><linearGradient id="g"><stop offset="0" stop-color="#f00"/></linearGradient></defs>'
        '<circle cx="32" cy="32" r="20" fill="url(#g)" onclick="x()"/><rect width="5" height="5" fill="url(https://evil.example/a)"/>'
        '<image href="https://evil.example/x.png"/><foreignObject><div>hi</div></foreignObject><a href="https://evil.example"><path d="M0 0"/></a>'
        '<use xlink:href="https://evil.example/s.svg#a"/><use href="#g"/><style>@import url(https://evil.example/c.css);</style>'
        '<style>.a{fill:url(#g)}</style><path d="M1 1L2 2" style="fill:url(data:image/png;base64,AAAA)"/></svg>')


def fake_keys(tmp_path, name="keys.json"):
    return KeyBox(tmp_path / name, b"test", "debutkit-test", protect=lambda raw: b"S" + raw[::-1], unprotect=lambda raw: raw[1:][::-1])


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def opener_returning(svg: str, record: list | None = None, error: Exception | None = None):
    def opener(request, timeout):
        if record is not None:
            record.append((request.full_url, dict(request.header_items()), json.loads(request.data)))
        if error is not None:
            raise error
        return Reply(json.dumps({"data": [{"b64_json": base64.b64encode(svg.encode()).decode()}]}).encode())
    return opener


def http_error(status: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.example/v1", status, "error", {}, io.BytesIO(body.encode()))  # type: ignore[arg-type]


# --- 입력과 정리 ---------------------------------------------------------------------------


def test_input_checks_and_prompt():
    assert logo.check_color("ff4f8b") == "#FF4F8B" and logo.check_colors(["#000000", "#ffffff"]) == ["#000000", "#FFFFFF"]
    for bad in ("red", "#12345", None, 5):
        with pytest.raises(logo.LogoError):
            logo.check_color(bad)
    with pytest.raises(logo.LogoError):
        logo.check_colors(["#000000"] * 5)
    assert logo.check_name("  부동   채널 ") == "부동 채널"
    with pytest.raises(logo.LogoError):
        logo.check_name("가" * 31)
    for bad in ("", "  ", "x" * 301, None):
        with pytest.raises(logo.LogoError):
            logo.check_description(bad)
    assert logo.check_key(f"  {KEY} \n") == KEY
    for bad in ("short", "has space in key", "키값키값키값키값키값"):
        with pytest.raises(logo.LogoError):
            logo.check_key(bad)
    prompt = logo.build_prompt("고양이 귀 헤드폰", "cute", ["#FF4F8B"])
    assert "no text" in prompt and "#FF4F8B" in prompt and "고양이 귀 헤드폰" in prompt and "trademarks" in prompt


def test_sanitize_removes_active_and_external_content():
    clean = logo.sanitize_svg(EVIL)
    lowered = clean.lower()
    for bad in ("script", "onload", "onclick", "evil.example", "foreignobject", "<ns0:image", "image href", "data:", "@import", "<a "):
        assert bad not in lowered, bad
    root = ET.fromstring(clean)
    assert root.find(f"{SVG}circle").get("fill") == "url(#g)"  # 안쪽 참조는 유지
    assert root.find(f"{SVG}rect").get("fill") is None  # 바깥 주소 참조는 제거
    uses = root.findall(f"{SVG}use")
    assert [use.get("href") for use in uses] == [None, "#g"]
    assert [style.text for style in root.findall(f"{SVG}style")] == [".a{fill:url(#g)}"]
    for bad in ('<!DOCTYPE svg [<!ENTITY a "x">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>', "<html/>", "not xml", "",
                '<svg xmlns="http://www.w3.org/2000/svg">' + " " * logo.SVG_LIMIT + "</svg>"):
        with pytest.raises(logo.LogoError):
            logo.sanitize_svg(bad)


def test_view_box_and_templates():
    assert logo.view_box(ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0, 0, 64 32"/>')) == (0, 0, 64, 32)
    assert logo.view_box(ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg" width="200px" height="100"/>')) == (0, 0, 200, 100)
    assert logo.view_box(ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg"/>')) == (0, 0, 1024, 1024)
    for template in logo.TEMPLATES:
        root = ET.fromstring(logo.template_svg(template, "#112233", "#445566"))
        assert root.get("viewBox") == "0 0 100 100" and "#112233" in logo.template_svg(template, "#112233", "#445566")
    with pytest.raises(logo.LogoError):
        logo.template_svg("dragon")


# --- 글꼴과 조합 ---------------------------------------------------------------------------


def test_text_outline_and_missing_glyphs():
    shape = logo.text_shape("부동 Live", "pretendard")
    assert shape.path.startswith("M") and shape.width > 300 and 60 < shape.height < 130 and shape.top < 0 < shape.bottom + 30
    assert logo.text_shape("방송", "blackhan").width > 0
    with pytest.raises(logo.LogoError, match="글꼴에 없는 글자: 😀"):
        logo.text_shape("방송😀", "pretendard")
    with pytest.raises(logo.LogoError):
        logo.text_shape("방송", "comic")


@pytest.mark.parametrize("layout", ["horizontal", "vertical", "symbol", "name"])
def test_compose_layouts(layout):
    svg = logo.compose(logo.template_svg("heart"), "부동 채널", layout=layout, text_color="#ffffff", background="#2a1f3d")
    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(svg.split("\n", 1)[1])
    width, height = (float(value) for value in root.get("viewBox").split()[2:])
    assert width > 0 and height > 0 and root.get("width") == root.get("viewBox").split()[2]
    assert root.find(f"{SVG}title").text == ("부동 채널" if layout != "symbol" else "부동 채널")
    assert root.find(f"{SVG}rect").get("width") == root.get("width")  # 배경은 숫자 크기(일부 변환기가 % 미지원)
    groups = root.findall(f"{SVG}g")
    assert (len(groups) == 1) == (layout != "name") and root.find(f"{SVG}svg") is None  # 중첩 svg 없음
    text_paths = [path for path in root.findall(f"{SVG}path") if path.get("fill") == "#FFFFFF"]
    assert (len(text_paths) == 1) == (layout != "symbol")
    assert root.find(f"{SVG}metadata") is None and "기본 도형" in root.find(f"{SVG}desc").text or layout == "name"
    if layout == "horizontal":
        assert width > height


def test_compose_marks_ai_symbols_and_checks_inputs():
    svg = logo.compose(logo.sanitize_svg(EVIL), "AI 로고", source={"provider": "OpenAI", "model": "gpt-image-2.6-flare"})
    assert logo.AI_COMPOSITE in svg and "생성형 AI(OpenAI gpt-image-2.6-flare)" in svg and "Pretendard Bold" in svg
    assert "<script" not in svg.lower() and "evil" not in svg
    with pytest.raises(logo.LogoError, match="채널 이름 필요"):
        logo.compose(logo.template_svg("star"), "  ")
    with pytest.raises(logo.LogoError, match="심볼 필요"):
        logo.compose(None, "이름")
    with pytest.raises(logo.LogoError):
        logo.compose(logo.template_svg("star"), "이름", layout="diagonal")


# --- 생성형 AI 요청 ------------------------------------------------------------------------


def test_openai_and_recraft_requests():
    record: list = []
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
    assert logo.request_symbol("openai", KEY, "prompt", "fast", ["#FF4F8B"], opener=opener_returning(svg, record)) == (svg, "gpt-image-2.6-flare")
    url, headers, body = record[-1]
    assert url == "https://api.openai.com/v1/images/generations" and headers["Authorization"] == f"Bearer {KEY}"
    assert body == {"model": "gpt-image-2.6-flare", "prompt": "prompt", "output_format": "svg", "n": 1, "size": "1024x1024", "quality": "medium"}
    logo.request_symbol("openai", KEY, "prompt", "best", [], opener=opener_returning(svg, record))
    assert record[-1][2]["model"] == "gpt-image-2.6-sunburst" and record[-1][2]["quality"] == "high"
    logo.request_symbol("recraft", KEY, "prompt", "fast", ["#FF4F8B", "#1E2327"], opener=opener_returning(svg, record))
    url, headers, body = record[-1]
    assert url == "https://external.api.recraft.ai/v1/images/generations"
    assert body == {"model": "recraftv4_1_vector", "prompt": "prompt", "size": "1:1", "response_format": "b64_json",
                    "controls": {"colors": [{"rgb": [255, 79, 139]}, {"rgb": [30, 35, 39]}]}}
    logo.request_symbol("recraft", KEY, "prompt", "best", [], opener=opener_returning(svg, record))
    assert record[-1][2]["model"] == "recraftv4_1_pro_vector" and "controls" not in record[-1][2]


@pytest.mark.parametrize(("status", "body", "expected"), [
    (401, '{"error": {"message": "Incorrect API key provided"}}', "API 키가 올바르지 않음"),
    (403, '{"error": {"message": "Your organization must be verified to use the model"}}', "조직 인증 필요"),
    (403, "forbidden", "허용하지 않음"),
    (429, '{"error": {"message": "Rate limit"}}', "요청 한도 초과 또는 잔액 부족"),
    (400, '{"error": {"message": "Your request was rejected by the safety system", "code": "moderation_blocked"}}', "안전 정책"),
    (500, "oops", "서비스 오류(500)"),
    (400, f'{{"error": {{"message": "bad size for key {KEY}"}}}}', "요청 오류(400)"),
])
def test_error_messages(status, body, expected):
    with pytest.raises(logo.LogoError) as caught:
        logo.request_symbol("openai", KEY, "prompt", "fast", [], opener=opener_returning("", error=http_error(status, body)))
    assert expected in str(caught.value) and KEY not in str(caught.value)


SIMPLE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="#FF4F8B"/></svg>'


class FakeClaude:
    """anthropic.Anthropic 대신: API 키를 받아 beta.messages.stream을 가진 객체를 돌려준다.

    ``error`` 는 요청을 시작할 때, ``late=True`` 이면 응답을 받는 도중(get_final_message)에 일으킨다.
    """

    def __init__(self, text="", stop="end_turn", model="claude-opus-5-5", error=None, late=False):
        self.text, self.stop, self.model, self.error, self.late = text, stop, model, error, late
        self.calls: list = []
        self.keys: list = []
        self.open = 0  # 닫히지 않은 응답 흐름 수

    def __call__(self, key):
        from types import SimpleNamespace

        self.keys.append(key)
        return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=self._stream)))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeStream(self)


class _FakeStream:
    def __init__(self, fake):
        self.fake = fake

    def __enter__(self):
        if self.fake.error is not None and not self.fake.late:
            raise self.fake.error
        self.fake.open += 1
        return self

    def __exit__(self, *exc):
        self.fake.open -= 1
        return False

    def get_final_message(self):
        from types import SimpleNamespace

        if self.fake.error is not None:
            raise self.fake.error
        return SimpleNamespace(stop_reason=self.fake.stop, model=self.fake.model,
                               content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.fake.text)])


def test_claude_writes_svg_code():
    pytest.importorskip("anthropic")
    fake = FakeClaude(text="다음은 심볼입니다.\n```svg\n" + SIMPLE + "\n```", model="claude-opus-4-8")
    svg, model = logo.request_symbol("claude", KEY, "prompt", "fast", ["#FF4F8B"], claude=fake)
    assert svg == SIMPLE and model == "claude-opus-4-8" and fake.keys == [KEY]  # 거절 대체 모델이 응답하면 그 이름을 기록
    assert fake.open == 0  # 응답 흐름을 다 받은 뒤 닫음
    call = fake.calls[-1]
    assert call["model"] == "claude-opus-5-5" and call["max_tokens"] == 16000 and call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"] and call["output_config"] == {"effort": "low"}
    assert "SVG" in call["system"] and "text, letters" in call["system"] and call["messages"] == [{"role": "user", "content": "prompt"}]
    assert "thinking" not in call and "temperature" not in call  # Opus 5.5는 생각 끄기, 샘플링 값 미지원
    logo.request_symbol("claude", KEY, "prompt", "best", [], claude=fake)
    assert fake.calls[-1]["output_config"] == {"effort": "high"}
    with pytest.raises(logo.LogoError, match="사용 정책"):
        logo.request_symbol("claude", KEY, "p", "fast", [], claude=FakeClaude(stop="refusal"))
    with pytest.raises(logo.LogoError, match="SVG가 없음$"):
        logo.request_symbol("claude", KEY, "p", "fast", [], claude=FakeClaude(text="그릴 수 없습니다"))
    with pytest.raises(logo.LogoError, match="잘림"):
        logo.request_symbol("claude", KEY, "p", "fast", [], claude=FakeClaude(text="<svg xmlns=", stop="max_tokens"))


def test_claude_errors():
    anthropic = pytest.importorskip("anthropic")
    httpx2 = pytest.importorskip("httpx2")
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    def status(cls, code, message):
        return cls(message, response=httpx2.Response(code, request=request), body=None)
    cases = [
        (status(anthropic.AuthenticationError, 401, "invalid x-api-key"), "API 키가 올바르지 않음"),
        (status(anthropic.PermissionDeniedError, 403, "not allowed"), "허용하지 않음"),
        (status(anthropic.RateLimitError, 429, "rate limited"), "요청 한도 초과 또는 잔액 부족"),
        (status(anthropic.BadRequestError, 400, f"Your credit balance is too low {KEY}"), "요청 오류(400)"),
        (status(anthropic.APIStatusError, 529, "Overloaded"), "서비스 오류(529)"),
        (anthropic.APIConnectionError(request=request), "Claude에 연결하지 못함"),
        (anthropic.APITimeoutError(request=request), "240초 넘게 멈춤"),
    ]
    for error, expected in cases:
        for late in (False, True):  # 요청 시작 때와 응답을 받는 도중 모두
            fake = FakeClaude(error=error, late=late)
            with pytest.raises(logo.LogoError) as caught:
                logo.request_symbol("claude", KEY, "p", "fast", [], claude=fake)
            assert expected in str(caught.value) and KEY not in str(caught.value), (expected, late, str(caught.value))
            assert fake.open == 0


def test_studio_with_claude(tmp_path):
    pytest.importorskip("anthropic")
    fake = FakeClaude(text=SIMPLE)
    studio = logo.LogoStudio(keys=fake_keys(tmp_path), folder=tmp_path / "logos", claude=fake)
    studio.set_key("claude", KEY)
    made = studio.generate("claude", "best", "고양이 귀 마이크", "cute", ["#FF4F8B", "#1E2327"])
    assert made["provider"] == "Claude" and made["model"] == "claude-opus-5-5" and "#FF4F8B" in fake.calls[-1]["messages"][0]["content"]
    svg = studio.make({"name": "부동", "symbol": {"id": made["id"]}})
    assert logo.AI_COMPOSITE in svg and "생성형 AI(Claude claude-opus-5-5)" in svg
    assert list(studio.status()["providers"])[:3] == ["comfyui", "huggingface", "claude"]


def test_network_and_bad_answers():
    with pytest.raises(logo.LogoError, match="연결하지 못함") as caught:
        logo.request_symbol("recraft", KEY, "p", "fast", [], opener=opener_returning("", error=urllib.error.URLError(f"no route {KEY}")))
    assert KEY not in str(caught.value)

    def empty(request, timeout):
        return Reply(b'{"data": []}')
    with pytest.raises(logo.LogoError, match="SVG가 없음"):
        logo.request_symbol("openai", KEY, "p", "fast", [], opener=empty)

    def broken(request, timeout):
        return Reply(b"<html>")
    with pytest.raises(logo.LogoError, match="응답을 읽지 못함"):
        logo.request_symbol("openai", KEY, "p", "fast", [], opener=broken)


# --- 키 보관과 작업 공간 ---------------------------------------------------------------------


def test_key_box_modes(tmp_path):
    box = fake_keys(tmp_path)
    assert box.mode == "file" and not box.has("openai")
    box.save("openai", KEY)
    assert KEY not in (tmp_path / "keys.json").read_text(encoding="utf-8") and box.load("openai") == KEY and box.has("openai")
    assert box.clear("openai") and not box.clear("openai") and box.load("openai") is None
    memory = KeyBox(tmp_path / "m.json", b"t", "svc", platform="darwin", keyring_module=None)
    memory._keyring = None
    assert memory.mode == "memory"
    memory.save("recraft", KEY)
    assert memory.load("recraft") == KEY and not (tmp_path / "m.json").exists() and memory.clear("recraft")

    class FakeKeyring:
        store: dict = {}

        def set_password(self, service, name, value):
            self.store[(service, name)] = value

        def get_password(self, service, name):
            return self.store.get((service, name))

        def delete_password(self, service, name):
            del self.store[(service, name)]
    ring = KeyBox(tmp_path / "r.json", b"t", "svc", platform="linux", keyring_module=FakeKeyring())
    assert ring.mode == "keyring"
    ring.save("openai", KEY)
    assert ring.load("openai") == KEY and ring.has("openai") and ring.clear("openai") and not ring.has("openai")


def test_studio_generates_records_and_makes(tmp_path):
    record: list = []
    studio = logo.LogoStudio(keys=fake_keys(tmp_path), folder=tmp_path / "logos", opener=opener_returning(EVIL, record), clock=lambda: 1_800_000_000)
    with pytest.raises(logo.LogoError, match="키를 먼저 저장"):
        studio.generate("openai", "fast", "고양이 귀", "cute", [])
    assert studio.set_key("openai", KEY)["providers"]["openai"]["key_saved"] is True
    made = studio.generate("openai", "fast", "고양이 귀 헤드폰", "bold", ["#FF4F8B"])
    assert made["provider"] == "OpenAI" and made["model"] == "gpt-image-2.6-flare" and made["time"] == 1_800_000_000 and "svg" not in made
    assert "bold silhouette" in record[-1][2]["prompt"]
    saved = (tmp_path / "logos" / f"{made['id']}.svg").read_text(encoding="utf-8")
    assert "script" not in saved and json.loads((tmp_path / "logos" / "log.jsonl").read_text(encoding="utf-8").splitlines()[0])["id"] == made["id"]
    status = studio.status()
    assert status["recent"][0]["id"] == made["id"] and status["key_storage"] == "file" and status["busy"] is False
    assert KEY not in json.dumps(status)
    ai_logo = studio.make({"name": "부동", "symbol": {"id": made["id"]}})
    assert logo.AI_COMPOSITE in ai_logo
    plain = studio.make({"name": "부동", "symbol": {"template": "moon", "primary": "#000000", "accent": "#FFFFFF"}, "layout": "vertical"})
    assert logo.AI_COMPOSITE not in plain and "기본 도형" in plain
    with pytest.raises(logo.LogoError, match="찾지 못함"):
        studio.make({"name": "부동", "symbol": {"id": "missing"}})
    for bad in ({"provider": "midjourney"}, {"provider": "openai", "quality": "ultra"}, {"provider": "openai", "style": "noir"}):
        with pytest.raises(logo.LogoError):
            studio.generate(bad["provider"], bad.get("quality"), "설명", bad.get("style"), [])
    again = logo.LogoStudio(keys=fake_keys(tmp_path), folder=tmp_path / "logos")  # 저장한 기록 다시 읽기
    assert again.symbol(made["id"])["provider"] == "OpenAI" and "script" not in again.symbol(made["id"])["svg"]
    studio.set_key("openai", None)
    assert studio.status()["providers"]["openai"]["key_saved"] is False


# --- 서버와 명령줄 ---------------------------------------------------------------------------


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read()
    headers = dict(response.getheaders())
    conn.close()
    return response.status, data, headers


def test_server_routes(tmp_path):
    from debutkit.overlay.server import OverlayServer

    srv = OverlayServer(port=0).start()
    try:
        srv.logo.keys = fake_keys(tmp_path)
        srv.logo._opener = opener_returning(EVIL)
        code, body, _ = request(srv.port, "GET", "/logo")
        assert code == 200 and "로고 만들기".encode() in body
        status = json.loads(request(srv.port, "GET", "/logo/status")[1])
        assert set(status["providers"]) == {"comfyui", "huggingface", "claude", "openai", "recraft"} and "star" in status["templates"] and status["recent"] == []
        code, body, headers = request(srv.port, "GET", "/logo/symbol.svg?template=crown&primary=112233&accent=445566")
        assert code == 200 and b"#112233" in body and headers["Content-Type"] == "image/svg+xml" and "default-src 'none'" in headers["Content-Security-Policy"]
        assert request(srv.port, "GET", "/logo/symbol.svg?template=dragon")[0] == 400
        assert request(srv.port, "GET", "/logo/symbol.svg?id=nothing")[0] == 404
        code, body, _ = request(srv.port, "POST", "/logo/make", {"name": "부동", "symbol": {"template": "star"}})
        assert code == 200 and json.loads(body)["svg"].startswith("<?xml")
        code, body, _ = request(srv.port, "POST", "/logo/make", {"name": "", "symbol": {"template": "star"}})
        assert code == 400 and "채널 이름" in json.loads(body)["error"]
        code, body, _ = request(srv.port, "POST", "/logo/generate", {"provider": "openai", "description": "별"})
        assert code == 400 and "키를 먼저 저장" in json.loads(body)["error"]
        code, body, _ = request(srv.port, "POST", "/logo/key", {"provider": "openai", "key": KEY})
        assert code == 200 and json.loads(body)["providers"]["openai"]["key_saved"] and KEY.encode() not in body
        code, body, _ = request(srv.port, "POST", "/logo/generate", {"provider": "openai", "quality": "fast", "description": "별", "colors": ["#FF4F8B"]})
        made = json.loads(body)["symbol"]
        assert code == 200 and made["provider"] == "OpenAI"
        code, body, headers = request(srv.port, "GET", f"/logo/symbol.svg?id={made['id']}")
        assert code == 200 and b"script" not in body
        code, body, _ = request(srv.port, "POST", "/logo/make", {"name": "부동", "symbol": {"id": made["id"]}})
        assert logo.AI_COMPOSITE in json.loads(body)["svg"]
        assert json.loads(request(srv.port, "POST", "/logo/key", {"provider": "openai", "clear": True})[1])["providers"]["openai"]["key_saved"] is False
    finally:
        srv.stop()


def test_cli_logo(tmp_path, capsys, monkeypatch):
    from debutkit.cli import main

    out = tmp_path / "logo.svg"
    assert main(["logo", "make", "--name", "부동 채널", "--template", "heart", "--color", "#112233", "--layout", "vertical", "--out", str(out)]) == 0
    assert "로고 저장" in capsys.readouterr().out and "#112233" in out.read_text(encoding="utf-8")
    assert main(["logo", "list"]) == 0 and "heart(하트)" in capsys.readouterr().out
    assert main(["logo", "make", "--template", "star", "--out", str(out)]) == 1 and "채널 이름 필요" in capsys.readouterr().err
    assert main(["logo", "make", "--name", "x", "--ai", "openai", "--out", str(out)]) == 1 and "심볼 설명" in capsys.readouterr().err
    monkeypatch.setattr("debutkit.secret.dpapi", lambda raw, protect, entropy: (b"S" + raw) if protect else raw[1:])
    monkeypatch.setattr("sys.stdin", io.StringIO(KEY + "\n"))
    assert main(["logo", "key", "recraft", "--stdin"]) == 0
    printed = capsys.readouterr().out
    assert "Recraft 키" in printed and KEY not in printed
    assert main(["logo", "key", "recraft", "--clear"]) == 0 and "삭제" in capsys.readouterr().out
