# 변경 내역

## 0.2.0 (2026-11-21)

- **설정 마법사** `debutkit-gui` / `debutkit gui`: PC 점검, 아바타 사용 조건, OBS 장면, 채팅·알림(자동 클립 포함), 마무리 5단계. stream2clip 앱과 같은 스타일
- **자동 클립** `overlay --clip`: 오버레이가 받은 채팅을 stream2clip 라이브 모드에 넘겨, 채팅 급증이나 방장의 `!clip` 때 OBS 리플레이 버퍼를 클립으로 저장. 결과는 설정 화면에 표시
- `scenes --replay-buffer [초]`: OBS 리플레이 버퍼 설정을 켜고 시작. 처음 켠 경우 OBS 재시작이 필요하다고 안내(OBS 33에서 확인)
- Windows 실행 파일: `packaging/build_windows.py`(PyInstaller, 만든 프로그램 실행 확인 포함), 태그 릴리스 워크플로
- `/test` 에 `"role": "owner"` 로 방장 표시 명령 시험
- doctor의 소프트웨어 목록 안내를 블로그 주소로

## 0.1.0 (2026-11-21)

- `doctor`, `scenes`, `overlay` 첫 공개
