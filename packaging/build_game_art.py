"""게임 패키지 배경 그림 만들기(src/debutkit/overlay/static/games/scene-*.jpg)와 생성 기록(scenes.json).

    python packaging/build_game_art.py make              모든 게임(없는 것만)
    python packaging/build_game_art.py make lol tft      고른 게임만(있으면 다시)
    python packaging/build_game_art.py finish            받은 원본을 1920x1080 JPEG로, 기록 갱신

- 모델: FLUX.1 schnell(Apache-2.0)을 AI Horde(계정 없이, 자원봉사자 GPU)에서 실행. 대기 때문에 1장에 수 분~십여 분.
  AI Horde 키가 있으면 환경 변수 DEBUTKIT_HORDE_KEY(대기 순서가 앞당겨질 수 있음)
- 지시문은 게임 이름, 로고, 캐릭터 없이 장면만 묘사(그 장르의 색, 지형, 빛). 공식 그림, 게임 화면은 쓰지도 학습하지도 않음
- 원본은 저장소 밖 ~/.cache/debutkit/game-art, 저장소에는 다듬은 JPEG와 기록(모델, 라이선스, 지시문, 시드, 작업자, 날짜)만
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "debutkit" / "overlay" / "static" / "games"
RAW = Path.home() / ".cache" / "debutkit" / "game-art"
API = "https://aihorde.net/api/v2"
MODEL = "Flux.1-Schnell fp8 (Compact)"
AGENT = "debutkit-game-art/1.0 (+https://github.com/BudongJW/debutkit)"
SIZE = (1344, 768)  # 익명으로 받을 수 있는 1MP 안팎의 16:9에 가까운 크기. 다듬을 때 1920x1080으로

#: 게임별 장면: (지시문, 시드). 실제로 고른 그림의 값 그대로. 그 장르의 장면이되 게임 이름, 상징, 캐릭터, 글자는 넣지 않음
#: "key art", "game background" 같은 말은 제목 글자를 그려 넣는 경우가 많아 피함(풍경, 장면 묘사로)
SCENES: dict[str, tuple[str, int]] = {
    "valorant": (
        "cinematic wide video game environment concept art, sunlit mediterranean town plaza turned tactical arena, stone arches "
        "and terracotta roofs, sharp angular concrete barriers, crisp red and off-white fabric banners with plain horizontal "
        "stripes only, crates for cover, golden hour light with long shadows, stylized semi-realistic 3D render, clean "
        "composition, no people, no text, no letters, no symbols, no logo, no user interface",
        11),
    "lol": (
        "cinematic wide fantasy video game environment concept art, aerial three-quarter view of a lush magical jungle valley "
        "split by a glowing teal river, ancient stone paths and ruined gold-trimmed towers, hextech-like glowing blue runes, warm"
        " sunset rim light, painterly high fantasy style, rich greens and gold, no people, no text, no logo, no user interface",
        7),
    "overwatch": (
        "cinematic wide video game environment concept art, bright optimistic near-future city plaza on a sunny day, sleek white "
        "curved buildings with orange accents and blue glass, floating walkways, holographic signs without text, clean stylized "
        "3D animated film look, soft sunlight, no people, no text, no logo, no user interface",
        7),
    "hearthstone": (
        "cozy fantasy tavern table seen from above, worn wooden planks, an ornate stone and brass game board in the center with "
        "glowing blue gem sockets, scattered playing cards face down, candles and a mug, warm firelight, hand-painted stylized "
        "fantasy illustration, rich browns and gold, no people, no text, no logo, no user interface",
        7),
    "pubg": (
        "wide cinematic landscape photograph style render of open countryside: golden wheat field, a lone wooden barn and rusty "
        "shipping containers, an olive military supply crate with plain unmarked sides landing under a parachute, rolling hills, "
        "dramatic overcast sky with a faint blue haze wall on the horizon, gritty semi-realistic look, muted olive and sand "
        "tones, plain unmarked surfaces, no writing anywhere, no people, no text, no letters, no logo",
        23),
    "maplestory": (
        "cute 2D platformer scenery illustration: bright blue sky with fluffy clouds, small floating grassy islands joined by "
        "rope ladders, cottages with mushroom roofs, big round leafy trees, little sparkles, pastel cheerful palette, hand-"
        "painted cartoon background art, empty sky, no writing anywhere, no characters, no text, no letters, no title, no logo",
        23),
    "lostark": (
        "cinematic wide dark fantasy video game environment concept art, gothic castle on a cliff at night under a starry sky, a "
        "beam of golden light rising from the castle, floating ancient ruins, glowing embers, deep navy and gold palette, epic "
        "painterly MMORPG key art style, no people, no text, no logo, no user interface",
        7),
    "fconline": (
        "wide cinematic view of a modern football stadium at night from high in the stands, bright floodlights, vivid striped "
        "green pitch with white lines, blurred crowd with bokeh lights, blank dark LED boards around the pitch, realistic sports "
        "render, no flags, no banners, no writing anywhere, no players, no text, no letters, no logo, no advertising",
        23),
    "tft": (
        "cinematic fantasy video game environment concept art, a floating island arena with a hexagonal tile board in the center,"
        " golden coins scattered, cosmic purple and blue sky with stars and nebula, magical glowing particles, polished stylized "
        "3D render, purple and gold palette, no people, no text, no logo, no user interface",
        7),
    "minecraft": (
        "voxel art landscape made of cubic blocks, grassy block hills, blocky oak trees, a small blocky cottage, a waterfall of "
        "cube water, square sun and blocky clouds in a bright blue sky, isometric-ish cinematic angle, clean stylized render, no "
        "people, no text, no logo, no user interface",
        7),
}
LICENSE = "FLUX.1 schnell: Apache-2.0"


def _headers() -> dict[str, str]:
    return {"apikey": os.environ.get("DEBUTKIT_HORDE_KEY") or "0000000000", "Client-Agent": f"debutkit:game-art:{AGENT}",
            "Content-Type": "application/json", "User-Agent": AGENT}


def _call(url: str, data: dict | None = None) -> dict:
    request = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=_headers())
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def make(key: str) -> dict:
    prompt, seed = SCENES[key]
    body = {"prompt": prompt, "models": [MODEL], "nsfw": False, "censor_nsfw": True, "r2": True, "shared": True,
            "trusted_workers": False, "slow_workers": True,
            "params": {"sampler_name": "k_euler", "cfg_scale": 1.0, "steps": 4, "width": SIZE[0], "height": SIZE[1], "seed": str(seed), "n": 1}}
    request_id = _call(f"{API}/generate/async", body)["id"]
    started = time.time()
    while True:
        time.sleep(12)
        state = _call(f"{API}/generate/check/{request_id}")
        print(f"{key}: {int(time.time() - started)}초, 대기 {state.get('queue_position')}", flush=True)
        if state.get("done"):
            break
        if state.get("faulted") or not state.get("is_possible", True):
            raise RuntimeError(f"{key}: AI Horde가 만들지 못함")
    generation = _call(f"{API}/generate/status/{request_id}")["generations"][0]
    image = generation["img"]
    data = (urllib.request.urlopen(urllib.request.Request(image, headers={"User-Agent": AGENT}), timeout=120).read()
            if image.startswith("http") else base64.b64decode(image))
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{key}.webp").write_bytes(data)
    record = {"model": "FLUX.1 schnell", "service": f"AI Horde ({MODEL})", "license": LICENSE, "prompt": body["prompt"], "seed": seed,
              "size": list(SIZE), "worker": generation.get("worker_name", ""), "made": datetime.date.today().isoformat()}
    (RAW / f"{key}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def finish() -> None:
    """원본을 1920x1080 JPEG(가운데 기준 자르기, 살짝 선명하게)로, scenes.json에 기록."""
    from PIL import Image, ImageFilter

    manifest = {}
    for key in SCENES:
        raw = RAW / f"{key}.webp"
        if not raw.is_file():
            print(f"{key}: 원본 없음(make 먼저)")
            continue
        with Image.open(raw) as image:
            image = image.convert("RGB")
            scale = max(1920 / image.width, 1080 / image.height)
            image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
            left, top = (image.width - 1920) // 2, (image.height - 1080) // 2
            image = image.crop((left, top, left + 1920, top + 1080)).filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
            out = OUT / f"scene-{key}.jpg"
            image.save(out, quality=84, optimize=True, progressive=True)
        manifest[key] = json.loads((RAW / f"{key}.json").read_text(encoding="utf-8"))
        print(f"{out.name}  ({out.stat().st_size / 1024:.0f} KB)")
    (OUT / "scenes.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("make", "finish"):
        print(__doc__)
        return 2
    if argv[0] == "finish":
        finish()
        return 0
    keys = argv[1:] or [key for key in SCENES if not (RAW / f"{key}.webp").is_file()]
    for key in keys:
        if key not in SCENES:
            print(f"없는 게임: {key}")
            return 2
        try:
            make(key)
        except (OSError, RuntimeError, KeyError, ValueError) as error:
            print(f"{key}: 실패({error})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
