import os
import time
import urllib.request

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from debutkit.doctor import FAIL, OK, WARN, Check  # noqa: E402
from debutkit.gui.app import Backend, Wizard, style_sheet  # noqa: E402
from debutkit.scenes import Report  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(style_sheet())
    yield application


def wait_for(app, condition, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


class Calls:
    def __init__(self):
        self.scenes = []
        self.urls = []
        self.autoclip = []

    def backend(self, **overrides):
        def run_checks(**kw):
            return [Check("obs", "OBS Studio", OK, "found"), Check("gpu", "그래픽카드", WARN, "내장", "QSV 사용"), Check("disk", "저장 공간", FAIL, "5 GB", "정리")]

        def apply_scenes(host, port, password, options, **kw):
            self.scenes.append((port, password, options, kw))
            return Report(created_scenes=["대기 화면", "본방송"], notes=["리플레이 버퍼 시작 (최대 60초)"]), []

        def make_autoclipper(hub, port, password):
            self.autoclip.append(port)

            class Fake:
                def start(self):
                    return self

                def stop(self):
                    pass

            return Fake(), "자동 클립 켬 (OBS 33.0.1)"

        base = dict(run_checks=run_checks, check_avatar=lambda path, agency: [Check("avatar", "아바타", WARN, f"{path} 법인 {agency}")],
                    apply_scenes=apply_scenes, make_autoclipper=make_autoclipper, open_url=self.urls.append)
        base.update(overrides)
        return Backend(**base)


def test_checks_run_on_open_and_show_states(app):
    calls = Calls()
    window = Wizard(calls.backend())
    try:
        assert wait_for(app, lambda: bool(window.checked))
        assert "준비 필요 1건" in window.check_summary.text()
        names = [window.check_rows.itemAtPosition(row, 0).widget().objectName() for row in range(3)]
        assert names == ["StateOk", "StateWarn", "StateMissing"]
        assert "→ 정리" in window.check_rows.itemAtPosition(2, 2).widget().text()
    finally:
        window.close()


def test_navigation_buttons(app):
    window = Wizard(Calls().backend())
    try:
        assert not window.back.isEnabled() and window.next.isEnabled()
        window.next.click()
        assert window.pages.currentIndex() == 1
        window.go(4)
        assert not window.next.isEnabled()
        assert "PC 점검" in window.summary.text()
    finally:
        window.close()


def test_avatar_check_passes_agency_flag(app):
    window = Wizard(Calls().backend())
    try:
        window.avatar_path.setText("model.vrm")
        window.avatar_agency.setChecked(True)
        window.check_avatar()
        assert wait_for(app, lambda: "model.vrm 법인 True" in window.avatar_result.text())
    finally:
        window.close()


def test_scenes_use_form_values(app):
    calls = Calls()
    window = Wizard(calls.backend())
    try:
        window.obs_port.setValue(4466)
        window.obs_password.setText("pw")
        window.avatar_app.setCurrentIndex(1)  # VSeeFace
        window.port.setValue(9100)
        window.scenes_button.click()
        assert wait_for(app, lambda: "만든 장면: 대기 화면, 본방송" in window.scenes_result.text())
        port, password, options, kw = calls.scenes[0]
        assert (port, password, options.avatar, kw["replay_buffer"]) == (4466, "pw", "vseeface", 60)
        assert options.overlay_url == "http://127.0.0.1:9100/chat"
        assert window.scenes_button.isEnabled()
    finally:
        window.close()


def test_scenes_error_is_shown(app):
    def broken(*a, **kw):
        raise RuntimeError("연결 거부")

    window = Wizard(Calls().backend(apply_scenes=broken))
    try:
        window.make_scenes()
        assert wait_for(app, lambda: "연결 거부" in window.scenes_result.text())
    finally:
        window.close()


def test_overlay_start_demo_autoclip_and_stop(app):
    calls = Calls()
    window = Wizard(calls.backend())
    try:
        window.port.setValue(18790)
        window.autoclip.setChecked(True)
        window.obs_port.setValue(4466)
        assert [label for label, _ in window.overlay_sources()] == ["데모"]  # 채널이 없으면 데모
        window.toggle_overlay()
        assert window.server is not None and not window.chzzk.isEnabled()
        page = urllib.request.urlopen(window.server.url + "/chat", timeout=5).read().decode()
        assert "startChat" in page
        assert wait_for(app, lambda: "자동 클립 켬" in window.overlay_log.toPlainText())
        assert calls.autoclip == [4466]
        assert wait_for(app, lambda: "데모 연결 시도" in window.overlay_log.toPlainText())
        window.open_button.click()
        assert calls.urls == [window.server.url]
        window.toggle_overlay()
        assert window.server is None and window.chzzk.isEnabled()
    finally:
        window.close()


def test_channel_fields_become_sources(app):
    window = Wizard(Calls().backend())
    try:
        window.chzzk.setText("https://chzzk.naver.com/live/0123456789abcdef0123456789abcdef")
        window.soop.setText("bjid")
        window.demo.setChecked(True)
        labels = [label for label, _ in window.overlay_sources()]
        assert labels == ["CHZZK https://chzzk.naver.com/live/0123456789abcdef0123456789abcdef", "SOOP bjid", "데모"]
    finally:
        window.close()
