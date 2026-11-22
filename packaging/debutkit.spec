# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: 라이브러리를 공유하는 프로그램 두 개를 한 폴더에.

    debutkit-gui.exe   설정 마법사 (콘솔 창 없음)
    debutkit.exe       명령줄 (doctor, scenes, overlay)

packaging/build_windows.py 로 실행한다.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent

# 쓰지 않는 Qt 모듈을 빼서 용량을 줄인다 (stream2clip과 같은 목록)
excludes = [
    "tkinter", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtNetwork", "PySide6.QtSql", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtDesigner",
    "faster_whisper", "ctranslate2", "onnxruntime", "yt_dlp",
]

# 메타데이터: doctor가 stream2clip 버전을 importlib.metadata로 읽는다
datas = collect_data_files("debutkit") + collect_data_files("stream2clip") + copy_metadata("stream2clip") + copy_metadata("debutkit")
hiddenimports = collect_submodules("debutkit") + ["stream2clip.live", "stream2clip.chzzk_api", "stream2clip.vrm", "stream2clip.obs", "stream2clip.gui.theme",
                                                  "stream2clip.tools", "stream2clip.ffmpeg", "stream2clip.export", "websocket"]


def analysis(script):
    return Analysis([str(ROOT / "packaging" / script)], pathex=[str(ROOT / "src")], datas=datas, hiddenimports=hiddenimports, excludes=excludes)


gui = analysis("entry_gui.py")
cli = analysis("entry_cli.py")
icon = str(ROOT / "assets" / "brand" / "app-icon" / "debutkit.ico")  # packaging/build_brand.py 로 생성
gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="debutkit-gui", console=False, icon=icon)
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="debutkit", console=True, icon=icon)
COLLECT(gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas, name="debutkit")
