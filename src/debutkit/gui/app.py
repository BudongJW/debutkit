"""설정 마법사: 명령줄 없이 PC 점검 → 아바타 → OBS 장면 → 채팅·알림 → 마무리 순서로 안내한다.

창은 입력을 모으고 결과를 보여 주기만 하고, 실제 일은 doctor / scenes / overlay / clip 모듈이 한다.
느린 일(점검, OBS 연결)은 작업 스레드에서 돌리고 결과는 Qt 시그널로 창에 돌려준다.
모양은 stream2clip 앱의 스타일 시트를 그대로 써서 두 프로그램이 한 가족처럼 보이게 한다.
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
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

from .. import __version__, doctor, scenes
from ..doctor import FAIL, INFO, LABELS, OK, OVERLAY_PORT, WARN

STEPS = ["1  PC 점검", "2  아바타", "3  OBS 장면", "4  채팅·알림", "5  마무리"]
AVATARS = [("VTube Studio (Live2D)", "vts"), ("VSeeFace (VRM)", "vseeface"), ("Warudo", "warudo"), ("VMagicMirror", "vmagicmirror"), ("아바타 없이", "none")]
STATE_STYLE = {OK: "StateOk", FAIL: "StateMissing", WARN: "StateWarn", INFO: "StateOther"}
#: stream2clip 스타일 시트에 없는 것만 더한다
EXTRA_STYLE = """
QLabel#StateWarn { background: #3A3218; color: #FFD84D; border-radius: 6px; padding: 2px 8px; font-weight: 700; }
QListWidget#Steps { background: #1D1A29; border: none; padding: 16px 8px; font-size: 14px; outline: 0; }
QListWidget#Steps::item { padding: 10px 12px; border-radius: 8px; border: none; }
QListWidget#Steps::item:selected { background: #FF4F8B; color: #15131F; font-weight: 800; border: none; }
"""
MEMBERSHIP_URL = "https://budongjw.github.io/join/"
STREAM2CLIP_URL = "https://budongjw.github.io/stream2clip/"
SOFTWARE_URL = "https://budongjw.github.io/software/"


def style_sheet() -> str:
    try:
        from stream2clip.gui.theme import STYLE_SHEET

        return STYLE_SHEET
    except Exception:  # stream2clip 없이도 동작
        return "QMainWindow, QWidget#Root { background: #15131F; } * { color: #F7F4FA; }"


def _make_overlay(sources: list[tuple[str, Callable[[], Any]]], port: int) -> Any:
    from ..overlay.server import OverlayServer

    return OverlayServer(sources, port=port)


def _make_autoclipper(hub: Any, port: int, password: str | None) -> tuple[Any, str]:
    from ..clip import AutoClipper, default_clip_dir, replay_clipper

    out = default_clip_dir()
    clipper = replay_clipper(out, "127.0.0.1", port, password)
    version = clipper.check(start_buffer=True)
    return AutoClipper(hub, clipper), f"자동 클립 켬 (OBS {version}). 저장 위치: {out}"


@dataclass
class Backend:
    """창이 부르는 실제 동작. 테스트에서 바꿔 끼운다."""

    run_checks: Callable[..., list[doctor.Check]] = doctor.run_checks
    check_avatar: Callable[..., list[doctor.Check]] = doctor.check_avatar
    apply_scenes: Callable[..., Any] = scenes.connect_and_apply
    make_overlay: Callable[..., Any] = _make_overlay
    make_autoclipper: Callable[..., Any] = _make_autoclipper
    open_url: Callable[[str], Any] = field(default=lambda url: QDesktopServices.openUrl(QUrl(url)))


class Bridge(QObject):
    """작업 스레드 → 창. 시그널은 창의 스레드에서 처리된다."""

    checks = Signal(object)
    avatar = Signal(object)
    scenes = Signal(str)
    log = Signal(str)


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


class Wizard(QMainWindow):
    def __init__(self, backend: Backend | None = None) -> None:
        super().__init__()
        self.backend = backend or Backend()
        self.bridge = Bridge()
        self.bridge.checks.connect(self._show_checks)
        self.bridge.avatar.connect(self._show_avatar)
        self.bridge.scenes.connect(self._show_scenes)
        self.bridge.log.connect(self._append_log)
        self.server: Any = None
        self.checked: list[doctor.Check] = []
        self._threads: list[threading.Thread] = []
        self._closed = False
        self.setWindowTitle(f"debutkit {__version__} - 첫 방송 준비")
        self.resize(980, 680)

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

    def _emit(self, signal: Any, value: Any) -> None:
        """작업 스레드에서 창으로. 창이 닫힌 뒤에는 보내지 않는다(닫힌 창의 객체를 건드리면 종료 때 충돌)."""
        if not self._closed:
            signal.emit(value)

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
        layout.addWidget(self._title("PC 점검", "방송에 필요한 사양과 프로그램을 확인합니다. 아무것도 설치하거나 바꾸지 않습니다."))
        self.check_rows = QGridLayout()
        self.check_rows.setHorizontalSpacing(12)
        self.check_rows.setVerticalSpacing(8)
        rows = QWidget()
        rows.setLayout(self.check_rows)
        self.check_summary = QLabel("")
        self.check_summary.setObjectName("Status")
        self.check_button = QPushButton("다시 점검")
        self.check_button.clicked.connect(self.run_checks)
        layout.addWidget(card(rows, self.check_summary))
        layout.addWidget(self.check_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def run_checks(self) -> None:
        self.check_button.setEnabled(False)
        self.check_summary.setText("점검 중...")
        port = self.port.value() if hasattr(self, "port") else OVERLAY_PORT
        self._run(lambda: self._emit(self.bridge.checks, self.backend.run_checks(overlay_port=port)))

    def _show_checks(self, checks: list[doctor.Check]) -> None:
        self.checked = checks
        while self.check_rows.count():
            item = self.check_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for row, check in enumerate(checks):
            state = QLabel(LABELS.get(check.status, check.status))
            state.setObjectName(STATE_STYLE.get(check.status, "StateOther"))
            state.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.check_rows.addWidget(state, row, 0)
            self.check_rows.addWidget(QLabel(check.title), row, 1)
            detail = text(check.detail + (f"\n→ {check.hint}" if check.hint and check.status != OK else ""), muted=check.status == OK)
            detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.check_rows.addWidget(detail, row, 2)
        self.check_rows.setColumnStretch(2, 1)
        self.check_summary.setText(doctor.summary(checks))
        self.check_button.setEnabled(True)

    # ------------------------------------------------------------------ 2. 아바타
    def _page_avatar(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("아바타", "모델 종류에 맞는 트래킹 프로그램을 쓰고, 모델의 사용 조건을 확인하세요."))
        guide = text(
            "<b>Live2D 모델</b> → VTube Studio (수익 방송은 유료 버전 필요)<br>"
            "<b>3D(VRM) 모델</b> → VSeeFace (상업적 이용 허용, 무료) 또는 Warudo<br>"
            "<b>아직 모델이 없다면</b> → VRoid Studio(무료)로 3D 모델을 만들거나 PNG 두 장으로 시작<br>"
            f'<a href="{SOFTWARE_URL}" style="color:#FF7AA8">프로그램 목록과 라이선스 보기</a>', links=True)
        self.avatar_path = QLineEdit()
        self.avatar_path.setPlaceholderText("모델 파일 (.vrm 등)")
        pick = QPushButton("파일 고르기")
        pick.clicked.connect(self._pick_avatar)
        self.avatar_agency = QCheckBox("소속사(기획사) 활동 기준으로 확인")
        self.avatar_agency.setChecked(True)
        check = QPushButton("사용 조건 확인")
        check.clicked.connect(self.check_avatar)
        self.avatar_result = text("", muted=True)
        row = QHBoxLayout()
        row.addWidget(self.avatar_path, 1)
        row.addWidget(pick)
        rows = QWidget()
        rows.setLayout(row)
        layout.addWidget(card(guide, title="어떤 프로그램을 쓰나요"))
        layout.addWidget(card(rows, self.avatar_agency, check, self.avatar_result, title="모델 사용 조건"))
        layout.addStretch(1)
        return page

    def _pick_avatar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "아바타 모델", "", "모델 (*.vrm *.model3.json *.moc3);;모든 파일 (*)")
        if path:
            self.avatar_path.setText(path)

    def check_avatar(self) -> None:
        path = self.avatar_path.text().strip()
        if not path:
            self.avatar_result.setText("모델 파일을 먼저 고르세요.")
            return
        agency = self.avatar_agency.isChecked()
        self._run(lambda: self._emit(self.bridge.avatar, self.backend.check_avatar(path, agency=agency)))

    def _show_avatar(self, checks: list[doctor.Check]) -> None:
        self.avatar_result.setText("\n".join(f"[{LABELS.get(c.status, c.status)}] {c.detail}" + (f"\n→ {c.hint}" if c.hint else "") for c in checks))

    # ------------------------------------------------------------------ 3. OBS 장면
    def _page_scenes(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("OBS 장면", "대기 화면, 본방송, 토크, 자리 비움, 엔딩 장면을 만듭니다. 이미 있는 장면은 건드리지 않습니다."))
        layout.addWidget(card(text("OBS를 켜고 <b>도구 > WebSocket 서버 설정 > WebSocket 서버 사용</b>을 체크하세요. "
                                   "비밀번호가 켜져 있으면 아래에 입력합니다. 처음이라면 OBS에서 장면 모음 > 새로 만들기를 먼저 권합니다.", links=True)))
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
        self.scenes_result.setText("OBS에 연결하는 중...")
        base = f"http://127.0.0.1:{self.port.value()}"
        options = scenes.SceneOptions(overlay_url=f"{base}/chat", alerts_url=f"{base}/alerts", avatar=str(self.avatar_app.currentData()))
        port, password, replay = self.obs_port.value(), self.obs_password.text() or None, 60 if self.replay.isChecked() else None

        def job() -> None:
            try:
                report, _ = self.backend.apply_scenes("127.0.0.1", port, password, options, replay_buffer=replay)
                self._emit(self.bridge.scenes, scenes.format_report(report))
            except Exception as error:
                self._emit(self.bridge.scenes, f"만들지 못했습니다: {error}\nOBS가 켜져 있고 WebSocket 서버가 사용 중인지 확인하세요.")

        self._run(job)

    def _show_scenes(self, message: str) -> None:
        self.scenes_result.setText(message)
        self.scenes_button.setEnabled(True)

    # ------------------------------------------------------------------ 4. 채팅·알림
    def _page_overlay(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("채팅·알림", "방송할 채널을 넣고 시작하면 OBS의 채팅창과 후원 알림이 켜집니다. 채팅은 저장하지 않습니다."))
        form = QFormLayout()
        self.chzzk = QLineEdit()
        self.chzzk.setPlaceholderText("https://chzzk.naver.com/live/채널ID")
        self.soop = QLineEdit()
        self.soop.setPlaceholderText("https://play.sooplive.co.kr/아이디")
        self.twitch = QLineEdit()
        self.twitch.setPlaceholderText("채널 이름")
        self.chzzk_api = QCheckBox("내 치지직 채널을 공식 API로 읽기 (stream2clip chzzk login 필요)")
        self.demo = QCheckBox("데모 채팅 함께 보기 (모양 맞추기)")
        self.autoclip = QCheckBox("채팅이 몰리거나 !clip 을 쓰면 자동 클립 (OBS 리플레이 버퍼 필요)")
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(OVERLAY_PORT)
        form.addRow("치지직", self.chzzk)
        form.addRow("SOOP", self.soop)
        form.addRow("Twitch", self.twitch)
        form.addRow("", self.chzzk_api)
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
        buttons = QHBoxLayout()
        buttons.addWidget(self.overlay_button)
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        actions = QWidget()
        actions.setLayout(buttons)
        self.overlay_log = QPlainTextEdit()
        self.overlay_log.setReadOnly(True)
        self.overlay_log.setMaximumBlockCount(200)
        self.overlay_log.setPlaceholderText("연결 상태와 저장한 클립이 여기에 표시됩니다.")
        layout.addWidget(card(fields, actions))
        layout.addWidget(self.overlay_log, 1)
        return page

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
            self._append_log("오버레이를 멈췄습니다.")
            return
        try:
            server = self.backend.make_overlay(self.overlay_sources(), self.port.value())
        except OSError as error:
            self._append_log(f"{self.port.value()}번 포트를 열지 못했습니다: {error}")
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
                    self._emit(self.bridge.log, f"자동 클립을 켜지 못했습니다: {error}")

            self._run(job)

    def _overlay_state(self, running: bool) -> None:
        self.overlay_button.setText("오버레이 멈추기" if running else "오버레이 시작")
        self.open_button.setEnabled(running)
        for widget in (self.chzzk, self.soop, self.twitch, self.chzzk_api, self.demo, self.autoclip, self.port):
            widget.setEnabled(not running)

    def _append_log(self, line: str) -> None:
        self.overlay_log.appendPlainText(line)

    # ------------------------------------------------------------------ 5. 마무리
    def _page_finish(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title("마무리", "방송을 켜기 전에 한 번 더 확인하세요."))
        self.summary = text("", links=True)
        layout.addWidget(card(self.summary, title="준비 상태"))
        layout.addWidget(card(text(
            "방송이 끝나면 <b>stream2clip</b>으로 채팅 반응이 큰 구간을 세로형 클립으로 만들 수 있습니다. "
            f'<a href="{STREAM2CLIP_URL}" style="color:#FF7AA8">stream2clip 받기</a>', links=True), title="방송 후"))
        layout.addWidget(text(
            f'소속 버튜버 프로그램(선택): 원하는 분만 따로 신청합니다. 키트 사용과는 무관합니다. '
            f'<a href="{MEMBERSHIP_URL}" style="color:#A39DB3">안내 보기</a>', muted=True, links=True))
        layout.addStretch(1)
        return page

    def _refresh_summary(self) -> None:
        lines = []
        need = [c.title for c in self.checked if c.status == FAIL]
        warn = sum(1 for c in self.checked if c.status == WARN)
        passed = "통과" + (f" (주의 {warn}건)" if warn else "")
        lines.append("PC 점검: " + ("필요 항목 " + ", ".join(need) if need else passed if self.checked else "아직 안 함"))
        lines.append("OBS 장면: " + (self.scenes_result.text().splitlines()[0] if self.scenes_result.text() else "아직 안 만듦"))
        lines.append("채팅·알림: " + (f"실행 중 ({self.server.url})" if self.server else "꺼짐"))
        self.summary.setText("<br>".join(lines))

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        self._closed = True
        if self.server is not None:
            self.server.stop()
            self.server = None
        for thread in self._threads:  # 점검·OBS 연결이 끝나길 잠깐 기다린다 (끝나지 않으면 데몬 스레드로 버림)
            thread.join(timeout=1.0)
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    QGuiApplication.setApplicationDisplayName("debutkit")
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
