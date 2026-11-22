debutkit 브랜드 파일 (컨셉 D, 귀 달린 마이크)
==============================================

구성
  board.png        컨셉 보드
  symbol/          심볼, 투명 배경. symbol-small 은 32px 이하용 단순화 버전
  wordmark/        글자(윤곽선 처리, 폰트 설치 불필요)
  lockup/          심볼과 글자 조합. horizontal(가로형), vertical(세로형)
  app-icon/        1024px 앱 아이콘. dark, light, dark_rounded(모서리 둥근 버전)
                   debutkit.ico 는 packaging/build_brand.py 로 생성(Windows 실행 파일 아이콘)
  favicon/         favicon.ico(16, 32, 48), favicon-16 에서 512 PNG, favicon.svg

파일 이름
  _dark-bg   어두운 배경용
  _light-bg  밝은 배경용
  SVG는 벡터 원본, PNG는 투명 배경(앱 아이콘 제외)

컬러
  Pink       #FF4F8B  메인 포인트(심볼, 어두운 배경 위 kit)
  Pink Deep  #BF3B68  밝은 배경 위 글자(크림 배경 대비 4.9:1)
  Slate      #1E2327  배경, 글자
  Cream      #FAF7F5  밝은 배경

서체(SIL Open Font License)
  워드마크  Jua
  태그라인  Noto Sans KR

사용처
  사이트 헤더, 파비콘, 공유 이미지  packaging/build_site.py 가 복사
  Windows 실행 파일 아이콘           app-icon/debutkit.ico
  설정 마법사 창 아이콘              src/debutkit/gui/icon.png
  오버레이 설정 화면 탭 아이콘       src/debutkit/overlay/static/favicon.svg

최종 채택 전 상표 검색(KIPRIS 등) 권장
