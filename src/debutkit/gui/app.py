"""설정 마법사: 명령줄 없이 PC 점검, 아바타, OBS 장면, 채팅과 알림, 마무리 순서로 안내한다.

창은 입력을 모으고 결과를 보여 주기만 하고, 실제 일은 doctor, scenes, overlay, clip, tools,
chzzk 모듈이 한다. 느린 일(점검, OBS 연결, 다운로드, 로그인)은 작업 스레드에서 돌리고 결과는
Qt 시그널로 창에 돌려준다. 스타일 시트는 채팅 연결 모듈에 있는 것을 쓰고, 없으면 기본 색만 쓴다.
"""

from __future__ import annotations

import os
import platform
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, camera, character, chzzk, clip, doctor, launcher, logs, motion, scenes, settings, speed, tools, vts
from ..doctor import FAIL, INFO, JOIN_URL, LABELS, OK, OVERLAY_PORT, SOFTWARE_URL, WARN

STEPS = ["1  PC 점검", "2  캐릭터", "3  OBS 장면", "4  채팅과 알림", "5  마무리"]
AVATARS = [("VTube Studio (Live2D)", "vts"), ("VSeeFace (VRM)", "vseeface"), ("Warudo", "warudo"), ("VMagicMirror", "vmagicmirror"),
           ("debutkit 캐릭터 화면(PNGTuber, VRM)", "debutkit"), ("아바타 사용 안 함", "none")]
STATE_STYLE = {OK: "StateOk", FAIL: "StateMissing", WARN: "StateWarn", INFO: "StateOther"}
#: 브랜드 컬러(assets/brand): Slate 배경, Cream 글자, Pink는 현재 단계와 선택 표시에만 사용
COLORS = {"ink": "#1E2327", "surface": "#262C31", "field": "#2E353B", "border": "#3A4249", "text": "#FAF7F5", "muted": "#A7B0B7",
          "pink": "#FF4F8B", "nav": "#191D20"}
STYLE_SHEET = """
QMainWindow, QDialog, QWidget#Root {{ background: {ink}; }}
* {{ color: {text}; font-size: 14px; }}
QWidget#Card {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; }}
QScrollArea#PageScroll, QWidget#PageBody {{ background: transparent; border: none; }}
QLabel#Title {{ font-size: 21px; font-weight: 700; }}
QLabel#Muted {{ color: {muted}; }}
QLabel#Eyebrow {{ color: {muted}; font-size: 12px; font-weight: 700; }}
QLabel#Status {{ color: {text}; font-weight: 600; }}
QLabel#StateOk, QLabel#StateWarn, QLabel#StateMissing, QLabel#StateOther {{ border-radius: 3px; padding: 2px 8px; font-weight: 700; font-size: 12px; }}
QLabel#StateOk {{ background: #1F3A2E; color: #4ADE9B; }}
QLabel#StateWarn {{ background: #3A3420; color: #FFD84D; }}
QLabel#StateMissing {{ background: #43242F; color: #FF8FB1; }}
QLabel#StateOther {{ background: {field}; color: {muted}; }}
QPushButton {{ background: {field}; border: 1px solid {border}; border-radius: 4px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {muted}; }}
QPushButton:pressed {{ background: {border}; }}
QPushButton:disabled {{ color: #6F7880; }}
QPushButton#Primary {{ background: {text}; color: {ink}; border-color: {text}; font-weight: 700; }}
QPushButton#Primary:hover {{ background: #FFFFFF; }}
QPushButton#Primary:disabled {{ background: {border}; color: {muted}; border-color: {border}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{ background: {field}; border: 1px solid {border}; border-radius: 4px; padding: 4px 8px; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {pink}; }}
QComboBox QAbstractItemView {{ background: {field}; selection-background-color: {border}; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 3px; border: 1px solid {border}; background: {field}; }}
QCheckBox::indicator:checked {{ background: {pink}; border-color: {pink}; }}
QCheckBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: #6F7880; }}
QListWidget#Steps {{ background: {nav}; border: none; border-right: 1px solid {border}; padding: 14px 0; outline: 0; }}
QListWidget#Steps::item {{ padding: 10px 18px; border: none; border-left: 3px solid transparent; color: {muted}; }}
QListWidget#Steps::item:selected {{ background: {surface}; color: {text}; font-weight: 700; border-left: 3px solid {pink}; }}
QListWidget#Characters, QListWidget#Motions, QListWidget#Launch {{ background: {field}; border: 1px solid {border}; border-radius: 4px; padding: 4px; outline: 0; }}
QListWidget#Characters::item, QListWidget#Motions::item, QListWidget#Launch::item {{ padding: 6px 8px; border-radius: 3px; color: {text}; }}
QListWidget#Characters::item:selected, QListWidget#Motions::item:selected, QListWidget#Launch::item:selected {{ background: {border}; color: {text}; }}
QToolTip {{ background: {field}; color: {text}; border: 1px solid {border}; }}
""".format(**COLORS)
EXTRA_STYLE = ""
LINK = "color:#FF8FB1"
ICON = Path(__file__).with_name("icon.png")  # packaging/build_brand.py 로 생성
MASCOTS = Path(__file__).resolve().parent.parent / "overlay" / "static" / "mascot"  # 마스코트 캐스트 그림(큐: 안내, 데비: 마무리)


def style_sheet() -> str:
    return STYLE_SHEET


def _make_overlay(sources: list[tuple[str, Callable[[], Any]]], port: int) -> Any:
    from ..overlay.server import OverlayServer

    return OverlayServer(sources, port=port)


def _make_autoclipper(hub: Any, port: int, password: str | None, gif: bool = False, shorts: bool = False) -> tuple[Any, str]:
    problem = clip.preflight()
    if problem:
        raise RuntimeError(problem)
    out = clip.default_clip_dir()
    clipper = clip.replay_clipper(out, "127.0.0.1", port, password)
    version = clipper.check(start_buffer=True)
    post = None
    if gif or shorts:
        from .. import clipfx
        from ..overlay.events import system_event

        post = clipfx.PostProcessor(gif, shorts, lambda message: hub.publish(system_event(message)))
    extra = ", ".join(name for name, on in (("움짤", gif), ("세로 쇼츠", shorts)) if on)
    return clip.AutoClipper(hub, clipper, post=post), f"자동 클립 시작(OBS {version}). 저장 위치: {out}" + (f". 클립마다 {extra}도 만듦" if extra else "")


def _check_youtube(address: str, api_key: str | None) -> str:
    from ..overlay.youtube_check import check, format_steps

    return "YouTube 연결 확인(할당량 약 11 단위 사용)\n" + format_steps(check(address, api_key))


ISSUE_URL = "https://github.com/BudongJW/debutkit/issues/new/choose"


def diagnostics(checks: list[doctor.Check]) -> str:
    """문제 제보, 확인 보고에 붙여 넣을 점검 결과. 사용자가 직접 복사해 붙여 넣는다(자동 전송 없음)."""
    head = f"debutkit {__version__}, {platform.platform()}, Python {platform.python_version()}"
    return head + "\n\n" + doctor.format_report(checks)


class PngDialog(QDialog):
    """PNGTuber 만들기: 이름과 상태별 이미지(입 다묾, 입 벌림 필수)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PNG로 캐릭터 만들기")
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("캐릭터 이름")
        form.addRow("이름", self.name)
        self.fields: dict[str, QLineEdit] = {}
        for state in character.PNG_STATES:
            path_field = QLineEdit()
            path_field.setPlaceholderText("필수" if state in ("idle", "talk") else "선택")
            pick = QPushButton("선택")
            pick.clicked.connect(lambda _=False, target=path_field: self._pick(target))
            form.addRow(character.STATE_NAMES[state], row(path_field, pick, stretch=0))
            self.fields[state] = path_field
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _pick(self, target: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "이미지 선택", "", "PNG 이미지 (*.png)")
        if path:
            target.setText(path)

    def values(self) -> tuple[str, dict[str, Path]]:
        return self.name.text().strip() or "PNGTuber", {state: Path(field_.text().strip()) for state, field_ in self.fields.items() if field_.text().strip()}


def _pick_png() -> tuple[str, dict[str, Path]] | None:
    dialog = PngDialog(QApplication.activeWindow())
    return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None


def _pick_character() -> str | None:
    path, _ = QFileDialog.getOpenFileName(None, "캐릭터 파일", "", "캐릭터 (*.vrm *.glb *.fbx *.zip *.model3.json *.inp *.inx);;모든 파일 (*)")
    return path or None


def _pick_motion() -> str | None:
    path, _ = QFileDialog.getOpenFileName(None, "동작 파일", "", "동작 (*.vrma *.fbx *.glb *.zip);;모든 파일 (*)")
    return path or None


def _pick_clip(clips: list[str]) -> str | None:
    """파일 안에 동작이 여러 개일 때 사용할 동작 선택. 취소하면 None."""
    chosen, accepted = QInputDialog.getItem(QApplication.activeWindow(), "동작 선택", "파일 안의 동작 중 등록할 동작", clips, 0, False)
    return chosen if accepted else None


def _pick_folder(title: str) -> str | None:
    return QFileDialog.getExistingDirectory(None, title) or None


def _add_phone_camera(host: str, port: int, password: str | None) -> dict[str, Any]:
    """OBS에 휴대폰 카메라 소스(SRT 수신 미디어 소스)를 만들고 휴대폰 앱 연결 정보를 돌려준다."""
    config = camera.load_config()
    with camera.connect(host, port, password) as client:
        result = camera.add_to_obs(client, config)
        state = camera.media_state(client)
    return {**result, "state": state, "info": camera.connection_info(config)}


def qr_pixmap(content: str, size: int = 200) -> QPixmap:
    """QR 코드 그림(흰 여백 4칸)."""
    cells = camera.qr_matrix(content)
    count = len(cells) + 8
    image = QImage(count, count, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    for y, line in enumerate(cells):
        for x, dark in enumerate(line):
            if dark:
                image.setPixel(x + 4, y + 4, QColor("black").rgb())
    return QPixmap.fromImage(image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))


def _make_voice_meter(server: Any, port: int, password: str | None, threshold: float, input_name: str | None = None) -> Any:
    """캐릭터 화면의 입 움직임: OBS 마이크 음량(채팅 연결 모듈 필요). 없으면 None."""
    try:
        import stream2clip.obs  # noqa: F401
    except ImportError:
        return None
    from ..overlay.events import system_event
    from ..overlay.voice import VoiceMeter

    return VoiceMeter(server.voice, "127.0.0.1", port, password, input_name=input_name, threshold=threshold,
                      notify=lambda text: server.hub.publish(system_event(text))).start()


def _make_vts_reactor(server: Any, reactions: list[Any]) -> Any:
    from ..overlay.events import system_event

    reactor = vts.VtsReactor(reactions, notify=lambda text: server.hub.publish(system_event(text))).start()
    server.hub.taps.append(reactor)
    return reactor


def _copy_text(text_: str) -> None:
    QGuiApplication.clipboard().setText(text_)


def _open_folder(path: Path) -> Any:
    path.mkdir(parents=True, exist_ok=True)
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _edit_launcher(parent: QWidget) -> bool:
    from .launch_dialog import LaunchDialog

    return LaunchDialog(parent).exec() == QDialog.DialogCode.Accepted


@dataclass
class Backend:
    """창이 부르는 실제 동작. 테스트에서 바꿔 끼운다."""

    run_checks: Callable[..., list[doctor.Check]] = doctor.run_checks
    check_avatar: Callable[..., list[doctor.Check]] = doctor.check_avatar
    apply_scenes: Callable[..., Any] = scenes.connect_and_apply
    add_phone_camera: Callable[..., dict[str, Any]] = _add_phone_camera
    make_overlay: Callable[..., Any] = _make_overlay
    make_autoclipper: Callable[..., Any] = _make_autoclipper
    can_download_ffmpeg: Callable[[], bool] = tools.can_download_ffmpeg
    download_ffmpeg: Callable[..., Any] = tools.download_ffmpeg
    chzzk_login: Callable[..., Path] = chzzk.login
    chzzk_signed_in: Callable[[], bool] = chzzk.signed_in
    clip_dir: Callable[[], Path] = clip.default_clip_dir
    check_update: Callable[[], str] = field(default=lambda: tools.update_message(__version__))
    measure_speed: Callable[[], doctor.Check] = field(default=lambda: speed.check(speed.measure_upload()))
    open_url: Callable[[str], Any] = field(default=lambda url: QDesktopServices.openUrl(QUrl(url)))
    open_folder: Callable[[Path], Any] = _open_folder
    check_youtube: Callable[[str, str | None], str] = _check_youtube
    load_settings: Callable[[], dict[str, Any]] = settings.load
    save_settings: Callable[[dict[str, Any]], Any] = settings.save
    clear_settings: Callable[[], Any] = settings.clear
    copy_text: Callable[[str], Any] = _copy_text
    log_dir: Callable[[], Path] = logs.log_dir
    list_characters: Callable[[], list[Any]] = character.all_characters
    active_character: Callable[[], str] = field(default=lambda: character.active().id)
    add_character: Callable[..., Any] = character.add
    add_png_character: Callable[..., Any] = character.add_png
    use_character: Callable[[str], Any] = character.use
    remove_character: Callable[[str], Any] = character.remove
    send_character: Callable[..., Path] = character.send
    pick_character: Callable[[], str | None] = _pick_character
    pick_png: Callable[[], Any] = _pick_png
    pick_folder: Callable[[str], str | None] = _pick_folder
    make_voice_meter: Callable[..., Any] = _make_voice_meter
    vts_connect: Callable[..., Any] = vts.connect
    vts_token: Callable[[], str | None] = vts.load_token
    make_vts_reactor: Callable[..., Any] = _make_vts_reactor
    list_motions: Callable[[], list[Any]] = motion.all_motions
    inspect_motion: Callable[..., Any] = motion.inspect
    add_motion: Callable[..., Any] = motion.add
    remove_motion: Callable[[str], Any] = motion.remove
    idle_motion: Callable[[], str] = field(default=lambda: getattr(motion.idle(), "id", ""))
    set_idle_motion: Callable[[str | None], Any] = motion.set_idle
    pick_motion: Callable[[], str | None] = _pick_motion
    pick_clip: Callable[[list[str]], str | None] = _pick_clip
    load_launcher: Callable[[], Any] = launcher.load
    save_launcher: Callable[[Any], Any] = launcher.save
    make_launcher: Callable[..., Any] = launcher.Launcher
    make_watcher: Callable[..., Any] = launcher.Watcher
    edit_launcher: Callable[[QWidget], bool] = _edit_launcher
    wait_for_obs: Callable[[int], bool] = field(default=lambda port: launcher.wait_for_port("127.0.0.1", port, 60.0))


class Bridge(QObject):
    """작업 스레드에서 창으로. 시그널은 창의 스레드에서 처리된다."""

    checks = Signal(object)
    avatar = Signal(object)
    scenes = Signal(str)
    camera = Signal(object)  # 결과(dict) 또는 실패 안내(str)
    log = Signal(str)
    ffmpeg = Signal(str, bool)  # 안내 문장, 끝났는지
    chzzk = Signal(str)
    update = Signal(str)
    speed = Signal(object)  # doctor.Check
    vts = Signal(object)  # {"message": 안내, "models": [...], "hotkeys": [...]}
    youtube = Signal(str)
    launch = Signal(str)  # 방송 시작 버튼 진행 한 줄
    launch_done = Signal(object)  # (세팅, 설정, 결과 목록, 켰는지)


def card(*widgets: QWidget, title: str = "") -> QWidget:
    box = QWidget()
    box.setObjectName("Card")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)
    if title:
        label = QLabel(title)
        label.setObjectName("Eyebrow")
        layout.addWidget(label)
    for widget in widgets:
        layout.addWidget(widget)
    return box


def text(content: str, *, muted: bool = False, links: bool = False) -> QLabel:
    label = QLabel(content)
    label.setWordWrap(True)
    if muted:
        label.setObjectName("Muted")
    if links:
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
    return label


def row(*widgets: QWidget, stretch: int | None = None) -> QWidget:
    """가로 한 줄. ``stretch`` 번째 칸이 남는 폭을 차지하고, 없으면 오른쪽을 비운다."""
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    for index, widget in enumerate(widgets):
        layout.addWidget(widget, 1 if index == stretch else 0)
    if stretch is None:
        layout.addStretch(1)
    return box


class Wizard(QMainWindow):
    def __init__(self, backend: Backend | None = None) -> None:
        super().__init__()
        self.backend = backend or Backend()
        self.bridge = Bridge()
        self.bridge.checks.connect(self._show_checks)
        self.bridge.avatar.connect(self._show_avatar)
        self.bridge.scenes.connect(self._show_scenes)
        self.bridge.camera.connect(self._show_camera)
        self.bridge.log.connect(self._append_log)
        self.bridge.ffmpeg.connect(self._show_ffmpeg)
        self.bridge.chzzk.connect(self._show_chzzk)
        self.bridge.update.connect(self._show_update)
        self.bridge.speed.connect(self._show_speed)
        self.bridge.youtube.connect(self._show_youtube)
        self.bridge.vts.connect(self._show_vts)
        self.bridge.launch.connect(self._launch_line)
        self.bridge.launch_done.connect(self._launch_done)
        self.server: Any = None
        self.launch_watcher: Any = None
        self._launch_lines: list[str] = []
        self.checked: list[doctor.Check] = []
        self._threads: list[threading.Thread] = []
        self._closed = False
        self.setWindowTitle(f"debutkit {__version__} 설정 마법사")
        self.resize(980, 700)

        root = QWidget()
        root.setObjectName("Root")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setStyleSheet(EXTRA_STYLE)
        self.nav = QListWidget()
        self.nav.setObjectName("Steps")
        self.nav.addItems(STEPS)
        self.nav.setFixedWidth(190)
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        outer.addWidget(self.nav)

        right = QVBoxLayout()
        right.setContentsMargins(24, 20, 24, 16)
        self.pages = QStackedWidget()
        for build in (self._page_checks, self._page_avatar, self._page_scenes, self._page_overlay, self._page_finish):
            self.pages.addWidget(build())
        right.addWidget(self.pages, 1)
        bar = QHBoxLayout()
        self.back = QPushButton("이전")
        self.next = QPushButton("다음")
        self.next.setObjectName("Primary")
        self.back.clicked.connect(lambda: self.go(self.pages.currentIndex() - 1))
        self.next.clicked.connect(lambda: self.go(self.pages.currentIndex() + 1))
        bar.addStretch(1)
        bar.addWidget(self.back)
        bar.addWidget(self.next)
        right.addLayout(bar)
        outer.addLayout(right, 1)
        self.setCentralWidget(root)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.pages.currentChanged.connect(self._on_page)
        # 저장한 설정: 채널을 저장해 둔 경우 채팅과 알림 단계에서 시작(방송마다 오버레이 시작만 누르면 되도록)
        self._keep_settings = True
        self._voice_input = ""
        saved = self.backend.load_settings()
        self.apply_settings(saved)
        start = 3 if any(saved.get(name) for name in ("chzzk", "soop", "twitch", "youtube", "chzzk_api", "demo")) else 0
        self.nav.setCurrentRow(start)
        self._on_page(start)
        if start:
            self._append_log("저장한 설정을 불러왔습니다. 오버레이 시작을 누르면 채팅창과 알림이 켜집니다.")

    # ------------------------------------------------------------------ 이동
    def go(self, index: int) -> None:
        if 0 <= index < self.pages.count():
            self.nav.setCurrentRow(index)

    def _on_page(self, index: int) -> None:
        self.back.setEnabled(index > 0)
        self.next.setEnabled(index < self.pages.count() - 1)
        self.next.setVisible(index < self.pages.count() - 1)
        if index == 0 and not self.checked and self.check_button.isEnabled():
            self.run_checks()
        if index == self.pages.count() - 1:
            self._refresh_summary()

    def _run(self, job: Callable[[], None]) -> None:
        self._threads = [thread for thread in self._threads if thread.is_alive()]
        thread = threading.Thread(target=job, daemon=True)
        self._threads.append(thread)
        thread.start()

    def _emit(self, signal: Any, *values: Any) -> None:
        """작업 스레드에서 창으로. 창이 닫힌 뒤에는 보내지 않는다(닫힌 창의 객체를 건드리면 종료 때 충돌)."""
        if not self._closed:
            signal.emit(*values)

    @staticmethod
    def _title(content: str, lead: str, mascot: str = "") -> QWidget:
        """페이지 머리말. mascot(마스코트 이름)을 주면 왼쪽에 그 캐릭터 그림(안내 역할, assets/brand/mascot/README.txt)."""
        box = QWidget()
        outer = QHBoxLayout(box)
        outer.setContentsMargins(0, 0, 0, 8)
        picture = MASCOTS / f"{mascot}.png"
        if mascot and picture.is_file():
            face = QLabel()
            face.setObjectName(f"Mascot-{mascot}")
            face.setPixmap(QPixmap(str(picture)).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            face.setFixedSize(68, 68)
            outer.addWidget(face, 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        title = QLabel(content)
        title.setObjectName("Title")
        column.addWidget(title)
        column.addWidget(text(lead, muted=True))
        outer.addLayout(column, 1)
        return box

    # ------------------------------------------------------------------ 1. 점검
    def _page_checks(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("PC 점검", "방송에 필요한 사양과 프로그램을 점검합니다. 프로그램 설치나 설정 변경은 하지 않습니다. "
                                     "무대 감독 큐가 순서대로 안내합니다.", mascot="cue"))
        self.check_rows = QGridLayout()
        self.check_rows.setHorizontalSpacing(12)
        self.check_rows.setVerticalSpacing(8)
        rows = QWidget()
        rows.setLayout(self.check_rows)
        self.check_summary = QLabel("")
        self.check_summary.setObjectName("Status")
        self.check_button = QPushButton("다시 점검")
        self.check_button.clicked.connect(self.run_checks)
        self.ffmpeg_button = QPushButton("ffmpeg 다운로드")
        self.ffmpeg_button.clicked.connect(self.download_ffmpeg)
        self.ffmpeg_button.setVisible(False)
        self.ffmpeg_status = text("", muted=True)
        self.ffmpeg_status.setVisible(False)
        self.speed_button = QPushButton("업로드 속도 측정")
        self.speed_button.clicked.connect(self.measure_speed)
        self.speed_result = text("업로드 속도를 측정해 송출 해상도와 비트레이트를 추천합니다. 측정 시 Cloudflare 측정 서버로 임의 데이터를 전송합니다(약 10초).", muted=True)
        layout.addWidget(card(rows, self.check_summary))
        layout.addWidget(row(self.check_button, self.ffmpeg_button, self.speed_button))
        layout.addWidget(self.ffmpeg_status)
        layout.addWidget(self.speed_result)
        layout.addStretch(1)
        return page

    def run_checks(self) -> None:
        self.check_button.setEnabled(False)
        self.check_summary.setText("점검 중")
        port = self.port.value() if hasattr(self, "port") else OVERLAY_PORT
        self._run(lambda: self._emit(self.bridge.checks, self.backend.run_checks(overlay_port=port)))

    def _show_checks(self, checks: list[doctor.Check]) -> None:
        self.checked = checks
        while self.check_rows.count():
            item = self.check_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, check in enumerate(checks):
            state = QLabel(LABELS.get(check.status, check.status))
            state.setObjectName(STATE_STYLE.get(check.status, "StateOther"))
            state.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.check_rows.addWidget(state, index, 0)
            self.check_rows.addWidget(QLabel(check.title), index, 1)
            detail = text(check.detail + (f"\n조치: {check.hint}" if check.hint and check.status != OK else ""), muted=check.status == OK)
            detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.check_rows.addWidget(detail, index, 2)
        self.check_rows.setColumnStretch(2, 1)
        self.check_summary.setText(doctor.summary(checks))
        self.check_button.setEnabled(True)
        missing = any(c.key == "ffmpeg" and c.status != OK for c in checks)
        self.ffmpeg_button.setVisible(missing and self.backend.can_download_ffmpeg())

    def measure_speed(self) -> None:
        self.speed_button.setEnabled(False)
        self.speed_result.setText("업로드 속도 측정 중(약 10초)")

        def job() -> None:
            try:
                found = self.backend.measure_speed()
            except Exception as error:
                found = doctor.Check("upload", "업로드 속도", INFO, f"측정 실패: {error}")
            self._emit(self.bridge.speed, found)

        self._run(job)

    def _show_speed(self, found: doctor.Check) -> None:
        state = LABELS.get(found.status, found.status)
        self.speed_result.setText(f"[{state}] 업로드 속도 {found.detail}" + (f"\n조치: {found.hint}" if found.hint and found.status != OK else ""))
        self.speed_button.setEnabled(True)

    def download_ffmpeg(self) -> None:
        self.ffmpeg_button.setEnabled(False)
        self.ffmpeg_status.setVisible(True)
        self.ffmpeg_status.setText("ffmpeg 다운로드 중")
        megabytes = tools.ffmpeg_megabytes()

        def progress(done: int, total: int) -> None:
            percent = int(done * 100 / total) if total else 0
            self._emit(self.bridge.ffmpeg, f"ffmpeg 다운로드 중 {percent}%({done / 1e6:.0f} / {megabytes} MB)", False)

        def job() -> None:
            try:
                written = self.backend.download_ffmpeg(on_progress=progress, cancelled=lambda: self._closed)
                folder = Path(written[0]).parent if written else ""
                self._emit(self.bridge.ffmpeg, f"ffmpeg 설치 완료: {folder}", True)
            except Exception as error:
                self._emit(self.bridge.ffmpeg, f"ffmpeg 다운로드 실패: {error}", True)

        self._run(job)

    def _show_ffmpeg(self, message: str, finished: bool) -> None:
        self.ffmpeg_status.setText(message)
        if finished:
            self.ffmpeg_button.setEnabled(True)
            if "완료" in message:
                self.run_checks()

    # ------------------------------------------------------------------ 2. 캐릭터
    def _page_avatar(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("캐릭터", "방송에 사용할 캐릭터를 등록하거나 만들고 사용 조건을 확인합니다. "
                                              "PNGTuber와 3D(VRM, GLB, FBX)는 debutkit 캐릭터 화면으로 바로 방송할 수 있습니다."))
        self.characters = QListWidget()
        self.characters.setObjectName("Characters")
        self.characters.setMaximumHeight(140)
        self.characters.currentRowChanged.connect(self._show_character)
        self.character_detail = text("", muted=True)
        add = QPushButton("파일, 폴더 추가")
        add.clicked.connect(self.add_character)
        make = QPushButton("PNG로 만들기")
        make.clicked.connect(self.make_png_character)
        self.use_button = QPushButton("방송에 사용")
        self.use_button.setObjectName("Primary")
        self.use_button.clicked.connect(self.use_character)
        self.send_button = QPushButton("방송 프로그램으로 보내기")
        self.send_button.clicked.connect(self.send_character)
        self.preview_button = QPushButton("미리보기")
        self.preview_button.clicked.connect(self.preview_character)
        self.sheet_button = QPushButton("그림 만들기(VRM)")
        self.sheet_button.setToolTip("VRM을 정면, 3/4, 얼굴, 표정 7종으로 그리고 PNGTuber 4상태로 등록")
        self.sheet_button.clicked.connect(self.character_sheet)
        self.tracker_button = QPushButton("얼굴 추적 창 열기")
        self.tracker_button.setToolTip("웹캠으로 얼굴을 추적해 캐릭터의 머리 움직임, 눈, 입, 웃음에 반영(브라우저에서 카메라 허용)")
        self.tracker_button.clicked.connect(self.open_tracker)
        self.phone_button = QPushButton("휴대폰 얼굴 추적")
        self.phone_button.setToolTip("아이폰 앱(iFacialMocap, VTube Studio)의 얼굴 추적 값(ARKit 표정 52개)을 캐릭터에 반영. 같은 Wi-Fi 필요")
        self.phone_button.clicked.connect(self.open_phone)
        self.vmc_button = QPushButton("VMC 송신")
        self.vmc_button.setToolTip("debutkit 얼굴 추적 값을 Warudo, VSeeFace, VMagicMirror로 보내기(VMC 프로토콜)")
        self.vmc_button.clicked.connect(self.open_vmc)
        self.remove_button = QPushButton("삭제")
        self.remove_button.clicked.connect(self.remove_character)
        layout.addWidget(card(self.characters, self.character_detail, row(add, make, self.sheet_button, self.use_button), row(self.send_button, self.preview_button, self.tracker_button, self.phone_button, self.vmc_button, self.remove_button),
                              title="내 캐릭터"))
        self._filling = False
        self._pending_reaction = ""
        self.motions = QListWidget()
        self.motions.setObjectName("Motions")
        self.motions.setMaximumHeight(110)
        self.motions.currentRowChanged.connect(self._show_motion)
        self.motion_detail = text("", muted=True)
        add_motion = QPushButton("동작 파일 추가")
        add_motion.setToolTip("VRMA(VRoid 공식 동작 등), Mixamo 등에서 받은 FBX, 동작이 든 GLB 또는 이 파일들을 담은 zip")
        add_motion.clicked.connect(self.add_motion)
        self.play_motion_button = QPushButton("한 번 실행")
        self.play_motion_button.clicked.connect(self.play_motion)
        self.remove_motion_button = QPushButton("삭제")
        self.remove_motion_button.clicked.connect(self.remove_motion)
        self.idle_motion = QComboBox()
        self.idle_motion.setMinimumWidth(200)
        self.idle_motion.setToolTip("대기 중 반복할 동작. 없음은 캐릭터 화면의 기본 움직임(호흡, 흔들림)")
        self.idle_motion.currentIndexChanged.connect(self._idle_changed)
        self.motion_reaction = QComboBox()
        self.motion_reaction.setMinimumWidth(160)
        self.motion_reaction.setToolTip("후원이 오면 실행할 동작")
        self.motion_min = QSpinBox()
        self.motion_min.setRange(0, 1_000_000)
        self.motion_min.setSingleStep(1000)
        self.motion_min.setSuffix(" 원 이상")
        self.motion_min.setToolTip("이 금액 이상의 후원에 반응(별풍선은 1개 100원으로 계산). 0은 모든 후원과 멤버십")
        layout.addWidget(card(self.motions, self.motion_detail, row(add_motion, self.play_motion_button, self.remove_motion_button),
                              row(QLabel("기본 동작"), self.idle_motion), row(QLabel("후원 반응"), self.motion_reaction, self.motion_min),
                              title="3D 캐릭터 동작(VRM, GLB, FBX)"))
        create = text(
            "<b>PNGTuber</b>: 입 다문 이미지와 입 벌린 이미지(투명 PNG, 같은 크기) 2장으로 시작. 눈 감은 이미지를 더하면 눈 깜빡임 표시<br>"
            '<b>3D(VRM)</b>: <a href="https://store.steampowered.com/app/1486350/VRoid_Studio/" style="{0}">VRoid Studio</a>(무료, 한국어, Windows와 macOS) 또는 '
            '<a href="https://account.vket.com/" style="{0}">Vket Avatar Maker</a>(웹, 무료. 법인, 소속사 사용은 HIKKY 사전 확인)로 제작. '
            "VSeeFace는 VRM 0.x만 읽으므로 내보낼 때 버전 선택<br>"
            '<b>3D(GLB, FBX)</b>: 사람 모양 뼈가 있는 모델 등록 가능. 뼈가 없으면 '
            '<a href="https://www.mixamo.com/" style="{0}">Mixamo</a>(무료) 자동 리깅 후 FBX로 받아 등록<br>'
            '<b>Live2D</b>: <a href="https://www.live2d.com/en/cubism/about/" style="{0}">Live2D Cubism Editor</a>(FREE 버전 제한 있음). '
            "일러스트 PSD를 리거에게 의뢰하는 방식이 일반적<br>"
            '<a href="https://github.com/BudongJW/debutkit/blob/main/docs/CHARACTER.md" style="{0}">제작 도구, 파일 형식, 라이선스 정리</a>'.format(LINK),
            links=True)
        layout.addWidget(card(create, title="캐릭터 만들기"))
        self.vts_state = text("VTube Studio 플러그인 API를 켠 뒤 연결하면 모델 불러오기와 후원 반응(단축키 실행)을 사용할 수 있습니다.", muted=True)
        connect_vts = QPushButton("VTube Studio 연결")
        connect_vts.clicked.connect(lambda: self.vts_action("login"))
        refresh = QPushButton("모델, 단축키 불러오기")
        refresh.clicked.connect(lambda: self.vts_action("list"))
        self.vts_models = QComboBox()
        self.vts_models.setMinimumWidth(200)
        load_model = QPushButton("모델 불러오기")
        load_model.clicked.connect(lambda: self.vts_action("load"))
        self.vts_hotkey = QComboBox()
        self.vts_hotkey.setEditable(True)
        self.vts_hotkey.setMinimumWidth(160)
        self.vts_hotkey.setToolTip("후원이 오면 실행할 VTube Studio 단축키 이름. 비워 두면 후원 반응 사용 안 함")
        self.vts_min = QSpinBox()
        self.vts_min.setRange(0, 1_000_000)
        self.vts_min.setSingleStep(1000)
        self.vts_min.setSuffix(" 원 이상")
        self.vts_min.setToolTip("이 금액 이상의 후원에 반응(별풍선은 1개 100원으로 계산). 0은 모든 후원과 멤버십")
        try_hotkey = QPushButton("시험 실행")
        try_hotkey.clicked.connect(lambda: self.vts_action("trigger"))
        layout.addWidget(card(self.vts_state, row(connect_vts, refresh), row(self.vts_models, load_model, stretch=0),
                              row(QLabel("후원 반응"), self.vts_hotkey, self.vts_min, try_hotkey), title="VTube Studio(Live2D)"))
        guide = text(
            "<b>PNGTuber, 3D(VRM)</b>: debutkit 캐릭터 화면(OBS 마이크 음량으로 입 움직임). OBS 장면 단계에서 아바타 프로그램을 debutkit으로 선택<br>"
            "<b>Live2D 모델</b>: VTube Studio(수익 방송 시 유료 버전 필요). 방송 프로그램으로 보내기로 모델 폴더에 복사<br>"
            "<b>3D(VRM) 얼굴 추적</b>: Warudo, VMagicMirror, VSeeFace(VRM 0.x만)<br>"
            f'<a href="{SOFTWARE_URL}" style="{LINK}">프로그램 목록과 라이선스</a>', links=True)
        self.avatar_path = QLineEdit()
        self.avatar_path.setPlaceholderText("모델 파일(.vrm 등)")
        pick = QPushButton("파일 선택")
        pick.clicked.connect(self._pick_avatar)
        self.avatar_agency = QCheckBox("소속사(기획사) 활동 기준으로 확인")
        self.avatar_agency.setChecked(True)
        check = QPushButton("사용 조건 확인")
        check.clicked.connect(self.check_avatar)
        self.avatar_result = text("", muted=True)
        layout.addWidget(card(row(self.avatar_path, pick, stretch=0), self.avatar_agency, check, self.avatar_result, title="모델 사용 조건(소속사 활동 기준 확인)"))
        layout.addWidget(card(guide, title="방송 프로그램"))
        layout.addStretch(1)
        self.refresh_characters()
        self.refresh_motions()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("PageScroll")
        page.setObjectName("PageBody")
        scroll.setWidget(page)
        return scroll

    # 캐릭터 목록과 작업
    def refresh_characters(self, select: str | None = None) -> None:
        self._character_list = self.backend.list_characters()
        active = self.backend.active_character()
        self.characters.blockSignals(True)
        self.characters.clear()
        for item in self._character_list:
            mark = "  [방송 사용 중]" if item.id == active else ""
            warn = f"  확인 필요 {len(item.warnings)}건" if item.warnings else ""
            self.characters.addItem(f"{item.name}  ({item.kind_name}){mark}{warn}")
        self.characters.blockSignals(False)
        ids = [item.id for item in self._character_list]
        target = select if select in ids else active if active in ids else (ids[0] if ids else None)
        if target is not None:
            self.characters.setCurrentRow(ids.index(target))
            self._show_character(ids.index(target))

    def selected_character(self) -> Any:
        row_ = self.characters.currentRow()
        return self._character_list[row_] if 0 <= row_ < len(self._character_list) else None

    def _show_character(self, row_: int) -> None:
        item = self._character_list[row_] if 0 <= row_ < len(self._character_list) else None
        if item is None:
            self.character_detail.setText("")
            return
        lines = [f"{item.kind_name}" + (f" {item.version}" if item.version else "") + (f", 제작자 {item.author}" if item.author else ""),
                 f"방송: {item.broadcast}"]
        lines += [f"사용 조건: {line}" for line in item.license] + [f"확인 필요: {line}" for line in item.warnings]
        self.character_detail.setText("\n".join(lines))
        self.send_button.setEnabled(item.kind in ("live2d", "vrm"))
        self.send_button.setText("VTube Studio로 보내기" if item.kind == "live2d" else "Warudo로 보내기" if item.kind == "vrm" else "방송 프로그램으로 보내기")
        self.remove_button.setEnabled(not item.builtin)
        self.preview_button.setEnabled(item.renders_in_overlay)
        self.sheet_button.setEnabled(item.kind == "vrm")
        self.tracker_button.setEnabled(item.renders_in_overlay)
        self.phone_button.setEnabled(item.renders_in_overlay)

    def _character_message(self, message: str) -> None:
        self.character_detail.setText(message)

    def add_character(self) -> None:
        path = self.backend.pick_character()
        if not path:
            return
        try:
            added = self.backend.add_character(path)
        except (ValueError, OSError) as error:
            return self._character_message(f"등록 실패: {error}")
        self.refresh_characters(added.id)

    def make_png_character(self) -> None:
        picked = self.backend.pick_png()
        if not picked:
            return
        name, images = picked
        try:
            added = self.backend.add_png_character(images.get("idle"), images.get("talk"), images.get("blink"), images.get("talk_blink"), name=name)
        except (ValueError, OSError) as error:
            return self._character_message(f"만들기 실패: {error}")
        self.refresh_characters(added.id)

    def use_character(self) -> None:
        item = self.selected_character()
        if item is None:
            return
        self.backend.use_character(item.id)
        if item.renders_in_overlay:  # OBS 장면의 아바타를 debutkit 캐릭터 화면으로
            self.avatar_app.setCurrentIndex(self.avatar_app.findData("debutkit"))
        elif item.kind == "live2d":
            self.avatar_app.setCurrentIndex(self.avatar_app.findData("vts"))
        self.refresh_characters(item.id)

    def remove_character(self) -> None:
        item = self.selected_character()
        if item is None or item.builtin:
            return
        self.backend.remove_character(item.id)
        self.refresh_characters()

    def send_character(self) -> None:
        item = self.selected_character()
        if item is None or item.kind not in ("live2d", "vrm"):
            return
        app = "vts" if item.kind == "live2d" else "warudo"
        title = "VTube Studio" if app == "vts" else "Warudo"
        try:
            target = self.backend.send_character(item, app, None)
        except ValueError:
            folder = self.backend.pick_folder(f"{title} 모델 폴더 선택({title}의 모델 폴더 열기 기능으로 위치 확인)")
            if not folder:
                return self._character_message(f"{title} 모델 폴더를 찾지 못해 보내지 않았습니다.")
            try:
                target = self.backend.send_character(item, app, folder)
            except (ValueError, OSError) as error:
                return self._character_message(f"보내기 실패: {error}")
        except OSError as error:
            return self._character_message(f"보내기 실패: {error}")
        self._character_message(f"{title}로 복사했습니다: {target}\n{title}를 다시 시작하면 모델 목록에 표시됩니다.")

    def preview_character(self) -> None:
        item = self.selected_character()
        if item is None:
            return
        if self.server is None:
            return self._character_message("채팅과 알림 단계에서 오버레이를 시작한 뒤 미리보기를 열 수 있습니다.")
        self.backend.open_url(f"{self.server.url}/character?id={urllib.parse.quote(item.id)}&demo")

    def character_sheet(self) -> None:
        item = self.selected_character()
        if self.server is None:
            return self._character_message("채팅과 알림 단계에서 오버레이를 시작한 뒤 그림 만들기를 열 수 있습니다.")
        target = f"?id={urllib.parse.quote(item.id)}" if item is not None and item.kind == "vrm" else ""
        self.backend.open_url(f"{self.server.url}/character/sheet{target}")

    # 3D 캐릭터 동작
    def refresh_motions(self, select: str | None = None) -> None:
        self._motion_list = self.backend.list_motions()
        idle = self.backend.idle_motion()
        self.motions.blockSignals(True)
        self.motions.clear()
        for item in self._motion_list:
            length = f", {item.duration:.1f}초" if item.duration else ""
            mark = "  [기본 동작]" if item.id == idle else ""
            warn = f"  확인 필요 {len(item.warnings)}건" if item.warnings else ""
            self.motions.addItem(f"{item.name}  ({item.kind_name}{length}){mark}{warn}")
        self.motions.blockSignals(False)
        self._filling = True
        reaction = self.motion_reaction.currentData() or self._pending_reaction
        self.idle_motion.clear()
        self.motion_reaction.clear()
        self.idle_motion.addItem("없음(기본 움직임)", "")
        self.motion_reaction.addItem("사용 안 함", "")
        for item in self._motion_list:
            self.idle_motion.addItem(item.name, item.id)
            self.motion_reaction.addItem(item.name, item.id)
        self.idle_motion.setCurrentIndex(max(0, self.idle_motion.findData(idle)))
        self.motion_reaction.setCurrentIndex(max(0, self.motion_reaction.findData(reaction)) if reaction else 0)
        self._filling = False
        ids = [item.id for item in self._motion_list]
        if not ids:
            self._show_motion(-1)
            return
        target = ids.index(select) if select in ids else 0
        self.motions.setCurrentRow(target)
        self._show_motion(target)

    def selected_motion(self) -> Any:
        row_ = self.motions.currentRow()
        return self._motion_list[row_] if 0 <= row_ < len(self._motion_list) else None

    def _show_motion(self, row_: int) -> None:
        item = self._motion_list[row_] if 0 <= row_ < len(self._motion_list) else None
        self.play_motion_button.setEnabled(item is not None)
        self.remove_motion_button.setEnabled(item is not None)
        if item is None:
            self.motion_detail.setText("VRMA(VRoid 공식 동작 등), Mixamo 등에서 받은 FBX, 동작이 든 GLB를 등록하면 3D 캐릭터(VRM, GLB, FBX)가 "
                                       "기본 동작이나 후원 반응으로 움직입니다. 동작 파일은 직접 받은 파일만 사용합니다.")
            return
        lines = [f"{item.kind_name}" + (f" {item.version}" if item.version else "") + (f", {item.duration:.1f}초" if item.duration else "")
                 + f", 움직이는 뼈 {item.bones}개" + (f", 동작 이름 {item.clip}" if item.clip else "")]
        lines += [f"사용 조건: {line}" for line in item.license] + [f"확인 필요: {line}" for line in item.warnings]
        self.motion_detail.setText("\n".join(lines))

    def _motion_message(self, message: str) -> None:
        self.motion_detail.setText(message)

    def add_motion(self) -> None:
        path = self.backend.pick_motion()
        if not path:
            return
        clip_name = ""
        try:
            if Path(path).suffix.lower() != ".zip":
                found = self.backend.inspect_motion(path)
                if len(found.clips) > 1:
                    picked = self.backend.pick_clip(found.clips)
                    if picked is None:
                        return
                    clip_name = picked
            added, skipped = self.backend.add_motion(path, clip=clip_name)
        except (ValueError, OSError) as error:
            return self._motion_message(f"등록 실패: {error}")
        self.refresh_motions(added[0].id)
        if len(added) > 1 or skipped:
            note = f"동작 {len(added)}개 등록" + (f", 건너뜀 {len(skipped)}개: " + " / ".join(skipped[:3]) if skipped else "")
            self._motion_message(note)

    def remove_motion(self) -> None:
        item = self.selected_motion()
        if item is None:
            return
        self.backend.remove_motion(item.id)
        self.refresh_motions()

    def play_motion(self) -> None:
        item = self.selected_motion()
        if item is None:
            return
        state = getattr(self.server, "motion", None) if self.server is not None else None
        if state is None:
            return self._motion_message("채팅과 알림 단계에서 오버레이를 시작한 뒤 실행할 수 있습니다.")
        state.play(item.id)
        self._motion_message(f"실행: {item.name}. 방송에 사용하는 캐릭터가 3D(VRM, GLB, FBX)일 때 캐릭터 화면에 표시됩니다.")

    def _idle_changed(self, _index: int) -> None:
        if self._filling:
            return
        chosen = self.idle_motion.currentData() or None
        try:
            self.backend.set_idle_motion(chosen)
        except (ValueError, OSError) as error:
            return self._motion_message(f"기본 동작 지정 실패: {error}")
        selected = self.selected_motion()
        self.refresh_motions(selected.id if selected else None)

    def motion_reaction_rules(self) -> list[str]:
        chosen = self.motion_reaction.currentData()
        return [f"{self.motion_min.value()}:{chosen}"] if chosen else []

    # VTube Studio
    def vts_reaction_rules(self) -> list[str]:
        hotkey = self.vts_hotkey.currentText().strip()
        return [f"{self.vts_min.value()}:{hotkey}"] if hotkey else []

    def vts_action(self, action: str) -> None:
        model_id = self.vts_models.currentData()
        hotkey = self.vts_hotkey.currentText().strip()
        if action == "trigger" and not hotkey:
            return self._show_vts({"message": "실행할 단축키 이름을 입력하거나 목록에서 선택하십시오."})
        if action == "login":
            self.vts_state.setText("VTube Studio 화면에서 debutkit 플러그인 허용을 누르십시오.")

        def job() -> None:
            result: dict[str, Any] = {}
            try:
                with self.backend.vts_connect(request_new=action == "login") as client:
                    if action == "load" and model_id:
                        client.load_model(model_id)
                        result["message"] = f"불러옴: {self.vts_models.currentText()}"
                    elif action == "trigger":
                        client.trigger(hotkey)
                        result["message"] = f"단축키 실행: {hotkey}"
                    else:
                        result["models"] = [(model.name, model.id, model.loaded) for model in client.models()]
                        result["hotkeys"] = [hotkey_.name for hotkey_ in client.hotkeys()]
                        result["message"] = "VTube Studio 연결됨. 모델과 현재 모델의 단축키를 불러왔습니다."
            except Exception as error:
                result["message"] = f"VTube Studio: {error}"
            self._emit(self.bridge.vts, result)

        self._run(job)

    def _show_vts(self, result: dict[str, Any]) -> None:
        self.vts_state.setText(result.get("message", ""))
        if "models" in result:
            self.vts_models.clear()
            for name, model_id, loaded in result["models"]:
                self.vts_models.addItem(name + (" (현재)" if loaded else ""), model_id)
        if result.get("hotkeys"):
            current = self.vts_hotkey.currentText()
            self.vts_hotkey.clear()
            self.vts_hotkey.addItems(result["hotkeys"])
            self.vts_hotkey.setEditText(current or result["hotkeys"][0])

    def open_tracker(self) -> None:
        """얼굴 추적 화면은 카메라를 쓰므로 OBS가 아닌 일반 브라우저에서 연다."""
        if self.server is None:
            return self._character_message("채팅과 알림 단계에서 오버레이를 시작한 뒤 얼굴 추적 창을 열 수 있습니다.")
        self.backend.open_url(f"{self.server.url}/tracker")
        self._character_message("브라우저에서 추적 시작을 누르고 카메라 사용을 허용하십시오. 추적 창을 닫으면 기본 움직임으로 돌아갑니다.")

    def open_phone(self) -> None:
        """휴대폰 얼굴 추적 설정 화면(휴대폰 앱의 IP 입력, 연결, 정면 맞추기)을 브라우저에서 연다."""
        if self.server is None:
            return self._character_message("채팅과 알림 단계에서 오버레이를 시작한 뒤 휴대폰 얼굴 추적을 설정할 수 있습니다.")
        self.backend.open_url(f"{self.server.url}/phone")
        self._character_message("휴대폰과 PC를 같은 Wi-Fi에 연결하고, 휴대폰 앱에 표시된 IP 주소를 입력한 뒤 연결 시작을 누르십시오. "
                                "처음 연결할 때 Windows 보안 경고가 나오면 개인 네트워크를 허용하십시오.")

    def open_vmc(self) -> None:
        """VMC 송신 설정 화면(보낼 주소와 포트, 퍼펙트 싱크, 좌우 반전)을 브라우저에서 연다."""
        if self.server is None:
            return self._character_message("채팅과 알림 단계에서 오버레이를 시작한 뒤 VMC 송신을 설정할 수 있습니다.")
        self.backend.open_url(f"{self.server.url}/vmc")
        self._character_message("받는 프로그램(Warudo, VSeeFace 등)에서 VMC 수신을 켜고 포트를 맞춘 뒤 송신 시작을 누르십시오.")

    def _pick_avatar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "아바타 모델", "", "모델 (*.vrm *.model3.json *.moc3);;모든 파일 (*)")
        if path:
            self.avatar_path.setText(path)

    def check_avatar(self) -> None:
        path = self.avatar_path.text().strip()
        if not path:
            self.avatar_result.setText("모델 파일을 먼저 선택하십시오.")
            return
        agency = self.avatar_agency.isChecked()
        self._run(lambda: self._emit(self.bridge.avatar, self.backend.check_avatar(path, agency=agency)))

    def _show_avatar(self, checks: list[doctor.Check]) -> None:
        self.avatar_result.setText("\n".join(f"[{LABELS.get(c.status, c.status)}] {c.detail}" + (f"\n조치: {c.hint}" if c.hint else "") for c in checks))

    # ------------------------------------------------------------------ 3. OBS 장면
    def _page_scenes(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("OBS 장면", "대기 화면, 본방송, 토크, 자리 비움, 엔딩 장면을 생성합니다. 기존 장면은 변경하지 않습니다."))
        layout.addWidget(card(text("OBS를 실행한 뒤 <b>도구 메뉴의 WebSocket 서버 설정</b>에서 <b>WebSocket 서버 사용</b>을 체크하십시오.<br>"
                                   "WebSocket 비밀번호를 사용하는 경우 아래에 입력하십시오.<br>"
                                   "처음 구성하는 경우 OBS 장면 모음 메뉴에서 새 장면 모음을 먼저 만들 것을 권장합니다.", links=True)))
        form = QFormLayout()
        self.obs_port = QSpinBox()
        self.obs_port.setRange(1, 65535)
        self.obs_port.setValue(4455)
        self.obs_password = QLineEdit()
        self.obs_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.obs_password.setText(os.environ.get("OBS_WEBSOCKET_PASSWORD", ""))
        self.avatar_app = QComboBox()
        for label, value in AVATARS:
            self.avatar_app.addItem(label, value)
        self.replay = QCheckBox("자동 클립용 리플레이 버퍼 사용(60초)")
        self.replay.setChecked(True)
        # 게임 패키지 배치: 방송 화면 미리보기에서 적용한 게임이 처음 값
        from ..overlay import games as game_packs

        self.scene_game = QComboBox()
        self.scene_game.addItem("기본 배치", "")
        for key, game in game_packs.GAMES.items():
            self.scene_game.addItem(f"{game.name} ({game.genre})", key)
        self.scene_game.setToolTip("고른 게임의 HUD(미니맵, 킬 로그, 체력과 스킬)를 피해 캐릭터, 채팅, 목표 게이지, 순위를 놓고 프레임을 넣습니다")
        self.scene_game.setCurrentIndex(max(0, self.scene_game.findData(game_packs.load()["game"])))
        self.scene_frames = QCheckBox("프레임 넣기(캐릭터 테두리, 대기, 자리 비움, 엔딩 화면)")
        form.addRow("WebSocket 포트", self.obs_port)
        form.addRow("비밀번호", self.obs_password)
        form.addRow("아바타 프로그램", self.avatar_app)
        form.addRow("게임 배치", self.scene_game)
        form.addRow("", self.scene_frames)
        form.addRow("", self.replay)
        fields = QWidget()
        fields.setLayout(form)
        self.scenes_button = QPushButton("장면 생성")
        self.scenes_button.setObjectName("Primary")
        self.scenes_button.clicked.connect(self.make_scenes)
        self.scenes_result = text("", muted=True)
        layout.addWidget(card(fields, self.scenes_button, self.scenes_result))
        self.camera_button = QPushButton("휴대폰 카메라 소스 추가")
        self.camera_button.setToolTip("휴대폰 카메라 영상(실사, 손 캠)을 같은 Wi-Fi로 받는 OBS 미디어 소스(SRT)를 현재 방송 장면에 추가")
        self.camera_button.clicked.connect(self.add_phone_camera)
        self.camera_result = text("휴대폰 앱(Larix Broadcaster 등)이 보내는 카메라 영상을 OBS 소스로 받습니다. 암호가 맞는 휴대폰만 연결되며 소리는 보내지 않습니다.",
                                  muted=True)
        self.camera_qr = QLabel()
        self.camera_qr.setVisible(False)
        layout.addWidget(card(row(self.camera_button), self.camera_result, self.camera_qr, title="휴대폰 카메라 영상"))
        layout.addStretch(1)
        return page

    def add_phone_camera(self) -> None:
        self.camera_button.setEnabled(False)
        self.camera_result.setText("OBS 연결 중")
        port, password = self.obs_port.value(), self.obs_password.text() or None

        def job() -> None:
            try:
                self._emit(self.bridge.camera, self.backend.add_phone_camera("127.0.0.1", port, password))
            except camera.CameraError as error:
                self._emit(self.bridge.camera, f"휴대폰 카메라 소스 추가 실패: {error}")
            except Exception as error:
                self._emit(self.bridge.camera, f"휴대폰 카메라 소스 추가 실패: {camera.obs_failure(error)}")

        self._run(job)

    def _show_camera(self, result: Any) -> None:
        self.camera_button.setEnabled(True)
        if isinstance(result, str):
            self.camera_qr.setVisible(False)
            self.camera_result.setText(result)
            return
        info = result["info"]
        where = ", ".join(result["added"]) + " 장면에 추가" if result["added"] else ", ".join(result["kept"]) + " 장면에 이미 있음"
        lines = [f"OBS 소스 {result['source']} {'만듦' if result['created'] else '설정 맞춤'}, {where}. 상태: {result['state']['text']}"]
        if info["address"]:
            lines += [f"휴대폰 앱 주소 {info['url']}, 암호 {info['passphrase']}(암호 길이 16), 모드 Caller, 지연 여유 {info['latency']}밀리초",
                      "Larix Broadcaster: 휴대폰 카메라로 아래 QR 코드를 찍어 가져온 뒤 방송 버튼(빨간 원)",
                      "OBS가 처음 수신할 때 Windows 보안 경고가 나오면 개인 네트워크를 허용하십시오."]
            if len(info["addresses"]) > 1:
                lines.append(f"같은 Wi-Fi가 아니면 다른 주소 사용: {', '.join(info['addresses'][1:])}")
            self.camera_qr.setPixmap(qr_pixmap(info["larix"]))
            self.camera_qr.setVisible(True)
        else:
            lines.append("이 PC의 내부 네트워크 주소를 찾지 못함: Wi-Fi나 유선 연결 확인")
            self.camera_qr.setVisible(False)
        self.camera_result.setText("\n".join(lines))

    def make_scenes(self) -> None:
        self._keep_settings = True
        self.remember()
        self.scenes_button.setEnabled(False)
        self.scenes_result.setText("OBS 연결 중")
        base = f"http://127.0.0.1:{self.port.value()}"
        options = scenes.SceneOptions(overlay_url=f"{base}/chat", alerts_url=f"{base}/alerts", character_url=f"{base}/character",
                                       draw_url=f"{base}/draw", pick_url=f"{base}/pick", wall_url=f"{base}/wall", race_url=f"{base}/race",
                                       goal_url=f"{base}/wall/goal", rank_url=f"{base}/wall/rank", frame_url=f"{base}/frame",
                                       avatar=str(self.avatar_app.currentData()), game=str(self.scene_game.currentData() or ""),
                                       frames=self.scene_frames.isChecked())
        port, password, replay = self.obs_port.value(), self.obs_password.text() or None, 60 if self.replay.isChecked() else None

        def job() -> None:
            try:
                report, _ = self.backend.apply_scenes("127.0.0.1", port, password, options, replay_buffer=replay)
                self._emit(self.bridge.scenes, scenes.format_report(report))
            except Exception as error:
                self._emit(self.bridge.scenes, f"장면 생성 실패: {error}\nOBS 실행 여부와 WebSocket 서버 사용 설정을 확인하십시오.")

        self._run(job)

    def _show_scenes(self, message: str) -> None:
        self.scenes_result.setText(message)
        self.scenes_button.setEnabled(True)

    # ------------------------------------------------------------------ 4. 채팅과 알림
    def _page_overlay(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("채팅과 알림", "방송 채널을 입력하고 오버레이를 시작하면 OBS 채팅창과 후원 알림이 표시됩니다. 채팅은 저장하지 않습니다."))
        form = QFormLayout()
        self.chzzk = QLineEdit()
        self.chzzk.setPlaceholderText("https://chzzk.naver.com/live/채널ID")
        self.soop = QLineEdit()
        self.soop.setPlaceholderText("https://play.sooplive.co.kr/아이디")
        self.twitch = QLineEdit()
        self.twitch.setPlaceholderText("채널 이름")
        self.youtube = QLineEdit()
        self.youtube.setPlaceholderText("방송 주소(https://www.youtube.com/watch?v=영상ID)")
        self.youtube_key = QLineEdit()
        self.youtube_key.setPlaceholderText("YouTube Data API 키(저장하지 않음)")
        self.youtube_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.youtube_key.setText(os.environ.get("YOUTUBE_API_KEY", ""))
        self.youtube_check_button = QPushButton("연결 확인")
        self.youtube_check_button.setToolTip("API 키, 라이브 채팅, 요청 방식, 스트리밍 방식을 한 번씩 확인(할당량 약 11 단위)")
        self.youtube_check_button.clicked.connect(self.check_youtube)
        self.chzzk_api = QCheckBox("본인 치지직 채널을 공식 API로 수신(로그인 필요, 권장)")
        signed_in = self.backend.chzzk_signed_in()
        self.chzzk_api.setChecked(signed_in)
        self.chzzk_id = QLineEdit()
        self.chzzk_id.setPlaceholderText("Client ID(치지직 개발자 센터)")
        self.chzzk_id.setText(os.environ.get("CHZZK_CLIENT_ID", ""))
        self.chzzk_secret = QLineEdit()
        self.chzzk_secret.setPlaceholderText("Client Secret")
        self.chzzk_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.chzzk_secret.setText(os.environ.get("CHZZK_CLIENT_SECRET", ""))
        self.chzzk_login_button = QPushButton("치지직 로그인")
        self.chzzk_login_button.clicked.connect(self.login_chzzk)
        self.chzzk_state = text("로그인됨" if signed_in else "로그인 전", muted=True)
        self.demo = QCheckBox("데모 채팅 함께 표시(표시 형태 확인용)")
        self.autoclip = QCheckBox("자동 클립: 채팅 급증 또는 !clip 입력 시 저장(OBS 리플레이 버퍼, ffmpeg 필요)")
        self.clip_gif = QCheckBox("클립마다 움짤(GIF)")
        self.clip_shorts = QCheckBox("클립마다 세로 쇼츠(1080x1920)")
        self.clip_gif.setToolTip("클립 앞 6초를 폭 480 GIF로. 클립 폴더에 함께 저장")
        self.clip_shorts.setToolTip("흐린 배경 위에 원본을 놓은 세로 영상. 다른 형태는 debutkit clip shorts 명령")
        self.chat_commands = QCheckBox("스트리머, 매니저 채팅 명령: !동작, !단축키, !모집, !마감, !추첨, !순서")
        self.chat_commands.setChecked(True)
        self.chat_commands.setToolTip("스트리머와 매니저의 채팅만 처리. 캐릭터 동작, VTube Studio 단축키, 시청자 참여 추첨 조작")
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(OVERLAY_PORT)
        form.addRow("치지직", self.chzzk)
        form.addRow("SOOP", self.soop)
        form.addRow("Twitch", self.twitch)
        form.addRow("YouTube", row(self.youtube, self.youtube_key, self.youtube_check_button, stretch=0))
        form.addRow("", self.chzzk_api)
        form.addRow("치지직 API", row(self.chzzk_id, self.chzzk_secret, self.chzzk_login_button, stretch=0))
        form.addRow("", self.chzzk_state)
        form.addRow("", self.demo)
        form.addRow("", self.autoclip)
        form.addRow("", row(self.clip_gif, self.clip_shorts))
        form.addRow("", self.chat_commands)
        self.voice_threshold = QSpinBox()
        self.voice_threshold.setRange(-70, -10)
        self.voice_threshold.setValue(-40)
        self.voice_threshold.setSuffix(" dB")
        self.voice_threshold.setToolTip("OBS 마이크 음량이 이 값을 넘으면 캐릭터가 말하는 것으로 표시. 잡음에 반응하면 높이고(-30 등), 말해도 반응이 없으면 낮춤")
        form.addRow("캐릭터 입 움직임 기준", self.voice_threshold)
        form.addRow("포트", self.port)
        fields = QWidget()
        fields.setLayout(form)
        self.overlay_button = QPushButton("오버레이 시작")
        self.overlay_button.setObjectName("Primary")
        self.overlay_button.clicked.connect(self.toggle_overlay)
        self.open_button = QPushButton("시작하기 화면 열기(OBS에 넣기, 시험 메시지)")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(lambda: self.server and self.backend.open_url(self.server.url))
        self.draw_button = QPushButton("추첨 조작 화면")
        self.draw_button.setToolTip("후원 추첨(상품, 확률, 금액별 횟수, 연출, 시험 추첨)과 시청자 참여 추첨(모집, 당첨자 뽑기, 순서 정하기)")
        self.draw_button.setEnabled(False)
        self.draw_button.clicked.connect(lambda: self.server and self.backend.open_url(f"{self.server.url}/draw/control"))
        self.remote_button = QPushButton("휴대폰 조작 화면")
        self.remote_button.setToolTip("같은 Wi-Fi의 휴대폰 브라우저로 시청자 참여 추첨, 3D 캐릭터 동작 조작(QR로 등록하고 PC에서 승인한 휴대폰만)")
        self.remote_button.setEnabled(False)
        self.remote_button.clicked.connect(lambda: self.server and self.backend.open_url(f"{self.server.url}/phone#remote"))
        self.broadcast_button = QPushButton("OBS 없이 바로 방송")
        self.broadcast_button.setToolTip("캐릭터, 채팅, 알림, 추첨을 모은 송출 화면을 치지직, SOOP, YouTube, Twitch로 바로 송출(Windows, ffmpeg 필요)")
        self.broadcast_button.setEnabled(False)
        self.broadcast_button.setVisible(sys.platform == "win32")
        self.broadcast_button.clicked.connect(lambda: self.server and self.backend.open_url(f"{self.server.url}/broadcast/control"))
        self.logo_button = QPushButton("로고 만들기")
        self.logo_button.setToolTip("아이콘, 기본 도형, 계정 없는 공개 모델(AI Horde) 또는 본인 키의 생성형 AI 심볼과 채널 이름으로 방송 로고(SVG, PNG) 만들기")
        self.logo_button.setEnabled(False)
        self.logo_button.clicked.connect(lambda: self.server and self.backend.open_url(f"{self.server.url}/logo"))
        #: 방송 연출 조작 화면(OBS 독으로도 사용): 뽑기판, 후원 벽, 참여 레이스
        self.stage_buttons: dict[str, QPushButton] = {}
        for path, label, tip in (("/pick/control", "뽑기판", "칸을 눌러 여는 뽑기판. 당첨 칸은 조작 화면에서만 보임. 채팅과 후원으로 시청자가 열기(선택)"),
                                 ("/wall/control", "후원 벽", "들어온 후원을 카드로 쌓는 방송 벽지, 목표 게이지, 후원 순위(치지직, SOOP, YouTube, Twitch)"),
                                 ("/race/control", "참여 레이스", "참여 추첨 참가자(!참가, 후원 참가)가 겨루는 레이스 게임")):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.setEnabled(False)
            button.clicked.connect(lambda _=False, path=path: self.server and self.backend.open_url(f"{self.server.url}{path}"))
            self.stage_buttons[path] = button
        self.overlay_log = QPlainTextEdit()
        self.overlay_log.setReadOnly(True)
        self.overlay_log.setMaximumBlockCount(200)
        self.overlay_log.setPlaceholderText("연결 상태와 저장한 클립이 이곳에 표시됩니다.")
        stage_label = QLabel("방송 연출")
        stage_label.setObjectName("Muted")
        layout.addWidget(card(fields, row(self.overlay_button, self.open_button, self.draw_button, self.remote_button, self.broadcast_button,
                                          self.logo_button), row(stage_label, *self.stage_buttons.values())))
        layout.addWidget(self.overlay_log, 1)
        return page

    def login_chzzk(self) -> None:
        client_id, secret = self.chzzk_id.text().strip(), self.chzzk_secret.text().strip()
        self.chzzk_login_button.setEnabled(False)
        self.chzzk_state.setText("브라우저에서 치지직 로그인과 동의를 진행하십시오(제한 시간 5분).")

        def job() -> None:
            try:
                self.backend.chzzk_login(client_id or None, secret or None)
                self._emit(self.bridge.chzzk, "로그인됨")
            except Exception as error:
                self._emit(self.bridge.chzzk, f"로그인 실패: {error}")

        self._run(job)

    def _show_chzzk(self, message: str) -> None:
        self.chzzk_state.setText(message)
        self.chzzk_login_button.setEnabled(True)
        if message == "로그인됨":
            self.chzzk_api.setChecked(True)

    def check_youtube(self) -> None:
        video, key = self.youtube.text().strip(), self.youtube_key.text().strip() or None
        if not video:
            self._append_log("YouTube 방송 주소를 먼저 입력하십시오.")
            return
        self.youtube_check_button.setEnabled(False)
        self._append_log("YouTube 연결 확인 중")

        def job() -> None:
            try:
                message = self.backend.check_youtube(video, key)
            except Exception as error:
                message = f"YouTube 연결 확인 실패: {error}"
            self._emit(self.bridge.youtube, message)

        self._run(job)

    def _show_youtube(self, message: str) -> None:
        self._append_log(message)
        self.youtube_check_button.setEnabled(self.server is None)

    def overlay_sources(self) -> list[tuple[str, Callable[[], Any]]]:
        from ..overlay import events

        sources: list[tuple[str, Callable[[], Any]]] = []
        if self.chzzk_api.isChecked():
            sources.append(("CHZZK 공식 API", events.chzzk_api_source))
        for label, field_, make in (("CHZZK", self.chzzk, events.chzzk_source), ("SOOP", self.soop, events.soop_source), ("Twitch", self.twitch, events.twitch_source)):
            value = field_.text().strip()
            if value:
                sources.append((f"{label} {value}", lambda v=value, m=make: m(v)))
        video, key = self.youtube.text().strip(), self.youtube_key.text().strip() or None
        if video:
            from ..overlay.youtube import youtube_source

            sources.append((f"YouTube {video}", lambda: youtube_source(video, key)))
        if self.demo.isChecked() or not sources:
            sources.append(("데모", lambda: events.DemoChat()))
        return sources

    def toggle_overlay(self) -> None:
        if self.server is not None:
            self.server.stop()
            self.server = None
            self._overlay_state(False)
            self._append_log("오버레이 중지")
            return
        if self.chzzk_api.isChecked():  # 토큰 갱신에 필요. 이 프로그램이 실행되는 동안만 쓰고 저장하지 않는다
            chzzk.use_credentials(self.chzzk_id.text().strip(), self.chzzk_secret.text().strip())
        try:
            server = self.backend.make_overlay(self.overlay_sources(), self.port.value())
        except OSError as error:
            self._append_log(f"{self.port.value()}번 포트 열기 실패: {error}")
            return
        server.hub.taps.append(lambda event: event.kind == "system" and self._emit(self.bridge.log, event.text))
        server.hub.taps.append(logs.status)  # 상태 안내만 이 PC의 기록 파일에
        server.start()
        self.server = server
        server.obs_target = ("127.0.0.1", self.obs_port.value(), self.obs_password.text() or None)  # 휴대폰 화면에서 카메라 소스 만들기
        self._overlay_state(True)
        self._keep_settings = True
        self.remember()
        meter = self.backend.make_voice_meter(server, self.obs_port.value(), self.obs_password.text() or None, float(self.voice_threshold.value()),
                                              self._voice_input or None)
        if meter is not None:
            server.attach(meter)
            self._append_log(f"캐릭터 화면: {server.url}/character (OBS 마이크 음량으로 입 움직임). 얼굴 추적: {server.url}/tracker(일반 브라우저), "
                             f"휴대폰 얼굴 추적: {server.url}/phone")
        reactions = vts.parse_reactions(self.vts_reaction_rules())
        if reactions and self.backend.vts_token():
            server.attach(self.backend.make_vts_reactor(server, reactions))
            self._append_log(f"VTube Studio 후원 반응: {self.vts_min.value():,}원 이상 후원 시 {reactions[0].hotkey} 실행")
        elif reactions:
            self._append_log("VTube Studio 후원 반응: 연결 전(캐릭터 단계의 VTube Studio 연결 필요)")
        motion_rules = vts.parse_reactions(self.motion_reaction_rules())
        motion_state = getattr(server, "motion", None)
        if motion_rules and motion_state is not None:
            server.hub.taps.append(motion.MotionReactor(motion_rules, motion_state))
            self._append_log(f"동작 후원 반응: {self.motion_min.value():,}원 이상 후원 시 {self.motion_reaction.currentText()} 실행")
        self._append_log(f"오버레이 실행 중: {server.url}/chat (채팅창), {server.url}/alerts (알림)")
        if self.autoclip.isChecked():
            port, password = self.obs_port.value(), self.obs_password.text() or None

            def job() -> None:
                try:
                    extras = {name: True for name, box in (("gif", self.clip_gif), ("shorts", self.clip_shorts)) if box.isChecked()}
                    clipper, message = self.backend.make_autoclipper(server.hub, port, password, **extras)
                    server.attach(clipper.start())
                    self._emit(self.bridge.log, message)
                except Exception as error:
                    self._emit(self.bridge.log, f"자동 클립 시작 실패: {error}")

            self._run(job)

    def _overlay_state(self, running: bool) -> None:
        self.overlay_button.setText("오버레이 중지" if running else "오버레이 시작")
        self.open_button.setEnabled(running)
        self.draw_button.setEnabled(running)
        for button in self.stage_buttons.values():
            button.setEnabled(running)
        self.remote_button.setEnabled(running)
        self.broadcast_button.setEnabled(running)
        self.logo_button.setEnabled(running)
        for widget in (self.chzzk, self.soop, self.twitch, self.youtube, self.youtube_key, self.youtube_check_button, self.chzzk_api, self.chzzk_id, self.chzzk_secret, self.chzzk_login_button,
                       self.demo, self.autoclip, self.clip_gif, self.clip_shorts, self.voice_threshold, self.port):
            widget.setEnabled(not running)

    def _append_log(self, line: str) -> None:
        self.overlay_log.appendPlainText(line)

    # ------------------------------------------------------------------ 5. 마무리
    def _page_finish(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("마무리", "방송 전 준비 상태를 확인합니다.", mascot="debi"))
        # 설정 마법사 다음 차례: 오버레이의 시작하기 화면(방송 준비 목록과 방송 직전 점검)과 같은 이름으로 안내
        self.next_state = text("오버레이를 켠 뒤 시작하기 화면에서 차례로 합니다: OBS 연결 확인, 채팅창과 알림과 캐릭터를 OBS에 넣기, "
                               "시험 후원으로 확인, 방송 모양 고르기. 방송할 때마다 시작하기 화면의 방송 직전 점검(OBS, 방송 장면, 알림 소리, "
                               "채팅 연결, 마이크)을 봅니다.", muted=True)
        self.next_button = QPushButton("시작하기 화면 열기")
        self.next_button.setObjectName("Primary")
        self.next_button.clicked.connect(self.open_start_page)
        layout.addWidget(card(self.next_state, self.next_button, title="다음 할 일"))
        layout.addWidget(self._launch_card())
        self.summary = text("", links=True)
        layout.addWidget(card(self.summary, title="준비 상태"))
        folder = QPushButton("클립 폴더 열기")
        folder.clicked.connect(lambda: self.backend.open_folder(self.backend.clip_dir()))
        self.clip_folder = text(str(self.backend.clip_dir()), muted=True)
        layout.addWidget(card(self.clip_folder, folder, title="자동 클립 저장 위치"))
        self.update_button = QPushButton("새 버전 확인")
        self.update_button.clicked.connect(self.check_update)
        self.update_result = text(f"현재 버전 {__version__}. 확인 버튼을 누를 때만 GitHub에 연결합니다.", muted=True, links=True)
        layout.addWidget(card(self.update_result, self.update_button, title="버전"))
        self.forget_button = QPushButton("저장한 설정 삭제")
        self.forget_button.clicked.connect(self.forget_settings)
        self.settings_state = text(f"채널 주소와 선택 항목은 이 PC에 저장해 다음 실행 때 불러옵니다. API 키와 비밀번호는 저장하지 않습니다.\n{settings.settings_path()}",
                                   muted=True)
        layout.addWidget(card(self.settings_state, self.forget_button, title="저장한 설정"))
        self.copy_button = QPushButton("점검 결과 복사")
        self.copy_button.clicked.connect(self.copy_diagnostics)
        report = QPushButton("문제 제보, 확인 보고(GitHub)")
        report.clicked.connect(lambda: self.backend.open_url(ISSUE_URL))
        logs_button = QPushButton("기록 폴더 열기")
        logs_button.clicked.connect(lambda: self.backend.open_folder(self.backend.log_dir()))
        self.report_state = text("점검 결과를 복사해 제보 양식에 붙여 넣습니다. 자동으로 전송하지 않습니다. "
                                 "오류 기록은 이 PC의 기록 폴더에만 저장합니다.", muted=True)
        layout.addWidget(card(self.report_state, row(self.copy_button, report, logs_button), title="문제 제보"))
        layout.addWidget(text(f'소속 버튜버 프로그램(선택, 키트 사용과 무관): <a href="{JOIN_URL}" style="color:#A7B0B7">참여 안내</a>',
                              muted=True, links=True))
        layout.addStretch(1)
        return page

    def open_start_page(self) -> None:
        """오버레이가 켜져 있으면 시작하기 화면을 열고, 꺼져 있으면 켜는 곳을 알려 준다."""
        if self.server:
            self.backend.open_url(self.server.url)
            return
        self.next_state.setText("오버레이가 꺼져 있습니다. 4단계 채팅과 알림에서 오버레이 시작을 누른 뒤 다시 누릅니다.")

    # ------------------------------------------------------------------ 방송 시작 버튼(launcher.py)
    def _launch_card(self) -> QWidget:
        self.launch_profiles = QComboBox()
        self.launch_profiles.setMinimumWidth(160)
        self.launch_button = QPushButton("켜기")
        self.launch_button.setObjectName("Primary")
        self.launch_button.setToolTip("끌 것을 먼저 끄고 켤 것을 차례로 켭니다. 이미 켜진 프로그램은 건너뜁니다")
        self.launch_button.clicked.connect(self.run_launch)
        self.launch_end_button = QPushButton("방송 끝")
        self.launch_end_button.setToolTip("이번 방송에 꺼 둔 프로그램을 다시 켜고 감시를 멈춥니다")
        self.launch_end_button.clicked.connect(self.end_launch)
        edit = QPushButton("세팅 편집")
        edit.clicked.connect(self.edit_launch)
        self.launch_state = text("방송에 필요한 프로그램, 폴더, 사이트를 차례로 켜고 메신저, 게임 런처처럼 방해되는 프로그램은 끕니다. "
                                 "세팅 편집에서 목록에 끌어다 놓습니다.", muted=True)
        self._fill_launch_profiles()
        return card(row(self.launch_profiles, self.launch_button, self.launch_end_button, edit), self.launch_state, title="방송 시작 버튼")

    def _fill_launch_profiles(self) -> None:
        try:
            config = self.backend.load_launcher()
        except OSError:
            return
        self.launch_profiles.clear()
        self.launch_profiles.addItems([profile.name for profile in config.profiles])
        self.launch_profiles.setCurrentText(config.active)

    def edit_launch(self) -> None:
        if self.backend.edit_launcher(self):
            self._fill_launch_profiles()
            self.launch_state.setText("세팅을 저장했습니다.")

    def _launch_buttons(self, enabled: bool) -> None:
        for widget in (self.launch_button, self.launch_end_button, self.launch_profiles):
            widget.setEnabled(enabled)

    def run_launch(self) -> None:
        config = self.backend.load_launcher()
        name = self.launch_profiles.currentText() or config.active
        try:
            profile = config.profile(name)
        except launcher.LauncherError as error:
            self.launch_state.setText(str(error))
            return
        if config.active != name:
            config.active = name
            self.backend.save_launcher(config)
        if self.launch_watcher is not None:
            self.launch_watcher.stop()
            self.launch_watcher = None
        self._launch_lines = []
        self._launch_buttons(False)
        self.launch_state.setText(f"{name} 켜는 중")
        obs_port = self.obs_port.value()

        def job() -> None:
            steps = self.backend.make_launcher(config, report=lambda step: self._emit(self.bridge.launch, step.text())).run(name)
            if profile.obs_check:
                self._emit(self.bridge.launch, "OBS 연결 확인 중(최대 60초)")
                ok = self.backend.wait_for_obs(obs_port)
                self._emit(self.bridge.launch, "OBS 연결 가능" if ok else "OBS WebSocket 응답 없음: OBS 도구 메뉴의 WebSocket 서버 설정 확인")
            self._emit(self.bridge.launch_done, (profile, config, steps, True))

        self._run(job)

    def end_launch(self) -> None:
        if self.launch_watcher is not None:
            self.launch_watcher.stop()
            self.launch_watcher = None
        config = self.backend.load_launcher()
        name = self.launch_profiles.currentText() or config.active
        self._launch_lines = []
        self._launch_buttons(False)
        self.launch_state.setText("방송 끝 정리 중")

        def job() -> None:
            steps = self.backend.make_launcher(config, report=lambda step: self._emit(self.bridge.launch, step.text())).end(name)
            self._emit(self.bridge.launch_done, (config.profile(name), config, steps, False))

        self._run(job)

    def _launch_line(self, line: str) -> None:
        self._launch_lines = (self._launch_lines + [line])[-10:]
        self.launch_state.setText("\n".join(self._launch_lines))

    def _launch_done(self, payload: tuple[Any, Any, list[Any], bool]) -> None:
        profile, config, steps, started = payload
        self._launch_buttons(True)
        if not steps:
            self._launch_line("할 일이 없음: 세팅 편집에서 켤 것, 끌 것을 추가" if started else "다시 켤 프로그램 없음")
        if not started:
            return
        if profile.watch and profile.stop:
            notify = lambda message: self._emit(self.bridge.launch, f"{time.strftime('%H:%M')} {message}")  # noqa: E731
            self.launch_watcher = self.backend.make_watcher(profile, config, notify).start()
            self._launch_line("꺼 둔 프로그램이 다시 켜지는지 감시 중(방송 끝을 누르면 멈춤)")
        if profile.overlay and self.server is None:
            self._launch_line("오버레이 시작(채팅과 알림 단계 설정)")
            self.toggle_overlay()

    def copy_diagnostics(self) -> None:
        if not self.checked:
            self.report_state.setText("PC 점검을 먼저 실행하십시오(PC 점검 단계).")
            return
        self.backend.copy_text(diagnostics(self.checked))
        self.report_state.setText("점검 결과를 복사했습니다. 제보 양식의 PC 점검 결과 칸에 붙여 넣으십시오.")

    def check_update(self) -> None:
        self.update_button.setEnabled(False)
        self.update_result.setText("확인 중")
        self._run(lambda: self._emit(self.bridge.update, self.backend.check_update()))

    def _show_update(self, message: str) -> None:
        url = tools.RELEASES_PAGE
        self.update_result.setText(message.replace(url, f'<a href="{url}" style="{LINK}">릴리스 페이지</a>'))
        self.update_button.setEnabled(True)

    def _refresh_summary(self) -> None:
        lines = []
        need = [c.title for c in self.checked if c.status == FAIL]
        warn = sum(1 for c in self.checked if c.status == WARN)
        passed = "통과" + (f" (주의 {warn}건)" if warn else "")
        lines.append("PC 점검: " + ("필요 항목 " + ", ".join(need) if need else passed if self.checked else "점검 전"))
        lines.append("OBS 장면: " + (self.scenes_result.text().splitlines()[0] if self.scenes_result.text() else "생성 전"))
        lines.append("채팅과 알림: " + (f"실행 중({self.server.url})" if self.server else "중지"))
        self.summary.setText("<br>".join(lines))

    # ------------------------------------------------------------------ 설정 저장
    def collect_settings(self) -> dict[str, Any]:
        """저장할 입력값(API 키, 비밀번호, Client Secret 제외)."""
        values: dict[str, Any] = {name: [field_.text().strip()] for name, field_ in
                                  (("chzzk", self.chzzk), ("soop", self.soop), ("twitch", self.twitch), ("youtube", self.youtube))}
        values.update(chzzk_api=self.chzzk_api.isChecked(), chzzk_client_id=self.chzzk_id.text().strip(), demo=self.demo.isChecked(),
                      clip=self.autoclip.isChecked(), clip_gif=self.clip_gif.isChecked(), clip_shorts=self.clip_shorts.isChecked(), chat_commands=self.chat_commands.isChecked(), overlay_port=self.port.value(), obs_port=self.obs_port.value(),
                      avatar_app=str(self.avatar_app.currentData()), replay_buffer=60 if self.replay.isChecked() else 0,
                      avatar_path=self.avatar_path.text().strip(), agency=self.avatar_agency.isChecked(),
                      voice_threshold=float(self.voice_threshold.value()), voice_input=self._voice_input, vts_reactions=self.vts_reaction_rules(),
                      motion_reactions=self.motion_reaction_rules())
        return settings.clean(values)

    def apply_settings(self, values: dict[str, Any]) -> None:
        for name, field_ in (("chzzk", self.chzzk), ("soop", self.soop), ("twitch", self.twitch), ("youtube", self.youtube)):
            if values.get(name):
                field_.setText(values[name][0])
        if values.get("chzzk_client_id") and not self.chzzk_id.text():  # 환경 변수가 우선
            self.chzzk_id.setText(values["chzzk_client_id"])
        for name, box in (("chzzk_api", self.chzzk_api), ("demo", self.demo), ("clip", self.autoclip), ("clip_gif", self.clip_gif),
                          ("clip_shorts", self.clip_shorts), ("agency", self.avatar_agency),
                          ("chat_commands", self.chat_commands)):
            if name in values:
                box.setChecked(values[name])
        if "replay_buffer" in values:
            self.replay.setChecked(values["replay_buffer"] > 0)
        for name, spin in (("overlay_port", self.port), ("obs_port", self.obs_port)):
            if name in values and spin.minimum() <= values[name] <= spin.maximum():
                spin.setValue(values[name])
        if values.get("avatar_app") and self.avatar_app.findData(values["avatar_app"]) >= 0:
            self.avatar_app.setCurrentIndex(self.avatar_app.findData(values["avatar_app"]))
        if values.get("avatar_path"):
            self.avatar_path.setText(values["avatar_path"])
        if "voice_threshold" in values and -70 <= values["voice_threshold"] <= -10:
            self.voice_threshold.setValue(round(values["voice_threshold"]))
        self._voice_input = values.get("voice_input", "")  # 명령줄에서 지정한 OBS 소스 이름 유지
        rules = vts.parse_reactions(values.get("vts_reactions"))
        if rules:  # 설정 마법사는 규칙 하나를 보여 준다(명령줄은 여러 개 가능)
            self.vts_hotkey.setEditText(rules[-1].hotkey)
            self.vts_min.setValue(rules[-1].min_won)
        motion_rules = vts.parse_reactions(values.get("motion_reactions"))
        if motion_rules:
            self._pending_reaction = motion_rules[-1].hotkey  # 동작을 다시 등록하면 선택되도록 기억
            self.motion_reaction.setCurrentIndex(max(0, self.motion_reaction.findData(motion_rules[-1].hotkey)))
            self.motion_min.setValue(motion_rules[-1].min_won)

    #: 입력란이 없어 collect_settings가 모르는 저장값. 저장할 때 기존 값을 유지한다(캐릭터 단계의 사용 버튼이 따로 저장)
    #: 설정 마법사가 입력 칸으로 다루는 항목. 그 밖의 저장 설정(추첨, 참여 추첨, 휴대폰, 캐릭터, 명령줄 --save 등)은 저장할 때 그대로 둔다
    MANAGED_SETTINGS = ("chzzk", "soop", "twitch", "youtube", "chzzk_api", "chzzk_client_id", "demo", "clip", "clip_gif", "clip_shorts",
                        "chat_commands", "overlay_port", "obs_port", "avatar_app", "replay_buffer", "avatar_path", "agency", "voice_threshold",
                        "voice_input", "vts_reactions", "motion_reactions")

    def remember(self) -> None:
        try:
            values = self.collect_settings()
            saved = self.backend.load_settings()
            values.update({key: value for key, value in saved.items() if key not in self.MANAGED_SETTINGS})
            self.backend.save_settings(values)
        except OSError as error:
            self._append_log(f"설정 저장 실패: {error}")

    def forget_settings(self) -> None:
        removed = self.backend.clear_settings()
        self._keep_settings = False  # 창을 닫을 때 다시 저장하지 않음
        self.settings_state.setText("저장한 설정을 삭제했습니다. 오버레이나 장면 생성을 다시 실행하면 그때의 입력값을 저장합니다."
                                    if removed else "저장한 설정이 없습니다.")

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        if self._keep_settings:
            self.remember()
        self._closed = True
        if self.launch_watcher is not None:
            self.launch_watcher.stop()
            self.launch_watcher = None
        if self.server is not None:
            self.server.stop()
            self.server = None
        for thread in self._threads:  # 점검, OBS 연결이 끝나길 잠깐 기다린다 (끝나지 않으면 데몬 스레드로 버림)
            thread.join(timeout=1.0)
        super().closeEvent(event)


def release(window: Wizard, app: QApplication | None, *, wait: float = 5.0) -> None:
    """종료 순서 고정: 작업 스레드 대기, 창 삭제, Qt 앱 종료.

    파이썬 종료 단계에서 창과 Qt 앱이 임의 순서로 지워지면 macOS에서 간헐적으로 비정상 종료(신호 10, 11, 6)했다.
    ``app`` 은 이 함수가 만든 Qt 앱일 때만 넘긴다(이미 있던 앱은 그대로 둔다).
    """
    for thread in window._threads:
        thread.join(timeout=wait)
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    if app is not None:
        app.shutdown()


def main(argv: list[str] | None = None) -> int:
    record = logs.setup("gui")
    existing = QApplication.instance()
    app = existing or QApplication(sys.argv if argv is None else argv)
    QGuiApplication.setApplicationDisplayName("debutkit")
    QGuiApplication.setWindowIcon(QIcon(str(ICON)))
    app.setStyleSheet(style_sheet())
    window = Wizard()
    window.show()
    if os.environ.get("DEBUTKIT_SMOKE"):  # 빌드 확인용: 열었다가 곧 닫는다
        QTimer.singleShot(1500, window.close)
        QTimer.singleShot(1600, app.quit)
    code = int(app.exec())
    window.close()
    release(window, None if existing else app)
    logs.close(record)
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
