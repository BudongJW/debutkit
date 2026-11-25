<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/brand/lockup/horizontal_dark-bg.svg">
  <img alt="debutkit" src="assets/brand/lockup/horizontal_light-bg.svg" width="360">
</picture>

버튜버 방송 준비용 오픈소스 소프트웨어<br>
PC 점검, OBS 장면 구성, 통합 채팅창과 후원 알림, 방송 중 자동 클립

<a href="LICENSE"><img alt="license" src="https://img.shields.io/badge/license-Apache--2.0-1E2327?style=flat-square"></a>
<img alt="version" src="https://img.shields.io/badge/version-1.0.0rc20-BF3B68?style=flat-square">
<a href="https://github.com/BudongJW/debutkit/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/BudongJW/debutkit/ci.yml?branch=main&style=flat-square&label=CI"></a>
<img alt="python" src="https://img.shields.io/badge/Python-3.10%2B-1E2327?style=flat-square">

[프로젝트 사이트](https://budongjw.github.io/debutkit/) | [사용 설명서](https://budongjw.github.io/debutkit/guide.html) | [다운로드](https://github.com/BudongJW/debutkit/releases/latest)

</div>

## 개요

- 신규 버튜버의 방송 전 준비 작업(PC 점검, 장면 구성, 채팅 연결)을 하나의 프로그램으로 제공
- 지원 플랫폼: 치지직, SOOP, Twitch, YouTube
- 트래킹(VTube Studio 등)과 송출(OBS Studio)은 기존 프로그램을 사용하고, 프로그램 사이의 설정과 연결을 담당. OBS 없이 송출 화면을 바로 보내는 토크 방송용 송출도 제공(Windows)

## 기능

| 기능 | 명령 | 내용 |
|---|---|---|
| 설정 마법사 | `debutkit-gui` | PC 점검, 캐릭터, OBS 장면, 채팅과 알림, 마무리의 5단계 안내. 모든 기능을 창에서 사용 |
| 방송 시작 버튼 | `debutkit launch` | 세팅별로 켤 것(프로그램, 바로가기, 폴더, 사이트)을 차례로 켜고 방해되는 프로그램(메신저, 게임 런처)은 먼저 끔. 이미 켜진 것 건너뛰기, 창 자리와 크기 기억(듀얼 모니터), 다시 켜짐 알림, 방송 끝에 꺼 둔 프로그램 다시 켜기. 운영체제와 보안 프로그램은 끄지 않음 |
| PC 점검 | `debutkit doctor` | 메모리, CPU, 그래픽카드, 저장 공간, 마이크, 웹캠, OBS, 트래킹 프로그램, ffmpeg 점검 및 조치 안내. 아바타 모델(VRM) 사용 조건 확인, 업로드 속도 측정 |
| 캐릭터 | `debutkit character`, `debutkit motion` | PNGTuber, 3D(VRM, GLB, FBX), Live2D 등록과 사용 조건 확인. PNGTuber와 3D는 debutkit 캐릭터 화면으로 방송(OBS 마이크 음량으로 입 움직임, 웹캠 얼굴 추적, 아이폰 얼굴 추적 `debutkit phone`, 퍼펙트 싱크). 얼굴 추적 값을 VMC 프로토콜로 Warudo, VSeeFace, VMagicMirror에 보내기(`debutkit vmc`). 3D 캐릭터 동작(VRMA, Mixamo 등의 FBX, GLB)으로 기본 동작과 후원 반응. Live2D는 VTube Studio로 보내기, 모델 불러오기, 후원 시 단축키 실행(`debutkit vts`) |
| OBS 장면 구성 | `debutkit scenes`, `debutkit camera` | 대기 화면, 본방송, 토크, 자리 비움, 엔딩 장면 생성. 아바타 투명 배경 캡처, 채팅창과 후원 알림 연결. 휴대폰 카메라 영상(SRT, 암호)을 받는 OBS 소스와 휴대폰 앱 연결 QR |
| 채팅창과 후원 알림 | `debutkit overlay`, `debutkit draw`, `debutkit raffle` | OBS 브라우저 소스용 통합 채팅창과 후원 알림. 표시 형태 5종. 후원 추첨 연출 7종(카드 뒤집기, 룰렛, 캡슐 뽑기, 즉석 복권, 티켓 출력, 추첨기, 타로, 상품과 확률표, 금액별 추첨 횟수). 시청자 참여 추첨(채팅 !참가로 모집, 당첨자 뽑기, 순서 정하기). 스트리머, 매니저 채팅 명령. 휴대폰 조작 화면(`debutkit remote`, QR 등록과 PC 승인, 요청 서명) |
| 방송 연출 | `debutkit pick`, `debutkit wall`, `debutkit race` | 뽑기판(당첨 칸은 조작 화면에서만, 채팅과 후원으로 시청자가 열기, 배치 공정성 확인), 후원 벽(단위별 카드 벽지, 시그니처 그림, 목표 게이지, 후원 순위), 참여 레이스(구슬 레이스, 달리기 경주, 서바이벌). 방송 화면 미리보기(`/stage`)와 방송 색(모든 화면의 색 맞춤). 모든 방송 화면이 공유 연결 하나를 쓰고 가운데 연출은 차례로 |
| 휴대폰 앱 | `mobile/` | 안드로이드(APK, MediaPipe), 아이폰(ARKit, 소스 빌드) 얼굴 추적과 카메라 영상(WebRTC, OBS 브라우저 소스로 직접 전송) 앱. 같은 QR로 등록하고 PC에서 승인, 서명된 요청과 값만 사용. 안드로이드는 PC 없이 바로 방송(캐릭터 화면 또는 카메라 영상을 치지직, SOOP, YouTube, Twitch로 송출) 지원. [mobile/README.md](mobile/README.md) |
| OBS 없이 바로 방송 | `debutkit broadcast` | Windows. 캐릭터, 채팅, 후원 알림, 추첨 연출을 모은 송출 화면을 치지직, SOOP, YouTube, Twitch로 바로 송출(ffmpeg 창 캡처, 하드웨어 H.264, 마이크). 스트림 키는 암호화 저장. 토크 방송용(게임 방송은 OBS) |
| 방송 로고 만들기 | `debutkit logo` | 함께 배포하는 아이콘(Fluent Emoji 356개, Phosphor 102개 굵기 6종, MIT, 한국어 검색, 채널 색 다시 칠하기)과 기본 도형 8종, 계정 없는 공개 모델 AI Horde(FLUX.1 schnell, 대기열 백그라운드 대기), 공개 이미지 모델 Qwen-Image(사용자의 ComfyUI 또는 Hugging Face 공개 데모) 또는 사용자 본인 API 키의 생성형 AI(Claude, OpenAI, Recraft) 심볼과 채널 이름(글꼴 윤곽선)으로 SVG, 투명 PNG 로고. 외곽선과 스티커 테두리 마감, 아이콘 출처와 AI 생성 표시 메타데이터, 받은 SVG 정리, API 키 암호화 저장 |
| 방송 중 자동 클립 | `debutkit overlay --clip`, `debutkit clip` | 채팅 급증 또는 스트리머와 매니저의 `!clip` 입력 시 OBS 리플레이 버퍼를 클립으로 저장. 클립마다 움짤(GIF)과 세로 쇼츠(1080x1920) 자동 생성(선택), 영상으로 움짤 GIF, WebP와 쇼츠 만들기, 워터마크 |
| 준비 도구 | `debutkit setup`, `debutkit chzzk` | ffmpeg 다운로드, 새 버전 확인, 치지직 공식 API 로그인 |

## 설치

### Windows

- [릴리스 페이지](https://github.com/BudongJW/debutkit/releases/latest)에서 설치 프로그램(`debutkit-버전-windows-x64-setup.exe`) 실행. 시작 메뉴에 debutkit 등록
- 설치 없이 사용하는 경우 `debutkit-버전-windows-x64.zip` 압축 해제 후 `debutkit-gui.exe` 실행
- 관리자 권한과 파이썬 설치 불필요. 자동 클립용 ffmpeg는 설치 과정 또는 설정 마법사에서 다운로드

### macOS, Linux

- macOS(Apple Silicon): `debutkit-버전-macos-arm64.zip` 압축 해제 후 debutkit.app 실행. 공증하지 않은 프로그램이므로 첫 실행은 Finder에서 우클릭 후 열기
- Linux(x64): `debutkit-버전-linux-x64.tar.gz` 압축 해제 후 `debutkit/debutkit-gui` 실행. Qt 실행에 `libxcb-cursor0` 등 그래픽 라이브러리 필요
- 파이썬 패키지로 설치하는 경우(Python 3.10 이상)

```bash
pip install "debutkit[gui] @ git+https://github.com/BudongJW/debutkit"
debutkit-gui
```

## 명령줄 사용 예

```bash
debutkit doctor --speed                # PC 점검과 업로드 속도 측정
debutkit scenes --replay-buffer        # OBS 장면 생성과 리플레이 버퍼 설정
debutkit setup --ffmpeg                # 자동 클립용 ffmpeg 다운로드(Windows)
debutkit overlay --chzzk https://chzzk.naver.com/live/채널ID --soop https://play.sooplive.co.kr/아이디 --clip
debutkit overlay --youtube https://www.youtube.com/watch?v=영상ID --youtube-key API키
debutkit youtube check https://www.youtube.com/watch?v=영상ID --youtube-key API키   # 방송 전 YouTube 연결 확인
debutkit character add 모델.vrm                 # 캐릭터 등록(VRM, GLB, FBX, Live2D 폴더나 zip, PNG는 character png)
debutkit character use 캐릭터                     # 방송에 사용. OBS 브라우저 소스 http://127.0.0.1:8790/character
debutkit motion add VRMA_MotionPack.zip          # 3D 캐릭터 동작 등록(VRMA, FBX, GLB, zip)
debutkit motion idle 동작                         # 기본 동작(대기 중 반복). 후원 반응은 overlay --motion-reaction 1000:동작
debutkit overlay --chzzk 채널주소 --clip --save   # 채널과 옵션 저장
debutkit overlay --saved                         # 다음 방송부터 저장한 설정으로 실행
debutkit draw set --on --prize 90:꽝 --prize 10:노래 --rule 1000:1   # 후원 추첨 연출(조작 화면 http://127.0.0.1:8790/draw/control)
debutkit raffle start                            # 시청자 참여 추첨 모집(채팅 !참가). 당첨자 뽑기 debutkit raffle draw 3
debutkit pick open 7 --by 치즈냥                  # 뽑기판 칸 열기(조작 화면 http://127.0.0.1:8790/pick/control)
debutkit race start --game marble                # 참여 추첨 참가자로 구슬 레이스
debutkit launch add 방송 "C:/Program Files/obs-studio/bin/64bit/obs64.exe" && debutkit launch   # 방송 시작 버튼
debutkit clip shorts 클립.mp4 --mode crop --focus 0.8   # 세로 쇼츠
```

- 방송 화면 미리보기: http://127.0.0.1:8790/stage (모든 방송 화면을 겹쳐 보기, 시험 후원, 방송 색)

- OBS 장면 생성 전 OBS의 도구 메뉴에서 WebSocket 서버 사용 설정 필요
- 오버레이 설정 화면: http://127.0.0.1:8790 (OBS용 주소 복사, 표시 형태 선택, 미리보기, 시험 메시지)
- 본인 치지직 채널은 공식 API 사용 권장(`debutkit chzzk login` 실행 후 `debutkit overlay --chzzk-api`)
- YouTube 채팅은 스트리밍 방식(연결 1회 5 단위)을 우선 사용하고, 사용할 수 없으면 요청 방식으로 자동 전환
- 리플레이 버퍼를 처음 설정한 경우 OBS 재시작 후 사용 가능
- 설정 마법사와 `--save`는 채널 주소와 선택 항목을 이 PC에 저장(API 키, 비밀번호 제외). `debutkit settings`로 확인, `--clear`로 삭제
- 클립 저장 위치: `동영상/debutkit-clips` (`--clip-dir`로 변경)

전체 사용법은 [사용 설명서](https://budongjw.github.io/debutkit/guide.html) 참고

## 운영 원칙

| 항목 | 내용 |
|---|---|
| 무상 공개 | 모든 기능을 Apache-2.0으로 공개. 소속 프로그램 참여 여부와 무관 |
| 정보 수집 없음 | 사용 통계 미전송. 오버레이는 이 PC(127.0.0.1)에서만 접속 가능, 채팅 미저장 |
| 공식 API 우선 | 치지직과 YouTube는 공식 API 사용. 비공식 수신은 다른 채널 시험 용도 |
| 기존 프로그램 활용 | 트래킹(VTube Studio, VSeeFace 등)과 송출(OBS Studio)은 기존 프로그램 사용 |

## 소속 버튜버 프로그램

- 운영 팀이 버튜버 소속사(엔터테인먼트) 사업을 함께 준비 중
- 소속 의향 등록은 희망자에 한해 별도 접수. 미등록 사용자에게도 모든 기능을 동일하게 제공
- 등록은 계약이 아니며 언제든 철회 가능
- 운영 원칙: [docs/MEMBERSHIP.md](docs/MEMBERSHIP.md), [참여 안내](https://budongjw.github.io/debutkit/join.html)

## 문서

| 문서 | 내용 |
|---|---|
| [프로젝트 사이트](https://budongjw.github.io/debutkit/) | 다운로드, 사용 설명서, 방송 소프트웨어, 릴리스 노트 |
| [docs/SOFTWARE.md](docs/SOFTWARE.md) | 버튜버 방송 소프트웨어 목록과 debutkit의 역할 |
| [docs/SIMILAR_PROJECTS.md](docs/SIMILAR_PROJECTS.md) | 유사 프로젝트 조사 |
| [docs/MEMBERSHIP.md](docs/MEMBERSHIP.md) | 소속 참여 동의 구조, 법률 확인 목록 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 개발 계획, 검증 현황 |
| [docs/RELEASING.md](docs/RELEASING.md) | 릴리스 절차, 코드 서명 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 기여 방법(DCO 서명), 표기 원칙 |

## 개발

```bash
git clone https://github.com/BudongJW/debutkit && cd debutkit
python -m venv .venv && .venv/Scripts/activate      # macOS, Linux: source .venv/bin/activate
pip install -e ".[gui,dev]"
pytest -q && ruff check .
```

- Windows 실행 파일: `pip install -e ".[gui,build]"` 후 `python packaging/build_windows.py`. 생성한 프로그램을 파이썬 없이 실행해 동작 확인. `--installer` 지정 시 설치 프로그램도 생성(Inno Setup 6 필요)
- macOS, Linux 실행 파일: `python packaging/build_app.py`(각 운영체제에서 실행)
- 릴리스: [docs/RELEASING.md](docs/RELEASING.md). `v*` 태그 push 시 GitHub Actions가 운영체제별 배포 파일을 만들어 첨부하고, Windows, macOS, Linux의 실제 OBS 검증(`verify.yml`)을 실행
- 프로젝트 사이트: `site/` 수정 후 `python packaging/build_site.py`로 확인. main 반영 시 GitHub Pages에 자동 배포

## 라이선스

[Apache-2.0](LICENSE). 연동하는 외부 프로그램(OBS Studio, VTube Studio 등)에는 각 프로그램의 라이선스 적용. 함께 배포하는 외부 코드의 출처와 라이선스는 `src/debutkit/overlay/static/vendor/README.txt`, `src/debutkit/vendor/README.txt`
