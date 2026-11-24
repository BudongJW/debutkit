"""debutkit: 버튜버 첫 방송 준비를 묶은 오픈소스 키트.

- ``doctor``  이 PC의 방송 준비 점검
- ``scenes``  OBS 장면 세트 자동 구성
- ``overlay`` CHZZK, SOOP, Twitch 통합 채팅창과 후원 알림
- ``clip``    방송 중 자동 클립 (채팅 급증 판단, OBS 리플레이 버퍼)
- ``tools``   ffmpeg 찾기와 다운로드, 새 버전 확인
- ``chzzk``   치지직 공식 Open API 로그인
- ``broadcast`` OBS 없이 바로 방송(Windows, 송출 화면 창 캡처와 RTMP 송출)
- ``gui``     위 과정을 순서대로 안내하는 설정 마법사

채팅 수신, OBS 제어, 급증 판단은 채팅 연결 모듈(``pip install "debutkit[live]"``)을 쓴다.
"""

__version__ = "1.0.0rc18"
