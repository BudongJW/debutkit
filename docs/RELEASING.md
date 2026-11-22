# 릴리스 절차

## 기본 절차

1. `CHANGELOG.md`에 버전 항목 작성(`## 0.6.0 (날짜)`)
2. `src/debutkit/__init__.py`, `pyproject.toml`의 버전 변경
3. 사이트(`site/index.html`, `site/guide.html`, `site/news.html`)의 버전과 릴리스 노트 갱신
4. `main`에 반영 후 CI 통과 확인
5. 태그 생성과 push: `git tag -a v0.6.0 -m "debutkit 0.6.0"`, `git push origin v0.6.0`
6. `.github/workflows/release.yml`이 운영체제별 배포 파일을 만들고 검증한 뒤 릴리스에 첨부
7. `.github/workflows/verify.yml`이 실제 OBS로 장면 생성, 리플레이 버퍼, 자동 클립을 검증

| 배포 파일 | 생성 위치 | 검증 내용 |
|---|---|---|
| `debutkit-버전-windows-x64-setup.exe` | Windows | 무인 설치, 실행, 시작 메뉴 등록, 제거, 설치 중 ffmpeg 다운로드 |
| `debutkit-버전-windows-x64.zip` | Windows | 파이썬 없이 명령줄과 설정 마법사 실행 |
| `debutkit-버전-macos-arm64.zip` | macOS(Apple Silicon) | 파이썬 없이 명령줄과 설정 마법사 실행 |
| `debutkit-버전-linux-x64.tar.gz` | Linux(Ubuntu 22.04 기준) | 파이썬 없이 명령줄과 설정 마법사 실행 |

## Windows 코드 서명

- 현재 상태: 인증서 없음. 배포 파일은 서명 없이 배포되며 SmartScreen 경고가 표시될 수 있음
- 동작 방식: 저장소 비밀값이 있으면 릴리스 빌드가 실행 파일과 설치 프로그램에 자동 서명(signtool, SHA-256, 타임스탬프). 없으면 서명 없이 진행

### 인증서 확보 방법

| 방법 | 비용 | 특징 |
|---|---|---|
| SignPath Foundation | 무료(오픈소스 대상, 심사 필요) | 오픈소스 프로젝트에 인증서와 서명 서비스 제공. 서명은 SignPath 서비스에서 진행하므로 별도 워크플로 단계 필요 |
| Azure Trusted Signing | 월 사용료 | Microsoft 관리형 서명. 신원 확인 절차 필요 |
| 상용 코드 서명 인증서(OV, EV) | 연 단위 구매 | PFX 파일 또는 하드웨어 토큰. PFX 방식은 아래 비밀값으로 바로 사용 가능 |

### PFX 인증서 등록

1. 인증서 파일을 Base64로 변환: PowerShell에서 `[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx"))`
2. GitHub 저장소 설정의 Secrets and variables, Actions 화면에서 비밀값 등록
   - `WINDOWS_SIGNING_PFX_BASE64`: 1번 결과
   - `WINDOWS_SIGNING_PASSWORD`: 인증서 비밀번호
3. 다음 태그 릴리스부터 서명 적용. 릴리스 로그의 코드 서명 줄로 확인

### 로컬 서명

```powershell
$env:DEBUTKIT_SIGN_PFX = "C:\path\cert.pfx"
$env:DEBUTKIT_SIGN_PASSWORD = "비밀번호"
python packaging/build_windows.py --installer
```

- signtool.exe(Windows SDK) 필요
- 타임스탬프 서버 기본값: http://timestamp.digicert.com (`DEBUTKIT_SIGN_TIMESTAMP`로 변경)

## macOS 서명과 공증

- 현재 상태: 서명, 공증 없음. 첫 실행 시 Gatekeeper 경고가 표시되며 Finder에서 우클릭 후 열기로 실행
- 적용 조건: Apple Developer Program 가입(연 단위 비용), Developer ID Application 인증서, 공증용 App Store Connect API 키
- 적용 방법: 위 자격 정보를 저장소 비밀값으로 등록한 뒤 macOS 작업에 `codesign`과 `notarytool` 단계 추가 필요(미구현)
