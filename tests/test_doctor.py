import json
import os

from debutkit import doctor
from debutkit.doctor import FAIL, INFO, OK, WARN, System, format_report, run_checks, steam_libraries, summary, to_json


def fake_system(**overrides):
    steam = r"C:\Steam"
    paths = {
        os.path.join(r"C:\Program Files", "obs-studio", "bin", "64bit", "obs64.exe"),
        os.path.join(steam, "steamapps", "common", "VTube Studio"),
        os.path.join(r"D:\Games", "steamapps", "common", "Warudo"),
    }
    vdf = '"libraryfolders"\n{\n "0" { "path" "C:\\\\Steam" }\n "1" { "path" "D:\\\\Games" }\n}'
    base = dict(
        os_name="Windows",
        env={"ProgramFiles": r"C:\Program Files"},
        which=lambda name: r"C:\ffmpeg\ffmpeg.exe" if name == "ffmpeg" else None,
        exists=lambda path: path in paths,
        port_open=lambda host, port: port == doctor.OBS_WEBSOCKET_PORT,
        memory_gb=lambda: 32.0,
        cpu_count=lambda: 12,
        disk_free_gb=lambda path: 400.0,
        gpu_names=lambda: ["NVIDIA GeForce RTX 4060"],
        package_version=lambda name: "0.14.1" if name == "stream2clip" else None,
        steam_root=lambda: steam,
        read_text=lambda path: vdf if path.endswith("libraryfolders.vdf") else None,
        find_ffmpeg=lambda: None,
        audio_inputs=lambda: ["마이크 (USB Audio)"],
        cameras=lambda: ["HD Webcam"],
        home=r"C:\Users\vt",
    )
    base.update(overrides)
    return System(**base)


def by_key(checks):
    return {check.key: check for check in checks}


def test_ready_pc_is_all_ok():
    checks = by_key(run_checks(fake_system()))
    assert checks["memory"].status == OK
    assert checks["gpu"].status == OK and "NVENC" in checks["gpu"].hint
    assert checks["obs"].status == OK
    assert checks["obs-websocket"].status == OK
    assert checks["tracking"].status == OK
    assert "VTube Studio" in checks["tracking"].detail and "Warudo" in checks["tracking"].detail  # 두 번째 Steam 라이브러리까지 본다
    assert checks["live"].status == OK
    assert checks["ffmpeg"].status == OK
    assert checks["overlay-port"].status == OK


def test_mic_and_webcam():
    found = by_key(run_checks(fake_system()))
    assert found["mic"].status == OK and "USB Audio" in found["mic"].detail
    assert found["camera"].status == OK
    none = by_key(run_checks(fake_system(audio_inputs=lambda: [], cameras=lambda: [])))
    assert none["mic"].status == FAIL  # 마이크는 방송 필수
    assert none["camera"].status == WARN and "아이폰" in none["camera"].hint  # 웹캠은 트래킹 방식에 따라 선택
    unknown = by_key(run_checks(fake_system(audio_inputs=lambda: None, cameras=lambda: None)))
    assert unknown["mic"].status == INFO and unknown["camera"].status == INFO
    many = by_key(run_checks(fake_system(audio_inputs=lambda: ["a", "b", "c", "d"])))
    assert many["mic"].detail == "a, b 외 2개"


def test_downloaded_ffmpeg_outside_path_counts():
    found = by_key(run_checks(fake_system(which=lambda name: None, find_ffmpeg=lambda: r"C:\Users\vt\.cache\tools\ffmpeg.exe")))
    assert found["ffmpeg"].status == OK and "tools" in found["ffmpeg"].detail


def test_missing_live_module_and_ffmpeg_hints():
    found = by_key(run_checks(fake_system(which=lambda name: None, package_version=lambda name: None)))
    assert found["live"].status == WARN and "debutkit[live]" in found["live"].hint
    assert "debutkit setup --ffmpeg" in found["ffmpeg"].hint  # Windows는 내려받기 안내
    mac = by_key(run_checks(fake_system(os_name="Darwin", which=lambda name: None)))
    assert "brew install ffmpeg" in mac["ffmpeg"].hint


def test_missing_obs_is_required_and_exit_message():
    checks = run_checks(fake_system(exists=lambda path: False, which=lambda name: None, port_open=lambda h, p: False))
    found = by_key(checks)
    assert found["obs"].status == FAIL
    assert "obs-websocket" not in found  # OBS가 없으면 원격 제어 점검은 하지 않는다
    assert found["tracking"].status == WARN
    assert found["ffmpeg"].status == INFO  # 방송 자체에는 필요 없다
    assert summary(checks).startswith("준비 필요 1건")


def test_low_spec_warnings():
    found = by_key(run_checks(fake_system(memory_gb=lambda: 8.0, cpu_count=lambda: 4, gpu_names=lambda: ["Intel(R) UHD Graphics 620"], disk_free_gb=lambda p: 5.0)))
    assert found["memory"].status == WARN
    assert found["cpu"].status == WARN
    assert found["gpu"].status == WARN
    assert found["disk"].status == FAIL


def test_websocket_off_is_a_warning_with_hint():
    found = by_key(run_checks(fake_system(port_open=lambda h, p: False)))
    assert found["obs-websocket"].status == WARN
    assert "WebSocket 서버 사용" in found["obs-websocket"].hint


def test_overlay_port_busy():
    found = by_key(run_checks(fake_system(port_open=lambda h, p: True)))
    assert found["overlay-port"].status == WARN
    assert found["vts-api"].status == OK  # VTube Studio API 포트가 열려 있음


def test_unknown_values_do_not_break():
    checks = run_checks(fake_system(memory_gb=lambda: None, cpu_count=lambda: None, gpu_names=lambda: [], disk_free_gb=lambda p: None, steam_root=lambda: None))
    found = by_key(checks)
    assert {found[key].status for key in ("memory", "cpu", "gpu", "disk")} == {INFO}


def test_a_failing_probe_is_reported_not_raised():
    def broken():
        raise RuntimeError("boom")

    checks = run_checks(fake_system(memory_gb=broken))
    assert any("boom" in check.detail for check in checks)
    assert any(check.key == "obs" for check in checks)  # 다른 점검은 계속


def test_steam_libraries_parses_vdf():
    assert steam_libraries(fake_system()) == [r"C:\Steam", r"D:\Games"]


def test_non_vrm_avatar_points_to_store_terms():
    found = by_key(run_checks(fake_system(), avatar="model3.json", agency=True))
    assert found["avatar"].status == INFO
    assert "법인" in found["avatar"].hint


def test_report_and_json():
    checks = run_checks(fake_system(port_open=lambda h, p: False))
    text = format_report(checks)
    assert "[정상]" in text and "[주의]" in text
    assert "조치:" in text  # 주의 항목에는 조치 방법을 붙인다
    data = json.loads(to_json(checks))
    assert {"key", "title", "status", "detail", "hint"} <= set(data[0])


def test_linux_capture_devices_from_proc_when_arecord_is_missing():
    from debutkit.doctor import _proc_capture_devices

    text = ("00-00: ALC892 Analog : ALC892 Analog : playback 1 : capture 1\n"
            "00-01: ALC892 Digital : ALC892 Digital : playback 1\n"
            "01-00: USB Audio : USB Audio : capture 1\n"
            "02-00: Loopback PCM : Loopback PCM : playback 8 : capture 8\n")
    assert _proc_capture_devices(text) == ["ALC892 Analog", "USB Audio", "Loopback PCM"]
    assert _proc_capture_devices("") == []
    assert _proc_capture_devices(None) is None
