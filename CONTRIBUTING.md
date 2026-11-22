# 기여 안내

- 대상: 버그 제보, 문서, 번역, 장면 디자인, 코드
- **소속사 프로그램과 무관**: 기여해도 소속 의무 없음, 소속에 기여 조건 없음

## DCO 서명

- 별도 기여자 라이선스 계약(CLA) 없음
- 커밋마다 [Developer Certificate of Origin](https://developercertificate.org/) 동의 서명 첨부
- 의미: 기여할 권리 보유, 프로젝트 라이선스(Apache-2.0) 공개 동의

```bash
git commit -s -m "변경 내용"
```

- `-s` 사용 시 커밋 메시지 끝에 `Signed-off-by: 이름 이메일` 추가
- 활동명, GitHub noreply 이메일 사용 가능(실명 불필요)

## 개발 환경

```bash
pip install -e ".[gui,dev]"
pytest -q
ruff check .
```

| 기준 | 내용 |
|---|---|
| 테스트 | 새 기능에 테스트 추가. OBS, 치지직, SOOP 등 외부 서비스는 가짜 구현으로 대체. 실제 서비스 확인 여부는 PR에 기재 |
| 개인정보 | 테스트 데이터에 실제 시청자 닉네임, 채팅 사용 금지 |
| 라이선스 | GPL 코드(Social Stream Ninja, OBS 플러그인 등) 복사 금지. 참고만 허용 |
| 문서 | 사용법 변경 시 README, `docs/`, `site/` 함께 수정 |
| 표기 | 개조식. 중간점, 꺽쇠, 화살표 등 특수문자 미사용(`tests/test_site.py` 로 확인) |

## 프로젝트 사이트

- 위치: `site/` (HTML, CSS만 사용)
- 확인: `python packaging/build_site.py` 후 `dist/site/index.html` 열기. 깨진 내부 링크가 있으면 실패
- 배포: main 반영 시 `.github/workflows/pages.yml` 이 https://budongjw.github.io/debutkit/ 에 게시
- 소식 글 추가: `site/news.html` 맨 위에 `article class="post"` 추가, `site/index.html` 소식 목록 갱신

## 금지 사항

- 사용자 동의 없이 정보를 외부로 보내는 기능(텔레메트리, 자동 신청 등)
- 소속 신청을 기능 사용 조건으로 만드는 변경
