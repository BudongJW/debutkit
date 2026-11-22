"""캐릭터 등록과 확인: 테스트용 파일을 코드로 만들어 확인한다(외부 모델 파일 없음)."""

import json
import struct
import zipfile
import zlib

import pytest

from debutkit import character, settings


def png(path, width=64, height=64, alpha=True):
    """최소 PNG(한 가지 색)."""
    color = 6 if alpha else 2
    channels = 4 if alpha else 3

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x80" * (width * channels) for _ in range(height))
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    path.write_bytes(data)
    return path


def glb(path, extensions, thumbnail=b""):
    gltf = {"asset": {"version": "2.0"}, "extensions": extensions}
    binary = b""
    if thumbnail:
        gltf["bufferViews"] = [{"buffer": 0, "byteOffset": 0, "byteLength": len(thumbnail)}]
        gltf["images"] = [{"bufferView": 0, "mimeType": "image/png"}]
        gltf["buffers"] = [{"byteLength": len(thumbnail)}]
        binary = thumbnail + b"\x00" * (-len(thumbnail) % 4)
    body = json.dumps(gltf).encode()
    body += b" " * (-len(body) % 4)
    chunks = struct.pack("<I4s", len(body), b"JSON") + body
    if binary:
        chunks += struct.pack("<I4s", len(binary), b"BIN\x00") + binary
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks)
    return path


def vrm1(path, **meta):
    base = {"name": "테스트 캐릭터", "authors": ["작가"], "licenseUrl": "https://vrm.dev/licenses/1.0/", "thumbnailImage": 0}
    return glb(path, {"VRMC_vrm": {"specVersion": "1.0", "meta": {**base, **meta}}}, thumbnail=png(path.with_suffix(".thumb"), 8, 8).read_bytes())


def live2d(folder, physics=True):
    folder.mkdir(parents=True)
    (folder / "hiyori.moc3").write_bytes(b"MOC3\x05" + b"\x00" * 60)
    png(folder / "texture_00.png")
    refs = {"Moc": "hiyori.moc3", "Textures": ["texture_00.png"]}
    if physics:
        (folder / "hiyori.physics3.json").write_text("{}", encoding="utf-8")
        refs["Physics"] = "hiyori.physics3.json"
    (folder / "hiyori.model3.json").write_text(json.dumps({"Version": 3, "FileReferences": refs}), encoding="utf-8")
    return folder


def test_vrm1_details_license_and_thumbnail(tmp_path):
    found = character.inspect(vrm1(tmp_path / "a.vrm", commercialUsage="personalProfit", avatarPermission="everyone"))
    assert found.kind == "vrm" and found.name == "테스트 캐릭터" and found.author == "작가" and found.version == "VRM 1.0"
    assert "상업적 이용: 개인 영리 가능" in found.license
    assert found.warnings == ["법인(소속사) 사용 불가. 개인 수익 방송은 가능"]
    added = character.add(tmp_path / "a.vrm")
    folder = character.library_dir() / added.id
    assert (folder / "a.vrm").is_file() and added.thumbnail == "thumbnail.png" and (folder / "thumbnail.png").read_bytes().startswith(b"\x89PNG")


def test_vrm_defaults_are_restrictive_and_vrm0_is_read(tmp_path):
    strict = character.inspect(glb(tmp_path / "b.vrm", {"VRMC_vrm": {"specVersion": "1.0", "meta": {"name": "b", "authors": []}}}))
    assert any("수익 방송" in warning for warning in strict.warnings) and any("제작자가 정한 사람" in warning for warning in strict.warnings)
    old = character.inspect(glb(tmp_path / "c.vrm", {"VRM": {"meta": {"title": "옛 모델", "author": "x", "allowedUserName": "Everyone",
                                                                      "commercialUssageName": "Allow", "licenseName": "CC_BY"}}}))
    assert old.version == "VRM 0.x" and old.name == "옛 모델" and "라이선스: CC_BY" in old.license
    with pytest.raises(character.CharacterError, match="VRM 정보"):
        character.inspect(glb(tmp_path / "plain.vrm", {}))
    (tmp_path / "bad.vrm").write_bytes(b"nope")
    with pytest.raises(character.CharacterError, match="glTF"):
        character.inspect(tmp_path / "bad.vrm")


def test_live2d_folder_and_zip(tmp_path):
    model = live2d(tmp_path / "src" / "hiyori", physics=False)
    found = character.inspect(tmp_path / "src")
    assert found.kind == "live2d" and found.name == "hiyori" and any("physics3.json" in warning for warning in found.warnings)
    archive = tmp_path / "hiyori.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for file in model.iterdir():
            bundle.write(file, f"hiyori/{file.name}")
    added = character.add(archive, name="히요리")
    assert added.id and added.files == {"model": "hiyori.model3.json"}
    assert (character.library_dir() / added.id / "hiyori.moc3").is_file()
    (model / "texture_00.png").unlink()
    with pytest.raises(character.CharacterError, match="texture_00.png"):
        character.inspect(model / "hiyori.model3.json")


def test_zip_with_parent_paths_is_refused(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "x")
    with pytest.raises(character.CharacterError, match="허용하지 않는 경로"):
        character.inspect(archive)


def test_png_character_checks_and_library(tmp_path):
    idle, talk = png(tmp_path / "a.png"), png(tmp_path / "b.png", 80, 64, alpha=False)
    added = character.add_png(idle, talk, name="My PNG")
    assert added.kind == "png" and added.files == {"idle": "idle.png", "talk": "talk.png"} and added.id == "my-png"
    assert any("투명 배경 없음" in warning for warning in added.warnings) and any("크기가 다름" in warning for warning in added.warnings)
    with pytest.raises(character.CharacterError, match="입 벌린 이미지"):
        character.png_character(idle, None)
    assert [item.id for item in character.all_characters()] == ["debutkit", "my-png"]
    assert character.add_png(idle, talk, name="My PNG").id == "my-png-2"


def test_use_active_files_and_remove(tmp_path):
    assert character.active().id == character.SAMPLE_ID and character.active().renders_in_overlay
    added = character.add_png(png(tmp_path / "a.png"), png(tmp_path / "b.png"), name="mine")
    character.use(added.id)
    assert settings.load()["character"] == added.id and character.active().id == added.id
    assert character.file_path(added, "idle.png").is_file()
    assert character.file_path(added, "../../settings.json") is None and character.file_path(added, "character.json") is None
    sample = character.sample()
    assert all(character.file_path(sample, name) for name in sample.files.values())  # 기본 캐릭터 파일이 패키지에 있음
    assert character.remove(added.id) and character.active().id == character.SAMPLE_ID
    with pytest.raises(character.CharacterError):
        character.remove(character.SAMPLE_ID)


def test_inochi2d_header(tmp_path):
    good = tmp_path / "a.inp"
    good.write_bytes(b"TRNSRTS\x00" + b"\x00" * 8)
    assert character.inspect(good).kind == "inochi2d"
    bad = tmp_path / "b.inp"
    bad.write_bytes(b"nope")
    with pytest.raises(character.CharacterError, match="Inochi2D"):
        character.inspect(bad)


def test_send_to_vts_and_warudo(tmp_path):
    from debutkit import cli

    steam = tmp_path / "steam"
    other = tmp_path / "games"
    (steam / "steamapps").mkdir(parents=True)
    (steam / "steamapps" / "libraryfolders.vdf").write_text('"libraryfolders" { "1" { "path" "' + str(other).replace("\\", "\\\\") + '" } }', encoding="utf-8")
    vts = other / "steamapps/common/VTube Studio/VTube Studio_Data/StreamingAssets/Live2DModels"
    vts.mkdir(parents=True)
    assert character.steam_libraries(str(steam)) == [steam, other]
    assert character.app_folder("vts", [steam, other]) == vts
    model = character.add(live2d(tmp_path / "src" / "hiyori"))
    target = character.send(model, "vts", libraries=[steam, other])
    assert target == vts / model.id and (target / "hiyori.model3.json").is_file() and not (target / "character.json").exists()
    with pytest.raises(character.CharacterError, match="Live2D 캐릭터만"):
        character.send(character.sample(), "vts", folder=vts)
    vrm = character.add(vrm1(tmp_path / "w.vrm"))
    assert vrm.id == "테스트-캐릭터"  # 한글 이름 유지
    with pytest.raises(character.CharacterError, match="모델 폴더를 찾지 못함"):
        character.send(vrm, "warudo", libraries=[steam])
    warudo = tmp_path / "warudo-models"
    warudo.mkdir()
    assert cli.main(["character", "send", vrm.id, "--to", "warudo", "--folder", str(warudo)]) == 0 and (warudo / "w.vrm").is_file()


def test_character_cli(tmp_path, capsys):
    from debutkit import cli

    assert cli.main(["character", "png", "--idle", str(png(tmp_path / "a.png")), "--talk", str(png(tmp_path / "b.png")), "--name", "Neko"]) == 0
    assert cli.main(["character", "use", "neko"]) == 0 and "/character" in capsys.readouterr().out
    assert cli.main(["character", "list"]) == 0
    out = capsys.readouterr().out
    assert "* neko" in out and "debutkit" in out
    assert cli.main(["character", "add", str(vrm1(tmp_path / "x.vrm")), "--name", "X Model"]) == 0
    assert cli.main(["character", "show", "x-model"]) == 0
    out = capsys.readouterr().out
    assert "사용 조건: 아바타 사용 허용 대상: 제작자 본인" in out and "확인 필요: 수익 방송" in out
    assert cli.main(["character", "show", "nobody"]) == 1
    assert cli.main(["character", "add", str(tmp_path / "missing.vrm")]) == 1 and "캐릭터 작업 실패" in capsys.readouterr().err
    assert cli.main(["character", "remove", "neko"]) == 0 and character.active().id == character.SAMPLE_ID
