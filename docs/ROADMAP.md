# 로드맵

## 0.1 (완료)

| 기능 | 확인 |
|---|---|
| `doctor` 방송 준비 점검, `--avatar` VRM 사용 조건(stream2clip `vrm`) | 실제 Windows PC에서 실행, 단위 테스트 |
| `scenes` OBS 장면 5종 | 실제 OBS 33.0.1(Windows)에서 장면 5종·소스 8개 생성, 재실행 시 건너뜀, 장면 스크린샷으로 배치 확인 |
| `overlay` 통합 채팅·알림 | 브라우저로 데모·테스트 확인. CHZZK·SOOP 실방송 채팅의 닉네임 해석 확인(2026-11-21) |

## 0.2 (완료): 설치 없이, 방송 중 자동 클립

| 기능 | 확인 |
|---|---|
| 설정 마법사(PySide6, stream2clip 스타일 공유) | 가짜 동작으로 단위 테스트 7개. 실제 동작으로 OBS 33 연결 → 장면 → 오버레이 → 자동 클립까지 창에서 실행 |
| 자동 클립 `overlay --clip` (stream2clip `SurgeDetector` + `ReplayClipper`) | 실제 OBS 33에서 `!clip` 13초 뒤 24초 길이 클립 저장 |
| `scenes --replay-buffer` | 실제 OBS 33: 설정은 바로 저장, **버퍼는 OBS 재시작 후 사용 가능**(프로필 전환으로 다시 읽게 하는 방법은 동작하지 않고 프로필을 남겨서 쓰지 않음) |
| Windows 실행 파일 | 로컬 빌드 zip 72 MB(풀면 163 MB). 파이썬 없이 `--version`, `doctor`, `scenes --dry-run`, 창 열고 닫기 확인 |

## 아직 확인하지 못한 것

- SOOP 별풍선·애드벌룬·영상풍선의 닉네임 칸(실제 후원 패킷 필요)
- VTube Studio 실행 중일 때 아바타 창 지정 문자열(`VTube Studio:UnityWndClass:VTube Studio.exe`)
- macOS, Linux의 OBS 장면 구성(소스 종류 이름)
- CHZZK 공식 API를 실제 로그인 계정으로
- 고급 출력 모드(AdvOut)에서 리플레이 버퍼 켜기

## 0.3: 더 쉬운 시작

- 마법사에서 ffmpeg 내려받기(stream2clip `tools.install_ffmpeg` 재사용)
- 업로드 속도 점검(송출 비트레이트 추천), 마이크·웹캠 장치 확인
- YouTube 라이브 채팅(공식 Live Streaming API)
- 아이콘과 설치 프로그램(Inno Setup, stream2clip 방식)
- 오버레이 테마 추가

## 함께 할 일 (stream2clip)

- `ChatMessage` 에 화면 표시용 닉네임(`name`, 저장하지 않음)을 추가하면 debutkit의 플랫폼별 변환 코드를 줄일 수 있음
- 자동 클립의 안내 문구(리플레이 버퍼 길이 부족 등)가 영어로 나옴 → stream2clip 번역 목록에 추가
- 방송 기록기(`stream2clip session record`)를 마법사에서 바로 켜기

## 소속사 프로젝트

- 소속사 이름, IP 귀속 원칙, 신청서 운영 도구, 프로그램 라이선스 비용 부담 결정 → [MEMBERSHIP.md](MEMBERSHIP.md) "열린 결정 사항"
- 법률 검토 후 블로그 모집 글 공개
