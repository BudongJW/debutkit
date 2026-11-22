# 릴리스 절차

## 기본 절차

1. `CHANGELOG.md`에 버전 항목 작성(`## 0.6.0 (날짜)`)
2. `src/debutkit/__init__.py`, `pyproject.toml`의 버전 변경
3. 사이트(`site/index.html`, `site/guide.html`, `site/news.html`)의 버전과 릴리스 노트 갱신
4. `main`에 반영 후 CI 통과 확인
5. 태그 생성과 push: `git tag -a v0.6.0 -m "debutkit 0.6.0"`, `git push origin v0.6.0`
6. `.github/workflows/release.yml`이 운영체제별 배포 파일을 만들고 검증한 뒤 릴리스에 첨부
7. `.github/workflows/verify.yml`이 Windows, macOS, Linux 각각 실제 OBS로 장면 생성, 리플레이 버퍼, 자동 클립을 검증하고, 실제 YouTube 서버로 채팅 수신 경로를 확인

| 배포 파일 | 생성 위치 | 검증 내용 |
|---|---|---|
| `debutkit-버전-windows-x64-setup.exe` | Windows | 무인 설치, 실행, 시작 메뉴 등록, 제거, 설치 중 ffmpeg 다운로드 |
| `debutkit-버전-windows-x64.zip` | Windows | 파이썬 없이 명령줄과 설정 마법사 실행 |
| `debutkit-버전-macos-arm64.zip` | macOS(Apple Silicon) | 파이썬 없이 명령줄과 설정 마법사 실행 |
| `debutkit-버전-linux-x64.tar.gz` | Linux(Ubuntu 22.04 기준) | 파이썬 없이 명령줄과 설정 마법사 실행 |

## Windows 코드 서명

- 현재 상태: 인증서 없음. 배포 파일은 서명 없이 배포되며 SmartScreen 경고가 표시될 수 있음
- 동작 방식: 저장소 비밀값이 있으면 릴리스 빌드가 실행 파일 2개, 설치 프로그램, 제거 프로그램(unins000.exe)에 자동 서명(signtool, SHA-256, 타임스탬프). 없으면 서명 없이 진행
- 서명 절차 시험: 릴리스 작업을 직접 실행(workflow_dispatch)하면 인증서 비밀값이 없을 때 임시 자체 서명 인증서로 서명부터 서명 확인(서명자, 타임스탬프)까지 실행. 태그 릴리스에는 사용하지 않음

### 권장 순서

1. SignPath Foundation 신청(무료, 오픈소스 대상): 지원 조건(OSI 승인 라이선스, 공개 저장소 등)을 신청 전 SignPath Foundation 안내에서 확인 후 신청서 제출. debutkit은 Apache-2.0, 공개 저장소, CI 빌드
2. 승인되면 SignPath 프로젝트와 서명 정책 구성, GitHub Actions 연동(SignPath 제출 단계를 release.yml의 Windows 작업에 추가)
3. 승인되지 않으면 상용 OV 인증서 구매 후 아래 PFX 방식으로 등록. EV 인증서와 하드웨어 토큰 방식은 클라우드 서명 서비스가 필요

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

- 현재 상태: 임시 서명(ad-hoc)과 강화된 런타임 적용, 공증 없음. 첫 실행 시 Gatekeeper 경고가 표시되며 Finder에서 우클릭 후 열기로 실행
- 동작 방식: 릴리스 빌드가 debutkit.app 전체를 강화된 런타임과 `packaging/macos/entitlements.plist`로 서명하고 `codesign --verify --strict` 확인 후 실행 검증. 아래 비밀값이 있으면 Developer ID로 서명하고 공증, 스테이플, Gatekeeper 평가까지 진행
- 적용 조건: Apple Developer Program 가입(연 단위 비용), Developer ID Application 인증서

### 비밀값 등록

| 비밀값 | 내용 |
|---|---|
| `MACOS_CERTIFICATE_P12_BASE64` | Developer ID Application 인증서와 개인 키를 내보낸 .p12 파일의 Base64(`base64 -i cert.p12`) |
| `MACOS_CERTIFICATE_PASSWORD` | .p12 파일 비밀번호 |
| `MACOS_SIGNING_IDENTITY` | 인증서 이름. 예: `Developer ID Application: 이름 (팀ID)` |
| `APPLE_ID` | Apple Developer 계정 이메일 |
| `APPLE_TEAM_ID` | 팀 ID(10자리) |
| `APPLE_APP_PASSWORD` | appleid.apple.com에서 만든 앱 암호 |

- 인증서 3개만 등록하면 서명만, 6개 모두 등록하면 공증까지 진행
- 공증 후에는 릴리스 노트의 macOS 첫 실행 안내(우클릭 후 열기) 삭제 가능

## YouTube 실제 수신 검증

- Verify 작업의 youtube 단계는 API 키 없이 실제 서버의 스트리밍 메서드 경로와 API 키 전달 방식을 확인
- 저장소 비밀값 `YOUTUBE_API_KEY`를 등록하면 방송 중인 YouTube 채팅으로 요청 방식과 스트리밍 방식 실제 수신까지 확인(실행 1회 약 11 단위)
- 확인할 방송 주소는 저장소 변수 `YOUTUBE_TEST_URL`로 지정. 없으면 24시간 라이브 방송 1개 사용
- 검증용 API 키는 방송용 키와 분리하고 API 제한을 YouTube Data API v3로 설정
