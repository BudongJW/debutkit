"""설정 마법사: 명령줄 없이 PC 점검, 아바타, OBS 장면, 채팅과 알림, 마무리 순서로 안내한다.

창은 입력을 모으고 결과를 보여 주기만 하고, 실제 일은 doctor, scenes, overlay, clip, tools,
chzzk 모듈이 한다. 느린 일(점검, OBS 연결, 다운로드, 로그인)은 작업 스레드에서 돌리고 결과는
Qt 시그널로 창에 돌려준다. 스타일 시트는 채팅 연결 모듈에 있는 것을 쓰고, 없으면 기본 색만 쓴다.
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, chzzk, clip, doctor, scenes, settings, speed, tools
from ..doctor import FAIL, INFO, JOIN_URL, LABELS, OK, OVERLAY_PORT, SOFTWARE_URL, WARN

STEPS = ["1  PC 점검", "2  아바타", "3  OBS 장면", "4  채팅과 알림", "5  마무리"]
AVATARS = [("VTube Studio (Live2D)", "vts"), ("VSeeFace (VRM)", "vseeface"), ("Warudo", "warudo"), ("VMagicMirror", "vmagicmirror"), ("아바타 사용 안 함", "none")]
STATE_STYLE = {OK: "StateOk", FAIL: "StateMissing", WARN: "StateWarn", INFO: "StateOther"}
#: 브랜드 컬러(assets/brand): Slate 배경, Cream 글자, Pink는 현재 단계와 선택 표시에만 사용
COLORS = {"ink": "#1E2327", "surface": "#262C31", "field": "#2E353B", "border": "#3A4249", "text": "#FAF7F5", "muted": "#A7B0B7",
          "pink": "#FF4F8B", "nav": "#191D20"}
STYLE_SHEET = """
QMainWindow, QDialog, QWidget#Root {{ background: {ink}; }}
* {{ color: {text}; font-size: 14px; }}
QWidget#Card {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; }}
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
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{ background: {field}; border: 1px solid {border}; border-radius: 4px; padding: 4px 8px; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {pink}; }}
QComboBox QAbstractItemView {{ background: {field}; selection-background-color: {border}; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 3px; border: 1px solid {border}; background: {field}; }}
QCheckBox::indicator:checked {{ background: {pink}; border-color: {pink}; }}
QCheckBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: #6F7880; }}
QListWidget#Steps {{ background: {nav}; border: none; border-right: 1px solid {border}; padding: 14px 0; outline: 0; }}
QListWidget#Steps::item {{ padding: 10px 18px; border: none; border-left: 3px solid transparent; color: {muted}; }}
QListWidget#Steps::item:selected {{ background: {surface}; color: {text}; font-weight: 700; border-left: 3px solid {pink}; }}
QToolTip {{ background: {field}; color: {text}; border: 1px solid {border}; }}
""".format(**COLORS)
EXTRA_STYLE = ""
LINK = "color:#FF8FB1"
ICON = Path(__file__).with_name("icon.png")  # packaging/build_brand.py 로 생성


def style_sheet() -> str:
    return STYLE_SHEET


def _make_overlay(sources: list[tuple[str, Callable[[], Any]]], port: int) -> Any:
    from ..overlay.server import OverlayServer

    return OverlayServer(sources, port=port)


def _make_autoclipper(hub: Any, port: int, password: str | None) -> tuple[Any, str]:
    problem = clip.preflight()
    if problem:
        raise RuntimeError(problem)
    out = clip.default_clip_dir()
    clipper = clip.replay_clipper(out, "127.0.0.1", port, password)
    version = clipper.check(start_buffer=True)
    return clip.AutoClipper(hub, clipper), f"자동 클립 시작(OBS {version}). 저장 위치: {out}"


def _check_youtube(address: str, api_key: str | None) -> str:
    from ..overlay.youtube_check import check, format_steps

    return "YouTube 연결 확인(할당량 약 11 단위 사용)\n" + format_steps(check(address, api_key))


def _open_folder(path: Path) -> Any:
    path.mkdir(parents=True, exist_ok=True)
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


@dataclass
class Backend:
    """창이 부르는 실제 동작. 테스트에서 바꿔 끼운다."""

    run_checks: Callable[..., list[doctor.Check]] = doctor.run_checks
    check_avatar: Callable[..., list[doctor.Check]] = doctor.check_avatar
    apply_scenes: Callable[..., Any] = scenes.connect_and_apply
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


class Bridge(QObject):
    """작업 스레드에서 창으로. 시그널은 창의 스레드에서 처리된다."""

    checks = Signal(object)
    avatar = Signal(object)
    scenes = Signal(str)
    log = Signal(str)
    ffmpeg = Signal(str, bool)  # 안내 문장, 끝났는지
    chzzk = Signal(str)
    update = Signal(str)
    speed = Signal(object)  # doctor.Check
    youtube = Signal(str)


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
        self.bridge.log.connect(self._append_log)
        self.bridge.ffmpeg.connect(self._show_ffmpeg)
        self.bridge.chzzk.connect(self._show_chzzk)
        self.bridge.update.connect(self._show_update)
        self.bridge.speed.connect(self._show_speed)
        self.bridge.youtube.connect(self._show_youtube)
        self.server: Any = None
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
    def _title(content: str, lead: str) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 8)
        title = QLabel(content)
        title.setObjectName("Title")
        layout.addWidget(title)
        layout.addWidget(text(lead, muted=True))
        return box

    # ------------------------------------------------------------------ 1. 점검
    def _page_checks(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("PC 점검", "방송에 필요한 사양과 프로그램을 점검합니다. 프로그램 설치나 설정 변경은 하지 않습니다."))
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

    # ------------------------------------------------------------------ 2. 아바타
    def _page_avatar(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("아바타", "모델 종류에 맞는 트래킹 프로그램을 안내하고 모델 파일의 사용 조건을 확인합니다."))
        guide = text(
            "<b>Live2D 모델</b>: VTube Studio(수익 방송 시 유료 버전 필요)<br>"
            "<b>3D(VRM) 모델</b>: VSeeFace(무료, 상업적 이용 허용) 또는 Warudo<br>"
            "<b>모델이 없는 경우</b>: VRoid Studio(무료)로 3D 모델 제작 또는 PNG 이미지 2장으로 시작<br>"
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
        layout.addWidget(card(guide, title="트래킹 프로그램"))
        layout.addWidget(card(row(self.avatar_path, pick, stretch=0), self.avatar_agency, check, self.avatar_result, title="모델 사용 조건"))
        layout.addStretch(1)
        return page

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
        form.addRow("WebSocket 포트", self.obs_port)
        form.addRow("비밀번호", self.obs_password)
        form.addRow("아바타 프로그램", self.avatar_app)
        form.addRow("", self.replay)
        fields = QWidget()
        fields.setLayout(form)
        self.scenes_button = QPushButton("장면 생성")
        self.scenes_button.setObjectName("Primary")
        self.scenes_button.clicked.connect(self.make_scenes)
        self.scenes_result = text("", muted=True)
        layout.addWidget(card(fields, self.scenes_button, self.scenes_result))
        layout.addStretch(1)
        return page

    def make_scenes(self) -> None:
        self._keep_settings = True
        self.remember()
        self.scenes_button.setEnabled(False)
        self.scenes_result.setText("OBS 연결 중")
        base = f"http://127.0.0.1:{self.port.value()}"
        options = scenes.SceneOptions(overlay_url=f"{base}/chat", alerts_url=f"{base}/alerts", avatar=str(self.avatar_app.currentData()))
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
        form.addRow("포트", self.port)
        fields = QWidget()
        fields.setLayout(form)
        self.overlay_button = QPushButton("오버레이 시작")
        self.overlay_button.setObjectName("Primary")
        self.overlay_button.clicked.connect(self.toggle_overlay)
        self.open_button = QPushButton("설정 화면 열기(주소 복사, 테스트 메시지)")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(lambda: self.server and self.backend.open_url(self.server.url))
        self.overlay_log = QPlainTextEdit()
        self.overlay_log.setReadOnly(True)
        self.overlay_log.setMaximumBlockCount(200)
        self.overlay_log.setPlaceholderText("연결 상태와 저장한 클립이 이곳에 표시됩니다.")
        layout.addWidget(card(fields, row(self.overlay_button, self.open_button)))
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
        server.start()
        self.server = server
        self._overlay_state(True)
        self._keep_settings = True
        self.remember()
        self._append_log(f"오버레이 실행 중: {server.url}/chat (채팅창), {server.url}/alerts (알림)")
        if self.autoclip.isChecked():
            port, password = self.obs_port.value(), self.obs_password.text() or None

            def job() -> None:
                try:
                    clipper, message = self.backend.make_autoclipper(server.hub, port, password)
                    server.attach(clipper.start())
                    self._emit(self.bridge.log, message)
                except Exception as error:
                    self._emit(self.bridge.log, f"자동 클립 시작 실패: {error}")

            self._run(job)

    def _overlay_state(self, running: bool) -> None:
        self.overlay_button.setText("오버레이 중지" if running else "오버레이 시작")
        self.open_button.setEnabled(running)
        for widget in (self.chzzk, self.soop, self.twitch, self.youtube, self.youtube_key, self.youtube_check_button, self.chzzk_api, self.chzzk_id, self.chzzk_secret, self.chzzk_login_button,
                       self.demo, self.autoclip, self.port):
            widget.setEnabled(not running)

    def _append_log(self, line: str) -> None:
        self.overlay_log.appendPlainText(line)

    # ------------------------------------------------------------------ 5. 마무리
    def _page_finish(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("마무리", "방송 전 준비 상태를 확인합니다."))
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
        layout.addWidget(text(f'소속 버튜버 프로그램(선택, 키트 사용과 무관): <a href="{JOIN_URL}" style="color:#A7B0B7">참여 안내</a>',
                              muted=True, links=True))
        layout.addStretch(1)
        return page

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
                      clip=self.autoclip.isChecked(), overlay_port=self.port.value(), obs_port=self.obs_port.value(),
                      avatar_app=str(self.avatar_app.currentData()), replay_buffer=60 if self.replay.isChecked() else 0,
                      avatar_path=self.avatar_path.text().strip(), agency=self.avatar_agency.isChecked())
        return settings.clean(values)

    def apply_settings(self, values: dict[str, Any]) -> None:
        for name, field_ in (("chzzk", self.chzzk), ("soop", self.soop), ("twitch", self.twitch), ("youtube", self.youtube)):
            if values.get(name):
                field_.setText(values[name][0])
        if values.get("chzzk_client_id") and not self.chzzk_id.text():  # 환경 변수가 우선
            self.chzzk_id.setText(values["chzzk_client_id"])
        for name, box in (("chzzk_api", self.chzzk_api), ("demo", self.demo), ("clip", self.autoclip), ("agency", self.avatar_agency)):
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

    def remember(self) -> None:
        try:
            self.backend.save_settings(self.collect_settings())
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
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
