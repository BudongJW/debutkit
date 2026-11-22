# 변경 내역

## 0.3.0 (2026-11-22)

### 추가
- `debutkit setup`: ffmpeg, 채팅 연결 모듈 확인. `--ffmpeg` 로 ffmpeg 내려받기(Windows, SHA-256 확인), `--from` 으로 이미 받은 압축 파일 사용
- `debutkit chzzk login`, `logout`: 치지직 공식 Open API 로그인, 토큰 삭제. 안내 문구 한국어
- 설정 마법사
  - PC 점검 화면에 ffmpeg 내려받기 버튼(ffmpeg 없음 표시 시). 진행률 표시, 완료 후 자동 재점검
  - 채팅과 알림 단계에 치지직 API 칸(Client ID, Client Secret)과 로그인 버튼. Secret은 파일 저장 없이 실행 중에만 사용
  - 마무리 단계에 자동 클립 저장 폴더 표시와 열기 버튼
- 오버레이 설정 화면에 방장 !clip 테스트 버튼(자동 클립 시험)
- 프로젝트 사이트(https://budongjw.github.io/debutkit/): 사용 설명서, 방송 소프트웨어, 소식, 참여 안내. `site/`, `packaging/build_site.py`, Pages 워크플로

### 변경
- PC 점검의 ffmpeg 확인: PATH와 내려받은 위치 모두 확인
- PC 점검 항목 이름: 채팅 연결 모듈(OBS 장면, 채팅창, 자동 클립에 필요). 미설치 시 주의
- PC 점검 해결 방법 표시: `해결:` 머리말
- 안내 주소: 계정 블로그에서 프로젝트 사이트로 이전
- 문서, 화면 문구: 개조식, 특수문자(중간점, 꺽쇠, 화살표) 미사용. 테스트로 확인

### 수정
- `overlay --clip` 에서 OBS 연결 실패 시 프로그램이 끝나지 않던 문제(시작 전 서버 정지 처리)
- 내려받은 ffmpeg를 PC 점검이 찾지 못하던 문제
- ffmpeg 없이 자동 클립을 켜면 클립마다 실패하던 문제: 시작 전 확인 후 안내
- 자동 클립 안내(리플레이 버퍼 길이 부족, 버퍼 꺼짐, ffmpeg 없음)의 영어 표시: 한국어로 변경

## 0.2.0 (2026-11-21)

- **설정 마법사** `debutkit-gui`, `debutkit gui`: PC 점검, 아바타 사용 조건, OBS 장면, 채팅과 알림(자동 클립 포함), 마무리 5단계
- **자동 클립** `overlay --clip`: 채팅 급증이나 방장의 `!clip` 시 OBS 리플레이 버퍼를 클립으로 저장. 결과는 설정 화면에 표시
- `scenes --replay-buffer [초]`: OBS 리플레이 버퍼 설정 켜기와 시작. 최초 설정 시 OBS 재시작 안내(OBS 33에서 확인)
- Windows 실행 파일: `packaging/build_windows.py`(PyInstaller, 실행 확인 포함), 태그 릴리스 워크플로
- `/test` 에 `"role": "owner"` 로 방장 표시 명령 시험

## 0.1.0 (2026-11-21)

- `doctor`, `scenes`, `overlay` 첫 공개
