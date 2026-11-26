debutkit 브랜드 파일 (메인 캐릭터 데비, 작은 심볼 마이)
====================================================

구성
- board.png     컨셉 보드(로고, 앱 아이콘, 파비콘, 색, 캐스트)
- symbol/       심볼(데비 배지), 투명 배경. symbol-small 은 32px 이하용(마이 단순화), mai 는 마이 전체 그림
- wordmark/     글자(윤곽선, 글꼴 설치 불필요). i의 점 자리는 노란 별
- lockup/       심볼과 글자 조합. horizontal(가로형), vertical(세로형)
- app-icon/     1024px 앱 아이콘(데비). dark, dark_rounded(모서리 둥근), light. debutkit.ico 는 Windows 실행 파일 아이콘(32px 이하는 마이)
- favicon/      favicon.svg, favicon.ico(16, 32, 48), favicon-16 에서 512 PNG
- mascot/       마스코트 캐스트 시안과 생성 기록(mascot/README.txt)

다시 만들기
- 모든 파일은 packaging/build_brand.py 가 만든다(직접 고치지 않음)
    python packaging/build_brand.py
- 필요: Pillow, fontTools, brotli, Chrome 또는 Edge(PNG를 그리는 데)

파일 이름
- _dark-bg   어두운 배경용(심볼 바깥에 흰 스티커 테두리, 글자는 흰색과 밝은 라벤더)
- _light-bg  밝은 배경용
- SVG는 벡터 원본, PNG는 투명 배경(앱 아이콘 제외)

심볼
- 메인 캐릭터 데비(데뷔 준비생): 라벤더 원형 배지 위 상반신. 원본 mascot/source/debi_1024.png
  - FLUX.1 schnell(Apache-2.0) 시안, 배경 제거. 생성 기록 mascot/draft/manifest.json
  - AI 생성물 자체는 저작물로 보호되지 않아 대표 그림은 사람 손질이나 다시 그리기 권장
- 작은 심볼 마이(리본 마이크): 파비콘, 32px 이하. build_brand.py 에서 도형으로 직접 그린 벡터
  - 은색 막대 2개 아래 줄 없는 얼굴판에 얼굴(눈과 입이 줄, 외곽선과 겹치지 않게), 양옆 민트 음파, 꼭대기 코랄 불, 노란 띠
  - 작은 크기: 음파, 받침, 불을 빼고 몸과 얼굴만

컬러
- Lavender        #A98BF7  심볼 몸, 어두운 배경의 강조
- Lavender Text   #5B3FC4  밝은 배경 위 글자와 링크(흰 배경 대비 약 7:1)
- Lavender Light  #C2ADFF  어두운 배경 위 kit
- Ink             #231B3D  외곽선, 글자, 어두운 배경
- Mint            #45D6B8  음파
- Yellow          #FFC93C  띠, 별
- Coral           #FF6F6F  꼭대기 불
- Cream           #FAF7F5  밝은 배경
- stream2clip(키리: 분홍, 크림, 검정)과 겹치지 않게 라벤더, 민트, 노랑 중심

서체(SIL Open Font License)
- 워드마크: Pretendard Bold(함께 배포한 글꼴, 윤곽선으로 변환)

사용처
- 사이트 헤더, 파비콘, 공유 이미지: packaging/build_site.py 가 복사
- 기본 캐릭터(PNGTuber 4상태): src/debutkit/overlay/static/character/sample(데비)
- Windows 실행 파일 아이콘: app-icon/debutkit.ico
- 설정 마법사 창 아이콘: src/debutkit/gui/icon.png
- 오버레이 화면 탭 아이콘: src/debutkit/overlay/static/favicon.svg

유의 사항
- 최종 채택 전 상표 검색(KIPRIS 등) 권장
