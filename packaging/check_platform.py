"""운영체제별 실제 점검 코드 실행 확인(CI용). 가짜 구현 없이 이 PC에서 doctor와 장면 설계를 실행한다.

    python packaging/check_platform.py

- doctor --json: 모든 점검 항목이 나오고 오류로 끝나지 않는지(필요 항목이 있어 종료 코드 1인 것은 정상)
- 마이크, 웹캠, 그래픽카드 항목: 감지 결과를 출력(CI 서버는 장치가 없어 필요, 주의, 참고가 정상)
- scenes --dry-run: 이 운영체제의 소스 종류로 장면 설계 출력
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys

REQUIRED = {"memory", "cpu", "gpu", "disk", "mic", "camera", "obs", "tracking", "live", "ffmpeg", "overlay-port"}


def run(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-m", "debutkit", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=180)


def expectations(argv: list[str]) -> dict[str, str]:
    """``--expect 항목=이름`` 목록. 해당 항목이 정상이고 설명에 이름이 들어 있어야 통과(장치를 붙인 CI에서 사용)."""
    found = {}
    for index, arg in enumerate(argv):
        if arg == "--expect" and index + 1 < len(argv) and "=" in argv[index + 1]:
            key, name = argv[index + 1].split("=", 1)
            found[key] = name
    return found


def main(argv: list[str] | None = None) -> int:
    expected = expectations(sys.argv[1:] if argv is None else argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]  # Windows 콘솔 기본 인코딩에서도 한국어 출력
    print(f"{platform.system()} {platform.release()} {platform.machine()}, Python {platform.python_version()}")
    doctor = run("doctor", "--json")
    if doctor.returncode not in (0, 1):
        print(doctor.stderr[-2000:])
        raise SystemExit(f"doctor 종료 코드 {doctor.returncode}")
    checks = {check["key"]: check for check in json.loads(doctor.stdout)}
    missing = REQUIRED - set(checks)
    if missing:
        raise SystemExit(f"점검 항목 누락: {', '.join(sorted(missing))}")
    errors = [check for check in checks.values() if "점검 중 오류" in check["detail"]]
    if errors:
        raise SystemExit("점검 중 오류: " + "; ".join(f"{check['key']}: {check['detail']}" for check in errors))
    for key in ("gpu", "mic", "camera", "obs", "ffmpeg"):
        check = checks[key]
        print(f"  {key:8} {check['status']:5} {check['detail']}")
    for key, name in expected.items():
        check = checks[key]
        if check["status"] != "ok" or name not in check["detail"]:
            raise SystemExit(f"{key}: '{name}' 장치를 정상으로 감지하지 못함 ({check['status']}, {check['detail']})")
        print(f"  {key}: '{name}' 감지 확인")
    scenes = run("scenes", "--dry-run")
    if scenes.returncode != 0 or "본방송" not in scenes.stdout:
        print(scenes.stdout[-1500:], scenes.stderr[-1500:])
        raise SystemExit("scenes --dry-run 실패")
    print("  scenes --dry-run: 정상")
    return 0


if __name__ == "__main__":
    sys.exit(main())
