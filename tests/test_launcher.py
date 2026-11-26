import json
import sys

import pytest

from debutkit import launcher, settings
from debutkit.launcher import Config, Item, Launcher, LauncherError, Proc, Profile, System, Window


class FakeSystem(System):
    """프로그램 켜기, 끄기, 창을 메모리로 흉내 낸다. ``stubborn`` 은 창 닫기 요청에 꺼지지 않는 프로그램."""

    can_place = True

    def __init__(self, procs=(), stubborn=(), screens=True):
        self.procs = list(procs)
        self.stubborn = set(stubborn)
        self.launched, self.closed, self.placed = [], [], []
        self.wins = []
        self.screens = screens
        self.next_pid = 1000

    def processes(self):
        return list(self.procs)

    def launch(self, item):
        if "broken" in item.target:
            raise OSError("실행 실패")
        self.launched.append(item.target)
        self.next_pid += 1
        name = launcher.process_key(item.target) if item.kind == "program" else "explorer.exe"
        self.procs.append(Proc(self.next_pid, name, item.target))
        self.wins.append(Window(self.next_pid * 10, self.next_pid, launcher.display_name(item.target, item.kind)))

    def close(self, proc, force):
        self.closed.append((proc.name, force))
        if force or proc.key not in self.stubborn:
            self.procs = [p for p in self.procs if p.pid != proc.pid]

    def windows(self):
        return list(self.wins)

    def placement(self, window):
        return {"x": 10, "y": 20, "width": 800 + window.pid % 7, "height": 600, "maximized": 0}

    def place(self, window, rect):
        self.placed.append((window.title, rect["x"]))
        return True

    def on_screen(self, rect):
        return self.screens


class Clock:
    def __init__(self):
        self.now = 0.0

    def sleep(self, seconds):
        self.now += max(seconds, 0.01)

    def __call__(self):
        return self.now


def make(system, config, **kwargs):
    clock = Clock()
    return Launcher(config, system, sleep=clock.sleep, clock=clock, resolve=lambda path: None, **kwargs)


def exe(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"MZ")
    return str(path)


def test_defaults_validation_and_round_trip(tmp_path):
    config = launcher.load()
    assert [p.name for p in config.profiles] == ["방송"] and config.active == "방송"
    with pytest.raises(LauncherError, match="세팅 이름이 비어"):
        launcher.check_profile({"name": " "})
    with pytest.raises(LauncherError, match="http"):
        launcher.check_item({"target": "chzzk.naver.com", "kind": "url"})
    with pytest.raises(LauncherError, match="켜는 간격"):
        launcher.check_item({"target": "a.exe", "delay": 999})
    with pytest.raises(LauncherError, match="종류"):
        launcher.check_item({"target": "a.exe", "kind": "virus"})
    item = launcher.check_item({"target": " \"C:\\OBS\\obs64.exe\" ", "delay": "5", "window": {"x": -1920, "y": 0, "width": 1280, "height": 720, "maximized": True}})
    assert item.target == "C:\\OBS\\obs64.exe" and item.delay == 5.0 and item.window["maximized"] == 1 and item.label == "obs64.exe"
    assert launcher.check_item({"target": "a.exe", "window": {"x": 0, "y": 0, "width": 5, "height": 5}}).window is None
    # 운영체제와 관계없이 Windows 경로도 파일 이름으로, .exe 를 붙이든 빼든 같은 프로그램
    assert launcher.file_name("C:\\OBS\\obs64.exe") == launcher.file_name("/opt/obs/obs64.exe") == "obs64.exe"
    assert launcher.same_program("obs64", "OBS64.exe") and launcher.same_program("C:\\Apps\\Discord.exe", "discord")
    assert not launcher.same_program("obs64", "obs32.exe")
    config = launcher.put_profile(config, {"name": "방송", "start": [asdict_item(item), "https://studio.chzzk.naver.com"], "stop": ["Discord", "discord.exe", "KakaoTalk.exe"]})
    # Windows는 .exe를 생략해도 같은 프로그램(Discord와 discord.exe 중복 제거)
    assert config.profile().start[1].kind == "url" and len(config.profile().stop) == (2 if sys.platform == "win32" else 3)
    launcher.copy_profile(config, "방송", "게임")
    with pytest.raises(LauncherError, match="같은 이름"):
        launcher.copy_profile(config, "방송", "게임")
    launcher.save(config)
    again = launcher.load()
    assert [p.name for p in again.profiles] == ["방송", "게임"] and again.profile("게임").start[0].window == item.window
    with pytest.raises(LauncherError, match="세팅 없음"):
        again.profile("작업")
    launcher.remove_profile(again, "방송")
    assert again.active == "게임"
    with pytest.raises(LauncherError, match="하나뿐"):
        launcher.remove_profile(again, "게임")
    restored = launcher.import_text(launcher.export_text(again))
    assert restored.to_dict() == again.to_dict()
    with pytest.raises(LauncherError, match="백업 파일이 아님"):
        launcher.import_text(json.dumps({"profiles": []}))


def asdict_item(item):
    return {"target": item.target, "kind": item.kind, "delay": item.delay, "window": item.window}


def test_broken_saved_file_keeps_valid_parts():
    settings.save_data(launcher.DATA, {"active": "없음", "profiles": [{"name": "방송", "start": [{"target": ""}, {"target": "obs64.exe"}, 3]},
                                                                    {"name": ""}, "x", {"name": "방송"}], "protect": ["obs64.exe", 5]})
    config = launcher.load()
    assert [p.name for p in config.profiles] == ["방송"] and [i.target for i in config.profile().start] == ["obs64.exe"] and config.protect == ["obs64.exe"]


def test_guess_kind(tmp_path):
    assert launcher.guess_kind("https://youtube.com/live") == "url"
    assert launcher.guess_kind(str(tmp_path)) == "folder"
    assert launcher.guess_kind("C:/Users/me/Desktop/OBS.lnk") == "shortcut"
    assert launcher.guess_kind("C:/x/obs64.exe") == "program"
    assert launcher.guess_kind("C:/x/memo.txt") == "file"


def test_run_stops_first_then_starts_in_order_skipping_running(tmp_path):
    obs, vts = exe(tmp_path, "obs64.exe"), exe(tmp_path, "VTube Studio.exe")
    system = FakeSystem([Proc(1, "Discord.exe", "C:/D/Discord.exe"), Proc(2, "Discord.exe", "C:/D/Discord.exe"), Proc(3, "obs64.exe", obs),
                         Proc(4, "Steam.exe", "C:/S/Steam.exe")], stubborn={"steam.exe"})
    config = Config([Profile("방송", start=[Item(obs), Item(vts, delay=3), Item(str(tmp_path), kind="folder"), Item("https://studio.chzzk.naver.com", kind="url"),
                                          Item(str(tmp_path / "없는.exe"))],
                             stop=["Discord.exe", "Steam.exe", "explorer.exe", "KakaoTalk.exe"])], "방송")
    lines = []
    run = make(system, config, report=lambda step: lines.append(step.text()))
    steps = run.run()
    states = [(step.state, step.label) for step in steps]
    assert states[:4] == [("stopped", "Discord.exe"), ("forced", "Steam.exe"), ("protected", "explorer.exe"), ("missing", "KakaoTalk.exe")]
    assert ("skipped", "obs64.exe") in states and ("started", "VTube Studio.exe") in states and ("failed", "없는.exe") in states
    assert system.launched == [vts, str(tmp_path), "https://studio.chzzk.naver.com"]
    assert system.closed[:2] == [("Discord.exe", False), ("Discord.exe", False)] and ("Steam.exe", True) in system.closed
    assert lines == [step.text() for step in steps]
    killed = launcher.load_session()["killed"]
    assert {item["key"] for item in killed} == {"discord.exe", "steam.exe"}


def test_end_restores_killed_programs_and_clears_session(tmp_path):
    discord = exe(tmp_path, "Discord.exe")
    system = FakeSystem([Proc(1, "Discord.exe", discord), Proc(2, "Gone.exe", str(tmp_path / "Gone.exe"))])
    config = Config([Profile("방송", stop=["Discord.exe", "Gone.exe"])], "방송")
    make(system, config).run()
    assert system.procs == []
    steps = make(system, config).end()
    assert [(s.state, s.label) for s in steps] == [("restored", "Discord.exe"), ("info", "Gone.exe")]
    assert system.launched == [discord] and launcher.load_session() == {}
    assert make(system, config).end() == []  # 기록이 없으면 할 일 없음


def test_windows_are_placed_only_for_new_windows_and_known_screens(tmp_path):
    obs = exe(tmp_path, "obs64.exe")
    rect = {"x": -1920, "y": 0, "width": 1280, "height": 720, "maximized": 0}
    system = FakeSystem()
    config = Config([Profile("방송", start=[Item(obs, window=rect)])], "방송")
    steps = make(system, config).run()
    assert ("placed", "obs64.exe") in [(s.state, s.label) for s in steps] and system.placed == [("obs64.exe", -1920)]
    unplugged = FakeSystem(screens=False)
    steps = make(unplugged, config).run()
    assert unplugged.placed == [] and any("모니터" in s.detail for s in steps)


def test_running_program_can_be_moved_when_asked(tmp_path):
    obs = exe(tmp_path, "obs64.exe")
    system = FakeSystem([Proc(7, "obs64.exe", obs)])
    system.wins.append(Window(70, 7, "OBS 32"))
    rect = {"x": 0, "y": 0, "width": 1000, "height": 700, "maximized": 1}
    config = Config([Profile("방송", start=[Item(obs, window=rect)], place_running=True)], "방송")
    make(system, config).run()
    assert system.placed == [("OBS 32", 0)] and system.launched == []


def test_remember_windows_takes_largest_window(tmp_path):
    obs = exe(tmp_path, "obs64.exe")
    system = FakeSystem([Proc(7, "obs64.exe", obs), Proc(9, "obs64.exe", obs)])
    system.wins += [Window(70, 7, "OBS"), Window(90, 9, "OBS 2")]
    config = Config([Profile("방송", start=[Item(obs), Item("https://x.com", kind="url")])], "방송")
    steps = launcher.remember_windows(config, system=system, resolve=lambda path: None)
    assert steps[0].state == "placed" and config.profile().start[0].window["width"] == 800 + 9 % 7
    assert steps[1].state == "missing" and config.profile().start[1].window is None
    assert launcher.remember_windows(config, system=System())[0].detail == "Windows에서만 기억"


def test_protect_list_and_own_process_are_never_stopped(tmp_path):
    own = launcher.process_key(sys.executable)
    system = FakeSystem([Proc(1, "obs64.exe"), Proc(2, own)])
    config = Config([Profile("방송", stop=["obs64.exe", own])], "방송", protect=["OBS64.EXE"])
    steps = make(system, config).run()
    assert [s.state for s in steps] == ["protected", "protected"] and system.closed == []


def test_watcher_notifies_and_rekills():
    system = FakeSystem([Proc(1, "Discord.exe")])
    profile = Profile("방송", stop=["Discord.exe", "explorer.exe"])
    notes = []
    watcher = launcher.Watcher(profile, Config([profile], "방송"), notes.append, system=system)
    watcher.start()
    watcher.stop()
    assert watcher.check() == [] and notes == []  # 처음부터 켜져 있던 것은 알리지 않음
    system.procs.append(Proc(5, "Discord.exe"))
    system.procs.append(Proc(6, "explorer.exe"))
    assert [p.pid for p in watcher.check()] == [5] and notes == ["꺼 둔 프로그램이 다시 켜짐: Discord.exe"]
    profile.rekill = True
    system.procs.append(Proc(8, "Discord.exe"))
    watcher.check()
    assert notes[-1] == "꺼 둔 프로그램이 다시 켜져 다시 끔: Discord.exe" and ("Discord.exe", True) in system.closed


def test_launch_failure_and_matches_full_path(tmp_path):
    system = FakeSystem()
    config = Config([Profile("방송", start=[Item("broken.exe")])], "방송")
    steps = make(system, config).run()
    assert steps[0].state == "failed" and "실행 실패" in steps[0].detail
    proc = Proc(1, "Game.exe", "C:\\Games\\A\\Game.exe")
    assert launcher.matches(proc, "game.exe") and launcher.matches(proc, "C:/Games/A/Game.exe") == (sys.platform == "win32")
    assert not launcher.matches(proc, "C:\\Games\\B\\Game.exe")
    assert launcher.summary([]).startswith("할 일이 없음")


def test_cli_manages_profiles_and_runs(tmp_path, monkeypatch, capsys):
    from debutkit.cli import main

    system = FakeSystem([Proc(3, "Discord.exe", "C:/D/Discord.exe")])
    monkeypatch.setattr(launcher, "default_system", lambda: system)
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    program = exe(tmp_path, "tool.exe")
    assert main(["launch", "add", "방송", program, "https://studio.chzzk.naver.com", "--delay", "0"]) == 0
    assert main(["launch", "add", "방송", "Discord.exe", "--stop"]) == 0
    assert main(["launch", "set", "방송", "--rekill", "--no-restore"]) == 0
    config = launcher.load()
    assert config.profile().rekill and not config.profile().restore and config.profile().watch and config.profile().stop == ["Discord.exe"]
    assert main(["launch", "copy", "방송", "게임"]) == 0 and main(["launch", "use", "게임"]) == 0
    assert main(["launch", "remove", "게임", "studio.chzzk.naver.com"]) == 0
    assert main(["launch", "remove", "게임", "없는것"]) == 1
    assert [i.kind for i in launcher.load().profile("게임").start] == ["program"] and launcher.load().active == "게임"
    assert main(["launch", "protect", "obs64.exe"]) == 0 and launcher.load().protect == ["obs64.exe"]
    assert main(["launch", "protect", "obs64", "--remove"]) == 0 and launcher.load().protect == []
    backup = tmp_path / "backup.json"
    assert main(["launch", "export", str(backup)]) == 0 and main(["launch", "delete", "방송"]) == 0
    assert main(["launch", "import", str(backup)]) == 0 and [p.name for p in launcher.load().profiles] == ["방송", "게임"]
    assert main(["launch", "delete", "없음"]) == 1 and "세팅 없음" in capsys.readouterr().err
    assert main(["launch", "run", "방송", "--no-watch"]) == 0
    out = capsys.readouterr().out
    assert "끔: Discord.exe" in out and "켬: tool.exe" in out and "켬: studio.chzzk.naver.com" in out
    assert system.launched == [program, "https://studio.chzzk.naver.com"]
    assert main(["launch", "end"]) == 0 and "다시 켤 프로그램 없음" in capsys.readouterr().out  # 게임 세팅은 방송 끝에 다시 켜기 꺼짐
    assert main(["launch", "list"]) == 0 and "* 게임" in capsys.readouterr().out


def test_wait_for_port_gives_up():
    clock = Clock()
    assert launcher.wait_for_port("127.0.0.1", 9, 0.0, clock=clock, sleep=clock.sleep) is False  # 한 번 시도하고 포기
