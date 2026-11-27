"""설정 마법사의 방송 시작 버튼 편집 창: 세팅, 켤 것과 끌 것(끌어다 놓기), 옵션, 창 위치 기억, 보호 목록, 백업."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import launcher

OPTIONS = (("skip_running", "이미 켜진 프로그램은 건너뛰기"), ("place_running", "이미 켜진 프로그램 창도 기억한 자리로 옮기기"),
           ("watch", "꺼 둔 프로그램이 다시 켜지면 알림"), ("rekill", "다시 켜지면 다시 끄기"), ("restore", "방송 끝에 꺼 둔 프로그램 다시 켜기"),
           ("overlay", "켠 뒤 오버레이 시작(채팅과 알림 단계 설정)"), ("obs_check", "켠 뒤 OBS 연결 확인"))


class DropList(QListWidget):
    """파일, 바로가기, 폴더, 사이트 주소를 끌어다 놓는 목록. 놓은 값은 ``dropped`` 함수로 넘긴다."""

    def __init__(self, dropped: Callable[[list[str]], None]) -> None:
        super().__init__()
        self.dropped = dropped
        self.setObjectName("Launch")  # 설정 마법사 스타일(캐릭터 목록과 같은 모양)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.setMinimumHeight(170)

    def _values(self, event: Any) -> list[str]:
        data = event.mimeData()
        if data.hasUrls():
            return [url.toLocalFile() or url.toString() for url in data.urls()]
        if data.hasText():
            return [line.strip() for line in data.text().splitlines() if line.strip()]
        return []

    def dragEnterEvent(self, event: Any) -> None:  # noqa: N802
        if self._values(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event: Any) -> None:  # noqa: N802
        if self._values(event):
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:  # noqa: N802
        values = self._values(event)
        if values:
            event.acceptProposedAction()
            self.dropped(values)


class LaunchDialog(QDialog):
    """세팅을 고치고 저장한다. ``processes`` 는 실행 중인 프로그램 목록(끌 것 고르기), ``resolve`` 는 바로가기 대상 풀기."""

    def __init__(self, parent: QWidget | None = None, *, load: Callable[[], launcher.Config] = launcher.load,
                 save: Callable[[launcher.Config], Any] = launcher.save, remember: Callable[..., list[launcher.Step]] = launcher.remember_windows,
                 processes: Callable[[], list[launcher.Proc]] | None = None, resolve: Callable[[str], str | None] = launcher.resolve_shortcut) -> None:
        super().__init__(parent)
        self.setWindowTitle("방송 시작 버튼 세팅")
        self.resize(860, 620)
        self._save, self._remember, self._resolve = save, remember, resolve
        self._processes = processes or (lambda: launcher.default_system().processes())
        self.config = load()
        self.current = self.config.active
        layout = QVBoxLayout(self)

        self.profiles = QComboBox()
        self.profiles.currentTextChanged.connect(self._switch)
        new, copy, rename, delete = (QPushButton(label) for label in ("새 세팅", "복제", "이름 바꾸기", "삭제"))
        new.clicked.connect(self.new_profile)
        copy.clicked.connect(self.copy_profile)
        rename.clicked.connect(self.rename_profile)
        delete.clicked.connect(self.delete_profile)
        top = QHBoxLayout()
        top.addWidget(QLabel("세팅"))
        top.addWidget(self.profiles, 1)
        for button in (new, copy, rename, delete):
            top.addWidget(button)
        layout.addLayout(top)
        hint = QLabel("프로그램, 바로가기, 폴더, 사이트 주소를 목록에 끌어다 놓습니다. 켜기를 누르면 끌 것을 먼저 끄고 켤 것을 위에서부터 차례로 켭니다.")
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        layout.addWidget(hint)

        grid = QGridLayout()
        self.start_list = DropList(self.add_start)
        self.stop_list = DropList(self.add_stop)
        self.start_list.currentRowChanged.connect(self._select_item)
        grid.addWidget(QLabel("켤 것"), 0, 0)
        grid.addWidget(QLabel("끌 것(방송에 방해되는 프로그램)"), 0, 1)
        grid.addWidget(self.start_list, 1, 0)
        grid.addWidget(self.stop_list, 1, 1)
        add_file, add_folder, add_site, up, down, remove_start = (QPushButton(label) for label in ("파일", "폴더", "사이트", "위로", "아래로", "빼기"))
        add_file.clicked.connect(self.pick_files)
        add_folder.clicked.connect(self.pick_folder)
        add_site.clicked.connect(self.ask_site)
        up.clicked.connect(lambda: self.move(-1))
        down.clicked.connect(lambda: self.move(1))
        remove_start.clicked.connect(self.remove_start)
        self.delay = QDoubleSpinBox()
        self.delay.setRange(*launcher.DELAY)
        self.delay.setDecimals(1)
        self.delay.setSingleStep(0.5)
        self.delay.setSuffix("초 뒤 다음")
        self.delay.setToolTip("이 항목을 켠 뒤 다음 항목까지 기다리는 시간. 무거운 프로그램은 넉넉하게")
        self.delay.valueChanged.connect(self._set_delay)
        grid.addWidget(self._buttons(add_file, add_folder, add_site, up, down, remove_start, self.delay), 2, 0)
        from_running, by_name, remove_stop = (QPushButton(label) for label in ("켜진 프로그램에서", "이름 입력", "빼기"))
        from_running.clicked.connect(self.pick_running)
        by_name.clicked.connect(self.ask_stop)
        remove_stop.clicked.connect(self.remove_stop)
        grid.addWidget(self._buttons(from_running, by_name, remove_stop), 2, 1)
        layout.addLayout(grid, 1)

        self.checks: dict[str, QCheckBox] = {}
        options = QGridLayout()
        for index, (key, label) in enumerate(OPTIONS):
            box = QCheckBox(label)
            box.toggled.connect(lambda on, key=key: self._set_flag(key, on))
            self.checks[key] = box
            options.addWidget(box, index // 2, index % 2)
        layout.addLayout(options)

        remember, protect, export, restore = (QPushButton(label) for label in ("지금 창 위치 기억", "보호 목록", "백업 저장", "백업 불러오기"))
        remember.setToolTip("켤 것이 지금 켜져 있는 창의 자리와 크기(최대화, 모니터 포함)를 기억합니다. Windows")
        remember.clicked.connect(self.remember_windows)
        protect.clicked.connect(self.edit_protect)
        export.clicked.connect(self.export_backup)
        restore.clicked.connect(self.import_backup)
        save_button = QPushButton("저장")
        save_button.setObjectName("Primary")
        save_button.clicked.connect(self.save_and_close)
        close = QPushButton("닫기")
        close.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        for button in (remember, protect, export, restore):
            bottom.addWidget(button)
        bottom.addStretch(1)
        bottom.addWidget(close)
        bottom.addWidget(save_button)
        layout.addLayout(bottom)
        self.state = QLabel("")
        self.state.setObjectName("Muted")
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        self._fill_profiles()

    @staticmethod
    def _buttons(*widgets: QWidget) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        for widget in widgets:
            row.addWidget(widget)
        row.addStretch(1)
        return box

    # ------------------------------------------------------------------ 세팅
    @property
    def profile(self) -> launcher.Profile:
        return self.config.profile(self.current)

    def _fill_profiles(self) -> None:
        self.profiles.blockSignals(True)
        self.profiles.clear()
        self.profiles.addItems([profile.name for profile in self.config.profiles])
        self.profiles.setCurrentText(self.current)
        self.profiles.blockSignals(False)
        self._show()

    def _switch(self, name: str) -> None:
        if name:
            self.current = name
            self._show()

    def _show(self) -> None:
        profile = self.profile
        self.start_list.clear()
        for item in profile.start:
            place = "  [창 위치]" if item.window else ""
            entry = QListWidgetItem(f"{item.label}  ({launcher.KINDS[item.kind]}, {item.delay:g}초){place}")
            entry.setToolTip(item.target)
            self.start_list.addItem(entry)
        self.stop_list.clear()
        self.stop_list.addItems(profile.stop)
        for key, box in self.checks.items():
            box.blockSignals(True)
            box.setChecked(bool(getattr(profile, key)))
            box.blockSignals(False)
        self.checks["rekill"].setEnabled(profile.watch)
        self.delay.setEnabled(False)

    def _ask(self, title: str, label: str, value: str = "") -> str | None:
        text, accepted = QInputDialog.getText(self, title, label, text=value)
        return text.strip() if accepted and text.strip() else None

    def _apply(self, change: Callable[[], Any], message: str = "") -> bool:
        try:
            change()
        except launcher.LauncherError as error:
            self.state.setText(str(error))
            return False
        self.state.setText(message)
        return True

    def new_profile(self) -> None:
        name = self._ask("새 세팅", "세팅 이름(예: 게임, 작업, 노래 방송)")
        if not name:
            return
        if name in [profile.name for profile in self.config.profiles]:
            self.state.setText(f"같은 이름의 세팅이 있음: {name}")
            return
        if self._apply(lambda: launcher.put_profile(self.config, {"name": name}), f"세팅 추가: {name}"):
            self.current = name
            self._fill_profiles()

    def copy_profile(self) -> None:
        name = self._ask("세팅 복제", "새 세팅 이름", f"{self.current} 복사")
        if name and self._apply(lambda: launcher.copy_profile(self.config, self.current, name), f"세팅 복제: {name}"):
            self.current = name
            self._fill_profiles()

    def rename_profile(self) -> None:
        name = self._ask("이름 바꾸기", "새 이름", self.current)
        if name and name != self.current:
            data = {**launcher.profile_dict(self.profile), "name": name}
            if self._apply(lambda: launcher.put_profile(self.config, data, old_name=self.current), f"이름 변경: {name}"):
                self.current = name
                self._fill_profiles()

    def delete_profile(self) -> None:
        name = self.current
        if self._apply(lambda: launcher.remove_profile(self.config, name), f"세팅 삭제: {name}"):
            self.current = self.config.active
            self._fill_profiles()

    # ------------------------------------------------------------------ 켤 것
    def add_start(self, values: list[str]) -> None:
        profile = self.profile
        added: list[str] = []
        notes: list[str] = []
        for value in values:
            try:
                item = launcher.check_item({"target": value})
            except launcher.LauncherError as error:
                notes.append(str(error))
                continue
            if len(profile.start) >= launcher.MAX_ITEMS:
                notes.append(f"켤 것은 {launcher.MAX_ITEMS}개까지")
                break
            profile.start.append(item)
            added.append(item.label)
        self._show()
        self.state.setText(". ".join(([f"추가: {', '.join(added)}"] if added else []) + notes))

    def pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "켤 프로그램, 바로가기, 파일", "", "프로그램과 바로가기 (*.exe *.lnk *.url *.bat);;모든 파일 (*)")
        if paths:
            self.add_start(paths)

    def pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "켤 폴더")
        if path:
            self.add_start([path])

    def ask_site(self) -> None:
        url = self._ask("사이트 추가", "주소(https://로 시작). 브라우저 새 창으로 엽니다", "https://")
        if url and url != "https://":
            self.add_start([url])

    def move(self, step: int) -> None:
        row = self.start_list.currentRow()
        items = self.profile.start
        if 0 <= row < len(items) and 0 <= row + step < len(items):
            items[row], items[row + step] = items[row + step], items[row]
            self._show()
            self.start_list.setCurrentRow(row + step)

    def remove_start(self) -> None:
        row = self.start_list.currentRow()
        if 0 <= row < len(self.profile.start):
            removed = self.profile.start.pop(row)
            self._show()
            self.state.setText(f"뺌: {removed.label}")

    def _select_item(self, row: int) -> None:
        items = self.profile.start
        self.delay.setEnabled(0 <= row < len(items))
        if 0 <= row < len(items):
            self.delay.blockSignals(True)
            self.delay.setValue(items[row].delay)
            self.delay.blockSignals(False)

    def _set_delay(self, value: float) -> None:
        row = self.start_list.currentRow()
        if 0 <= row < len(self.profile.start):
            self.profile.start[row].delay = round(value, 1)
            entry = self.start_list.item(row)
            item = self.profile.start[row]
            entry.setText(f"{item.label}  ({launcher.KINDS[item.kind]}, {item.delay:g}초)" + ("  [창 위치]" if item.window else ""))

    # ------------------------------------------------------------------ 끌 것
    def add_stop(self, values: list[str]) -> None:
        profile = self.profile
        added: list[str] = []
        notes: list[str] = []
        for value in values:
            name = value
            if value.lower().endswith(".lnk"):  # 바로가기는 대상 프로그램 이름으로
                target = self._resolve(value)
                if not target:
                    notes.append(f"바로가기 대상을 알 수 없음: {Path(value).name}")
                    continue
                name = target
            name = Path(name).name if Path(name).suffix.lower() == ".exe" else name
            if launcher.blocked(name, self.config):
                notes.append(f"끌 수 없는 프로그램(운영체제, 보안, debutkit, 보호 목록): {name}")
                continue
            if launcher.process_key(name) in {launcher.process_key(existing) for existing in profile.stop}:
                continue
            if len(profile.stop) >= launcher.MAX_ITEMS:
                notes.append(f"끌 것은 {launcher.MAX_ITEMS}개까지")
                break
            profile.stop.append(name)
            added.append(name)
        self._show()
        self.state.setText(". ".join(([f"끌 것 추가: {', '.join(added)}"] if added else []) + notes))

    def pick_running(self) -> None:
        names = sorted({proc.name for proc in self._processes() if proc.name and not launcher.blocked(proc.name, self.config)}, key=str.casefold)
        if not names:
            self.state.setText("고를 수 있는 프로그램이 없음")
            return
        chosen, accepted = QInputDialog.getItem(self, "끌 프로그램", "지금 켜진 프로그램(운영체제, 보안 프로그램은 제외)", names, 0, False)
        if accepted and chosen:
            self.add_stop([chosen])

    def ask_stop(self) -> None:
        name = self._ask("끌 것 추가", "프로그램 이름(예: Discord.exe, KakaoTalk.exe)")
        if name:
            self.add_stop([name])

    def remove_stop(self) -> None:
        row = self.stop_list.currentRow()
        if 0 <= row < len(self.profile.stop):
            removed = self.profile.stop.pop(row)
            self._show()
            self.state.setText(f"뺌: {removed}")

    # ------------------------------------------------------------------ 옵션, 도구
    def _set_flag(self, key: str, on: bool) -> None:
        setattr(self.profile, key, on)
        self.checks["rekill"].setEnabled(self.profile.watch)

    def remember_windows(self) -> None:
        steps = self._remember(self.config, self.current)
        self._show()
        self.state.setText(launcher.summary(steps).replace("\n", ", "))

    def edit_protect(self) -> None:
        text, accepted = QInputDialog.getMultiLineText(self, "보호 목록", "끄지 않을 프로그램(한 줄에 하나). 운영체제, 보안 프로그램, debutkit은 항상 보호",
                                                       "\n".join(self.config.protect))
        if accepted:
            self.config.protect = [line.strip() for line in text.splitlines() if line.strip()][: launcher.MAX_ITEMS]
            self.state.setText(f"보호 목록 {len(self.config.protect)}개")

    def export_backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "백업 저장", "debutkit-방송시작버튼.json", "JSON (*.json)")
        if path:
            try:
                Path(path).write_text(launcher.export_text(self.config), encoding="utf-8")
            except OSError as error:
                self.state.setText(f"저장 실패: {error}")
                return
            self.state.setText(f"백업 저장: {path}")

    def import_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "백업 불러오기", "", "JSON (*.json)")
        if not path:
            return
        try:
            self.config = launcher.import_text(Path(path).read_text(encoding="utf-8"))
        except (OSError, launcher.LauncherError) as error:
            self.state.setText(f"불러오기 실패: {error}")
            return
        self.current = self.config.active
        self._fill_profiles()
        self.state.setText("백업을 불러왔습니다. 저장을 누르면 적용됩니다.")

    def save_and_close(self) -> None:
        self.config.active = self.current
        try:
            self._save(self.config)
        except OSError as error:
            self.state.setText(f"저장 실패: {error}")
            return
        self.accept()
