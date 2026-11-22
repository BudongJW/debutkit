# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: 라이브러리를 공유하는 프로그램 두 개를 한 폴더에(Windows, macOS, Linux).

    debutkit-gui   설정 마법사 (콘솔 창 없음)
    debutkit       명령줄 (doctor, scenes, overlay, setup, chzzk)

macOS에서는 debutkit.app 묶음도 만든다(두 프로그램 모두 Contents/MacOS 안).
packaging/build_app.py(모든 운영체제) 또는 packaging/build_windows.py(설치 프로그램 포함)로 실행한다.
"""

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
sys.path.insert(0, SPECPATH)
from build_app import unused  # noqa: E402

VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "src" / "debutkit" / "__init__.py").read_text(encoding="utf-8")).group(1)

# 쓰지 않는 Qt 모듈을 빼서 용량을 줄인다
excludes = [
    "tkinter", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtNetwork", "PySide6.QtSql", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtDesigner",
    "faster_whisper", "ctranslate2", "onnxruntime", "yt_dlp",
    "PIL._avif",  # AVIF 이미지 미사용. Pillow는 모듈이 없으면 AVIF만 비활성화
]

# 메타데이터: doctor가 채팅 연결 모듈 버전을 importlib.metadata로 읽는다
datas = collect_data_files("debutkit") + collect_data_files("stream2clip") + copy_metadata("stream2clip") + copy_metadata("debutkit")
hiddenimports = collect_submodules("debutkit") + ["stream2clip.live", "stream2clip.chzzk_api", "stream2clip.vrm", "stream2clip.obs",
                                                  "stream2clip.tools", "stream2clip.ffmpeg", "stream2clip.export", "websocket",
                                                  "grpc", "google.protobuf.descriptor_pb2", "google.protobuf.json_format", "google.protobuf.message_factory"]

if sys.platform == "win32":
    icon = str(ROOT / "assets" / "brand" / "app-icon" / "debutkit.ico")  # packaging/build_brand.py 로 생성
else:
    icon = str(ROOT / "assets" / "brand" / "app-icon" / "app-icon_dark_rounded.png")  # macOS는 PyInstaller가 icns로 변환(Pillow 필요)


def analysis(script):
    result = Analysis([str(ROOT / "packaging" / script)], pathex=[str(ROOT / "src")], datas=datas, hiddenimports=hiddenimports, excludes=excludes)
    result.binaries = [entry for entry in result.binaries if not unused(entry[0])]
    result.datas = [entry for entry in result.datas if not unused(entry[0])]
    return result


gui = analysis("entry_gui.py")
cli = analysis("entry_cli.py")
gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="debutkit-gui", console=False, icon=icon)
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="debutkit", console=True, icon=icon)
folder = COLLECT(gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas, name="debutkit")

if sys.platform == "darwin":
    BUNDLE(folder, name="debutkit.app", icon=icon, bundle_identifier="io.github.budongjw.debutkit",
           info_plist={"CFBundleName": "debutkit", "CFBundleDisplayName": "debutkit", "CFBundleShortVersionString": VERSION,
                       "CFBundleVersion": VERSION, "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "11.0"})
