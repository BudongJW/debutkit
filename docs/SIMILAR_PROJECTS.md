# 유사 프로젝트 조사

> 조사일 2026-11-21. GitHub 저장소의 라이선스·최근 활동·★는 GitHub API로 확인한 값. 1차 출처로 확인하지 못한 것은 (미확인). 방송 후 클립 쪽 조사는 stream2clip의 `reports/버튜버 영상 작업 프로젝트 레퍼런스.md` 참고.

## 결론

트래킹, 멀티 플랫폼 채팅 오버레이, 치지직 라이브러리는 이미 있다. 하지만 **"한국 플랫폼 우선 + 버튜버용 OBS 장면 + 데뷔 전 점검 + 클립 연계 + 선택형 소속"을 묶은 오픈소스는 찾지 못했다.** 이름 `debutkit` 은 GitHub, PyPI, npm에서 쓰이지 않는다.

| 우리가 만들 빈틈 | 근거 |
|---|---|
| 공식 API 우선, 한국 플랫폼 통합 채팅·알림(Apache-2.0) | Social Stream Ninja는 CHZZK·SOOP을 지원하지만 GPL-3.0이고 팝아웃 채팅 화면을 긁는 방식. ChaosRat은 SOOP 없음. 나머지는 단일 플랫폼 |
| 열린 라이선스 버튜버 OBS 장면 세트 | 대기·본방송·자리 비움·엔딩 장면을 오픈 라이선스로 공개한 사례 없음(상용 팩만 있음) |
| 데뷔 전 PC 점검 | OBS loganalyzer는 방송 후 로그 진단. 방송 전 점검 도구 없음 |
| 셋업 → 방송 → 클립 연결 | 셋업 도구와 stream2clip 같은 클립 도구를 잇는 프로젝트 없음 |
| 오픈소스 커뮤니티 기반 선택형 소속 | 상용 유사 모델(마스코즈 파트너스, IRIAM 데뷔 지원)만 있고 오픈소스 버전 없음 |

## 1. 버튜버 스타터·셋업 킷

| 이름 | URL | 라이선스 | 최근 활동 | 겹치는 부분 | 빈틈 |
|---|---|---|---|---|---|
| awesome-vtuber | https://github.com/sigvt/awesome-vtuber | NOASSERTION | 2022-11 (방치) | 링크 모음 | 킷, 한국 플랫폼 없음 |
| openvtuberproject | https://github.com/kwea123/openvtuberproject | MIT | 2022-10 | 저비용 툴 모음 | 방치, OBS·채팅 없음 |
| OpenSeeFace | https://github.com/emilianavt/OpenSeeFace | BSD-2 | 2026-09, 2.1k★ | 웹캠 얼굴 트래킹 엔진 | 가져다 쓸 부품 |
| SnekStudio | https://github.com/ExpiredPopsicle/SnekStudio | GPL-3.0 | 2026-11, 432★ | 오픈소스 버튜버 앱 | OBS 장면, 채팅, 한국 플랫폼 없음 |
| OWL VTuberStudio | https://github.com/Off-World-Live-Collaborative/VTuberStudio | Apache-2.0 | 2024-02 | 언리얼 3D 스튜디오 템플릿 | 초보자용 아님 |
| OBS loganalyzer | https://github.com/obsproject/loganalyzer | GPL-2.0 | 2026-10 | OBS 설정 문제 진단 | 방송 후 로그 기준, 버튜버 특화 없음 |
| vTuber Kit | https://kyuppin.itch.io/vtuber-kit | (미확인) | 2025-10 | 2D 아바타 + OpenSeeFace 올인원 | OBS 템플릿, 채팅 없음 |

## 2. CHZZK·SOOP 채팅·알림 오버레이

| 이름 | URL | 라이선스 | 최근 활동 | 겹치는 부분 | 빈틈 |
|---|---|---|---|---|---|
| Social Stream Ninja | https://github.com/steveseguin/social_stream | GPL-3.0 | 2026-11, 1.2k★ | CHZZK·SOOP 포함 120개 이상 플랫폼 | 화면 긁기 방식, GPL이라 코드 혼합 불가. 호환 대안으로만 안내 |
| ChaosRat | https://github.com/yf-dev/chaosrat | README상 MIT (LICENSE 파일 미감지) | 2026-11, 9★ | CHZZK·Twitch·YouTube·Kick 통합 채팅 | SOOP 없음 |
| ChzzkHelper | https://github.com/LeinneSW/ChzzkHelper | LGPL-2.1 | 2026-03 | 투표, 알림, 채팅 위젯 | CHZZK만 |
| soop-chat-mini | https://github.com/return0927/soop-chat-mini | LGPL-3.0 | 2025-02 | SOOP 채팅 위젯 | SOOP만, 휴면 |
| chzzkpy | https://github.com/gunyu1019/chzzkpy | MIT | 2026-11, 47★ | Python CHZZK 채팅·후원 | 라이브러리 |
| CHZZK 공식 Session API | https://chzzk.gitbook.io/chzzk/chzzk-api/session | 공식 API | 운영 중 | 내 채널의 채팅·후원·구독 이벤트 | debutkit `--chzzk-api` 가 사용(stream2clip 경유) |

- SOOP은 자체 위젯 URL을 OBS 브라우저 소스로 붙이는 공식 기능이 있다. SOOP 공식 Open API에 채팅·별풍선 이벤트가 있는지는 (미확인).
- 비공식 CHZZK 채팅 접속(로그인 없는 시청자 읽기)은 네이버가 승인한 방식이 아니다. 내 채널은 공식 API(`--chzzk-api`)를 권장한다.

## 3. 소속사 연계, 데뷔 지원

| 이름 | URL | 형태 | 겹치는 부분 | 빈틈 |
|---|---|---|---|---|
| 마스코즈 MASCOZ (오버더핸드) | https://welcon.kocca.kr/en/directory/content/mascoz--7962 | 상용 | 무료 3D 아바타, 트래킹, OBS 연동 + 파트너스 프로그램으로 신인 육성. **가장 가까운 모델** | 오픈소스 아님, 3D 중심, Live2D·멀티 채팅 없음 |
| SOOP 웰컴 버추얼·모션캡처 스튜디오 | https://newsis.com/view/NISX20260803_0003734436 | 플랫폼 지원 | 신규 버추얼 스트리머 정착 지원 | 3D 아바타 보유자 대상, 소프트웨어 킷 아님 |
| 치지직 모션스테이지·챌린저 등급 | https://ddaily.co.kr/page/view/2025031111315578513 | 플랫폼 지원 | 스튜디오, 제작비 지원 | 데뷔 전 셋업 지원 없음 |
| IRIAM Debut Support Program | https://us.iriam.com/debut-support-program | 상용 | 무료 캐릭터 일러스트 + 앱 데뷔 | 모바일 앱 전용, 북미 한정 |

- "오픈소스 사용자·기여자가 소속 버튜버가 되는" 사례는 찾지 못했다. 그만큼 신뢰 설계가 중요하다: 텔레메트리 없음, 명시적 선택, 소속과 무관한 전체 기능 제공([MEMBERSHIP.md](MEMBERSHIP.md)).
- 플랫폼의 스튜디오·제작비 지원은 우리가 만들 것이 아니라 블로그와 키트에서 "지원 프로그램 안내"로 연결한다.

## 4. 이름

| 이름 | GitHub | PyPI | npm |
|---|---|---|---|
| debutkit | 0건 | 없음 | 없음 |
| stream2debut | 0건 | 없음 | 없음 |

검색 결과 상위는 무관한 "Alesis Debut Kit"(전자드럼). 상표(KIPRIS)는 확인하지 않았다.
