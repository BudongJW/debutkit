# 릴리스 절차

## 기본 절차

1. `CHANGELOG.md`에 버전 항목 작성(`## 0.6.0 (날짜)`)
2. `src/debutkit/__init__.py`, `pyproject.toml`의 버전 변경
3. 사이트(`site/index.html`, `site/guide.html`, `site/news.html`)의 버전과 릴리스 노트 갱신
4. `main`에 반영 후 CI 통과 확인
5. 태그 생성과 push: `git tag -a v0.6.0 -m "debutkit 0.6.0"`, `git push origin v0.6.0`
6. `.github/workflows/release.yml`이 운영체제별 배포 파일을 만들고 검증한 뒤 릴리스에 첨부
7. `.github/workflows/verify.yml`이 Windows, macOS, Linux 각각 실제 OBS로 장면 생성, 리플레이 버퍼, 자동 클립을 검증하고, 실제 YouTube 서버로 채팅 수신 경로를 확인. Windows에서는 OBS 없이 바로 방송(Edge 송출 화면 창, x264, 이 PC 안의 RTMP 수신)도 확인

### 사전 릴리스(후보)

- 버전 표기: `1.0.0rc1`(PEP 440). 태그 `v1.0.0rc1`, `CHANGELOG.md` 항목 `## 1.0.0rc1 (날짜)`
- 릴리스 작업이 사전 릴리스로 표시하고 릴리스 노트 첫머리에 실제 환경 확인 안내를 넣음
- GitHub의 최신 릴리스(`releases/latest`)와 프로그램의 새 버전 확인은 사전 릴리스를 제외. 정식 버전은 같은 번호의 후보보다 높게 판단(1.0.0이 1.0.0rc1보다 높음)
- Windows 버전 정보와 macOS 번들 버전에는 숫자 부분(`1.0.0`)만 기록. 제품 버전 문자열에는 전체 표기 기록
- 정식 출시: 후보 이후 변경 내역을 `## 1.0.0 (날짜)`로 정리하고 위 기본 절차 진행

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

1. SignPath Foundation 신청(무료, 오픈소스 대상, https://signpath.org/apply)
2. 승인되면 아래 SignPath 연동 절차로 설정
3. 승인되지 않으면 상용 OV 인증서 구매 후 아래 PFX 방식으로 등록. EV 인증서와 하드웨어 토큰 방식은 클라우드 서명 서비스가 필요

### SignPath Foundation 신청 전 확인 사항

SignPath Foundation 조건(https://signpath.org/terms, 2026-11-22 확인)과 debutkit의 대응 현황.

| 조건 | debutkit 현황 |
|---|---|
| OSI 승인 라이선스, 독점 구성 요소 없음 | Apache-2.0. 함께 배포하는 Python, Qt for Python, gRPC 등도 오픈소스 |
| 서명할 형태로 이미 배포 중, 활발한 유지 관리 | 0.7.1부터 같은 형태(설치 프로그램, zip)로 릴리스 |
| 다운로드 페이지의 기능 설명 | 프로젝트 사이트, 사용 설명서 |
| 홈페이지의 코드 서명 정책(Code signing policy) | `site/signing.html`. 사이트 하단과 릴리스 노트에서 링크 |
| 역할 지정(Authors, Reviewers, Approvers) | 코드 서명 정책 페이지의 담당 역할 표 |
| 개인정보 정책 | 코드 서명 정책 페이지의 개인정보 항목(자동 전송 없음, 연결 조건 표) |
| 제거 방법 제공, 알리지 않은 시스템 변경 금지 | 제거 프로그램 제공, 현재 사용자 계정에만 설치 |
| 제품 이름과 버전 메타데이터 | 0.7.1부터 실행 파일과 설치 프로그램에 기록. SignPath 아티팩트 구성에서 일치 여부 강제 |
| CI에서 소스로 빌드, 릴리스별 수동 승인 | GitHub Actions 빌드. 서명 정책에서 승인자 수동 승인 지정 |
| 모든 담당자의 다단계 인증(GitHub, SignPath) | 저장소 소유자가 GitHub 다단계 인증 사용 여부 확인 필요 |

### 신청 시기

- 신청서의 평판(Reputation) 항목은 프로젝트가 널리 쓰이거나 신뢰받는다는 근거(언론 보도, 블로그, 다운로드 수, GitHub 통계, 커뮤니티 논의)를 요구
- 2026-11-22 기준 저장소 생성 2일, 별 0개, 릴리스 다운로드 합계 약 22회(대부분 검증용)로 근거 부족. 사용자 확보 후 신청 권장
- 신청 기준 예시: 실제 사용자 이슈나 사용 후기, 릴리스 다운로드 수백 회 이상, 외부 소개 글 등 링크로 제시할 수 있는 근거

### 신청서 작성 초안

신청 양식(https://signpath.org/apply, 2026-11-22 확인)의 항목별 입력값. 이름, 이메일, 동의 항목은 신청자가 직접 입력하고 제출. 양식에 reCAPTCHA 적용.

| 항목 | 입력값 |
|---|---|
| Project Name | `debutkit` |
| Repository URL | `https://github.com/BudongJW/debutkit` |
| Homepage URL | `https://budongjw.github.io/debutkit/` |
| Download URL | `https://budongjw.github.io/debutkit/#download`. 양식 안내상 이 페이지에 SignPath Foundation 사용 언급 필요. 신청 직전 다운로드 영역의 코드 서명 항목에 `Windows 코드 서명: SignPath Foundation 프로그램 신청 중`을 추가하고, 승인 후 공식 문구로 교체 |
| Privacy Policy URL | `https://budongjw.github.io/debutkit/signing.html#privacy` |
| Wikipedia URL | 비움 |
| Tagline | `Open-source setup kit for VTuber streamers: PC checks, OBS scene setup, a combined chat overlay for CHZZK, SOOP, Twitch and YouTube, and automatic clips.` |
| Category | `Other`(선택지: Accessibility, AI Tools, Audio, Developer Tools, Educational, Gaming, Graphics, Productivity, Science, Other) |
| Description | 아래 문단 |
| Reputation | 신청 시점의 근거 링크(릴리스 다운로드 수, 이슈, 소개 글). 보조 근거: 릴리스마다 Windows, macOS, Linux의 실제 OBS로 자동 검증하는 공개 워크플로(`https://github.com/BudongJW/debutkit/actions/workflows/verify.yml`) |
| Maintainer Type | `Individual maintainer(s)`. 소속사 사업을 법인으로 운영하게 되면 해당 유형 재검토 |
| Build System | `GitHub Actions` |
| First Name, Last Name, Email | 신청자 본인. SignPath 계정 이름과 알림 주소로 사용 |
| Company Name | 비움(법인 설립 시 법인명) |
| Primary Discovery Channel | 신청자 선택 |
| Code of Conduct 동의 | 신청자가 내용 확인 후 동의(필수) |
| 마케팅 수신 동의 | 선택 사항. 체크하지 않아도 신청 가능 |
| 개인정보 처리 동의 | 필수 |

Description 입력값:

```text
debutkit helps new VTuber streamers prepare their first broadcast. It checks the PC (OBS, graphics, microphone, webcam, disk space and upload speed), creates a ready-made set of OBS scenes through the OBS WebSocket API, runs a local chat and donation alert overlay that combines CHZZK, SOOP, Twitch and YouTube chat, and saves clips from the OBS replay buffer when chat activity surges or the streamer types a command. It is distributed as a Windows installer, a macOS app, a Linux archive and a Python package under the Apache-2.0 license, with no telemetry.
```

### SignPath 연동 절차(승인 후)

1. SignPath에서 프로젝트 생성(슬러그 `debutkit`). 신뢰 빌드 시스템 GitHub.com을 조직에 추가하고 프로젝트에 연결. SignPath GitHub App 설치
2. 아티팩트 구성 2개 생성: 슬러그 `programs`(내용 `packaging/signpath/programs.xml`), `installer`(내용 `packaging/signpath/installer.xml`)
3. 서명 정책 생성(슬러그 `release-signing`). 승인자 수동 승인 지정
4. GitHub 저장소 설정의 Secrets and variables, Actions 화면에서 등록
   - 변수 `SIGNPATH_ORGANIZATION_ID`: SignPath 조직 ID(등록하면 태그 릴리스에서 SignPath 서명 사용)
   - 변수 `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_POLICY_SLUG`: 슬러그가 `debutkit`, `release-signing`과 다를 때만
   - 비밀값 `SIGNPATH_API_TOKEN`: 서명 요청 제출 권한이 있는 SignPath 사용자의 API 토큰
5. `site/signing.html`의 서명 현황 갱신, 정책 첫머리에 SignPath가 요구하는 문구 추가: `Free code signing provided by SignPath.io, certificate by SignPath Foundation`(각 이름에 https://about.signpath.io, https://signpath.org 링크)
6. 태그 릴리스 실행 중 SignPath에서 서명 요청 2건(실행 파일, 설치 프로그램) 승인. 승인 대기 제한 시간 1시간

- 릴리스 작업 순서: 빌드와 버전 정보 확인, 실행 파일 서명 요청, 실행 확인과 압축, 설치 프로그램 빌드, 설치 프로그램 서명 요청, 설치와 제거 검증, 릴리스 첨부
- SignPath 방식은 제거 프로그램(unins000.exe)에 서명하지 않음. 인증서 파일(PFX) 방식만 제거 프로그램까지 서명
- Inno Setup은 설치 프로그램의 버전 정보 문자열 끝을 공백으로 채움(예: 제품 이름 `debutkit` 뒤 공백). 첫 서명 요청에서 SignPath가 제품 이름 또는 버전 불일치로 거부하면 `installer.xml`의 제한 값 조정 필요
- 직접 실행한 릴리스 작업(서명 시험)에는 SignPath를 사용하지 않음

### 인증서 확보 방법

| 방법 | 비용 | 특징 |
|---|---|---|
| SignPath Foundation | 무료(오픈소스 대상, 심사 필요) | 오픈소스 프로젝트에 인증서와 서명 서비스 제공. 릴리스 작업에 연동 단계 구현 완료(저장소 변수 등록 시 사용) |
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

## 휴대폰 앱(안드로이드 APK) 서명

릴리스 작업이 안드로이드 APK(`debutkit-phone-버전-android.apk`)를 만들어 첨부한다. 서명 키 비밀값이 없으면 시험용 디버그 키(빌드마다 달라짐)로 서명하므로 새 버전 설치 전에 이전 앱을 지워야 한다. 배포 키는 한 번 정하면 바꿀 수 없다(바꾸면 기존 사용자가 업데이트 불가).

1. 저장소 소유자 PC에서 키 생성(JDK의 keytool): `keytool -genkeypair -v -keystore debutkit-release.jks -alias debutkit -keyalg RSA -keysize 4096 -validity 10000`
2. 키 파일과 비밀번호를 오프라인 두 곳 이상에 보관(분실하면 같은 앱으로 업데이트 불가)
3. 저장소 비밀값 등록
   - `ANDROID_KEYSTORE_BASE64`: 키 파일의 base64(`base64 -w0 debutkit-release.jks`, Windows는 `certutil -encode` 후 머리글과 꼬리글 제거)
   - `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`(위 예시는 `debutkit`), `ANDROID_KEY_PASSWORD`
4. 등록 후 첫 릴리스 노트에 이전 시험용 서명 앱을 지운 뒤 설치하라는 안내 유지(릴리스 노트는 서명 상태에 따라 자동)
5. F-Droid 신청 시 F-Droid 서명 또는 재현 가능 빌드 방식 선택. Android 개발자 인증(2027 전 세계 적용 예정)은 서명 키 지문 등록 필요

iOS 앱은 앱 스토어 계정(개인 연 99달러, 판매자명에 본명 표시)이 정해질 때까지 소스 빌드만 안내한다(`mobile/ios/README.md`).

## YouTube 실제 수신 검증

- Verify 작업의 youtube 단계는 API 키 없이 실제 서버의 스트리밍 메서드 경로와 API 키 전달 방식을 확인
- 저장소 비밀값 `YOUTUBE_API_KEY`를 등록하면 방송 중인 YouTube 채팅으로 요청 방식과 스트리밍 방식 실제 수신까지 확인(실행 1회 약 11 단위)
- 확인할 방송 주소는 저장소 변수 `YOUTUBE_TEST_URL`로 지정. 없으면 24시간 라이브 방송 1개 사용
- 검증용 API 키는 방송용 키와 분리하고 API 제한을 YouTube Data API v3로 설정
