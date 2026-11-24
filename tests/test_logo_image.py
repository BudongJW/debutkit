"""공개 이미지 모델 심볼: 배경 제거, 벡터화, ComfyUI와 Hugging Face Space 연결(가짜 서버), 로고 만들기 연결."""

from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.parse

import pytest

np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")
ImageDraw = pytest.importorskip("PIL.ImageDraw")

from debutkit import logo, logo_image  # noqa: E402
from debutkit.secret import KeyBox  # noqa: E402

TOKEN = "hf_testTOKEN1234567890abcdef"


def drawn(background=(16, 240, 16), size=512, scale=4) -> bytes:
    """모델 출력처럼 안티에일리어싱된 평면 심볼: 진한 테두리의 분홍 원, 흰 눈, 크림색 귀."""
    big = Image.new("RGB", (size * scale, size * scale), background)
    pen = ImageDraw.Draw(big)
    s = scale
    pen.polygon([(150 * s, 170 * s), (170 * s, 60 * s), (230 * s, 140 * s)], fill=(250, 247, 245), outline=(30, 35, 39), width=10 * s)
    pen.ellipse((110 * s, 120 * s, 400 * s, 410 * s), fill=(255, 79, 139), outline=(30, 35, 39), width=14 * s)
    pen.ellipse((200 * s, 220 * s, 240 * s, 260 * s), fill=(255, 255, 255))
    pen.ellipse((280 * s, 220 * s, 320 * s, 260 * s), fill=(255, 255, 255))
    image = big.resize((size, size), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def png(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# --- 지시문 ------------------------------------------------------------------------------


def test_key_colour_avoids_the_palette():
    assert logo_image.key_colour(["#FF4F8B", "#1E2327"]) == logo_image.GREEN
    assert logo_image.key_colour(["#22CC44"]) == logo_image.MAGENTA  # 초록 계열을 쓰면 자홍 배경
    assert logo_image.key_colour(["#7A8A7A"]) == logo_image.GREEN  # 채도가 낮은 회색 계열은 상관없음
    prompt = logo_image.raster_prompt("고양이 귀 마이크", "cute", ["#FF4F8B"], logo_image.GREEN)
    assert "No text" in prompt and "#00FF00" in prompt and "#FF4F8B" in prompt and "고양이 귀 마이크" in prompt
    assert "#FF00FF" in logo_image.raster_prompt("별", "cute", [], logo_image.MAGENTA)


# --- 배경 제거와 벡터화 --------------------------------------------------------------------


def test_cut_out_removes_the_background_and_its_halo():
    cut = logo_image.cut_out(drawn(), logo_image.GREEN)
    pixels = np.asarray(cut).astype(int)
    alpha = pixels[..., 3]
    assert alpha[5, 5] == 0 and alpha[256, 256] == 255  # 배경은 투명, 원 안은 불투명
    rim = (alpha > 0) & (alpha < 255)
    assert rim.any()
    greenish = (pixels[..., 1] > pixels[..., 0] + 40) & (pixels[..., 1] > pixels[..., 2] + 40)
    assert not (greenish & (alpha > 20)).any()  # 가장자리에 초록 기운이 남지 않음
    assert 0.2 < logo_image.coverage(cut) < 0.5
    white = pixels[240, 220]
    assert white[3] == 255 and min(white[:3]) > 240  # 흰 눈은 배경과 색이 달라 그대로


def test_dull_green_is_keyed_everywhere():
    """모델이 순수 초록 대신 탁한 초록을 칠해도 크로마 키로: 도형이 감싼 고리 안 배경까지 지운다."""
    big = Image.new("RGB", (2048, 2048), (91, 198, 105))
    pen = ImageDraw.Draw(big)
    pen.ellipse((440, 480, 1600, 1640), fill=(250, 232, 189), outline=(34, 38, 66), width=40)
    pen.ellipse((1500, 1500, 1900, 1900), outline=(64, 38, 76), width=36)  # 케이블 고리: 안쪽은 배경
    cut = logo_image.cut_out(png(big.resize((512, 512), Image.Resampling.LANCZOS)), logo_image.GREEN)
    pixels = np.asarray(cut).astype(int)
    assert pixels[5, 5, 3] == 0 and pixels[425, 425, 3] == 0  # 바깥 배경과 고리 안 배경
    assert pixels[256, 256, 3] == 255
    greenish = (pixels[..., 1] > pixels[..., 0] + 40) & (pixels[..., 1] > pixels[..., 2] + 40)
    assert not (greenish & (pixels[..., 3] > 20)).any()


def test_near_identical_colours_merge():
    image = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    pen.rectangle((20, 20, 99, 179), fill=(250, 232, 189, 255))
    pen.rectangle((100, 20, 179, 179), fill=(252, 231, 186, 255))  # 눈으로 구분되지 않는 크림색
    pen.rectangle((60, 80, 140, 120), fill=(34, 38, 66, 255))
    poster = logo_image.posterize(image)
    assert len(poster.palette) == 2


def test_real_model_sample_vectorizes_cleanly():
    """AI Horde FLUX.1 schnell(Apache-2.0) 실제 출력: 탁한 초록(약 91,198,105) 배경과 고리 모양 케이블."""
    from pathlib import Path

    data = (Path(__file__).parent / "data" / "logo_flux_schnell_dull_green.webp").read_bytes()
    svg = logo.sanitize_svg(logo_image.symbol_svg(data, logo_image.GREEN))
    fills = [tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)) for value in re.findall(r'fill="#([0-9A-F]{6})"', svg)]
    assert not any(g > r + 30 and g > b + 30 for r, g, b in fills)  # 초록 잔여 없음
    creams = [fill for fill in fills if min(fill) > 170]
    assert len(creams) == 1 and 3 <= len(fills) <= 7  # 넓은 크림색 면이 한 색
    assert len(svg) < 200_000


def test_cut_out_uses_the_drawn_background_when_it_differs():
    data = drawn(background=(40, 40, 200))  # 요청과 다른 파란 단색 배경: 테두리와 이어진 부분만 지움
    cut = logo_image.cut_out(data, logo_image.GREEN)
    alpha = np.asarray(cut)[..., 3]
    assert alpha[5, 5] == 0 and alpha[256, 256] == 255


def test_symbol_svg_is_clean_vector():
    svg = logo_image.symbol_svg(drawn(), logo_image.GREEN)
    cleaned = logo.sanitize_svg(svg)
    assert 'viewBox="0 0 1024 1024"' in cleaned and cleaned.count("<path") >= 3
    fills = [tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)) for value in re.findall(r'fill="#([0-9A-F]{6})"', cleaned)]
    assert any(r > 200 and g < 130 for r, g, b in fills)  # 분홍
    assert any(max(r, g, b) < 70 for r, g, b in fills)  # 진한 테두리
    assert not any(g > r + 60 and g > b + 60 for r, g, b in fills)  # 초록 없음
    assert len(fills) <= logo_image.TRACE_COLORS
    composed = logo.compose(cleaned, "부동", source={"provider": "ComfyUI", "model": "Qwen-Image"})
    assert logo.AI_COMPOSITE in composed


def test_symbol_svg_refuses_pictures_without_a_background():
    empty = png(Image.new("RGB", (256, 256), (0, 255, 0)))
    with pytest.raises(logo_image.ImageModelError, match="남은 그림"):
        logo_image.symbol_svg(empty, logo_image.GREEN)
    rng = np.random.default_rng(1)
    noise = png(Image.fromarray(rng.integers(0, 255, (256, 256, 3), dtype=np.uint8)))
    with pytest.raises(logo_image.ImageModelError, match="배경"):
        logo_image.symbol_svg(noise, logo_image.GREEN)
    with pytest.raises(logo_image.ImageModelError, match="읽지 못함"):
        logo_image.symbol_svg(b"not an image", logo_image.GREEN)


def test_square_crop_centres_the_content():
    image = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((300, 50, 379, 149), fill=(255, 0, 0, 255))
    square = logo_image.square_crop(image, size=100, margin=0.0)
    alpha = np.asarray(square)[..., 3]
    assert square.size == (100, 100) and alpha[50, 50] == 255 and alpha[2, 50] == 255  # 80x100 내용이 세로를 가득
    assert alpha[50, 2] == 0  # 좌우는 가운데 정렬 여백


def test_boundary_loops_follow_pixel_edges():
    block = np.zeros((4, 4), dtype=bool)
    block[1:3, 1:3] = True
    loops = logo_image._boundary_loops(block)
    assert len(loops) == 1 and sorted(loops[0]) == sorted([(1, 1), (2, 1), (3, 1), (3, 2), (3, 3), (2, 3), (1, 3), (1, 2)])
    ring = np.ones((5, 5), dtype=bool)
    ring[2, 2] = False
    assert len(logo_image._boundary_loops(ring)) == 2  # 바깥과 구멍
    diagonal = np.array([[True, False], [False, True]])
    assert len(logo_image._boundary_loops(diagonal)) == 2  # 꼭짓점만 닿은 두 픽셀은 따로


def test_trace_stacks_layers_largest_first():
    labels = np.full((40, 40), -1, dtype=np.int32)
    labels[5:35, 5:35] = 0
    labels[15:25, 15:25] = 1
    svg = logo_image.trace(logo_image.Poster(labels, [(255, 79, 139), (30, 35, 39)]))
    assert svg.index('fill="#FF4F8B"') < svg.index('fill="#1E2327"')
    assert logo.sanitize_svg(svg).count("<path") == 2


# --- ComfyUI(가짜 서버) ---------------------------------------------------------------------


def http_error(url: str, code: int, body: bytes = b"") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "error", {}, io.BytesIO(body))


class FakeComfy:
    """ComfyUI HTTP 응답 흉내: /object_info, /prompt, /history, /view."""

    def __init__(self, *, unets=("qwen_image_2512_fp8_e4m3fn.safetensors", "qwen_image_edit_fp8.safetensors", "qwen_image_2.1.safetensors"),
                 clips=("qwen_2.5_vl_7b_fp8_scaled.safetensors",), vaes=("qwen_image_vae.safetensors",),
                 loras=("Qwen-Image-Lightning-8steps-V1.1.safetensors",), types=("stable_diffusion", "qwen_image"), combo=False,
                 history_error=None, image=None, rounds=2):
        self.unets, self.clips, self.vaes, self.loras, self.types = unets, clips, vaes, loras, types
        self.combo, self.history_error, self.image, self.rounds = combo, history_error, image or drawn(), rounds
        self.workflows: list[dict] = []
        self.polls = 0

    def _list(self, values):
        return ["COMBO", {"options": list(values)}] if self.combo else [list(values)]

    def __call__(self, request, timeout=None):
        url = request.full_url
        path = urllib.parse.urlsplit(url).path
        if path == "/object_info/UNETLoader":
            return self._json({"UNETLoader": {"input": {"required": {"unet_name": self._list(self.unets), "weight_dtype": [["default"]]}}}})
        if path == "/object_info/UnetLoaderGGUF":
            raise http_error(url, 404)
        if path == "/object_info/CLIPLoader":
            return self._json({"CLIPLoader": {"input": {"required": {"clip_name": self._list(self.clips), "type": self._list(self.types)}}}})
        if path == "/object_info/VAELoader":
            return self._json({"VAELoader": {"input": {"required": {"vae_name": self._list(self.vaes)}}}})
        if path == "/object_info/LoraLoaderModelOnly":
            return self._json({"LoraLoaderModelOnly": {"input": {"required": {"lora_name": self._list(self.loras)}}}})
        if path == "/prompt":
            self.workflows.append(json.loads(request.data)["prompt"])
            return self._json({"prompt_id": "p1", "number": 1, "node_errors": {}})
        if path == "/history/p1":
            self.polls += 1
            if self.polls < self.rounds:
                return self._json({})
            if self.history_error:
                return self._json({"p1": {"status": {"status_str": "error", "completed": False,
                                                     "messages": [["execution_error", {"node_type": "KSampler", "exception_message": self.history_error}]]},
                                          "outputs": {}}})
            return self._json({"p1": {"status": {"status_str": "success", "completed": True},
                                      "outputs": {"11": {"images": [{"filename": "debutkit_logo_00001_.png", "subfolder": "", "type": "output"}]}}}})
        if path == "/view":
            assert urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["filename"] == ["debutkit_logo_00001_.png"]
            return io.BytesIO(self.image)
        raise AssertionError(url)

    @staticmethod
    def _json(data):
        return io.BytesIO(json.dumps(data).encode())


def test_comfy_fast_uses_lightning():
    fake = FakeComfy()
    made = logo_image.comfy_image(None, "prompt", "fast", opener=fake, seed=42, sleep=lambda _: None)
    flow = fake.workflows[-1]
    assert flow["1"]["inputs"]["unet_name"] == "qwen_image_2512_fp8_e4m3fn.safetensors"  # 편집, 2.1(연구용) 모델 제외
    assert flow["2"]["inputs"] == {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"}
    assert flow["4"]["inputs"]["lora_name"].startswith("Qwen-Image-Lightning") and flow["5"]["inputs"]["model"] == ["4", 0]
    sampler = flow["9"]["inputs"]
    assert (sampler["steps"], sampler["cfg"], sampler["seed"]) == (8, 1.0, 42) and flow["8"]["inputs"]["width"] == 1024
    assert flow["6"]["inputs"]["text"] == "prompt" and flow["11"]["class_type"] == "SaveImage"
    assert made.seed == 42 and made.master == fake.image and "Lightning" in made.model and "ComfyUI" in made.model


def test_comfy_best_without_lora_and_new_combo_format():
    fake = FakeComfy(combo=True)
    logo_image.comfy_image("http://192.168.0.20:8188/", "prompt", "best", opener=fake, seed=1, sleep=lambda _: None)
    flow = fake.workflows[-1]
    assert "4" not in flow and flow["5"]["inputs"]["model"] == ["1", 0]
    assert (flow["9"]["inputs"]["steps"], flow["9"]["inputs"]["cfg"], flow["8"]["inputs"]["width"]) == (30, 2.5, 1328)
    assert flow["7"]["inputs"]["text"] == logo_image.NEGATIVE


def test_comfy_explains_missing_files_and_failures():
    with pytest.raises(logo_image.ImageModelError, match="diffusion_models.*vae"):
        logo_image.comfy_image(None, "p", "fast", opener=FakeComfy(unets=("sdxl.safetensors",), vaes=()), sleep=lambda _: None)
    with pytest.raises(logo_image.ImageModelError, match="업데이트"):
        logo_image.comfy_image(None, "p", "fast", opener=FakeComfy(types=("stable_diffusion",)), sleep=lambda _: None)
    with pytest.raises(logo_image.ImageModelError, match="그래픽 메모리 부족"):
        logo_image.comfy_image(None, "p", "fast", opener=FakeComfy(history_error="CUDA out of memory"), sleep=lambda _: None)
    with pytest.raises(logo_image.ImageModelError, match="KSampler"):
        logo_image.comfy_image(None, "p", "fast", opener=FakeComfy(history_error="bad tensor"), sleep=lambda _: None)
    ticks = iter(range(0, 100000, 100))
    with pytest.raises(logo_image.ImageModelError, match="끝나지 않음"):
        logo_image.comfy_image(None, "p", "fast", opener=FakeComfy(rounds=10**6), sleep=lambda _: None, clock=lambda: next(ticks), timeout=600)

    def refused(request, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError(10061, "refused"))
    with pytest.raises(logo_image.ImageModelError, match="연결하지 못함.*127.0.0.1:8188"):
        logo_image.comfy_image(None, "p", "fast", opener=refused, sleep=lambda _: None)
    with pytest.raises(logo_image.ImageModelError, match="주소 형식"):
        logo_image.check_address("file:///etc/passwd")
    assert logo_image.check_address(" http://127.0.0.1:8188/ ") == "http://127.0.0.1:8188"


# --- Hugging Face Space(가짜 서버) ----------------------------------------------------------


class FakeSpace:
    """Hugging Face API와 Gradio 큐 응답 흉내."""

    def __init__(self, *, stages=None, completed=None, parameters=None, file_url=None, meta_status=200, image=None):
        self.stages = stages or {}
        self.completed = completed
        self.parameters = parameters or logo_image.SPACE_PARAMETERS
        self.file_url = file_url
        self.meta_status = meta_status
        self.image = image or drawn()
        self.joined: list[dict] = []
        self.headers: list[dict] = []

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.headers.append(dict(request.header_items()))
        parts = urllib.parse.urlsplit(url)
        if parts.netloc == "huggingface.co":
            if self.meta_status != 200:
                raise http_error(url, self.meta_status)
            space = parts.path.removeprefix("/api/spaces/")
            host = "https://" + space.lower().replace("/", "-").replace(".", "-") + ".hf.space"
            return self._json({"runtime": {"stage": self.stages.get(space, "RUNNING")}, "host": host})
        host = f"{parts.scheme}://{parts.netloc}"
        if parts.path == "/config":
            return self._json({"api_prefix": "/gradio_api", "dependencies": [{"id": 0, "api_name": "other"}, {"id": 3, "api_name": "infer"}]})
        if parts.path == "/gradio_api/info":
            return self._json({"named_endpoints": {"/infer": {"parameters": [{"parameter_name": name} for name in self.parameters]}}})
        if parts.path == "/gradio_api/queue/join":
            self.joined.append({"host": host, **json.loads(request.data)})
            return self._json({"event_id": "e1"})
        if parts.path == "/gradio_api/queue/data":
            done = self.completed or {"msg": "process_completed", "success": True,
                                      "output": {"data": [{"url": self.file_url or f"{host}/gradio_api/file=/tmp/a.png", "path": "/tmp/a.png"}, 42]}}
            lines = [{"msg": "estimation", "rank": 0}, {"msg": "process_starts"}, {"msg": "progress"}, done]
            return io.BytesIO(b"".join(b"data: " + json.dumps(line).encode() + b"\n\n" for line in lines))
        if parts.path.startswith("/gradio_api/file="):
            return io.BytesIO(self.image)
        raise AssertionError(url)

    @staticmethod
    def _json(data):
        return io.BytesIO(json.dumps(data).encode())


def test_space_fast_request():
    fake = FakeSpace()
    made = logo_image.space_image(TOKEN, "prompt", "fast", opener=fake, seed=9)
    joined = fake.joined[-1]
    assert joined["host"] == "https://multimodalart-qwen-image-fast.hf.space" and joined["fn_index"] == 3
    assert joined["data"] == ["prompt", 9, False, "1:1", 1.0, 8, False]  # 지시문 다듬기(다른 서비스 전송) 끔
    assert all(headers.get("Authorization") == f"Bearer {TOKEN}" for headers in fake.headers)
    assert made.master == fake.image and made.seed == 9 and "multimodalart/Qwen-Image-Fast" in made.model


def test_space_best_falls_back_when_the_first_is_down():
    fake = FakeSpace(stages={"Qwen/Qwen-Image-2512": "RUNTIME_ERROR"})
    made = logo_image.space_image(TOKEN, "prompt", "best", opener=fake, seed=1)
    assert fake.joined[-1]["host"] == "https://qwen-qwen-image.hf.space" and fake.joined[-1]["data"][4:6] == [4.0, 40]
    assert "Qwen/Qwen-Image)" in made.model
    down = FakeSpace(stages={"Qwen/Qwen-Image-2512": "PAUSED", "Qwen/Qwen-Image": "BUILD_ERROR"})
    with pytest.raises(logo_image.ImageModelError, match="동작하지 않음.*PAUSED"):
        logo_image.space_image(TOKEN, "prompt", "best", opener=down)


def test_space_errors_are_explained_without_the_token():
    quota = FakeSpace(completed={"msg": "process_completed", "success": False, "title": "ZeroGPU quota exceeded",
                                 "output": {"error": f"You have exceeded your free ZeroGPU quota ({TOKEN})"}})
    with pytest.raises(logo_image.ImageModelError) as caught:
        logo_image.space_image(TOKEN, "prompt", "fast", opener=quota)
    assert "한도 초과" in str(caught.value) and TOKEN not in str(caught.value)
    with pytest.raises(logo_image.ImageModelError, match="토큰이 올바르지 않음"):
        logo_image.space_image(TOKEN, "prompt", "fast", opener=FakeSpace(meta_status=401))
    with pytest.raises(logo_image.ImageModelError, match="입력 형식이 바뀜"):
        logo_image.space_image(TOKEN, "prompt", "fast", opener=FakeSpace(parameters=["prompt", "seed"]))
    with pytest.raises(logo_image.ImageModelError, match="다른 주소"):
        logo_image.space_image(TOKEN, "prompt", "fast", opener=FakeSpace(file_url="https://example.com/a.png"))

    def offline(request, timeout=None):
        raise urllib.error.URLError(f"no route {TOKEN}")
    with pytest.raises(logo_image.ImageModelError) as caught:
        logo_image.space_image(TOKEN, "prompt", "fast", opener=offline)
    assert "연결하지 못함" in str(caught.value) and TOKEN not in str(caught.value)


# --- 로고 만들기 연결 -----------------------------------------------------------------------


def fake_keys(tmp_path):
    return KeyBox(tmp_path / "keys.json", b"test", "debutkit-test", protect=lambda raw: b"S" + raw[::-1], unprotect=lambda raw: raw[1:][::-1])


def test_studio_makes_a_symbol_with_comfyui(tmp_path):
    fake = FakeComfy()
    studio = logo.LogoStudio(keys=fake_keys(tmp_path), folder=tmp_path / "logos", opener=fake, sleep=lambda _: None)
    status = studio.status()["providers"]
    assert list(status)[:2] == ["comfyui", "huggingface"] and status["comfyui"]["needs_key"] is False
    assert status["comfyui"]["address"] == "http://127.0.0.1:8188" and status["huggingface"]["needs_key"] is True
    with pytest.raises(logo.LogoError, match="키가 필요 없음"):
        studio.set_key("comfyui", "anything-long-enough")
    made = studio.generate("comfyui", "fast", "고양이 귀 마이크", "cute", ["#FF4F8B", "#1E2327"], "http://127.0.0.1:8188")
    assert made["provider"].startswith("ComfyUI") and isinstance(made["seed"], int) and "Plain solid pure green" in made["prompt"]
    assert "고양이 귀 마이크" in fake.workflows[-1]["6"]["inputs"]["text"]
    assert (tmp_path / "logos" / f"{made['id']}.png").read_bytes() == fake.image  # 원본 그림 보관
    assert (tmp_path / "logos" / f"{made['id']}.svg").is_file()
    svg = studio.make({"name": "부동", "symbol": {"id": made["id"]}})
    assert logo.AI_COMPOSITE in svg and "Qwen-Image" in svg
    again = logo.LogoStudio(keys=fake_keys(tmp_path), folder=tmp_path / "logos")
    assert again.symbol(made["id"])["seed"] == made["seed"]
    with pytest.raises(logo.LogoError, match="주소 형식"):
        studio.generate("comfyui", "fast", "별", "cute", [], "ftp://host")


def test_studio_needs_a_token_for_hugging_face(tmp_path):
    fake = FakeSpace()
    studio = logo.LogoStudio(keys=fake_keys(tmp_path), folder=tmp_path / "logos", opener=fake)
    with pytest.raises(logo.LogoError, match="Hugging Face.*키를 먼저 저장"):
        studio.generate("huggingface", "fast", "별", "cute", [])
    studio.set_key("huggingface", TOKEN)
    made = studio.generate("huggingface", "fast", "별", "cute", ["#22CC44"])
    assert "#FF00FF" in made["prompt"] and fake.joined[-1]["data"][0] == made["prompt"]  # 초록을 쓰면 자홍 배경
    assert "multimodalart/Qwen-Image-Fast" in made["model"]
