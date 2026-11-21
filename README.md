<div align="center">

# debutkit

### 첫 방송까지, 한 번에.

버튜버가 방송을 시작하는 데 필요한 준비를 묶은 오픈소스 키트<br>
PC 점검 · OBS 장면 세트 · 치지직/SOOP/Twitch 통합 채팅창과 후원 알림 · 방송 후 클립은 [stream2clip](https://github.com/BudongJW/stream2clip)

<a href="LICENSE"><img alt="license" src="https://img.shields.io/badge/license-Apache--2.0-F7F4FA?style=for-the-badge&labelColor=15131F"></a>
<img alt="version" src="https://img.shields.io/badge/version-0.1.0-FF4F8B?style=for-the-badge&labelColor=15131F">
<img alt="python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=15131F">

</div>

## 무엇을 하나

| 명령 | 하는 일 |
|---|---|
| `debutkit doctor` | 메모리, CPU, 그래픽카드, 저장 공간, OBS와 원격 제어, 트래킹 프로그램(VTube Studio, Warudo 등), stream2clip, ffmpeg를 점검하고 해결 방법을 알려 줌. `--avatar model.vrm --agency` 로 아바타 모델의 수익화·법인(기획사) 사용 허락까지 확인 |
| `debutkit scenes` | OBS에 버튜버 장면 5종(대기 화면, 본방송, 토크, 자리 비움, 엔딩)을 자동으로 만듦. 아바타는 투명 배경으로 캡처, 채팅창·후원 알림이 미리 연결됨. 이미 있는 장면은 건드리지 않음 |
| `debutkit overlay` | OBS 브라우저 소스용 통합 채팅창(`/chat`)과 후원·구독 알림(`/alerts`). 치지직(공식 API 또는 시청자 읽기), SOOP, Twitch를 한 화면에. 방송 없이 모양을 맞추는 데모와 테스트 버튼 |

방송이 끝나면 [stream2clip](https://github.com/BudongJW/stream2clip)으로 채팅 반응이 큰 구간을 찾아 세로형 클립을 만듭니다.

## 빠른 시작

```bash
pip install "debutkit[live] @ git+https://github.com/BudongJW/debutkit"
debutkit doctor
```

```bash
debutkit overlay --chzzk https://chzzk.naver.com/live/<채널ID> --soop https://play.sooplive.co.kr/<아이디>
```

```bash
debutkit scenes          # OBS 실행 + 도구 > WebSocket 서버 설정 > 사용 체크 후
```

- 오버레이 설정 화면: http://127.0.0.1:8790 (OBS에 붙일 주소 복사, 미리보기, 테스트 채팅·후원)
- 채팅창 모양: `/chat?theme=bubble&font=26&max=10&fade=30&platform=0`
- 내 치지직 채널은 공식 API 권장: `stream2clip chzzk login` 한 번 → `debutkit overlay --chzzk-api`
- OBS에 연결하지 않고 장면 설계도만 보기: `debutkit scenes --dry-run`

## 원칙

| 원칙 | 내용 |
|---|---|
| 조건 없는 오픈소스 | 모든 기능을 누구나 무료로. 소속사 프로그램 참여 여부와 무관 |
| 수집하지 않음 | 사용 통계를 보내지 않음. 오버레이는 이 PC(127.0.0.1)에서만 열리고 채팅을 저장하지 않음 |
| 공식 경로 우선 | 치지직은 공식 Open API를 우선 사용. 비공식 시청자 읽기는 남의 채널 테스트용 |
| 만들지 않고 잇기 | 트래킹(VTube Studio, VSeeFace 등)과 송출(OBS)은 기존 프로그램을 쓰고, 키트는 그 사이를 연결 |

## 소속 버튜버 프로그램 (선택)

debutkit을 만드는 팀은 버튜버 소속사(엔터) 프로젝트를 함께 운영합니다. 원하는 사람만 따로 의향을 등록할 수 있고, **등록하지 않아도 키트는 똑같이 쓸 수 있습니다.** 신청은 계약이 아니며 언제든 철회할 수 있습니다. 구조와 원칙: [docs/MEMBERSHIP.md](docs/MEMBERSHIP.md)

## 문서

| 문서 | 내용 |
|---|---|
| [docs/SOFTWARE.md](docs/SOFTWARE.md) | 버튜버 방송에 필요한 소프트웨어 목록과 키트가 만들 것 / 연결할 것 |
| [docs/SIMILAR_PROJECTS.md](docs/SIMILAR_PROJECTS.md) | 유사 프로젝트 조사와 debutkit이 채우는 빈틈 |
| [docs/MEMBERSHIP.md](docs/MEMBERSHIP.md) | 소속 참여 동의 구조, 법률 확인 목록 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 다음 단계 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 기여 방법(DCO 서명) |

## 개발

```bash
git clone https://github.com/BudongJW/debutkit && cd debutkit
python -m venv .venv && .venv/Scripts/activate      # macOS, Linux: source .venv/bin/activate
pip install -e ".[live,dev]"
pytest -q && ruff check .
```

## 라이선스

[Apache-2.0](LICENSE). 연결하는 외부 프로그램(OBS, VTube Studio 등)은 각자의 라이선스를 따릅니다.
