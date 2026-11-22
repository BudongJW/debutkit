<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/brand/lockup/horizontal_dark-bg.svg">
  <img alt="debutkit" src="assets/brand/lockup/horizontal_light-bg.svg" width="360">
</picture>

### 첫 방송까지, 한 번에.

버튜버 첫 방송 준비를 묶은 오픈소스 키트<br>
PC 점검, OBS 장면 세트, 치지직 SOOP Twitch 통합 채팅창과 후원 알림, 방송 중 자동 클립

<a href="LICENSE"><img alt="license" src="https://img.shields.io/badge/license-Apache--2.0-F7F4FA?style=for-the-badge&labelColor=15131F"></a>
<img alt="version" src="https://img.shields.io/badge/version-0.3.0-FF4F8B?style=for-the-badge&labelColor=15131F">
<a href="https://github.com/BudongJW/debutkit/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/BudongJW/debutkit/ci.yml?branch=main&style=for-the-badge&label=CI&labelColor=15131F"></a>
<img alt="python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=15131F">

[프로젝트 사이트](https://budongjw.github.io/debutkit/) | [사용 설명서](https://budongjw.github.io/debutkit/guide.html) | [다운로드](https://github.com/BudongJW/debutkit/releases/latest)

</div>

## 기능

| 기능 | 내용 |
|---|---|
| **설정 마법사** `debutkit-gui` | PC 점검, 아바타, OBS 장면, 채팅과 알림, 마무리 5단계 안내. 아래 기능 전부 창에서 사용 |
| PC 점검 `doctor` | 메모리, CPU, 그래픽카드, 저장 공간, 마이크, 웹캠, OBS와 원격 제어, 트래킹 프로그램, ffmpeg 점검과 해결 방법 표시. `--avatar model.vrm --agency` 로 VRM 모델의 수익화, 법인(기획사) 사용 허락 확인 |
| OBS 장면 `scenes` | 장면 5종(대기 화면, 본방송, 토크, 자리 비움, 엔딩) 자동 생성. 아바타 투명 배경 캡처, 채팅창과 후원 알림 연결. 기존 장면 유지. `--replay-buffer` 로 자동 클립용 리플레이 버퍼 설정 |
| 채팅과 알림 `overlay` | OBS 브라우저 소스용 통합 채팅창(`/chat`), 후원과 구독 알림(`/alerts`). 치지직(공식 API 또는 시청자 읽기), SOOP, Twitch. 데모 채팅, 테스트 버튼 |
| 자동 클립 `overlay --clip` | 채팅 급증 또는 방장, 매니저의 `!clip` 시 OBS 리플레이 버퍼를 클립으로 저장. 동시 송출 시 전 플랫폼 채팅 합산 |
| 준비 도구 `setup`, `chzzk` | ffmpeg 내려받기(`setup --ffmpeg`), 새 버전 확인(`setup --check-update`), 치지직 공식 API 로그인(`chzzk login`) |

## 빠른 시작

**Windows 실행 파일**

- [릴리스](https://github.com/BudongJW/debutkit/releases)에서 `debutkit-버전-windows-x64.zip` 다운로드, 압축 해제
- `debutkit-gui.exe` 실행
- 파이썬 불필요. 자동 클립용 ffmpeg는 마법사 PC 점검 화면에서 내려받기

**파이썬 패키지**

```bash
pip install "debutkit[gui] @ git+https://github.com/BudongJW/debutkit"
debutkit-gui
```

**명령줄**

```bash
debutkit doctor
debutkit scenes --replay-buffer        # OBS 실행, 도구 메뉴의 WebSocket 서버 설정에서 서버 사용 체크 후
debutkit setup --ffmpeg                # 자동 클립용 ffmpeg (Windows)
debutkit overlay --chzzk https://chzzk.naver.com/live/채널ID --soop https://play.sooplive.co.kr/아이디 --clip
```

- 오버레이 설정 화면: http://127.0.0.1:8790 (OBS용 주소 복사, 미리보기, 테스트 채팅과 후원, 방장 !clip 시험)
- 채팅창 모양: `/chat?theme=bubble&font=26&max=10&fade=30&platform=0`
- 내 치지직 채널: 공식 API 권장. `debutkit chzzk login` 1회 후 `debutkit overlay --chzzk-api`
- 리플레이 버퍼 최초 설정 시 OBS 재시작 필요
- 클립 저장 위치: `동영상/debutkit-clips` (`--clip-dir` 로 변경)
- OBS 연결 없이 장면 설계도 확인: `debutkit scenes --dry-run`

상세 사용법: [사용 설명서](https://budongjw.github.io/debutkit/guide.html)

## 원칙

| 원칙 | 내용 |
|---|---|
| 조건 없는 오픈소스 | 모든 기능 무료 공개. 소속사 프로그램 참여 여부와 무관 |
| 수집 없음 | 사용 통계 전송 없음. 오버레이는 이 PC(127.0.0.1)에서만 열림. 채팅 저장 없음 |
| 공식 경로 우선 | 치지직은 공식 Open API 우선. 비공식 시청자 읽기는 다른 채널 시험용 |
| 연결 중심 | 트래킹(VTube Studio, VSeeFace 등)과 송출(OBS)은 기존 프로그램 사용. 키트는 그 사이 연결 |

## 소속 버튜버 프로그램 (선택)

- 운영 팀이 버튜버 소속사(엔터) 프로젝트 병행
- 의향 등록은 희망자만 별도 진행. **미등록 시에도 키트 기능 동일**
- 신청은 계약 아님, 언제든 철회 가능
- 구조와 원칙: [docs/MEMBERSHIP.md](docs/MEMBERSHIP.md), [참여 안내](https://budongjw.github.io/debutkit/join.html)

## 문서

| 문서 | 내용 |
|---|---|
| [프로젝트 사이트](https://budongjw.github.io/debutkit/) | 다운로드, 사용 설명서, 방송 소프트웨어, 소식 |
| [docs/SOFTWARE.md](docs/SOFTWARE.md) | 버튜버 방송 소프트웨어 목록, 키트의 역할 |
| [docs/SIMILAR_PROJECTS.md](docs/SIMILAR_PROJECTS.md) | 유사 프로젝트 조사, debutkit이 채우는 빈틈 |
| [docs/MEMBERSHIP.md](docs/MEMBERSHIP.md) | 소속 참여 동의 구조, 법률 확인 목록 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 다음 단계 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 기여 방법(DCO 서명) |

## 개발

```bash
git clone https://github.com/BudongJW/debutkit && cd debutkit
python -m venv .venv && .venv/Scripts/activate      # macOS, Linux: source .venv/bin/activate
pip install -e ".[gui,dev]"
pytest -q && ruff check .
```

- Windows 실행 파일: `pip install -e ".[gui,build]"` 후 `python packaging/build_windows.py`. 생성한 프로그램을 파이썬 없이 실행해 확인까지 수행
- 릴리스: CHANGELOG에 버전 항목 작성 후 `v*` 태그 push. GitHub Actions가 zip 첨부, CHANGELOG 항목으로 릴리스 노트 작성
- 프로젝트 사이트: `site/` 수정 후 `python packaging/build_site.py` 로 확인. main 반영 시 GitHub Pages 자동 배포

## 라이선스

[Apache-2.0](LICENSE). 연결하는 외부 프로그램(OBS, VTube Studio 등)은 각 프로그램의 라이선스 적용
