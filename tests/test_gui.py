import os
import sys
import time
import urllib.request
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from debutkit.doctor import FAIL, OK, WARN, Check  # noqa: E402
from debutkit.gui.app import Backend, Wizard, style_sheet  # noqa: E402
from debutkit.scenes import Report  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(style_sheet())
    yield application
    # 파이썬이 끝날 때 Qt 객체가 엉뚱한 순서로 지워지면 Linux·macOS에서 segfault가 난다: 먼저 정리
    for widget in application.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    application.processEvents()
    if hasattr(application, "shutdown"):
        application.shutdown()


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
        self.stored = {}
        self.saves = []
        self.cleared = []

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
                    apply_scenes=apply_scenes, make_autoclipper=make_autoclipper, open_url=self.urls.append,
                    chzzk_signed_in=lambda: False, can_download_ffmpeg=lambda: True,
                    load_settings=lambda: dict(self.stored), save_settings=self.saves.append, clear_settings=lambda: self.cleared.append(1) or True,
                    make_voice_meter=lambda *a, **k: None)
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
        assert "조치: 정리" in window.check_rows.itemAtPosition(2, 2).widget().text()
        assert not window.ffmpeg_button.isVisibleTo(window)  # ffmpeg 항목이 없으면 버튼도 없음
    finally:
        window.close()


def test_missing_ffmpeg_offers_download_and_rechecks(app):
    runs = []

    def run_checks(**kw):
        runs.append(1)
        status = OK if len(runs) > 1 else "info"
        return [Check("ffmpeg", "ffmpeg", status, "찾지 못함", "내려받기")]

    def download(on_progress, cancelled):
        on_progress(50, 100)
        return [r"C:\tools\ffmpeg.exe", r"C:\tools\ffprobe.exe"]

    window = Wizard(Calls().backend(run_checks=run_checks, download_ffmpeg=download))
    try:
        assert wait_for(app, lambda: bool(window.checked))
        assert window.ffmpeg_button.isVisibleTo(window)
        window.ffmpeg_button.click()
        assert wait_for(app, lambda: "설치 완료" in window.ffmpeg_status.text())
        assert wait_for(app, lambda: len(runs) == 2 and not window.ffmpeg_button.isVisibleTo(window))  # 받은 뒤 다시 점검
    finally:
        window.close()


def test_chzzk_login_uses_fields_and_checks_api(app):
    seen = []

    def login(client_id, client_secret):
        seen.append((client_id, client_secret))

    window = Wizard(Calls().backend(chzzk_login=login))
    try:
        assert not window.chzzk_api.isChecked()
        window.chzzk_id.setText("id")
        window.chzzk_secret.setText("secret")
        window.chzzk_login_button.click()
        assert wait_for(app, lambda: window.chzzk_state.text() == "로그인됨")
        assert seen == [("id", "secret")] and window.chzzk_api.isChecked()
    finally:
        window.close()


def test_chzzk_login_error_is_shown(app):
    def login(client_id, client_secret):
        raise RuntimeError("Client ID 필요")

    window = Wizard(Calls().backend(chzzk_login=login))
    try:
        window.login_chzzk()
        assert wait_for(app, lambda: "로그인 실패: Client ID 필요" in window.chzzk_state.text())
        assert window.chzzk_login_button.isEnabled()
    finally:
        window.close()


def test_finish_page_opens_clip_folder(app, tmp_path):
    opened = []
    window = Wizard(Calls().backend(clip_dir=lambda: tmp_path / "clips", open_folder=opened.append))
    try:
        window.go(4)
        assert str(tmp_path / "clips") in window.clip_folder.text()
        next(b for b in window.findChildren(type(window.next)) if b.text() == "클립 폴더 열기").click()
        assert opened == [tmp_path / "clips"]
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


def test_update_check_shows_link(app):
    from debutkit import tools

    window = Wizard(Calls().backend(check_update=lambda: f"새 버전 0.9.0 있음 (현재 0.3.0): {tools.RELEASES_PAGE}"))
    try:
        window.go(4)
        window.update_button.click()
        assert wait_for(app, lambda: "새 버전 0.9.0" in window.update_result.text())
        assert "릴리스 페이지</a>" in window.update_result.text() and window.update_button.isEnabled()
    finally:
        window.close()


def test_youtube_field_becomes_a_source(app):
    window = Wizard(Calls().backend())
    try:
        window.youtube.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        window.youtube_key.setText("KEY")
        labels = [label for label, _ in window.overlay_sources()]
        assert labels == ["YouTube https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
        source = window.overlay_sources()[0][1]()
        assert source.api_key == "KEY" and source.video == "dQw4w9WgXcQ"
    finally:
        window.close()


def test_speed_button_shows_advice(app):
    window = Wizard(Calls().backend(measure_speed=lambda: Check("upload", "업로드 속도", WARN, "5.0 Mbps. 권장 720p 30fps", "유선 연결 권장")))
    try:
        window.speed_button.click()
        assert wait_for(app, lambda: "5.0 Mbps" in window.speed_result.text())
        assert "[주의]" in window.speed_result.text() and "조치: 유선 연결 권장" in window.speed_result.text()
        assert window.speed_button.isEnabled()
    finally:
        window.close()


def test_youtube_check_button_reports_steps(app):
    asked = []
    window = Wizard(Calls().backend(check_youtube=lambda video, key: asked.append((video, key)) or "YouTube 연결 확인\n  [정상] 스트리밍 방식  연결 성공"))
    try:
        window.youtube_check_button.click()
        assert "방송 주소를 먼저 입력" in window.overlay_log.toPlainText() and not asked
        window.youtube.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        window.youtube_key.setText("KEY")
        window.youtube_check_button.click()
        assert wait_for(app, lambda: "[정상] 스트리밍 방식" in window.overlay_log.toPlainText())
        assert asked == [("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "KEY")]
        assert window.youtube_check_button.isEnabled()
    finally:
        window.close()


def test_saved_settings_open_the_overlay_page_filled_in(app):
    calls = Calls()
    calls.stored = {"chzzk": ["https://chzzk.naver.com/live/abc"], "clip": True, "overlay_port": 8800, "obs_port": 4460, "avatar_app": "vseeface",
                    "replay_buffer": 0, "demo": False}
    window = Wizard(calls.backend())
    try:
        assert window.pages.currentIndex() == 3 and not window.checked  # PC 점검을 자동으로 돌리지 않음
        assert window.chzzk.text() == "https://chzzk.naver.com/live/abc" and window.autoclip.isChecked()
        assert window.port.value() == 8800 and window.obs_port.value() == 4460 and window.avatar_app.currentData() == "vseeface"
        assert not window.replay.isChecked() and "저장한 설정을 불러왔습니다" in window.overlay_log.toPlainText()
    finally:
        window.close()


def test_closing_saves_inputs_without_secrets(app):
    calls = Calls()
    window = Wizard(calls.backend())
    window.soop.setText("https://play.sooplive.co.kr/id")
    window.youtube_key.setText("AIza-secret")
    window.obs_password.setText("pw")
    window.chzzk_secret.setText("client-secret")
    window.close()
    saved = calls.saves[-1]
    assert saved["soop"] == ["https://play.sooplive.co.kr/id"] and "chzzk" not in saved
    assert not any(value in str(saved) for value in ("AIza-secret", "pw", "client-secret"))


def test_saving_keeps_the_chosen_character(app):
    """캐릭터 단계의 사용 버튼이 저장한 캐릭터를 오버레이 시작, 창 닫기 저장이 지우지 않는다."""
    calls = Calls()
    calls.stored = {"demo": True, "character": "neko"}
    window = Wizard(calls.backend())
    window.soop.setText("https://play.sooplive.co.kr/id")
    window.close()
    assert calls.saves[-1]["character"] == "neko" and calls.saves[-1]["soop"] == ["https://play.sooplive.co.kr/id"]


def test_forgetting_settings_stops_saving_until_next_start(app):
    calls = Calls()
    window = Wizard(calls.backend())
    window.forget_button.click()
    assert calls.cleared and "삭제했습니다" in window.settings_state.text()
    window.close()
    assert calls.saves == []


def test_release_waits_for_workers_and_deletes_the_window(app):
    import threading

    from debutkit.gui.app import release

    window = Wizard(Calls().backend())
    finished = threading.Event()
    worker = threading.Thread(target=lambda: (time.sleep(0.2), finished.set()))
    worker.start()
    window._threads.append(worker)
    destroyed = []
    window.destroyed.connect(lambda: destroyed.append(True))
    window.close()
    release(window, None)  # 테스트의 Qt 앱은 그대로 둔다
    assert finished.is_set() and destroyed == [True]


def test_report_buttons_copy_diagnostics_and_open_pages(app):
    calls = Calls()
    calls.stored = {"demo": True}  # 채팅과 알림 단계에서 시작: PC 점검이 자동으로 돌지 않음
    copied = []
    opened = []
    window = Wizard(calls.backend(copy_text=copied.append, open_folder=opened.append, log_dir=lambda: Path("logs-folder")))
    try:
        window.copy_button.click()
        assert not copied and "먼저 실행" in window.report_state.text()
        window.run_checks()
        assert wait_for(app, lambda: bool(window.checked))
        window.copy_button.click()
        assert copied and copied[0].startswith("debutkit ") and "OBS Studio" in copied[0] and "복사했습니다" in window.report_state.text()
        buttons = {button.text(): button for button in window.findChildren(QPushButton)}
        buttons["문제 제보, 확인 보고(GitHub)"].click()
        buttons["기록 폴더 열기"].click()
        assert calls.urls[-1].endswith("/issues/new/choose") and opened == [Path("logs-folder")]
    finally:
        window.close()


def test_character_page_add_make_use_send_and_preview(app, tmp_path):
    from test_character import live2d, png, vrm1

    from debutkit import character

    vrm = vrm1(tmp_path / "hero.vrm", commercialUsage="corporation", avatarPermission="everyone")
    folder = tmp_path / "vts-models"
    folder.mkdir()
    picks = {"file": str(vrm), "folder": str(folder)}
    calls = Calls()
    window = Wizard(calls.backend(pick_character=lambda: picks["file"], pick_folder=lambda title: picks["folder"],
                                  pick_png=lambda: ("Cat", {"idle": png(tmp_path / "i.png"), "talk": png(tmp_path / "t.png")})))
    try:
        assert window.characters.count() == 2 and "[방송 사용 중]" in window.characters.item(0).text()  # 기본 캐릭터(2D, 3D 데비)
        assert not window.remove_button.isEnabled() and not window.send_button.isEnabled()
        window.characters.setCurrentRow(1)
        assert window.selected_character().id == character.SAMPLE_3D_ID and not window.remove_button.isEnabled()
        window.add_character()
        assert window.selected_character().kind == "vrm" and "Warudo로 보내기" == window.send_button.text()
        assert "상업적 이용: 법인 포함 가능" in window.character_detail.text()
        window.use_character()
        assert character.active().kind == "vrm" and window.avatar_app.currentData() == "debutkit"
        window.make_png_character()
        assert window.selected_character().id == "cat" and window.characters.count() == 4
        picks["file"] = str(live2d(tmp_path / "l2d" / "hiyori") / "hiyori.model3.json")
        window.add_character()
        window.send_character()  # 자동으로 찾지 못하면 폴더를 물어본다
        assert (folder / window.selected_character().id / "hiyori.model3.json").is_file() and "VTube Studio로 복사" in window.character_detail.text()
        window.use_character()
        assert window.avatar_app.currentData() == "vts"
        window.characters.setCurrentRow(3)  # Live2D(hiyori)
        window.preview_character()
        assert "오버레이를 시작한 뒤" in window.character_detail.text()
        window.open_tracker()
        assert "얼굴 추적 창을 열 수 있습니다" in window.character_detail.text()
        assert window.tracker_button.isEnabled() == window.selected_character().renders_in_overlay  # Live2D는 VTube Studio가 추적
        assert window.phone_button.isEnabled() == window.selected_character().renders_in_overlay
        window.open_phone()
        assert "휴대폰 얼굴 추적을 설정할 수 있습니다" in window.character_detail.text()
        picks["file"] = str(tmp_path / "missing.vrm")
        window.add_character()
        assert "등록 실패" in window.character_detail.text()
    finally:
        window.close()


def test_overlay_start_attaches_voice_meter(app):
    meters = []

    class FakeServer:
        url = "http://127.0.0.1:8790"

        def __init__(self):
            self.hub = type("Hub", (), {"taps": []})()
            self.attached = []

        def start(self):
            return self

        def stop(self):
            pass

        def attach(self, part):
            self.attached.append(part)

    server = FakeServer()
    calls = Calls()
    window = Wizard(calls.backend(make_overlay=lambda sources, port: server,
                                  make_voice_meter=lambda srv, port, password, threshold, name: meters.append((port, threshold)) or "meter"))
    try:
        window.voice_threshold.setValue(-35)
        window.toggle_overlay()
        assert meters == [(4455, -35.0)] and "meter" in server.attached and "/character" in window.overlay_log.toPlainText()
        assert "/tracker" in window.overlay_log.toPlainText()
        window.open_tracker()
        assert calls.urls[-1] == "http://127.0.0.1:8790/tracker"
        window.open_phone()
        assert calls.urls[-1] == "http://127.0.0.1:8790/phone" and "Wi-Fi" in window.character_detail.text()
        assert "/phone" in window.overlay_log.toPlainText()
        assert server.obs_target == ("127.0.0.1", 4455, None)  # 휴대폰 화면에서 OBS 카메라 소스 만들기
        assert window.remote_button.isEnabled()
        window.remote_button.click()
        assert calls.urls[-1] == "http://127.0.0.1:8790/phone#remote"
        assert window.broadcast_button.isEnabled() and window.broadcast_button.isHidden() == (sys.platform != "win32")
        window.broadcast_button.click()
        assert calls.urls[-1] == "http://127.0.0.1:8790/broadcast/control"
        assert window.logo_button.isEnabled()
        window.logo_button.click()
        assert calls.urls[-1] == "http://127.0.0.1:8790/logo"
        assert calls.saves[-1]["voice_threshold"] == -35.0
    finally:
        window.close()


def test_vts_card_connects_loads_triggers_and_saves_reaction(app):
    pytest.importorskip("websocket")
    from vts_fake import FakeVts

    from debutkit import vts

    fake = FakeVts()
    reactors = []

    class FakeServer:
        url = "http://127.0.0.1:8790"

        def __init__(self):
            self.hub = type("Hub", (), {"taps": []})()
            self.attached = []

        def start(self):
            return self

        def stop(self):
            pass

        def attach(self, part):
            self.attached.append(part)

    server = FakeServer()
    calls = Calls()
    window = Wizard(calls.backend(vts_connect=lambda request_new=False: vts.connect(fake.url, request_new=request_new),
                                  make_overlay=lambda sources, port: server,
                                  make_vts_reactor=lambda srv, reactions: reactors.append(reactions) or "reactor"))
    try:
        window.vts_action("login")
        assert wait_for(app, lambda: window.vts_models.count() == 2), window.vts_state.text()
        assert "연결됨" in window.vts_state.text() and window.vts_hotkey.count() == 2 and vts.load_token() == "new-token"
        window.vts_models.setCurrentIndex(1)
        window.vts_action("load")
        assert wait_for(app, lambda: fake.loaded == ["m2"])
        window.vts_hotkey.setEditText("Heart")
        window.vts_min.setValue(1000)
        window.vts_action("trigger")
        assert wait_for(app, lambda: fake.triggered == ["Heart"])
        assert window.collect_settings()["vts_reactions"] == ["1000:Heart"]
        window.toggle_overlay()
        assert reactors and reactors[0][0].hotkey == "Heart" and "reactor" in server.attached
        assert "1,000원 이상 후원 시 Heart" in window.overlay_log.toPlainText()
    finally:
        window.close()
        fake.close()


def test_motion_card_adds_sets_idle_plays_and_saves_reaction(app, tmp_path):
    from model_fake import humanoid_glb, vrma

    from debutkit import motion

    plays = []

    class FakeMotion:
        def play(self, motion_id):
            plays.append(motion_id)

    class FakeServer:
        url = "http://127.0.0.1:8790"

        def __init__(self):
            self.hub = type("Hub", (), {"taps": []})()
            self.motion = FakeMotion()

        def start(self):
            return self

        def stop(self):
            pass

        def attach(self, part):
            pass

    server = FakeServer()
    motion.add(vrma(tmp_path / "bow.vrma"))
    picks = {"file": str(vrma(tmp_path / "wave.vrma")), "clip": "Wave"}
    calls = Calls()
    calls.stored = {"motion_reactions": ["2000:bow"]}
    window = Wizard(calls.backend(pick_motion=lambda: picks["file"], pick_clip=lambda clips: picks["clip"], make_overlay=lambda sources, port: server))
    try:
        assert window.motions.count() == 1 and window.motion_reaction.currentData() == "bow" and window.motion_min.value() == 2000
        window.add_motion()
        assert window.motions.count() == 2 and window.selected_motion().id == "wave" and "VRMA 1.0" in window.motion_detail.text()
        picks["file"] = str(humanoid_glb(tmp_path / "pack.glb", clips=("Idle", "Wave")))
        window.add_motion()
        assert motion.get("pack-wave").clip == "Wave" and window.selected_motion().id == "pack-wave"
        picks["clip"] = None  # 동작 선택 취소: 등록하지 않음
        window.add_motion()
        assert window.motions.count() == 3
        window.idle_motion.setCurrentIndex(window.idle_motion.findData("wave"))
        assert motion.idle().id == "wave" and any("[기본 동작]" in window.motions.item(row).text() for row in range(window.motions.count()))
        window.motion_reaction.setCurrentIndex(window.motion_reaction.findData("pack-wave"))
        window.motion_min.setValue(3000)
        assert window.collect_settings()["motion_reactions"] == ["3000:pack-wave"]
        window.play_motion()
        assert "오버레이를 시작한 뒤" in window.motion_detail.text() and plays == []
        window.toggle_overlay()
        assert any(isinstance(tap, motion.MotionReactor) for tap in server.hub.taps)
        assert "3,000원 이상 후원 시 pack Wave 실행" in window.overlay_log.toPlainText()
        window.play_motion()
        assert plays == ["pack-wave"] and "실행: pack Wave" in window.motion_detail.text()
        picks["file"] = str(tmp_path / "missing.vrma")
        window.add_motion()
        assert "등록 실패" in window.motion_detail.text()
        window.motions.setCurrentRow([item.id for item in window._motion_list].index("wave"))
        window.remove_motion()
        assert motion.idle() is None and window.idle_motion.currentData() == "" and window.motions.count() == 2
    finally:
        window.close()


def test_draw_button_opens_control_page_and_settings_survive(app):
    class FakeServer:
        url = "http://127.0.0.1:8790"

        def __init__(self):
            self.hub = type("Hub", (), {"taps": []})()

        def start(self):
            return self

        def stop(self):
            pass

        def attach(self, part):
            pass

    calls = Calls()
    calls.stored = {"draw_enabled": True, "draw_prizes": ["9:꽝", "1:사진"], "draw_style": "wheel"}
    window = Wizard(calls.backend(make_overlay=lambda sources, port: FakeServer()))
    try:
        assert not window.draw_button.isEnabled()
        window.toggle_overlay()
        assert window.draw_button.isEnabled()
        window.draw_button.click()
        assert calls.urls[-1] == "http://127.0.0.1:8790/draw/control"
        saved = calls.saves[-1]  # 설정 마법사가 저장할 때 조작 화면에서 저장한 추첨 설정을 지우지 않음
        assert saved["draw_enabled"] is True and saved["draw_prizes"] == ["9:꽝", "1:사진"] and saved["draw_style"] == "wheel"
    finally:
        window.close()


def test_chat_commands_checkbox_saves_and_restores(app):
    calls = Calls()
    window = Wizard(calls.backend())
    try:
        assert window.chat_commands.isChecked() and window.collect_settings()["chat_commands"] is True
        window.chat_commands.setChecked(False)
        assert window.collect_settings()["chat_commands"] is False
        window.apply_settings({"chat_commands": True})
        assert window.chat_commands.isChecked() and window.draw_button.text() == "추첨 조작 화면"
    finally:
        window.close()
    calls = Calls()
    calls.stored = {"chat_commands": False, "raffle_command": "!들어감", "raffle_title": "노래 신청", "phone_enabled": True, "phone_app": "vts",
                    "phone_ip": "192.168.0.12", "phone_center_yaw": 0.1,
                    "remote_enabled": True, "remote_address": "192.168.0.5", "remote_port": 8800}
    window = Wizard(calls.backend())
    try:
        assert not window.chat_commands.isChecked()
        window.remember()
        assert calls.saves[-1]["raffle_command"] == "!들어감" and calls.saves[-1]["raffle_title"] == "노래 신청"
        assert calls.saves[-1]["phone_enabled"] is True and calls.saves[-1]["phone_ip"] == "192.168.0.12" and calls.saves[-1]["phone_center_yaw"] == 0.1
        assert calls.saves[-1]["remote_enabled"] is True and calls.saves[-1]["remote_address"] == "192.168.0.5" and calls.saves[-1]["remote_port"] == 8800
    finally:
        window.close()


def test_phone_camera_button_shows_connection_and_qr(app):
    added = []

    def add_phone_camera(host, port, password):
        added.append((host, port, password))
        if len(added) > 1:
            raise RuntimeError("Cannot reach OBS at ws://127.0.0.1:4455")
        return {"source": "[DK] 휴대폰 카메라", "created": True, "updated": False, "added": ["본방송"], "kept": [],
                "state": {"exists": True, "state": "OBS_MEDIA_STATE_OPENING", "text": "휴대폰 연결 대기"},
                "info": {"addresses": ["192.168.0.5", "10.0.0.2"], "address": "192.168.0.5", "port": 9710, "latency": 200, "passphrase": "abcdefghjkmn",
                         "url": "srt://192.168.0.5:9710", "larix": "larix://set/v1?conn[][url]=srt://192.168.0.5:9710", "source": "[DK] 휴대폰 카메라"}}

    calls = Calls()
    window = Wizard(calls.backend(add_phone_camera=add_phone_camera))
    try:
        window.obs_password.setText("pw")
        window.add_phone_camera()
        assert wait_for(app, lambda: window.camera_button.isEnabled() and "본방송" in window.camera_result.text())
        assert added == [("127.0.0.1", 4455, "pw")]
        assert "srt://192.168.0.5:9710" in window.camera_result.text() and "abcdefghjkmn" in window.camera_result.text()
        assert "10.0.0.2" in window.camera_result.text() and window.camera_qr.isVisibleTo(window) is not None
        assert not window.camera_qr.pixmap().isNull() and window.camera_qr.pixmap().width() == 200
        window.add_phone_camera()
        assert wait_for(app, lambda: "실패" in window.camera_result.text())
        assert "연결하지 못함" in window.camera_result.text()
    finally:
        window.close()


def test_launch_card_runs_watches_starts_overlay_and_ends(app):
    from debutkit import launcher

    config = launcher.Config([launcher.Profile("방송", stop=["Discord.exe"], overlay=True), launcher.Profile("게임")], "방송")
    saved, runs, watchers, edits = [], [], [], []

    class FakeLauncher:
        def __init__(self, config, report):
            self.report = report

        def run(self, name):
            runs.append(("run", name))
            step = launcher.Step("stopped", "Discord.exe")
            self.report(step)
            return [step]

        def end(self, name):
            runs.append(("end", name))
            step = launcher.Step("restored", "Discord.exe")
            self.report(step)
            return [step]

    class FakeWatcher:
        def __init__(self, profile, config, notify):
            self.notify, self.stopped = notify, False
            watchers.append(self)

        def start(self):
            return self

        def stop(self):
            self.stopped = True

    window = Wizard(Calls().backend(load_launcher=lambda: config, save_launcher=saved.append, make_launcher=FakeLauncher, make_watcher=FakeWatcher,
                                    edit_launcher=lambda parent: edits.append(parent) or True))
    try:
        window.port.setValue(18791)
        assert [window.launch_profiles.itemText(i) for i in range(window.launch_profiles.count())] == ["방송", "게임"]
        window.launch_button.click()
        assert wait_for(app, lambda: "감시 중" in window.launch_state.text())
        assert runs == [("run", "방송")] and "끔: Discord.exe" in window.launch_state.text() and window.server is not None  # 켠 뒤 오버레이 시작
        watchers[0].notify("꺼 둔 프로그램이 다시 켜짐: Discord.exe")
        assert wait_for(app, lambda: "다시 켜짐: Discord.exe" in window.launch_state.text())
        window.launch_end_button.click()
        assert wait_for(app, lambda: "다시 켬: Discord.exe" in window.launch_state.text() and window.launch_button.isEnabled())
        assert watchers[0].stopped and runs[-1] == ("end", "방송")
        window.launch_profiles.setCurrentText("게임")
        window.launch_button.click()
        assert wait_for(app, lambda: runs[-1] == ("run", "게임")) and saved and saved[-1].active == "게임"
        [button for button in window.findChildren(QPushButton) if button.text() == "세팅 편집"][0].click()
        assert edits and "세팅을 저장" in window.launch_state.text()
    finally:
        window.close()


def test_launch_dialog_edits_and_saves(app, tmp_path, monkeypatch):
    from debutkit import launcher
    from debutkit.gui.launch_dialog import LaunchDialog

    stored = []
    program = tmp_path / "tool.exe"
    program.write_bytes(b"MZ")
    dialog = LaunchDialog(load=launcher.load, save=stored.append, processes=lambda: [launcher.Proc(1, "KakaoTalk.exe"), launcher.Proc(2, "explorer.exe")],
                          resolve=lambda path: "C:/Apps/Discord/Discord.exe",
                          remember=lambda config, name: [launcher.Step("placed", "tool.exe", "0,0 800x600")])
    try:
        dialog.add_start([str(program), "https://studio.chzzk.naver.com", str(tmp_path)])
        assert [item.kind for item in dialog.profile.start] == ["program", "url", "folder"]
        dialog.start_list.setCurrentRow(0)
        dialog.delay.setValue(5.5)
        dialog.move(1)
        assert [item.kind for item in dialog.profile.start] == ["url", "program", "folder"] and dialog.profile.start[1].delay == 5.5
        dialog.add_stop(["C:/Users/me/Desktop/Discord.lnk", "explorer.exe", "Discord.exe"])
        assert dialog.profile.stop == ["Discord.exe"] and "끌 수 없는" in dialog.state.text()
        monkeypatch.setattr("debutkit.gui.launch_dialog.QInputDialog.getItem", lambda *a, **k: ("KakaoTalk.exe", True))
        dialog.pick_running()
        assert dialog.profile.stop == ["Discord.exe", "KakaoTalk.exe"]
        dialog.checks["watch"].setChecked(False)
        assert not dialog.profile.watch and not dialog.checks["rekill"].isEnabled()
        monkeypatch.setattr("debutkit.gui.launch_dialog.QInputDialog.getText", lambda *a, **k: ("게임", True))
        dialog.copy_profile()
        assert dialog.current == "게임" and dialog.profiles.currentText() == "게임" and dialog.profile.stop == ["Discord.exe", "KakaoTalk.exe"]
        dialog.remember_windows()
        assert "창 위치 맞춤: tool.exe" in dialog.state.text()
        dialog.save_and_close()
        assert stored and stored[-1].active == "게임" and [p.name for p in stored[-1].profiles] == ["방송", "게임"]
    finally:
        dialog.close()


def test_saving_keeps_settings_the_wizard_does_not_manage(app):
    calls = Calls()
    calls.stored = {"chzzk": ["old"], "draw_design": "night", "draw_effect": "confetti", "youtube_interval": 15.0, "raffle_title": "참여"}
    window = Wizard(calls.backend(save_settings=lambda values: calls.saves.append(values)))
    try:
        window.chzzk.setText("")  # 비운 입력 칸은 저장하지 않음(마법사가 다루는 항목)
        window.remember()
        saved = calls.saves[-1]
        assert "chzzk" not in saved and saved["draw_design"] == "night" and saved["draw_effect"] == "confetti"
        assert saved["youtube_interval"] == 15.0 and saved["raffle_title"] == "참여"
    finally:
        window._keep_settings = False
        window.close()
