"""3D 캐릭터 동작(VRMA, FBX, GLB): 파일 확인, 보관함, 기본 동작, 실행 요청, 후원 반응, 명령줄."""

import http.client
import json
import time
import urllib.parse
import zipfile
from pathlib import Path

import pytest
from model_fake import MIXAMO, NAMES, fbx_ascii, fbx_binary, humanoid_glb, vrma

from debutkit import cli, motion, settings
from debutkit.overlay.events import OverlayEvent, system_event
from debutkit.overlay.server import OverlayServer
from debutkit.vts import parse_reactions

STATIC = Path(motion.__file__).parent / "overlay" / "static"
MIXAMO_BONES = ["mixamorig:" + name for name in MIXAMO.values()]


def test_vrma_details(tmp_path):
    found = motion.inspect(vrma(tmp_path / "wave.vrma"))
    assert found.kind == "vrma" and found.version == "VRMA 1.0" and found.duration == 2.0 and found.bones == 2 and found.clip == ""
    assert any("VRoid 공식 동작" in line for line in found.license) and found.warnings == []
    assert any("입 모양" in line for line in motion.inspect(vrma(tmp_path / "talk.vrma", expressions=("aa", "surprised"))).warnings)
    with pytest.raises(motion.MotionError, match="엉덩이"):
        motion.inspect(vrma(tmp_path / "nohips.vrma", hips=False))
    with pytest.raises(motion.MotionError, match="동작\\(animation\\) 없음"):
        motion.inspect(vrma(tmp_path / "still.vrma", animate=False))
    with pytest.raises(motion.MotionError, match="VRMA 정보"):  # 확장자만 .vrma인 일반 GLB
        motion.inspect(humanoid_glb(tmp_path / "plain.vrma", clips=("x",)))


def test_glb_details_and_clip_choice(tmp_path):
    path = humanoid_glb(tmp_path / "pack.glb", names="mixamo", clips=("Idle", "Wave", "Bow"))
    found = motion.inspect(path)
    assert found.kind == "glb" and found.clips == ["Idle", "Wave", "Bow"] and found.clip == "Idle" and found.duration == 2.0
    assert found.bones == 2 and any("동작 3개 중 Idle" in line and "Wave" in line for line in found.warnings)
    assert motion.inspect(path, clip="Wave").clip == "Wave"
    with pytest.raises(motion.MotionError, match="동작 목록: Idle, Wave, Bow"):
        motion.inspect(path, clip="Dance")
    single = motion.inspect(humanoid_glb(tmp_path / "only.glb", names="vroid", clips=("Take 001",), mesh=False, skin=False))
    assert single.clip == "Take 001" and single.clips == ["Take 001"] and single.warnings == []
    assert any("Mixamo" in line for line in single.license)


def test_glb_errors(tmp_path):
    with pytest.raises(motion.MotionError, match="동작\\(animation\\)이 없는 GLB"):
        motion.inspect(humanoid_glb(tmp_path / "model.glb"))
    with pytest.raises(motion.MotionError, match="캐릭터로 등록"):
        motion.inspect(humanoid_glb(tmp_path / "avatar.glb", vrm=True, clips=("x",)))
    with pytest.raises(motion.MotionError, match="사람 모양 뼈를 찾지 못함\\(왼쪽 아래팔"):
        motion.inspect(humanoid_glb(tmp_path / "partial.glb", skip=("leftLowerArm", "leftHand"), clips=("x",)))
    broken = tmp_path / "broken.glb"
    broken.write_bytes(b"glTF\x02\x00\x00\x00" + b"\x00" * 12)
    with pytest.raises(motion.MotionError):
        motion.inspect(broken)
    for name, pattern in (("walk.bvh", "bvh2vrma"), ("avatar.vrm", "캐릭터로 등록"), ("notes.txt", "지원하지 않는 동작 파일")):
        (tmp_path / name).write_bytes(b"x")
        with pytest.raises(motion.MotionError, match=pattern):
            motion.inspect(tmp_path / name)


@pytest.mark.parametrize("version", [7400, 7500])
def test_fbx_binary_motion(tmp_path, version):
    path = fbx_binary(tmp_path / "Waving.fbx", bones=MIXAMO_BONES, version=version, stacks=[("mixamo.com", 2.5)],
                      animated=["mixamorig:Hips", "mixamorig:LeftArm", "mixamorig:LeftForeArm"])
    found = motion.inspect(path)
    assert found.kind == "fbx" and found.duration == 2.5 and found.bones == 3 and found.clip == "mixamo.com" and found.clips == ["mixamo.com"]
    assert found.version == f"FBX {version // 1000}.{version % 1000 // 100}" and any("Mixamo" in line for line in found.license)
    assert found.warnings == []
    two = fbx_binary(tmp_path / "two.fbx", bones=MIXAMO_BONES, stacks=[("Take 001", 1.0), ("Take 002", 70.0)], animated=["mixamorig:Hips"])
    assert motion.inspect(two).clip == "Take 002"  # 동작 층 정보가 없으면 곡선 수가 같으므로 긴 동작
    picked = motion.inspect(two, clip="Take 001")
    assert picked.clip == "Take 001" and picked.duration == 1.0 and len(picked.warnings) == 1


def test_fbx_skips_empty_mixamo_take(tmp_path):
    """Mixamo FBX는 비어 있는 Take 001과 실제 동작 mixamo.com을 함께 담는다. 곡선이 연결된 동작만 사용."""
    path = fbx_binary(tmp_path / "Samba Dancing.fbx", bones=MIXAMO_BONES, stacks=[("Take 001", 1.0), ("mixamo.com", 70.0)],
                      animated=["mixamorig:Hips", "mixamorig:LeftArm"], layered=True)
    found = motion.inspect(path)
    assert found.clips == ["mixamo.com"] and found.clip == "mixamo.com" and found.duration == 70.0 and found.bones == 2
    assert any("긴 동작" in line for line in found.warnings)
    with pytest.raises(motion.MotionError, match="파일에 없는 동작 이름: Take 001"):
        motion.inspect(path, clip="Take 001")
    added, _ = motion.add(path)
    assert added[0].name == "Samba Dancing" and added[0].clip == "mixamo.com"


def test_fbx_ascii_motion_and_errors(tmp_path):
    found = motion.inspect(fbx_ascii(tmp_path / "idle.fbx", bones=list(NAMES["unreal"].values()), stacks=[("Idle", 3.0)], animated=["pelvis", "spine_01"]))
    assert found.duration == 3.0 and found.bones == 2 and found.clips == ["Idle"]
    with pytest.raises(motion.MotionError, match="동작이 없는 FBX"):
        motion.inspect(fbx_binary(tmp_path / "model.fbx", bones=MIXAMO_BONES))
    with pytest.raises(motion.MotionError, match="사람 모양 뼈"):
        motion.inspect(fbx_binary(tmp_path / "prop.fbx", bones=["Root", "Bone1"], stacks=[("Take", 1.0)], animated=["Bone1"]))
    with pytest.raises(motion.MotionError, match="움직이는 동작이 없음"):
        motion.inspect(fbx_binary(tmp_path / "camera.fbx", bones=MIXAMO_BONES + ["Prop"], stacks=[("Take", 1.0)], animated=["Prop"]))
    with pytest.raises(motion.MotionError, match="FBX 6.1"):
        motion.inspect(fbx_binary(tmp_path / "old.fbx", bones=MIXAMO_BONES, version=6100, stacks=[("Take", 1.0)], animated=["mixamorig:Hips"]))
    (tmp_path / "fake.fbx").write_text("not fbx", encoding="utf-8")
    with pytest.raises(motion.MotionError, match="FBX 파일이 아님"):
        motion.inspect(tmp_path / "fake.fbx")


def test_character_fbx_still_reads_after_parser_change(tmp_path):
    """FBX 구조 읽기가 숫자 값을 함께 읽도록 바뀌어도 캐릭터 확인은 그대로."""
    from debutkit import character

    details = character.fbx_details(fbx_binary(tmp_path / "x.fbx", bones=MIXAMO_BONES, morphs=["jawOpen"], stacks=[("mixamo.com", 1.0)]))
    assert details["bones"] == MIXAMO_BONES and details["morphs"] == ["jawOpen"]


def test_library_idle_and_remove(tmp_path):
    added, skipped = motion.add(vrma(tmp_path / "wave.vrma"), name="손 흔들기")
    assert skipped == [] and [item.name for item in added] == ["손 흔들기"]
    item = added[0]
    assert (motion.library_dir() / item.id / "wave.vrma").is_file() and motion.get(item.id).duration == 2.0
    assert motion.file_path(item, "wave.vrma") is not None and motion.file_path(item, "motion.json") is None
    assert motion.file_path(item, "../motion.json") is None
    second, _ = motion.add(humanoid_glb(tmp_path / "pack.glb", clips=("Idle", "Wave")), clip="Wave")
    assert second[0].name == "pack Wave" and second[0].clip == "Wave"
    assert motion.idle() is None
    motion.set_idle(item.id)
    assert motion.idle().id == item.id and settings.load()["idle_motion"] == item.id
    overview = motion.overview()
    assert overview["idle"] == item.id and [entry["id"] for entry in overview["motions"]] == sorted([item.id, second[0].id])
    with pytest.raises(motion.MotionError, match="등록한 동작 없음"):
        motion.set_idle("없는-동작")
    assert motion.remove(item.id) is not None and motion.idle() is None and "idle_motion" not in settings.load()
    assert motion.remove(item.id) is None and motion.remove("") is None
    motion.set_idle(second[0].id)
    motion.set_idle(None)
    assert motion.idle() is None


def test_zip_and_folder_register_every_motion(tmp_path):
    folder = tmp_path / "pack"
    folder.mkdir()
    vrma(folder / "VRMA_01.vrma")
    vrma(folder / "VRMA_02.vrma")
    humanoid_glb(folder / "avatar.glb", vrm=True)
    (folder / "readme.txt").write_text("credit", encoding="utf-8")
    archive = tmp_path / "pack.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in folder.iterdir():
            bundle.write(path, f"VRMA_MotionPack/{path.name}")
        bundle.writestr("__MACOSX/VRMA_MotionPack/._VRMA_01.vrma", b"junk")
    added, skipped = motion.add(archive, name="무시되는 이름")
    assert sorted(item.name for item in added) == ["VRMA_01", "VRMA_02"] and len(skipped) == 1 and "avatar.glb" in skipped[0]
    added, _ = motion.add(folder)
    assert len(added) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(motion.MotionError, match="찾지 못함"):
        motion.add(empty)
    with pytest.raises(motion.MotionError, match="등록할 수 있는 동작 파일 없음"):
        only = tmp_path / "only"
        only.mkdir()
        humanoid_glb(only / "avatar.glb", vrm=True)
        motion.add(only)


def test_state_and_reactor():
    state = motion.MotionState()
    subscriber, current = state.subscribe()
    assert current["seq"] == 0 and current["play"] == ""
    first = state.play("wave")
    assert first["play"] == "wave" and first["seq"] == 1 and subscriber.get_nowait() == first
    stop = state.play(stop=True)
    assert stop["stop"] is True and stop["play"] == "" and stop["seq"] == 2
    state.unsubscribe(subscriber)
    assert state._subscribers == []


def test_reactor_plays_registered_motions(tmp_path):
    big, _ = motion.add(vrma(tmp_path / "big.vrma"))
    small, _ = motion.add(vrma(tmp_path / "small.vrma"))
    state = motion.MotionState()
    reactor = motion.MotionReactor(parse_reactions([f"10000:{big[0].id}", f"0:{small[0].id}", "5000:없는-동작"]), state)
    donation = OverlayEvent("chzzk", "donation", "시청자", (("text", "응원"),), amount=12000.0, unit="원")
    reactor(donation)
    reactor(OverlayEvent("chzzk", "donation", "시청자", (("text", "응원"),), amount=1000.0, unit="원"))
    reactor(OverlayEvent("chzzk", "donation", "시청자", (("text", "응원"),), amount=6000.0, unit="원"))  # 없는 동작 규칙: 실행 안 함
    reactor(OverlayEvent("chzzk", "chat", "시청자", (("text", "안녕"),)))
    reactor(system_event("연결"))
    assert reactor.played == [big[0].id, small[0].id] and state.current["play"] == small[0].id


@pytest.fixture
def server():
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def request(srv, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    return response.status, response.getheader("Content-Type"), response.read()


def test_server_list_files_and_play(server, tmp_path):
    added, _ = motion.add(vrma(tmp_path / "손 인사.vrma"))
    item = added[0]
    status, _, body = request(server, "GET", "/motion/list")
    listed = json.loads(body)
    assert status == 200 and listed["idle"] == "" and listed["motions"][0]["id"] == item.id
    url = listed["motions"][0]["url"]
    assert "%20" in url
    status, kind, body = request(server, "GET", url)
    assert status == 200 and kind == "model/gltf-binary" and body[:4] == b"glTF"
    quoted = urllib.parse.quote(item.id)
    for bad in (f"/motion/files/{quoted}/motion.json", f"/motion/files/{quoted}/..%2Fmotion.json", "/motion/files/%EC%97%86%EC%9D%8C/x.vrma",
                f"/motion/files/{quoted}/..%5Cmotion.json"):
        assert request(server, "GET", bad)[0] == 404, bad
    status, _, body = request(server, "POST", "/motion", {"id": item.id})
    assert status == 200 and json.loads(body)["play"] == item.id and server.motion.current["play"] == item.id
    assert request(server, "POST", "/motion", {"id": "없는-동작"})[0] == 404
    assert request(server, "POST", "/motion", {"stop": True})[0] == 200 and server.motion.current["stop"] is True
    assert request(server, "POST", "/motion", ["not", "a", "dict"])[0] == 404


def test_live_stream_carries_motion_requests(server, tmp_path):
    added, _ = motion.add(vrma(tmp_path / "wave.vrma"))
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/live")
    stream = conn.getresponse()

    def event():
        name = stream.fp.readline().decode().strip().removeprefix("event: ")
        data = json.loads(stream.fp.readline().decode().removeprefix("data: "))
        stream.fp.readline()
        return name, data

    names = [event()[0] for _ in range(3)]
    assert names == ["voice", "tracking", "motion"]
    request(server, "POST", "/motion", {"id": added[0].id})
    name, data = event()
    assert name == "motion" and data["play"] == added[0].id and data["seq"] == 1 and abs(data["time"] - time.time()) < 5
    stream.close()
    conn.close()


def test_cli_motion_commands(tmp_path, capsys):
    path = vrma(tmp_path / "wave.vrma")
    assert cli.main(["motion", "add", str(path), "--name", "인사"]) == 0
    out = capsys.readouterr().out
    assert "등록: 인사" in out and "VRMA 1.0" in out and "2.0초" in out
    assert cli.main(["motion", "idle", "인사"]) == 0 and motion.idle().id == "인사"
    assert cli.main(["motion", "list"]) == 0 and "* 인사" in capsys.readouterr().out
    assert cli.main(["motion", "idle"]) == 0 and "기본 동작: 인사" in capsys.readouterr().out
    assert cli.main(["motion", "show", "인사"]) == 0 and "사용 조건" in capsys.readouterr().out
    assert cli.main(["motion", "show", "없음"]) == 1
    assert cli.main(["motion", "idle", "--off"]) == 0 and motion.idle() is None
    assert cli.main(["motion", "add", str(tmp_path / "없는 파일.vrma")]) == 1 and "동작 작업 실패" in capsys.readouterr().err
    srv = OverlayServer([], port=0).start()
    try:
        assert cli.main(["motion", "play", "인사", "--port", str(srv.port)]) == 0 and srv.motion.current["play"] == "인사"
        assert "동작 실행: 인사" in capsys.readouterr().out
        assert cli.main(["motion", "play", "없음", "--port", str(srv.port)]) == 1 and "등록한 동작 없음" in capsys.readouterr().err
        assert cli.main(["motion", "play", "--stop", "--port", str(srv.port)]) == 0 and srv.motion.current["stop"] is True
        assert cli.main(["motion", "play", "--port", str(srv.port)]) == 2
        port = srv.port
    finally:
        srv.stop()
    assert cli.main(["motion", "play", "인사", "--port", str(port)]) == 1 and "오버레이에 연결하지 못함" in capsys.readouterr().err
    assert cli.main(["motion", "remove", "인사"]) == 0 and motion.get("인사") is None


def test_overlay_motion_reaction_option_and_saved_setting():
    args = cli.build_parser().parse_args(["overlay", "--motion-reaction", "1000:wave"])
    assert args.motion_reaction == ["1000:wave"]
    saved_args = cli.build_parser().parse_args(["overlay"])
    used = cli.apply_saved(saved_args, {"motion_reactions": ["0:bow"]}, saved_args.overlay_defaults)
    assert saved_args.motion_reaction == ["0:bow"] and "motion_reactions" in used
    assert settings.clean({"motion_reactions": ["0:bow"], "idle_motion": "idle"}) == {"motion_reactions": ["0:bow"], "idle_motion": "idle"}


def test_character_page_plays_motions_and_vendor_is_bundled():
    script = (STATIC / "character.js").read_text(encoding="utf-8")
    assert "/motion/list" in script and "three-vrm-animation.module.min.js" in script and "debutkitLive.subscribe" in script and '"motion"' in script
    assert "VRMExpression_" in script and all(name in script for name in motion.DRIVEN_EXPRESSIONS)
    vendor = STATIC / "vendor" / "three-vrm-animation"
    assert (vendor / "three-vrm-animation.module.min.js").is_file() and (vendor / "LICENSE").is_file()
    readme = (STATIC / "vendor" / "README.txt").read_text(encoding="utf-8")
    assert "three-vrm-animation 3.5.5 (MIT)" in readme and "three-vrm-animation/three-vrm-animation.module.min.js" in readme
    build = (Path(motion.__file__).parents[2] / "packaging" / "build_app.py").read_text(encoding="utf-8")
    assert '"three-vrm-animation.module.min.js"' in build
