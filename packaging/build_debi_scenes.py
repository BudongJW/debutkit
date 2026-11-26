"""메인 캐릭터 데비의 장면 그림(방송 중, 방송 준비, 일상): src/debutkit/overlay/static/mascot/scenes/*.jpg 와 생성 기록.

    python packaging/build_debi_scenes.py make                 없는 장면만 그리기
    python packaging/build_debi_scenes.py make live_desk       고른 장면만(있으면 다시)
    python packaging/build_debi_scenes.py finish               받은 원본을 JPEG로, 기록 갱신

- 모델: Qwen-Image-Edit-2511(Apache-2.0)을 Hugging Face Space(prithivMLmods/Qwen-Image-Edit-2511-LoRAs-Fast, Anime 로라)에서 실행.
  데비 원본(assets/brand/mascot/source/debi_1024.png)을 16:9 바탕에 놓고 참조로 주어 같은 캐릭터로 새 장면을 그림
- 필요: gradio_client, huggingface_hub 로그인(무료 계정은 하루 ZeroGPU 사용량이 적어 한 번에 4~5장)
- 원본은 저장소 밖 ~/.cache/debutkit/debi-scenes, 저장소에는 JPEG와 기록(모델, 라이선스, 지시문, 시드, 날짜)만
"""

from __future__ import annotations

import base64
import datetime
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "debutkit" / "overlay" / "static" / "mascot" / "scenes"
RECORD = ROOT / "assets" / "brand" / "mascot" / "scenes.json"
RAW = Path.home() / ".cache" / "debutkit" / "debi-scenes"
SOURCE = ROOT / "assets" / "brand" / "mascot" / "source" / "debi_1024.png"
SPACE = "prithivMLmods/Qwen-Image-Edit-2511-LoRAs-Fast"
LORA = "Anime-V2"
SEED = 21
SIZE = (1344, 768)
#: 모든 장면에 붙이는 캐릭터 설명(같은 디자인 유지)과 금지(글자, 로고)
DESIGN = ("Keep her exact character design: chibi proportions with a big head, lavender hair with a side ponytail tied by a yellow hair clip, "
          "a big yellow star hair clip on the other side of her head, mint green headphones, teal green eyes, rosy cheeks, "
          "a lavender zip-up jacket with coral collar and cuffs and mint sleeve panels, a white t-shirt, mint shoes. "
          "Same cute anime illustration style with thick dark outlines and soft flat cel shading. "
          "No text, no letters, no numbers, no logos, no watermark, no signature.")
#: 장면: 키 -> (묶음, 이름, 지시문)
SCENES = {
    "live_desk": ("방송 중", "책상에서 인사", "Redraw this girl as a full scene illustration: she sits at a cozy streaming desk at night, "
                  "speaking into a desk microphone on a boom arm and waving at the viewer with a big smile, a large monitor beside her glows with "
                  "colorful blurry chat bubbles, a ring light, fairy lights and plushies on the shelf, lavender and mint room lighting."),
    "live_sing": ("방송 중", "노래 방송", "Redraw this girl as a full scene illustration: she sings into her microphone on a small stage, "
                  "eyes closed happily, one hand raised, soft spotlights, floating sparkles and music notes, lavender and pink stage lights, a dark background."),
    "live_game": ("방송 중", "게임 방송", "Redraw this girl as a full scene illustration: she sits in a gaming chair holding a game controller, "
                  "leaning forward with an excited determined face, the glowing monitor reflects on her face, a cozy dark room with neon mint and lavender light strips."),
    "prep_checklist": ("방송 준비", "점검 목록 확인", "Redraw this girl as a full scene illustration: she holds a clipboard checklist and a pencil, "
                       "checking items with a nervous but determined face, a laptop open on the desk beside her, sticky notes on the wall, afternoon light in a cozy room."),
    "prep_setup": ("방송 준비", "마이크와 카메라 설치", "Redraw this girl as a full scene illustration: she stands on her toes adjusting a microphone and a small webcam "
                   "on her desk, cables and a small toolbox nearby, focused cute face with her tongue slightly out, a bright tidy room."),
    "prep_mirror": ("방송 준비", "거울 앞 준비", "Redraw this girl as a full scene illustration: she stands in front of a round mirror, fixing her yellow star hair clip "
                    "and smiling at her reflection, a small vanity table with a hairbrush and a cup of tea, warm morning light."),
    "daily_cafe": ("일상", "카페에서", "Redraw this girl as a full scene illustration: she sits by a cafe window holding a big bubble tea with both hands, "
                   "happily sipping through a straw, a slice of strawberry cake on the table, sunny street outside, warm pastel colors."),
    "daily_walk": ("일상", "공원 산책", "Redraw this girl as a full scene illustration: she walks happily along a park path with a canvas tote bag "
                   "on her shoulder, cherry blossom petals falling, blue sky, a small cat following her."),
    "daily_sleep": ("일상", "방송 끝나고 잠", "Redraw this girl as a full scene illustration: she has fallen asleep at her desk with her head on her arms, "
                    "headphones still on, a small smile, a blanket over her shoulders, a desk lamp glowing, a night window with stars."),
}


def reference():
    """원본 데비(투명)를 16:9 연한 바탕 가운데에(Qwen-Image-Edit는 들어온 그림의 비율로 그림)."""
    from PIL import Image

    image = Image.open(SOURCE).convert("RGBA")
    image = image.crop(image.getbbox())
    image.thumbnail((SIZE[0], int(SIZE[1] * 0.92)), Image.Resampling.LANCZOS)
    back = Image.new("RGB", SIZE, (246, 242, 250))
    back.paste(image, ((SIZE[0] - image.width) // 2, SIZE[1] - image.height - 20), image)
    buffer = io.BytesIO()
    back.save(buffer, "JPEG", quality=95)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def make(keys: list[str]) -> None:
    from gradio_client import Client
    from huggingface_hub import get_token

    RAW.mkdir(parents=True, exist_ok=True)
    wanted = keys or [key for key in SCENES if not (RAW / f"{key}.png").is_file()]
    if not wanted:
        print("모든 장면이 있음")
        return
    data = reference()
    client = Client(SPACE, token=get_token(), verbose=False, httpx_kwargs={"timeout": 900})
    for key in wanted:
        started = time.time()
        answer = client.predict(json.dumps([data]), f"{SCENES[key][2]} {DESIGN}", LORA, SEED, False, 1.0, 4, api_name="/edit_image")
        if answer.get("status") != "success":
            raise SystemExit(f"{key}: {answer.get('message') or answer.get('status')}")
        (RAW / f"{key}.png").write_bytes(base64.b64decode(answer["image"].split(",", 1)[1]))
        print(key, f"{time.time() - started:.0f}초", flush=True)


def finish() -> None:
    from PIL import Image

    OUT.mkdir(parents=True, exist_ok=True)
    record = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.is_file() else {}
    for key, (group, title, scene) in SCENES.items():
        raw = RAW / f"{key}.png"
        if not raw.is_file():
            continue
        with Image.open(raw) as picture:
            picture.convert("RGB").save(OUT / f"{key}.jpg", "JPEG", quality=90, optimize=True, progressive=True)
        record[key] = {"group": group, "title": title, "file": f"src/debutkit/overlay/static/mascot/scenes/{key}.jpg",
                       "tool": f"Hugging Face Space {SPACE}", "model": "Qwen-Image-Edit-2511 (Rapid-AIO, 4 steps)", "license": "Apache-2.0",
                       "lora": "prithivMLmods/Qwen-Image-Edit-2511-Anime", "reference": "assets/brand/mascot/source/debi_1024.png",
                       "prompt": f"{scene} {DESIGN}", "seed": SEED, "steps": 4,
                       "date": record.get(key, {}).get("date") or datetime.date.today().isoformat()}
    RECORD.write_text(json.dumps(dict(sorted(record.items(), key=lambda item: list(SCENES).index(item[0]))), ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
    print(f"{len(record)}장: {', '.join(record)}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("make", "finish"):
        raise SystemExit(__doc__)
    make(sys.argv[2:]) if sys.argv[1] == "make" else finish()
