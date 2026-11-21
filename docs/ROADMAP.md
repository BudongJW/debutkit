# 로드맵

## 0.1 (현재)

| 기능 | 상태 | 확인 |
|---|---|---|
| `doctor` 방송 준비 점검 | 완료 | 실제 Windows PC에서 실행 |
| `doctor --avatar` VRM 사용 조건(stream2clip `vrm`) | 완료 | 단위 테스트 |
| `scenes` OBS 장면 5종 | 완료 | 실제 OBS 33.0.1(Windows)에서 장면 5종·소스 8개 생성, 재실행 시 건너뜀, 장면 스크린샷으로 배치와 채팅 표시 확인. macOS·Linux OBS는 미확인. 아바타 창 지정 문자열은 VTube Studio 실행 상태에서 미확인 |
| `overlay` 통합 채팅·알림 | 완료 | 데모·테스트 버튼을 브라우저로 확인. CHZZK·SOOP 채팅은 실제 방송에서 닉네임 해석 확인(2026-11-21) |
| SOOP 별풍선·애드벌룬 닉네임 칸 | 추정 | 실제 후원 패킷으로 확인 필요 |
| CHZZK 공식 API(`--chzzk-api`) | 완료 | 단위 테스트. 실제 로그인 계정으로는 미확인 |

## 0.2: 설치 없이

- Windows 실행 파일과 설치 프로그램(stream2clip `packaging/` 방식 재사용)
- 처음 실행 시 순서대로 안내하는 설정 마법사(PySide6, stream2clip 테마 공유): 점검 → 트래킹 프로그램 안내 → 장면 만들기 → 오버레이 시작
- OBS 리플레이 버퍼 켜기와 stream2clip 라이브 모드 연결(`--clip`): 채팅이 몰리면 자동으로 클립 저장

## 0.3: 더 많은 점검과 플랫폼

- 업로드 속도 점검(송출 비트레이트 추천)
- 마이크·웹캠 장치 목록 확인
- YouTube 라이브 채팅(공식 Live Streaming API)
- SOOP 공식 API 확인 후 지원
- 오버레이 테마 추가, 커스텀 CSS 갤러리

## 함께 할 일 (stream2clip)

- stream2clip `ChatMessage` 에 화면 표시용 닉네임(`name`, 저장하지 않음)을 추가하면 debutkit의 플랫폼별 변환 코드를 줄일 수 있음
- 방송 기록기(`stream2clip session record`)를 debutkit 설정 마법사에서 바로 켜기

## 소속사 프로젝트

- 소속사 이름, IP 귀속 원칙, 신청서 운영 도구 결정 → [MEMBERSHIP.md](MEMBERSHIP.md) "열린 결정 사항"
- 법률 검토 후 블로그 모집 글 공개
