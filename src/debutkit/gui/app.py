"""설정 마법사: 명령줄 없이 PC 점검, 아바타, OBS 장면, 채팅과 알림, 마무리 순서로 안내한다.

창은 입력을 모으고 결과를 보여 주기만 하고, 실제 일은 doctor, scenes, overlay, clip, tools,
chzzk 모듈이 한다. 느린 일(점검, OBS 연결, 내려받기, 로그인)은 작업 스레드에서 돌리고 결과는
Qt 시그널로 창에 돌려준다. 스타일 시트는 채팅 연결 모듈에 있는 것을 쓰고, 없으면 기본 색만 쓴다.
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
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

from .. import __version__, chzzk, clip, doctor, scenes, tools
from ..doctor import FAIL, INFO, JOIN_URL, LABELS, OK, OVERLAY_PORT, SOFTWARE_URL, WARN

STEPS = ["1  PC 점검", "2  아바타", "3  OBS 장면", "4  채팅과 알림", "5  마무리"]
AVATARS = [("VTube Studio (Live2D)", "vts"), ("VSeeFace (VRM)", "vseeface"), ("Warudo", "warudo"), ("VMagicMirror", "vmagicmirror"), ("아바타 없이", "none")]
STATE_STYLE = {OK: "StateOk", FAIL: "StateMissing", WARN: "StateWarn", INFO: "StateOther"}
#: 기본 스타일 시트에 없는 것만 더한다
EXTRA_STYLE = """
QLabel#StateWarn { background: #3A3218; color: #FFD84D; border-radius: 6px; padding: 2px 8px; font-weight: 700; }
QListWidget#Steps { background: #1D1A29; border: none; padding: 16px 8px; font-size: 14px; outline: 0; }
QListWidget#Steps::item { padding: 10px 12px; border-radius: 8px; border: none; }
QListWidget#Steps::item:selected { background: #FF4F8B; color: #15131F; font-weight: 800; border: none; }
"""
LINK = "color:#FF7AA8"
ICON = Path(__file__).with_name("icon.png")  # packaging/build_brand.py 로 생성


def style_sheet() -> str:
    try:
        from stream2clip.gui.theme import STYLE_SHEET

        return STYLE_SHEET
    except Exception:  # 채팅 연결 모듈 없이도 동작
        return "QMainWindow, QWidget#Root { background: #15131F; } * { color: #F7F4FA; }"


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
    return clip.AutoClipper(hub, clipper), f"자동 클립 켬 (OBS {version}). 저장 위치: {out}"


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
    open_url: Callable[[str], Any] = field(default=lambda url: QDesktopServices.openUrl(QUrl(url)))
    open_folder: Callable[[Path], Any] = _open_folder


class Bridge(QObject):
    """작업 스레드에서 창으로. 시그널은 창의 스레드에서 처리된다."""

    checks = Signal(object)
    avatar = Signal(object)
    scenes = Signal(str)
    log = Signal(str)
    ffmpeg = Signal(str, bool)  # 안내 문장, 끝났는지
    chzzk = Signal(str)
    update = Signal(str)


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
        self.server: Any = None
        self.checked: list[doctor.Check] = []
        self._threads: list[threading.Thread] = []
        self._closed = False
        self.setWindowTitle(f"debutkit {__version__} - 첫 방송 준비")
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
        self.nav.setCurrentRow(0)
        self._on_page(0)

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
        layout.addWidget(self._title("PC 점검", "방송에 필요한 사양과 프로그램 확인. 설치나 설정 변경 없음"))
        self.check_rows = QGridLayout()
        self.check_rows.setHorizontalSpacing(12)
        self.check_rows.setVerticalSpacing(8)
        rows = QWidget()
        rows.setLayout(self.check_rows)
        self.check_summary = QLabel("")
        self.check_summary.setObjectName("Status")
        self.check_button = QPushButton("다시 점검")
        self.check_button.clicked.connect(self.run_checks)
        self.ffmpeg_button = QPushButton("ffmpeg 내려받기")
        self.ffmpeg_button.clicked.connect(self.download_ffmpeg)
        self.ffmpeg_button.setVisible(False)
        self.ffmpeg_status = text("", muted=True)
        self.ffmpeg_status.setVisible(False)
        layout.addWidget(card(rows, self.check_summary))
        layout.addWidget(row(self.check_button, self.ffmpeg_button))
        layout.addWidget(self.ffmpeg_status)
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
            detail = text(check.detail + (f"\n해결: {check.hint}" if check.hint and check.status != OK else ""), muted=check.status == OK)
            detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.check_rows.addWidget(detail, index, 2)
        self.check_rows.setColumnStretch(2, 1)
        self.check_summary.setText(doctor.summary(checks))
        self.check_button.setEnabled(True)
        missing = any(c.key == "ffmpeg" and c.status != OK for c in checks)
        self.ffmpeg_button.setVisible(missing and self.backend.can_download_ffmpeg())

    def download_ffmpeg(self) -> None:
        self.ffmpeg_button.setEnabled(False)
        self.ffmpeg_status.setVisible(True)
        self.ffmpeg_status.setText("ffmpeg 내려받는 중")
        megabytes = tools.ffmpeg_megabytes()

        def progress(done: int, total: int) -> None:
            percent = int(done * 100 / total) if total else 0
            self._emit(self.bridge.ffmpeg, f"ffmpeg 내려받는 중 {percent}% ({done / 1e6:.0f} / {megabytes} MB)", False)

        def job() -> None:
            try:
                written = self.backend.download_ffmpeg(on_progress=progress, cancelled=lambda: self._closed)
                folder = Path(written[0]).parent if written else ""
                self._emit(self.bridge.ffmpeg, f"ffmpeg 준비 완료: {folder}", True)
            except Exception as error:
                self._emit(self.bridge.ffmpeg, f"ffmpeg 내려받기 실패: {error}", True)

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
        layout.addWidget(self._title("아바타", "모델 종류에 맞는 트래킹 프로그램 선택, 모델 사용 조건 확인"))
        guide = text(
            "<b>Live2D 모델</b>: VTube Studio (수익 방송은 유료 버전 필요)<br>"
            "<b>3D(VRM) 모델</b>: VSeeFace (상업적 이용 허용, 무료) 또는 Warudo<br>"
            "<b>모델 없음</b>: VRoid Studio(무료)로 3D 모델 제작 또는 PNG 2장으로 시작<br>"
            f'<a href="{SOFTWARE_URL}" style="{LINK}">프로그램 목록과 라이선스</a>', links=True)
        self.avatar_path = QLineEdit()
        self.avatar_path.setPlaceholderText("모델 파일 (.vrm 등)")
        pick = QPushButton("파일 고르기")
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
            self.avatar_result.setText("모델 파일 먼저 선택")
            return
        agency = self.avatar_agency.isChecked()
        self._run(lambda: self._emit(self.bridge.avatar, self.backend.check_avatar(path, agency=agency)))

    def _show_avatar(self, checks: list[doctor.Check]) -> None:
        self.avatar_result.setText("\n".join(f"[{LABELS.get(c.status, c.status)}] {c.detail}" + (f"\n해결: {c.hint}" if c.hint else "") for c in checks))

    # ------------------------------------------------------------------ 3. OBS 장면
    def _page_scenes(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("OBS 장면", "대기 화면, 본방송, 토크, 자리 비움, 엔딩 장면 생성. 기존 장면은 그대로 유지"))
        layout.addWidget(card(text("OBS 실행 후 <b>도구 메뉴의 WebSocket 서버 설정</b>에서 <b>WebSocket 서버 사용</b> 체크<br>"
                                   "비밀번호 사용 시 아래 칸에 입력<br>"
                                   "처음 구성하는 경우 OBS 장면 모음 메뉴에서 새 장면 모음 생성 후 진행 권장", links=True)))
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
        self.replay = QCheckBox("자동 클립용 리플레이 버퍼 켜기 (60초)")
        self.replay.setChecked(True)
        form.addRow("WebSocket 포트", self.obs_port)
        form.addRow("비밀번호", self.obs_password)
        form.addRow("아바타 프로그램", self.avatar_app)
        form.addRow("", self.replay)
        fields = QWidget()
        fields.setLayout(form)
        self.scenes_button = QPushButton("장면 만들기")
        self.scenes_button.setObjectName("Primary")
        self.scenes_button.clicked.connect(self.make_scenes)
        self.scenes_result = text("", muted=True)
        layout.addWidget(card(fields, self.scenes_button, self.scenes_result))
        layout.addStretch(1)
        return page

    def make_scenes(self) -> None:
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
                self._emit(self.bridge.scenes, f"생성 실패: {error}\n확인: OBS 실행, WebSocket 서버 사용")

        self._run(job)

    def _show_scenes(self, message: str) -> None:
        self.scenes_result.setText(message)
        self.scenes_button.setEnabled(True)

    # ------------------------------------------------------------------ 4. 채팅과 알림
    def _page_overlay(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("채팅과 알림", "채널 입력 후 시작하면 OBS 채팅창과 후원 알림 표시. 채팅 저장 없음"))
        form = QFormLayout()
        self.chzzk = QLineEdit()
        self.chzzk.setPlaceholderText("https://chzzk.naver.com/live/채널ID")
        self.soop = QLineEdit()
        self.soop.setPlaceholderText("https://play.sooplive.co.kr/아이디")
        self.twitch = QLineEdit()
        self.twitch.setPlaceholderText("채널 이름")
        self.chzzk_api = QCheckBox("내 치지직 채널을 공식 API로 읽기 (로그인 필요, 권장)")
        signed_in = self.backend.chzzk_signed_in()
        self.chzzk_api.setChecked(signed_in)
        self.chzzk_id = QLineEdit()
        self.chzzk_id.setPlaceholderText("Client ID (치지직 개발자 센터)")
        self.chzzk_id.setText(os.environ.get("CHZZK_CLIENT_ID", ""))
        self.chzzk_secret = QLineEdit()
        self.chzzk_secret.setPlaceholderText("Client Secret")
        self.chzzk_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.chzzk_secret.setText(os.environ.get("CHZZK_CLIENT_SECRET", ""))
        self.chzzk_login_button = QPushButton("치지직 로그인")
        self.chzzk_login_button.clicked.connect(self.login_chzzk)
        self.chzzk_state = text("로그인됨" if signed_in else "로그인 안 됨", muted=True)
        self.demo = QCheckBox("데모 채팅 함께 표시 (모양 맞추기)")
        self.autoclip = QCheckBox("채팅 급증 또는 !clip 시 자동 클립 (OBS 리플레이 버퍼, ffmpeg 필요)")
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(OVERLAY_PORT)
        form.addRow("치지직", self.chzzk)
        form.addRow("SOOP", self.soop)
        form.addRow("Twitch", self.twitch)
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
        self.open_button = QPushButton("설정 화면 열기 (주소 복사, 테스트)")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(lambda: self.server and self.backend.open_url(self.server.url))
        self.overlay_log = QPlainTextEdit()
        self.overlay_log.setReadOnly(True)
        self.overlay_log.setMaximumBlockCount(200)
        self.overlay_log.setPlaceholderText("연결 상태와 저장한 클립 표시")
        layout.addWidget(card(fields, row(self.overlay_button, self.open_button)))
        layout.addWidget(self.overlay_log, 1)
        return page

    def login_chzzk(self) -> None:
        client_id, secret = self.chzzk_id.text().strip(), self.chzzk_secret.text().strip()
        self.chzzk_login_button.setEnabled(False)
        self.chzzk_state.setText("브라우저에서 치지직 로그인, 동의 진행 (5분 안에)")

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

    def overlay_sources(self) -> list[tuple[str, Callable[[], Any]]]:
        from ..overlay import events

        sources: list[tuple[str, Callable[[], Any]]] = []
        if self.chzzk_api.isChecked():
            sources.append(("CHZZK 공식 API", events.chzzk_api_source))
        for label, field_, make in (("CHZZK", self.chzzk, events.chzzk_source), ("SOOP", self.soop, events.soop_source), ("Twitch", self.twitch, events.twitch_source)):
            value = field_.text().strip()
            if value:
                sources.append((f"{label} {value}", lambda v=value, m=make: m(v)))
        if self.demo.isChecked() or not sources:
            sources.append(("데모", lambda: events.DemoChat()))
        return sources

    def toggle_overlay(self) -> None:
        if self.server is not None:
            self.server.stop()
            self.server = None
            self._overlay_state(False)
            self._append_log("오버레이 멈춤")
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
        self._append_log(f"오버레이 실행 중: {server.url}/chat (채팅창), {server.url}/alerts (알림)")
        if self.autoclip.isChecked():
            port, password = self.obs_port.value(), self.obs_password.text() or None

            def job() -> None:
                try:
                    clipper, message = self.backend.make_autoclipper(server.hub, port, password)
                    server.attach(clipper.start())
                    self._emit(self.bridge.log, message)
                except Exception as error:
                    self._emit(self.bridge.log, f"자동 클립 켜기 실패: {error}")

            self._run(job)

    def _overlay_state(self, running: bool) -> None:
        self.overlay_button.setText("오버레이 멈추기" if running else "오버레이 시작")
        self.open_button.setEnabled(running)
        for widget in (self.chzzk, self.soop, self.twitch, self.chzzk_api, self.chzzk_id, self.chzzk_secret, self.chzzk_login_button,
                       self.demo, self.autoclip, self.port):
            widget.setEnabled(not running)

    def _append_log(self, line: str) -> None:
        self.overlay_log.appendPlainText(line)

    # ------------------------------------------------------------------ 5. 마무리
    def _page_finish(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("마무리", "방송 시작 전 최종 확인"))
        self.summary = text("", links=True)
        layout.addWidget(card(self.summary, title="준비 상태"))
        folder = QPushButton("클립 폴더 열기")
        folder.clicked.connect(lambda: self.backend.open_folder(self.backend.clip_dir()))
        self.clip_folder = text(str(self.backend.clip_dir()), muted=True)
        layout.addWidget(card(self.clip_folder, folder, title="자동 클립 저장 위치"))
        self.update_button = QPushButton("새 버전 확인")
        self.update_button.clicked.connect(self.check_update)
        self.update_result = text(f"현재 버전 {__version__}. 확인할 때만 GitHub에 연결", muted=True, links=True)
        layout.addWidget(card(self.update_result, self.update_button, title="버전"))
        layout.addWidget(text(f'소속 버튜버 프로그램(선택, 키트 사용과 무관): <a href="{JOIN_URL}" style="color:#A39DB3">참여 안내</a>',
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
        lines.append("PC 점검: " + ("필요 항목 " + ", ".join(need) if need else passed if self.checked else "미실행"))
        lines.append("OBS 장면: " + (self.scenes_result.text().splitlines()[0] if self.scenes_result.text() else "미생성"))
        lines.append("채팅과 알림: " + (f"실행 중 ({self.server.url})" if self.server else "꺼짐"))
        self.summary.setText("<br>".join(lines))

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        self._closed = True
        if self.server is not None:
            self.server.stop()
            self.server = None
        for thread in self._threads:  # 점검, OBS 연결이 끝나길 잠깐 기다린다 (끝나지 않으면 데몬 스레드로 버림)
            thread.join(timeout=1.0)
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
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
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
