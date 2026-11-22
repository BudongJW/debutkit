# 유사 프로젝트 조사

- 조사일: 2026-11-21
- GitHub 저장소의 라이선스, 최근 활동, 별 수는 GitHub API 확인 값
- 1차 출처 미확인 항목은 (미확인) 표시

## 조사 결과

- 기존 사례가 있는 분야: 트래킹, 멀티 플랫폼 채팅 오버레이, 치지직 라이브러리
- 사례가 없는 분야: 한국 플랫폼 우선 지원, 버튜버용 OBS 장면, 데뷔 전 점검, 방송 중 자동 클립, 선택형 소속을 함께 제공하는 오픈소스
- `debutkit` 이름은 GitHub, PyPI, npm에서 사용되지 않음

| debutkit 차별점 | 근거 |
|---|---|
| 공식 API 우선, 한국 플랫폼 통합 채팅과 알림(Apache-2.0) | Social Stream Ninja는 CHZZK, SOOP 지원하나 GPL-3.0, 팝아웃 채팅 화면 수집 방식. ChaosRat은 SOOP 미지원. 나머지는 단일 플랫폼 |
| 열린 라이선스 버튜버 OBS 장면 세트 | 대기, 본방송, 자리 비움, 엔딩 장면의 오픈 라이선스 공개 사례 없음(상용 팩만 존재) |
| 데뷔 전 PC 점검 | OBS loganalyzer는 방송 후 로그 진단. 방송 전 점검 도구 없음 |
| 방송 준비부터 방송 중 클립까지 연결 | 방송 준비 도구와 클립 도구를 연결한 프로젝트 없음 |
| 오픈소스 커뮤니티 기반 선택형 소속 | 상용 유사 모델(마스코즈 파트너스, IRIAM 데뷔 지원)만 존재 |

## 1. 버튜버 시작용 도구 모음

| 이름 | URL | 라이선스 | 최근 활동 | 공통 기능 | 부족한 점 |
|---|---|---|---|---|---|
| awesome-vtuber | https://github.com/sigvt/awesome-vtuber | NOASSERTION | 2022-11 (방치) | 링크 모음 | 킷, 한국 플랫폼 없음 |
| openvtuberproject | https://github.com/kwea123/openvtuberproject | MIT | 2022-10 | 저비용 툴 모음 | 방치, OBS와 채팅 없음 |
| OpenSeeFace | https://github.com/emilianavt/OpenSeeFace | BSD-2 | 2026-09, 별 2.1k | 웹캠 얼굴 트래킹 엔진 | 활용 가능 부품 |
| SnekStudio | https://github.com/ExpiredPopsicle/SnekStudio | GPL-3.0 | 2026-11, 별 432 | 오픈소스 버튜버 앱 | OBS 장면, 채팅, 한국 플랫폼 없음 |
| OWL VTuberStudio | https://github.com/Off-World-Live-Collaborative/VTuberStudio | Apache-2.0 | 2024-02 | 언리얼 3D 스튜디오 템플릿 | 초보자용 아님 |
| OBS loganalyzer | https://github.com/obsproject/loganalyzer | GPL-2.0 | 2026-10 | OBS 설정 문제 진단 | 방송 후 로그 기준, 버튜버 특화 없음 |
| vTuber Kit | https://kyuppin.itch.io/vtuber-kit | (미확인) | 2025-10 | 2D 아바타, OpenSeeFace 올인원 | OBS 템플릿, 채팅 없음 |

## 2. CHZZK, SOOP 채팅과 알림 오버레이

| 이름 | URL | 라이선스 | 최근 활동 | 공통 기능 | 부족한 점 |
|---|---|---|---|---|---|
| Social Stream Ninja | https://github.com/steveseguin/social_stream | GPL-3.0 | 2026-11, 별 1.2k | CHZZK, SOOP 포함 120개 이상 플랫폼 | 화면 수집 방식, GPL이라 코드 혼합 불가. 호환 대안으로만 안내 |
| ChaosRat | https://github.com/yf-dev/chaosrat | README상 MIT (LICENSE 파일 미감지) | 2026-11, 별 9 | CHZZK, Twitch, YouTube, Kick 통합 채팅 | SOOP 없음 |
| ChzzkHelper | https://github.com/LeinneSW/ChzzkHelper | LGPL-2.1 | 2026-03 | 투표, 알림, 채팅 위젯 | CHZZK만 |
| soop-chat-mini | https://github.com/return0927/soop-chat-mini | LGPL-3.0 | 2025-02 | SOOP 채팅 위젯 | SOOP만, 휴면 |
| chzzkpy | https://github.com/gunyu1019/chzzkpy | MIT | 2026-11, 별 47 | Python CHZZK 채팅, 후원 | 라이브러리 |
| CHZZK 공식 Session API | https://chzzk.gitbook.io/chzzk/chzzk-api/session | 공식 API | 운영 중 | 내 채널의 채팅, 후원, 구독 이벤트 | debutkit `--chzzk-api` 가 사용 |

- SOOP: 자체 위젯 주소를 OBS 브라우저 소스로 붙이는 공식 기능 존재. 공식 Open API의 채팅, 별풍선 이벤트 제공 여부 (미확인)
- 비공식 CHZZK 채팅 접속(로그인 없는 수신)은 네이버가 승인한 방식이 아님. 본인 채널은 공식 API(`--chzzk-api`) 사용 권장

## 3. 소속사 연계, 데뷔 지원

| 이름 | URL | 형태 | 공통 기능 | 부족한 점 |
|---|---|---|---|---|
| 마스코즈 MASCOZ (오버더핸드) | https://welcon.kocca.kr/en/directory/content/mascoz--7962 | 상용 | 무료 3D 아바타, 트래킹, OBS 연동, 파트너스 프로그램으로 신인 육성. **가장 가까운 모델** | 오픈소스 아님, 3D 중심, Live2D와 멀티 채팅 없음 |
| SOOP 웰컴 버추얼, 모션캡처 스튜디오 | https://newsis.com/view/NISX20260803_0003734436 | 플랫폼 지원 | 신규 버추얼 스트리머 정착 지원 | 3D 아바타 보유자 대상, 소프트웨어 킷 아님 |
| 치지직 모션스테이지, 챌린저 등급 | https://ddaily.co.kr/page/view/2025031111315578513 | 플랫폼 지원 | 스튜디오, 제작비 지원 | 데뷔 전 셋업 지원 없음 |
| IRIAM Debut Support Program | https://us.iriam.com/debut-support-program | 상용 | 무료 캐릭터 일러스트, 앱 데뷔 | 모바일 앱 전용, 북미 한정 |

- 오픈소스 사용자나 기여자가 소속 버튜버로 이어지는 사례는 확인되지 않음
- 따라서 신뢰 확보 장치가 필요함: 텔레메트리 없음, 명시적 선택, 소속과 무관한 전체 기능 제공([MEMBERSHIP.md](MEMBERSHIP.md))
- 플랫폼의 스튜디오, 제작비 지원은 개발 대상이 아님. 사이트와 키트에서 지원 프로그램으로 안내

## 4. 이름

| 이름 | GitHub | PyPI | npm |
|---|---|---|---|
| debutkit | 0건 | 없음 | 없음 |
| stream2debut | 0건 | 없음 | 없음 |

- 검색 상위 결과는 무관한 제품(Alesis Debut Kit, 전자드럼)
- 상표(KIPRIS) 미확인
