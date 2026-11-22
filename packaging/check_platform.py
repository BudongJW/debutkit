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


def main() -> int:
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
    scenes = run("scenes", "--dry-run")
    if scenes.returncode != 0 or "본방송" not in scenes.stdout:
        print(scenes.stdout[-1500:], scenes.stderr[-1500:])
        raise SystemExit("scenes --dry-run 실패")
    print("  scenes --dry-run: 정상")
    return 0


if __name__ == "__main__":
    sys.exit(main())
