"""일반 3D 모델(GLB, FBX) 등록: 뼈와 표정 이름 대응, 파일 확인, 캐릭터 화면 제공."""

import http.client
import json
import re
import urllib.parse
import zipfile
from pathlib import Path

import pytest
from model_fake import NAMES, fbx_ascii, fbx_binary, humanoid_glb

from debutkit import character, humanoid
from debutkit.overlay.server import OverlayServer

STATIC = Path(character.__file__).parent / "overlay" / "static"
REQUIRED_NAMES = {
    "biped": ["Bip001 Pelvis", "Bip001 Spine", "Bip001 Head", "Bip001 L UpperArm", "Bip001 L Forearm", "Bip001 L Hand", "Bip001 R UpperArm",
              "Bip001 R Forearm", "Bip001 R Hand", "Bip001 L Thigh", "Bip001 L Calf", "Bip001 L Foot", "Bip001 R Thigh", "Bip001 R Calf", "Bip001 R Foot"],
    "cc": ["CC_Base_Hip", "CC_Base_Waist", "CC_Base_Head", "CC_Base_L_Upperarm", "CC_Base_L_Forearm", "CC_Base_L_Hand", "CC_Base_R_Upperarm",
           "CC_Base_R_Forearm", "CC_Base_R_Hand", "CC_Base_L_Thigh", "CC_Base_L_Calf", "CC_Base_L_Foot", "CC_Base_R_Thigh", "CC_Base_R_Calf", "CC_Base_R_Foot"],
}


@pytest.mark.parametrize("convention", sorted(NAMES))
def test_bone_conventions_find_all_required_bones(convention):
    found = humanoid.match_bones(NAMES[convention].values())
    assert humanoid.missing_bones(found) == [] and found["chest"] == NAMES[convention]["chest"] and found["jaw"] == NAMES[convention]["jaw"]
    assert found["leftLowerLeg"] == NAMES[convention]["leftLowerLeg"] and found["rightHand"] == NAMES[convention]["rightHand"]


@pytest.mark.parametrize("convention", sorted(REQUIRED_NAMES))
def test_more_bone_conventions(convention):
    assert humanoid.missing_bones(humanoid.match_bones(REQUIRED_NAMES[convention])) == []


def test_three_js_sanitized_names_and_first_match():
    """three.js는 노드 이름의 공백을 _로 바꾸고 . : / [ ]를 지운다. 같은 비교 값이 되어야 한다."""
    sanitized = [re.sub(r"[\[\].:/]", "", name.replace(" ", "_")) for name in NAMES["rigify"].values()]
    assert humanoid.missing_bones(humanoid.match_bones(sanitized)) == []
    assert humanoid.match_bones(["mixamorig2:Hips", "mixamorig:Hips"])["hips"] == "mixamorig2:Hips"
    assert humanoid.match_bones(["DEF-upper_arm.L", "DEF-upper_arm.L.001"])["leftUpperArm"] == "DEF-upper_arm.L"
    assert humanoid.bone_label("rightLowerLeg") == "오른쪽 종아리" and humanoid.bone_label("hips") == "엉덩이"


def test_expression_names_and_arkit_fallback():
    vroid = humanoid.match_expressions(["Fcl_MTH_A", "Face.Fcl_EYE_Close", "Fcl_EYE_Close_L", "Fcl_ALL_Joy"])
    assert vroid == {"aa": {"Fcl_MTH_A": 1.0}, "blink": {"Face.Fcl_EYE_Close": 1.0}, "blinkLeft": {"Fcl_EYE_Close_L": 1.0}, "happy": {"Fcl_ALL_Joy": 1.0}}
    vrchat = humanoid.match_expressions(["vrc.v_aa", "vrc.v_oh", "viseme_I", "まばたき"])
    assert vrchat["aa"] == {"vrc.v_aa": 1.0} and vrchat["oh"] == {"vrc.v_oh": 1.0} and vrchat["ih"] == {"viseme_I": 1.0} and "blink" in vrchat
    arkit = humanoid.match_expressions(["blendShape1.jawOpen", "eyeBlinkLeft", "eyeBlinkRight", "mouthSmileLeft", "mouthSmileRight", "mouthPucker"])
    assert arkit["aa"] == {"blendShape1.jawOpen": 1.0} and arkit["blink"] == {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0}
    assert arkit["ou"] == {"blendShape1.jawOpen": 0.2, "mouthPucker": 0.9} and arkit["happy"] == {"mouthSmileLeft": 0.8, "mouthSmileRight": 0.8}
    assert humanoid.match_expressions(["mouthPucker"]) == {}  # 첫 항목(jawOpen)이 없으면 대체하지 않음
    assert humanoid.match_expressions(["Fcl_MTH_A", "jawOpen"])["aa"] == {"Fcl_MTH_A": 1.0}  # 이름이 맞는 표정 우선


def test_browser_uses_the_same_name_rules():
    """캐릭터 화면(character.js)의 이름 비교 규칙이 파이썬과 같아야 같은 뼈를 찾는다."""
    script = (STATIC / "character.js").read_text(encoding="utf-8")
    assert humanoid._STRIP.pattern == r"[\s_\-.:/\[\]\\|]+"
    assert r'name.replace(/[\s_\-.:\/\[\]\\|]+/g, "").toLowerCase()' in script
    assert 'replace(/^mixamorig\\d*/, "")' in script and "split(/[.|:]/).pop()" in script


def test_glb_humanoid_registers_with_expressions(tmp_path):
    glb = humanoid_glb(tmp_path / "Neko Model.glb", names="vroid", morphs=("Fcl_MTH_A", "Fcl_EYE_Close"))
    found = character.inspect(glb)
    assert found.kind == "model" and found.version == "GLB(glTF 2.0)" and found.name == "Neko Model" and found.renders_in_overlay
    assert not any("입 모양" in warning or "눈 감기" in warning for warning in found.warnings)
    assert any("사용 조건 정보가 없음" in line for line in found.license) and any("VRM 변환 필요" in warning for warning in found.warnings)
    added = character.add(glb)
    assert added.files == {"model": "Neko Model.glb"} and (character.library_dir() / added.id / "Neko Model.glb").is_file()
    plain = character.inspect(humanoid_glb(tmp_path / "plain.glb"))
    assert any("턱 뼈로 입 움직임" in warning for warning in plain.warnings) and any("눈 감기 표정 없음" in warning for warning in plain.warnings)
    assert any("Mixamo" in line for line in plain.license)
    nojaw = character.inspect(humanoid_glb(tmp_path / "nojaw.glb", skip=("jaw",), morphs=("jawOpen", "eyeBlinkLeft", "eyeBlinkRight")))
    assert not any("입 모양" in warning or "눈 감기" in warning for warning in nojaw.warnings)  # ARKit 대체


def test_glb_problems_are_explained(tmp_path):
    with pytest.raises(character.CharacterError, match="왼쪽 아래팔, 왼쪽 손, 오른쪽 아래팔"):
        character.inspect(humanoid_glb(tmp_path / "a.glb", skip=("leftLowerArm", "leftHand", "rightLowerArm", "rightHand")))
    with pytest.raises(character.CharacterError, match="뼈대"):
        character.inspect(humanoid_glb(tmp_path / "b.glb", skin=False))
    other = {bone: f"bone_{number}" for number, bone in enumerate(NAMES["mixamo"])}
    with pytest.raises(character.CharacterError, match="Mixamo 자동 리깅"):
        character.inspect(humanoid_glb(tmp_path / "c.glb", names=other))
    assert character.inspect(humanoid_glb(tmp_path / "d.glb", vrm=True)).kind == "vrm"  # 확장자만 .glb인 VRM
    for name, message in (("e.gltf", "GLB"), ("f.pmx", "MMD"), ("g.obj", "지원하지 않는 파일")):
        (tmp_path / name).write_text("x", encoding="utf-8")
        with pytest.raises(character.CharacterError, match=message):
            character.inspect(tmp_path / name)


@pytest.mark.parametrize("version", [7400, 7500])
def test_fbx_binary_bones_morphs_and_textures(tmp_path, version):
    folder = tmp_path / "model"
    (folder / "textures").mkdir(parents=True)
    from test_character import png

    png(folder / "textures" / "skin.png")
    (folder / "hair.tga").write_bytes(b"tga")
    bones = list(NAMES["mixamo"].values())
    fbx = fbx_binary(folder / "char.fbx", bones=bones, morphs=["Fcl_MTH_A", "blendShape1.eyeBlinkLeft"], version=version,
                     videos=[("textures\\skin.png", b""), ("embedded.png", b"\x89PNG data"), ("hair.tga", b""), ("..\\outside.png", b""), ("gone.jpg", b"")])
    details = character.fbx_details(fbx)
    assert details["version"] == f"FBX 7.{version % 1000 // 100}" and details["bones"] == bones
    assert details["morphs"] == ["Fcl_MTH_A", "blendShape1.eyeBlinkLeft"] and ("embedded.png", True) in details["textures"]
    found = character.inspect(fbx)
    assert found.kind == "model" and found.files == {"model": "char.fbx", "texture1": "textures/skin.png"}
    assert any("텍스처 파일 2개를 찾지 못함(outside.png, gone.jpg)" in warning for warning in found.warnings)
    assert any("TGA" in warning for warning in found.warnings) and not any("입 모양" in warning for warning in found.warnings)
    added = character.add(folder)  # 폴더 등록: FBX와 텍스처 복사
    library = character.library_dir() / added.id
    assert (library / "char.fbx").is_file() and (library / "textures" / "skin.png").is_file() and not (library / "hair.tga").exists()


def test_fbx_ascii_old_and_broken(tmp_path):
    ascii_fbx = fbx_ascii(tmp_path / "a.fbx", bones=list(NAMES["unreal"].values()), morphs=["vrc.v_aa"], textures=["skin.png"])
    details = character.fbx_details(ascii_fbx)
    assert details["version"] == "FBX 7.4" and len(details["bones"]) == len(NAMES["unreal"]) and details["morphs"] == ["vrc.v_aa"]
    assert character.inspect(ascii_fbx).kind == "model"
    with pytest.raises(character.CharacterError, match="FBX 6.1"):
        character.inspect(fbx_binary(tmp_path / "old.fbx", bones=["Hips"], version=6100))
    broken = tmp_path / "broken.fbx"
    broken.write_bytes(fbx_binary(tmp_path / "ok.fbx", bones=list(NAMES["mixamo"].values())).read_bytes()[:120])
    with pytest.raises(character.CharacterError):
        character.inspect(broken)
    (tmp_path / "text.fbx").write_text("hello", encoding="utf-8")
    with pytest.raises(character.CharacterError, match="FBX 파일이 아님"):
        character.inspect(tmp_path / "text.fbx")


def test_zip_with_fbx_and_folder_detection(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    fbx_binary(source / "neko.fbx", bones=list(NAMES["mixamo"].values()))
    archive = tmp_path / "neko.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(source / "neko.fbx", "neko/neko.fbx")
    assert character.add(archive, name="네코").files == {"model": "neko.fbx"}


@pytest.fixture
def server():
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def get(srv, path):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request("GET", path)
    response = conn.getresponse()
    return response.status, response.getheader("Content-Type"), response.read()


def test_server_gives_name_table_and_model_files(server, tmp_path):
    status, kind, body = get(server, "/character/humanoid.json")
    table = json.loads(body)
    assert status == 200 and kind == "application/json" and table["required"] == list(humanoid.REQUIRED)
    assert table["bones"]["leftarm"] == "leftUpperArm" and table["expressions"]["fclmtha"] == "aa" and table["arkit"]["aa"] == {"jawOpen": 1.0}
    added = character.add(humanoid_glb(tmp_path / "모델 #1.glb", morphs=("A",)))
    info = json.loads(get(server, "/character/info?id=" + urllib.parse.quote(added.id))[2])
    assert info["kind"] == "model" and info["renders"]
    status, kind, body = get(server, info["files"]["model"])
    assert status == 200 and kind == "model/gltf-binary" and body.startswith(b"glTF")
    folder = tmp_path / "fbx"
    folder.mkdir()
    from test_character import png

    png(folder / "skin.png")
    fbx = character.add(fbx_binary(folder / "m.fbx", bones=list(NAMES["mixamo"].values()), videos=[("skin.png", b"")]))
    info = json.loads(get(server, "/character/info?id=" + urllib.parse.quote(fbx.id))[2])
    assert get(server, info["files"]["model"])[:2] == (200, "application/octet-stream")
    assert get(server, info["files"]["texture1"])[:2] == (200, "image/png")
    assert get(server, f"/character/files/{urllib.parse.quote(fbx.id)}/other.png")[0] == 404


def test_vrm_glb_is_sent_to_warudo_as_vrm(tmp_path):
    added = character.add(humanoid_glb(tmp_path / "v.glb", vrm=True))
    target = tmp_path / "warudo"
    target.mkdir()
    assert character.send(added, "warudo", folder=target) == target / "v.vrm"
    with pytest.raises(character.CharacterError, match="VRM\\) 캐릭터만"):
        character.send(character.add(humanoid_glb(tmp_path / "m.glb")), "warudo", folder=target)
