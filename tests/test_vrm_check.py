"""VRM 점검(표정, 텍스처 무게)과 가벼운 사본(텍스처 줄이기): 공개 VRM 11종을 재어 정한 기준을 작은 시험 파일로 확인한다."""

import http.client
import io
import json
import struct
import zlib
from pathlib import Path
from urllib.parse import quote

import pytest

from debutkit import character
from debutkit.overlay import tracking
from debutkit.overlay.server import OverlayServer

STATIC = Path(__file__).resolve().parent.parent / "src" / "debutkit" / "overlay" / "static"
BIND = {"morphTargetBinds": [{"node": 0, "index": 0, "weight": 1.0}]}
TEXTURE_WARNING = "텍스처가 무거움"


def header_png(width, height):
    """크기만 적은 PNG 머리글(점검은 머리글만 읽는다)."""
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0) + b"\x00" * 4


def small_png(width=4, height=4):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x4f\x8b\x80" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def vrm1(preset=(), custom=(), empty=(), bones=None, **meta):
    base = {"name": "점검 모델", "authors": ["작가"], "avatarPermission": "everyone", "commercialUsage": "corporation", "creditNotation": "unnecessary"}
    return {"VRMC_vrm": {"specVersion": "1.0", "meta": {**base, **meta},
                         "expressions": {"preset": {**{name: BIND for name in preset}, **{name: {} for name in empty}},
                                         "custom": {name: BIND for name in custom}},
                         "humanoid": {"humanBones": bones or {"hips": {"node": 0}}}}}


def vrm_file(path, extensions, images=(), extra=b""):
    """VRM 시험 파일: images(그림 바이트)는 앞에서부터 bufferView, extra는 그림 뒤의 다른 자료(정점 등)."""
    views, binary = [], b""
    for blob in [*images, extra] if extra else list(images):
        binary += b"\x00" * (-len(binary) % 4)
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(blob)})
        binary += blob
    binary += b"\x00" * (-len(binary) % 4)
    gltf = {"asset": {"version": "2.0"}, "extensionsUsed": list(extensions), "extensions": extensions, "bufferViews": views,
            "images": [{"bufferView": index, "mimeType": "image/png", "name": f"tex{index}"} for index in range(len(images))],
            "buffers": [{"byteLength": len(binary)}]}
    body = json.dumps(gltf, ensure_ascii=False).encode()
    body += b" " * (-len(body) % 4)
    chunks = struct.pack("<I4s", len(body), b"JSON") + body + struct.pack("<I4s", len(binary), b"BIN\x00") + binary
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks)
    return path


def check_of(extensions, images=()):
    return character.vrm_check({"extensions": extensions, "images": [{"bufferView": i} for i in range(len(images))],
                                "bufferViews": _views(images)}, b"".join(images))


def _views(images):
    views, offset = [], 0
    for blob in images:
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(blob)})
        offset += len(blob)
    return views


def test_vrm1_expressions_count_only_moving_ones():
    found = check_of(vrm1(preset=("aa", "ih", "blink", "happy", "angry"), empty=("sad", "relaxed", "surprised")))
    assert found["emotions"] == ["happy", "angry"] and found["vowels"] == ["aa", "ih"] and found["blink"] == "both"
    assert found["warnings"] == [] and found["perfect_sync"] == 0 and found["jaw"] is False


def test_missing_mouth_and_blink_are_warned_and_jaw_counts():
    bare = check_of(vrm1(preset=("happy",)))
    assert any(text.startswith("입 모양 표정") for text in bare["warnings"]) and any(text.startswith("눈 깜빡임 표정") for text in bare["warnings"])
    jaw = check_of(vrm1(preset=("blinkLeft", "blinkRight"), bones={"hips": {"node": 0}, "jaw": {"node": 1}}))
    assert jaw["jaw"] and jaw["blink"] == "sides" and jaw["warnings"] == []  # 턱 뼈로 입을 움직이고, 좌우 눈 표정으로 깜빡임


def test_vrm0_names_follow_three_vrm():
    groups = [{"presetName": "a", "binds": [{"mesh": 0, "index": 0, "weight": 100}]}, {"presetName": "blink_l", "binds": [{"index": 1}]},
              {"presetName": "blink_r", "binds": [{"index": 2}]}, {"presetName": "joy", "binds": [{"index": 3}]},
              {"presetName": "unknown", "name": "Surprised", "binds": [{"index": 4}]}, {"presetName": "sorrow", "binds": []},
              {"presetName": "fun", "materialValues": [{"materialName": "face"}]}]
    found = check_of({"VRM": {"meta": {"title": "옛"}, "blendShapeMaster": {"blendShapeGroups": groups}, "humanoid": {"humanBones": [{"bone": "hips"}]}}})
    assert found["emotions"] == ["happy", "relaxed", "surprised"] and found["vowels"] == ["aa"] and found["blink"] == "sides" and found["warnings"] == []


def test_perfect_sync_needs_enough_arkit_names():
    assert check_of(vrm1(preset=("aa", "blink"), custom=tracking.ARKIT_NAMES[:11]))["perfect_sync"] == 0
    names = [name[0].upper() + name[1:] for name in tracking.ARKIT_NAMES]  # VRoid 퍼펙트 싱크 표기(BrowDownLeft)
    assert check_of(vrm1(preset=("aa", "blink"), custom=names))["perfect_sync"] == 52


def test_texture_weight_matches_measured_models():
    vroid = check_of(vrm1(preset=("aa", "blink")), [header_png(2048, 2048)] * 4 + [header_png(1024, 1024)] * 8)
    assert vroid["textures"]["largest"] == 2048 and vroid["textures"]["count"] == 12 and 100 < vroid["textures"]["gpu_mb"] < 256
    assert not any(TEXTURE_WARNING in text for text in vroid["warnings"])  # VRoid 샘플 크기는 경고하지 않음
    heavy = check_of(vrm1(preset=("aa", "blink")), [header_png(4096, 4096)])
    assert any(text.startswith(TEXTURE_WARNING) and "4096px" in text for text in heavy["warnings"])


def test_jpeg_header_size():
    image = pytest.importorskip("PIL.Image")
    out = io.BytesIO()
    image.new("RGB", (300, 200), (10, 20, 30)).save(out, "JPEG")
    assert character._image_size(out.getvalue()) == (300, 200) and character._image_size(b"GIF89a....") is None


def test_modification_permission():
    assert not character.modification_allowed({"extensions": vrm1()})  # VRM 1.0 기본값 prohibited
    assert character.modification_allowed({"extensions": vrm1(modification="allowModification")})
    assert not character.modification_allowed({"extensions": {"VRM": {"meta": {"licenseName": "CC_BY_NC_ND"}}}})
    assert character.modification_allowed({"extensions": {"VRM": {"meta": {"licenseName": "CC0"}}}})
    assert not character.modification_allowed({"extensions": {}})


def _picture(width, height):
    """가운데는 불투명한 색, 가장자리는 투명한 그림(머리카락 텍스처처럼)."""
    image_module = pytest.importorskip("PIL.Image")
    picture = image_module.new("RGBA", (width, height), (0, 0, 0, 0))
    for y in range(height // 4, height * 3 // 4):
        for x in range(width // 4, width * 3 // 4, 1):
            picture.putpixel((x, y), (200, 120 + (x * 50 // width), 40, 255))
    out = io.BytesIO()
    picture.save(out, "PNG")
    return out.getvalue()


def test_shrink_keeps_vrm_data_and_transparent_edges(tmp_path):
    image_module = pytest.importorskip("PIL.Image")
    extra = b"VERTEX-DATA-" * 33
    extensions = vrm1(preset=("aa", "blink", "happy"), modification="allowModification")
    path = vrm_file(tmp_path / "big.vrm", extensions, [_picture(512, 256), small_png()], extra)
    data, changed = character.shrink_vrm(path, max_size=128)
    assert [item["name"] for item in changed] == ["tex0"] and changed[0]["to"] == [128, 64] and changed[0]["after"] < changed[0]["before"]
    out = tmp_path / "light.vrm"
    out.write_bytes(data)
    gltf, binary = character.read_glb(out)
    assert gltf["extensions"] == extensions and character.vrm_expressions(gltf) == character.vrm_expressions(character.read_glb(path)[0])
    views = gltf["bufferViews"]
    assert all(view["byteOffset"] % 4 == 0 for view in views) and gltf["buffers"][0]["byteLength"] == len(binary)
    assert binary[views[2]["byteOffset"]:views[2]["byteOffset"] + views[2]["byteLength"]] == extra  # 정점 등 다른 자료는 그대로
    assert binary[views[1]["byteOffset"]:views[1]["byteOffset"] + views[1]["byteLength"]] == small_png()  # 작은 그림은 그대로
    first = character._image_bytes(gltf, binary, 0)[0]
    with image_module.open(io.BytesIO(first)) as picture:
        picture = picture.convert("RGBA")
        assert picture.size == (128, 64) and picture.getpixel((0, 0))[3] == 0
        red, green, _, alpha = picture.getpixel((64, 32))
        assert alpha == 255 and abs(red - 200) <= 3 and green > 120  # 가운데 색이 어두워지지 않음
    assert character.shrink_vrm(path, max_size=1024) == (b"", [])  # 줄일 그림 없음


def test_lighten_registers_a_copy_and_respects_permission(tmp_path):
    pytest.importorskip("PIL.Image")
    allowed = character.add(vrm_file(tmp_path / "ok.vrm", vrm1(preset=("aa", "blink"), modification="allowModification"), [_picture(256, 256)]))
    made, report = character.lighten(allowed.id, max_size=64)
    assert made.kind == "vrm" and made.name == f"{allowed.name} 가벼운 사본" and made.license == allowed.license and made.author == "작가"
    assert made.warnings[0].startswith("원본(점검 모델)의 텍스처를 64px") and report["after"] < report["before"] and len(report["images"]) == 1
    saved = character.get(made.id)
    assert saved is not None and character.file_path(saved, "ok.vrm").stat().st_size == report["after"]
    prohibited = character.add(vrm_file(tmp_path / "no.vrm", vrm1(preset=("aa", "blink")), [_picture(256, 256)]))
    with pytest.raises(character.CharacterError, match="수정을 허용하지 않음"):
        character.lighten(prohibited.id, max_size=64)
    with pytest.raises(character.CharacterError, match="등록한 VRM"):
        character.lighten(character.SAMPLE_ID)


def test_rendered_pngtuber_keeps_license_warnings_only(tmp_path):
    source = character.add(vrm_file(tmp_path / "plain.vrm", vrm1(commercialUsage="personalNonProfit")))
    assert any(text.startswith("입 모양 표정") for text in source.warnings) and "수익 방송(후원, 광고) 불가" in source.warnings
    pictures = {}
    for state in character.PNG_STATES:
        pictures[state] = tmp_path / f"{state}.png"
        pictures[state].write_bytes(small_png())
    made = character.add_rendered(source, pictures)
    assert "수익 방송(후원, 광고) 불가" in made.warnings and not any(text.startswith(("입 모양 표정", "눈 깜빡임 표정")) for text in made.warnings)


@pytest.fixture
def server():
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def request(srv, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = json.loads(response.read())
    conn.close()
    return response.status, data


def test_check_and_lighten_over_http(server, tmp_path):
    pytest.importorskip("PIL.Image")
    added = character.add(vrm_file(tmp_path / "web.vrm", vrm1(preset=("aa", "blinkLeft", "blinkRight", "happy"), modification="allowModification"),
                                   [_picture(256, 128)]))
    status, data = request(server, "GET", f"/character/sheet/check?id={quote(added.id)}")
    assert status == 200 and data["blink"] == "sides" and data["emotions"] == ["happy"] and data["modification"] is True
    assert data["textures"]["largest"] == 256 and data["light"] == character.LIGHT_TEXTURE and data["size"] > 0
    status, data = request(server, "POST", "/character/lighten", {"id": added.id})
    assert status == 400 and "줄일 텍스처 없음" in data["error"]  # 1024px 이하라 줄일 것이 없음
    status, data = request(server, "GET", "/character/sheet/check?id=debutkit")
    assert status == 400 and "VRM 캐릭터" in data["error"]


def test_pages_use_side_blinks_when_there_is_no_both_eyes_blink():
    overlay = (STATIC / "character.js").read_text(encoding="utf-8")
    sheet = (STATIC / "character-sheet.js").read_text(encoding="utf-8")
    assert "blinkSides" in overlay and "blinkBoth" in overlay  # 캐릭터 화면: 좌우 표정만 있는 모델도 깜빡임
    assert 'name === "blink" && manager.getExpression("blinkLeft")' in sheet  # 표정 시트의 눈 감음
    # VRM 0.x는 팔 회전 부호가 반대(VRoid 샘플에서 팔이 올라가던 문제), 얼굴 틀은 머리 크기에 맞춤(큰 머리 로우폴리)
    assert 'metaVersion === "0" ? -1 : 1' in sheet and "target.rotation.set(x * flip, y, z * flip)" in sheet and "function headSize()" in sheet
    assert "/character/sheet/check" in sheet and "/character/lighten" in sheet and "innerHTML" not in sheet


def test_pose_maker_parts_presets_random_and_png():
    """포즈 그림(미타포즈와 같은 쓰임): 부위별 자세(몸, 머리, 왼팔, 오른팔, 다리), 추천 자세, 잠금과 랜덤, 표정과 각도, 투명 PNG."""
    import re

    sheet = (STATIC / "character-sheet.js").read_text(encoding="utf-8")
    page = (STATIC / "character-sheet.html").read_text(encoding="utf-8")
    parts = re.search(r"const PARTS = \{(.*?)\n\};", sheet, re.S).group(1)
    for part in ("body:", "head:", "leftArm:", "rightArm: { name: \"오른팔\", options: mirrorArm(LEFT_ARM) }", "legs:"):
        assert part in parts, part
    for preset in ("relaxed:", "wave:", "hip:", "cheer:", "a:"):
        assert preset in sheet.split("const PRESETS = {")[1].split("};")[0], preset
    assert "if (locks[part]) continue;" in sheet and 'toDataURL("image/png")' in sheet and "renderPose(1024, 1536" in sheet
    for element in ('id="pose-shot"', 'id="parts"', 'id="random"', 'id="pose-face"', 'id="pose-angle"', 'id="pose-bg"', 'id="save-pose"'):
        assert element in page, element


def test_pose_maker_joints_pose_files_and_saved_poses():
    """미타포즈 수준: 관절 직접 돌리기, 자세 파일(VRMA 원하는 시점, MMD VPD), 내 자세 저장. 파일은 브라우저 안에서만 읽음."""
    sheet = (STATIC / "character-sheet.js").read_text(encoding="utf-8")
    page = (STATIC / "character-sheet.html").read_text(encoding="utf-8")
    for element in ('id="joint-bone"', 'id="joint-x"', 'id="joint-y"', 'id="joint-z"', 'id="joint-reset-all"', 'id="pose-file"', 'accept=".vrma,.vpd,.json"',
                    'id="vrma-time"', 'id="vpd-arm"', 'id="pose-file-off"', 'id="my-pose-name"', 'id="my-pose-save"', 'id="my-poses"',
                    'id="my-pose-load"', 'id="my-pose-remove"'):
        assert element in page, element
    # 관절: 고른 자세 위에 더하고, 오른쪽은 거울(같은 값이면 양쪽이 같은 동작), 팔은 축 이름이 다름
    assert "target.quaternion.multiply(" in sheet and 'bone.startsWith("right") ? -1 : 1' in sheet and 'arm: ["비틀기", "앞뒤", "위아래"]' in sheet
    # VRMA: 동작을 잠깐 재생해 정규화 뼈 회전을 받음. 끝 시점이 0초로 돌아가지 않게 한 번만 재생
    assert "createVRMAnimationClip" in sheet and "THREE.LoopOnce" in sheet and "clampWhenFinished = true" in sheet
    # VPD: Shift_JIS, 전각 숫자, 왼손 좌표 -> 오른손(x, y 부호), MMD 팔 기준 각도 보정, 비틀기 뼈는 부모에 합침
    assert 'new TextDecoder("shift_jis")' in sheet and "0xFEE0" in sheet and "new THREE.Quaternion(-x, -y, z, w)" in sheet
    for name in ('"上半身2": "chest"', '"首": "neck"', '"頭": "head"', '"腕": "UpperArm"', '"ひじ": "LowerArm"', '"手首": "Hand"', '"足": "UpperLeg"',
                 '"ひざ": "LowerLeg"', '"足首": "Foot"', '"親指0": "ThumbMetacarpal"', '"小指3": "LittleDistal"', "腕捩", "手捩", "下半身", "センター"):
        assert name in sheet, name
    assert "back.clone().multiply(rotation).multiply(rest)" in sheet  # 아래팔, 손, 손가락은 MMD 팔 기준으로 바꿔 계산
    # 저장: 이 PC 서버(/character/poses). 추천 자세나 부위를 고르면 파일 자세는 꺼짐
    assert '"/character/poses"' in sheet and '"/character/poses/remove"' in sheet and sheet.count("dropFilePose();") >= 6
    assert "innerHTML" not in sheet and "https://" not in sheet


def test_pose_maker_sends_the_pose_over_vmc():
    """VMC로 자세 보내기: 지금 자세의 정규화 뼈를 서버(/vmc/pose)로, 자세가 바뀌면 바로, 5초마다 계속 알림, 화면을 닫으면 멈춤."""
    sheet = (STATIC / "character-sheet.js").read_text(encoding="utf-8")
    page = (STATIC / "character-sheet.html").read_text(encoding="utf-8")
    for element in ('id="vmc-host"', 'id="vmc-port"', 'id="vmc-face"', 'id="vmc-send"', 'id="vmc-state"', 'href="/vmc"'):
        assert element in page, element
    assert '"/vmc/pose"' in sheet and '"/vmc/pose/stop"' in sheet and "keepalive: true" in sheet and "setInterval(vmcSend, 5000)" in sheet
    assert "if (vmcOn) vmcSend();" in sheet  # 다시 그릴 때(부위, 관절, 자세 파일, 표정) 같이 보냄
    assert "[q.x * flip, q.y, q.z * flip, q.w, p.x * flip, p.y, p.z * flip]" in sheet  # VRM 0.x도 VRM 1.0 방향으로


def test_pose_parts_hands_presets_and_helpers():
    """포즈 3차: 부위 8개(허리, 상체, 머리, 팔, 손, 다리), 손 모양 8종, 추천 자세 10종이 모두 있는 선택지, 예시 그림, 자세 보정, 자세 JSON."""
    import re

    sheet = (STATIC / "character-sheet.js").read_text(encoding="utf-8")
    page = (STATIC / "character-sheet.html").read_text(encoding="utf-8")

    def keys(start, end="\n};"):
        block = sheet.split(start, 1)[1].split(end, 1)[0]
        return re.findall(r"^  (\w+): \{ name:", block, re.M)

    options = {"leftArm": keys("const LEFT_ARM = {"), "leftHand": keys("const LEFT_HAND = {")}
    options["rightArm"], options["rightHand"] = options["leftArm"], options["leftHand"]
    for part in ("body", "upper", "head", "legs"):
        block = sheet.split(f"  {part}: {{ name:", 1)[1].split("\n  } },", 1)[0]
        options[part] = re.findall(r"^    (\w+): \{ name:", block, re.M)
    assert len(options["leftArm"]) == 14 and len(options["leftHand"]) == 8 and len(options["upper"]) == 8
    assert len(options["head"]) == 9 and len(options["body"]) == 7 and len(options["legs"]) == 8
    assert sum(len(found) for found in options.values()) == 7 + 8 + 9 + 14 * 2 + 8 * 2 + 8  # 부위별 선택지 76개
    base = dict(re.findall(r'(\w+): "(\w+)"', sheet.split("const BASE = {", 1)[1].split("};", 1)[0]))
    presets = sheet.split("const PRESETS = {", 1)[1].split("\n};", 1)[0]
    found = re.findall(r"^  (\w+): \{ name: \"[^\"]+\", parts: \{ \.\.\.BASE, (.*?) \} \},", presets, re.M | re.S)
    assert len(found) == 10
    for name, body in found:
        chosen = {**base, **dict(re.findall(r'(\w+): "(\w+)"', body))}
        assert set(chosen) == set(options), name  # 모든 부위를 정함
        for part, key in chosen.items():
            assert key in options[part], (name, part, key)
    # 손가락 뼈 이름은 VRM 사람 모양 뼈(ALL_BONES가 만드는 이름)
    for finger in ("Thumb", "Index", "Middle", "Ring", "Little"):
        assert f'curl("{finger}"' in sheet or finger == "Thumb"
    assert "leftThumbMetacarpal: [0, a[0], a[1]]" in sheet and "[`left${finger}Proximal`]" in sheet
    # 예시 그림(손은 손을 들어 가까이), 자세 보정, 자세 JSON, 그리는 뼈 자리와 잘림 방지
    for code in ("function renderOption(", "function showGallery(", "function fixArms()", "function insideTorso(", "function poseJson()",
                 "function readPoseJson(", 'poseState[arm] = "wave"', "humanoid.getRawBoneNode(name)", "object.frustumCulled = false"):
        assert code in sheet, code
    for element in ('id="part-gallery"', 'id="gallery-items"', 'id="fix-arms"', 'id="pose-json"', 'accept=".vrma,.vpd,.json"'):
        assert element in page, element
    assert "debugBones" not in sheet and "handZoom" not in sheet  # 확인용 도구는 남기지 않음
