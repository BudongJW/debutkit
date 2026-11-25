"""클립 다듬기: 저장한 클립(또는 아무 영상)으로 움짤(GIF, WebP)과 세로 쇼츠(1080x1920 MP4)를 만든다.

- ffmpeg 사용(자동 클립과 같은 ffmpeg). GIF는 영상마다 색표를 따로 만들어(palettegen, paletteuse) 번짐을 줄인다
- WebP는 ffmpeg로 프레임을 읽어 Pillow로 저장(ffmpeg 배포판마다 WebP 인코더 유무가 달라서. Pillow는 로고 추가 의존성)
- 세로 쇼츠: 흐린 배경(원본을 크게 흐리게 깔고 가운데 원본), 자르기(가로 위치 지정, 캐릭터 쪽으로), 위아래 여백
- 워터마크: PNG 그림(예: debutkit logo로 만든 로고)을 9곳 중 한 곳에 크기와 투명도를 정해 얹는다
- 만든 파일은 원본 옆에 저장하고 이미 있으면 이름 뒤에 번호를 붙인다(덮어쓰지 않음). 원본은 바꾸지 않는다
- 자동 클립(``overlay --clip-gif``, ``--clip-shorts``)은 클립을 저장할 때마다 백그라운드에서 만든다
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

POSITIONS = {"top-left": "왼쪽 위", "top": "위 가운데", "top-right": "오른쪽 위", "left": "왼쪽 가운데", "center": "가운데", "right": "오른쪽 가운데",
             "bottom-left": "왼쪽 아래", "bottom": "아래 가운데", "bottom-right": "오른쪽 아래"}
SHORTS_MODES = {"blur": "흐린 배경", "crop": "자르기", "fit": "위아래 여백"}
GIF_WIDTH = (160, 1280)
FPS = (5, 30)
MAX_SECONDS = 60.0
SHORTS_SIZE = (1080, 1920)
TIMEOUT = 600


class ClipFxError(RuntimeError):
    """만들지 못함. 메시지는 한국어 안내."""


@dataclass(frozen=True)
class Watermark:
    image: Path
    position: str = "bottom-right"
    size: float = 0.18  # 결과 폭에 대한 그림 폭 비율
    opacity: float = 0.85

    def check(self) -> "Watermark":
        if not Path(self.image).is_file():
            raise ClipFxError(f"워터마크 그림 없음: {self.image}")
        if Path(self.image).suffix.lower() not in (".png", ".webp", ".jpg", ".jpeg"):
            raise ClipFxError("워터마크 그림은 PNG, WebP, JPEG(투명 배경은 PNG 권장)")
        if self.position not in POSITIONS:
            raise ClipFxError("워터마크 위치는 " + ", ".join(POSITIONS))
        if not 0.03 <= self.size <= 0.6:
            raise ClipFxError("워터마크 크기는 결과 폭의 3%에서 60% 사이")
        if not 0.1 <= self.opacity <= 1.0:
            raise ClipFxError("워터마크 투명도는 0.1에서 1 사이")
        return self


@dataclass(frozen=True)
class Info:
    duration: float
    width: int
    height: int
    audio: bool


def find_ffmpeg() -> str:
    from .tools import ffmpeg_path, install_hint

    found = ffmpeg_path() or shutil.which("ffmpeg")
    if not found:
        raise ClipFxError(f"ffmpeg 없음: {install_hint()}")
    return found


def _ffprobe(ffmpeg: str) -> str:
    sibling = Path(ffmpeg).with_name("ffprobe" + Path(ffmpeg).suffix)
    return str(sibling) if sibling.is_file() else (shutil.which("ffprobe") or "ffprobe")


def _run(command: Sequence[str], *, timeout: float = TIMEOUT, stdout: Any = subprocess.DEVNULL) -> subprocess.CompletedProcess[Any]:
    try:
        result = subprocess.run(list(command), stdout=stdout, stderr=subprocess.PIPE, timeout=timeout,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    except FileNotFoundError as error:
        raise ClipFxError(f"ffmpeg 실행 실패: {error}") from None
    except subprocess.TimeoutExpired:
        raise ClipFxError(f"시간 초과({timeout:.0f}초): 더 짧게 잘라서 다시 시도") from None
    if result.returncode != 0:
        tail = [line for line in result.stderr.decode("utf-8", "replace").splitlines() if line.strip()][-3:]
        raise ClipFxError("ffmpeg 오류: " + " / ".join(tail))
    return result


def probe(source: Path, ffmpeg: str | None = None) -> Info:
    """영상 길이, 크기, 소리 유무(ffprobe)."""
    ffmpeg = ffmpeg or find_ffmpeg()
    result = _run([_ffprobe(ffmpeg), "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(source)],
                  stdout=subprocess.PIPE, timeout=60)
    try:
        data = json.loads(result.stdout or b"{}")
    except ValueError:
        raise ClipFxError("영상 정보를 읽지 못함") from None
    streams = data.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video" and stream.get("width")), None)
    if video is None:
        raise ClipFxError(f"영상이 아님: {Path(source).name}")
    try:
        duration = float((data.get("format") or {}).get("duration") or 0)
    except ValueError:
        duration = 0.0
    return Info(duration, int(video["width"]), int(video["height"]), any(stream.get("codec_type") == "audio" for stream in streams))


def output_path(source: Path, suffix: str, extension: str, out_dir: Path | None = None) -> Path:
    """원본 옆(또는 ``out_dir``)의 새 파일 이름. 있으면 ``-2``, ``-3`` 을 붙인다."""
    folder = out_dir or source.parent
    candidate = folder / f"{source.stem}{suffix}{extension}"
    number = 2
    while candidate.exists():
        candidate = folder / f"{source.stem}{suffix}-{number}{extension}"
        number += 1
    return candidate


def _range(start: float | None, duration: float | None, info: Info | None) -> list[str]:
    if start is not None and start < 0:
        raise ClipFxError("시작 위치는 0초 이상")
    if duration is not None and not 0 < duration <= MAX_SECONDS:
        raise ClipFxError(f"길이는 0초보다 길고 {MAX_SECONDS:g}초 이내")
    if info is not None and start is not None and info.duration and start >= info.duration:
        raise ClipFxError(f"시작 위치가 영상 길이({info.duration:.1f}초)보다 뒤")
    found: list[str] = []
    if start:
        found += ["-ss", f"{start:.3f}"]
    if duration:
        found += ["-t", f"{duration:.3f}"]
    return found


def _place(position: str, margin: int) -> tuple[str, str]:
    x = {"left": str(margin), "center": "(main_w-overlay_w)/2", "right": f"main_w-overlay_w-{margin}"}
    y = {"top": str(margin), "middle": "(main_h-overlay_h)/2", "bottom": f"main_h-overlay_h-{margin}"}
    vertical, _, horizontal = position.partition("-") if "-" in position else (position, "", "")
    if position in ("left", "right"):
        return x[position], y["middle"]
    if position == "center":
        return x["center"], y["middle"]
    return x[horizontal or "center"], y[vertical]


def _watermark(chain: str, label: str, watermark: Watermark | None, width: int, input_index: int = 1) -> tuple[str, str]:
    """워터마크를 얹는 필터. (필터 문자열, 마지막 출력 이름)."""
    if watermark is None:
        return chain, label
    mark_width = max(8, int(width * watermark.size) // 2 * 2)
    x, y = _place(watermark.position, max(4, int(width * 0.03)))
    chain += (f";[{input_index}:v]scale={mark_width}:-1,format=rgba,colorchannelmixer=aa={watermark.opacity:.2f}[wm]"
              f";[{label}][wm]overlay={x}:{y}:format=auto[marked]")
    return chain, "marked"


def gif_command(ffmpeg: str, source: Path, target: Path, *, start: float | None = None, duration: float | None = None, width: int = 480,
                fps: int = 15, watermark: Watermark | None = None, info: Info | None = None) -> list[str]:
    if not GIF_WIDTH[0] <= width <= GIF_WIDTH[1]:
        raise ClipFxError(f"움짤 폭은 {GIF_WIDTH[0]}에서 {GIF_WIDTH[1]} 픽셀")
    if not FPS[0] <= fps <= FPS[1]:
        raise ClipFxError(f"초당 장수는 {FPS[0]}에서 {FPS[1]}")
    width -= width % 2
    command = [ffmpeg, "-hide_banner", "-y", *_range(start, duration, info), "-i", str(source)]
    if watermark:
        command += ["-i", str(watermark.check().image)]
    chain, label = _watermark(f"[0:v]fps={fps},scale={width}:-2:flags=lanczos[base]", "base", watermark, width)
    chain += f";[{label}]split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a"
    return command + ["-filter_complex", chain, "-loop", "0", "-an", str(target)]


def shorts_command(ffmpeg: str, source: Path, target: Path, *, mode: str = "blur", focus: float = 0.5, start: float | None = None,
                   duration: float | None = None, watermark: Watermark | None = None, info: Info | None = None) -> list[str]:
    if mode not in SHORTS_MODES:
        raise ClipFxError("쇼츠 형태는 blur(흐린 배경), crop(자르기), fit(위아래 여백)")
    if not 0.0 <= focus <= 1.0:
        raise ClipFxError("자르는 가로 위치는 0(왼쪽)에서 1(오른쪽) 사이")
    width, height = SHORTS_SIZE
    command = [ffmpeg, "-hide_banner", "-y", *_range(start, duration, info), "-i", str(source)]
    if watermark:
        command += ["-i", str(watermark.check().image)]
    if mode == "blur":
        chain = (f"[0:v]split[bgsrc][fgsrc];[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
                 f"gblur=sigma=28,eq=brightness=-0.06[bg];[fgsrc]scale={width}:-2:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]")
    elif mode == "crop":
        chain = f"[0:v]scale=-2:{height}:flags=lanczos,crop={width}:{height}:(iw-{width})*{focus:.3f}:0,setsar=1[base]"
    else:
        chain = f"[0:v]scale={width}:-2:flags=lanczos,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[base]"
    chain, label = _watermark(chain, "base", watermark, width)
    command += ["-filter_complex", chain, "-map", f"[{label}]"]
    if info is None or info.audio:
        command += ["-map", "0:a?", "-c:a", "aac", "-b:a", "160k"]
    return command + ["-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)]


def make_gif(source: Path, *, out_dir: Path | None = None, **options: Any) -> Path:
    ffmpeg = find_ffmpeg()
    source = _source(source)
    info = probe(source, ffmpeg)
    target = output_path(source, "", ".gif", out_dir)
    _run(gif_command(ffmpeg, source, target, info=info, **options))
    return target


def make_shorts(source: Path, *, out_dir: Path | None = None, **options: Any) -> Path:
    ffmpeg = find_ffmpeg()
    source = _source(source)
    info = probe(source, ffmpeg)
    target = output_path(source, "-shorts", ".mp4", out_dir)
    _run(shorts_command(ffmpeg, source, target, info=info, **options))
    return target


def make_webp(source: Path, *, out_dir: Path | None = None, start: float | None = None, duration: float | None = None, width: int = 480,
              fps: int = 15, quality: int = 75, watermark: Watermark | None = None) -> Path:
    """움직이는 WebP(투명도 유지, GIF보다 선명하고 작음). ffmpeg로 RGBA 프레임을 읽어 Pillow로 저장한다."""
    if not 10 <= quality <= 100:
        raise ClipFxError("WebP 화질은 10에서 100 사이")
    if not GIF_WIDTH[0] <= width <= GIF_WIDTH[1]:
        raise ClipFxError(f"움짤 폭은 {GIF_WIDTH[0]}에서 {GIF_WIDTH[1]} 픽셀")
    if not FPS[0] <= fps <= FPS[1]:
        raise ClipFxError(f"초당 장수는 {FPS[0]}에서 {FPS[1]}")
    try:
        from PIL import Image
    except ImportError:
        raise ClipFxError('WebP 움짤에는 Pillow 필요: pip install "debutkit[logo]"') from None
    ffmpeg = find_ffmpeg()
    source = _source(source)
    info = probe(source, ffmpeg)
    width -= width % 2
    height = max(2, round(info.height * width / info.width / 2) * 2)
    command = [ffmpeg, "-hide_banner", *_range(start, duration, info), "-i", str(source)]
    if watermark:
        command += ["-i", str(watermark.check().image)]
    chain, label = _watermark(f"[0:v]fps={fps},scale={width}:{height}:flags=lanczos[base]", "base", watermark, width)
    command += ["-filter_complex", f"{chain};[{label}]format=rgba[out]", "-map", "[out]", "-f", "rawvideo", "-an", "-"]
    data = _run(command, stdout=subprocess.PIPE).stdout
    size = width * height * 4
    frames = [Image.frombytes("RGBA", (width, height), data[index:index + size]) for index in range(0, len(data) - size + 1, size)]
    if not frames:
        raise ClipFxError("만들 프레임이 없음: 시작 위치와 길이 확인")
    target = output_path(source, "", ".webp", out_dir)
    frames[0].save(target, "WEBP", save_all=True, append_images=frames[1:], duration=round(1000 / fps), loop=0, quality=quality, method=4)
    return target


def _source(source: Path) -> Path:
    source = Path(source)
    if not source.is_file():
        raise ClipFxError(f"영상 파일 없음: {source}")
    return source


class PostProcessor:
    """자동 클립이 저장한 클립마다 움짤, 쇼츠를 만든다(백그라운드 한 줄로 차례대로). ``notify`` 는 오버레이 안내."""

    def __init__(self, gif: bool, shorts: bool, notify: Callable[[str], None], *, gif_seconds: float = 6.0,
                 make: dict[str, Callable[..., Path]] | None = None) -> None:
        import queue
        import threading

        self.gif, self.shorts, self.notify, self.gif_seconds = gif, shorts, notify, gif_seconds
        self.make = make or {"gif": make_gif, "shorts": make_shorts}
        self._queue: queue.Queue[Path | None] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="debutkit-clipfx", daemon=True)
        self._thread.start()

    def __call__(self, clip: Path) -> None:
        if self.gif or self.shorts:
            self._queue.put(Path(clip))

    def _loop(self) -> None:
        while True:
            clip = self._queue.get()
            if clip is None:
                return
            self.process(clip)

    def process(self, clip: Path) -> list[Path]:
        made: list[Path] = []
        jobs = ([("gif", "움짤", {"duration": self.gif_seconds})] if self.gif else []) + ([("shorts", "세로 쇼츠", {})] if self.shorts else [])
        for key, label, options in jobs:
            try:
                path = self.make[key](clip, **options)
            except ClipFxError as error:
                self.notify(f"{label} 만들기 실패({clip.name}): {error}")
                continue
            made.append(path)
            self.notify(f"{label} 저장: {path.name}")
        return made

    def stop(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=1)
