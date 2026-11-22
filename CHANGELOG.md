# 변경 내역

## 0.5.0 (2026-11-22)

### 추가
- YouTube 라이브 채팅: `overlay --youtube 방송주소 --youtube-key 키`, 마법사 YouTube 칸. 공식 YouTube Data API, 요청 간격 기본 10초(`--youtube-interval`, 최소 5초). 슈퍼챗, 슈퍼스티커, 멤버십 알림. 자동 클립 판단에도 합산
- 업로드 속도 측정과 송출 비트레이트 추천: `doctor --speed`, 마법사 PC 점검 화면 버튼. 측정값의 70% 기준으로 해상도와 영상 비트레이트 추천. 직접 실행할 때만 Cloudflare 측정 서버 연결
- 채팅창 테마 3종: `card`(이름 줄 분리, 플랫폼 색 띠), `outline`(외곽선 글자), `light`(밝은 말풍선)
- 오버레이 설정 화면의 채팅창 모양 선택(테마, 글자 크기, 줄 수, 사라짐, 플랫폼 표시). 선택이 OBS용 주소와 미리보기에 바로 반영
- Windows 설치 프로그램(`setup.exe`): 관리자 권한 없이 설치, 시작 메뉴 바로 가기, ffmpeg 내려받기 선택 작업. 릴리스 빌드에서 조용한 설치, 실행, 제거 확인

### 변경
- 데모 채팅에 YouTube 포함

## 0.4.0 (2026-11-22)

### 추가
- PC 점검: 마이크(사용 중인 입력 장치, 없으면 필요), 웹캠(없으면 주의) 확인
- `debutkit setup --check-update`, 마법사 마무리 단계의 새 버전 확인 버튼. 지정할 때만 GitHub 연결
- 이슈 양식: 문제 제보(`doctor --json` 결과 칸), 기능 제안. 소속 의향 등록은 이슈로 받지 않음 안내
- 사이트 sitemap.xml

### 변경
- 릴리스 노트: CHANGELOG의 해당 버전 항목으로 자동 작성(`packaging/release_notes.py`)

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
