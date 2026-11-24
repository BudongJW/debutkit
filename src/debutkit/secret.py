"""비밀값 보관(스트림 키, 생성형 AI API 키): 이 PC의 이 사용자만 풀 수 있게 암호화.

- Windows: DPAPI(CryptProtectData)로 암호화해 설정 폴더의 JSON 파일에 저장
- 그 밖의 운영체제: keyring(macOS 키체인, 리눅스 Secret Service)이 설치되어 있으면 그곳에, 없으면 이번 실행 동안 메모리에만
- 값은 화면, 기록, 오류 문장에 표시하지 않는다
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Callable


class SecretUnavailable(RuntimeError):
    """이 운영체제에서는 암호화 저장을 할 수 없음."""


def dpapi(data: bytes, protect: bool, entropy: bytes) -> bytes:  # pragma: no cover - Windows 전용(테스트는 Windows에서만 실행)
    """Windows DPAPI 암호화(protect=True) 또는 해제. 같은 Windows 사용자만 풀 수 있다."""
    if sys.platform != "win32":
        raise SecretUnavailable("Windows에서만 지원")
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source_buffer = ctypes.create_string_buffer(data, len(data))
    entropy_buffer = ctypes.create_string_buffer(entropy, len(entropy))
    source = Blob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_char)))
    salt = Blob(len(entropy), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_char)))
    result = Blob()
    if not function(ctypes.byref(source), None, ctypes.byref(salt), None, None, 0x1, ctypes.byref(result)):  # CRYPTPROTECT_UI_FORBIDDEN
        raise OSError(ctypes.get_last_error(), "암호화 처리 실패")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


class KeyBox:
    """이름별 비밀값 상자. Windows는 DPAPI 파일, 다른 운영체제는 keyring 또는 메모리.

    ``protect``, ``unprotect`` 를 주면(시험용) 운영체제와 관계없이 그 함수로 파일에 저장한다.
    """

    def __init__(self, path: Path, entropy: bytes, service: str, *, platform: str | None = None,
                 protect: Callable[[bytes], bytes] | None = None, unprotect: Callable[[bytes], bytes] | None = None,
                 keyring_module: object | None = None) -> None:
        self.path, self.entropy, self.service = path, entropy, service
        self._platform = platform or sys.platform
        self._protect, self._unprotect = protect, unprotect
        self._memory: dict[str, str] = {}
        self._keyring = keyring_module if keyring_module is not None else self._find_keyring()

    def _find_keyring(self) -> object | None:
        if self._platform == "win32":
            return None
        try:
            import keyring  # type: ignore[import-not-found]
        except ImportError:
            return None
        return keyring

    @property
    def mode(self) -> str:
        """file(DPAPI 등 암호화 파일), keyring(운영체제 보관소), memory(저장 안 함)."""
        if self._protect is not None or self._platform == "win32":
            return "file"
        return "keyring" if self._keyring is not None else "memory"

    def _read(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {name: value for name, value in data.items() if isinstance(value, str)} if isinstance(data, dict) else {}

    def save(self, name: str, value: str) -> None:
        if self.mode == "memory":
            self._memory[name] = value
            return
        if self.mode == "keyring":
            self._keyring.set_password(self.service, name, value)  # type: ignore[attr-defined]
            return
        sealed = (self._protect or (lambda raw: dpapi(raw, True, self.entropy)))(value.encode("utf-8"))
        stored = self._read()
        stored[name] = base64.b64encode(sealed).decode("ascii")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(stored, indent=2), encoding="utf-8")

    def load(self, name: str) -> str | None:
        """저장한 값. 없거나 풀지 못하면(다른 사용자, 손상) None."""
        if self.mode == "memory":
            return self._memory.get(name)
        if self.mode == "keyring":
            try:
                return self._keyring.get_password(self.service, name)  # type: ignore[attr-defined]
            except Exception:
                return None
        sealed = self._read().get(name)
        if not sealed:
            return None
        try:
            return (self._unprotect or (lambda raw: dpapi(raw, False, self.entropy)))(base64.b64decode(sealed)).decode("utf-8")
        except (OSError, ValueError, UnicodeDecodeError, SecretUnavailable):
            return None

    def has(self, name: str) -> bool:
        if self.mode == "file":
            return name in self._read()
        return self.load(name) is not None

    def clear(self, name: str) -> bool:
        if self.mode == "memory":
            return self._memory.pop(name, None) is not None
        if self.mode == "keyring":
            try:
                self._keyring.delete_password(self.service, name)  # type: ignore[attr-defined]
                return True
            except Exception:
                return False
        stored = self._read()
        if stored.pop(name, None) is None:
            return False
        self.path.write_text(json.dumps(stored, indent=2), encoding="utf-8")
        return True
