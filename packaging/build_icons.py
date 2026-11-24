"""로고 만들기 아이콘 묶음 만들기(개발용, 배포 파일에는 결과 JSON만 들어감).

원본 저장소에서 버튜버 주제 아이콘만 골라 한국어 이름과 검색어를 붙이고 숫자 자릿수를 줄여
``src/debutkit/overlay/static/vendor/icons/`` 에 gzip 압축 JSON과 라이선스 원문으로 저장한다.

- Microsoft Fluent Emoji(MIT): Flat(컬러 평면)과 High Contrast(단색). Color 판은 SVG 필터가 많아 쓰지 않음
- Phosphor Icons(MIT): 굵기 6종(thin, light, regular, bold, fill, duotone)

원본은 미리 받아 두고 경로를 넘긴다(앱 실행 중에는 인터넷에서 아이콘을 받지 않음)::

    git clone --filter=blob:none --no-checkout --depth 1 https://github.com/microsoft/fluentui-emoji.git fluent
    git -C fluent sparse-checkout set --no-cone /LICENSE "/assets/*/metadata.json" "/assets/*/Flat/" "/assets/*/High Contrast/" \
        "/assets/*/Default/Flat/" "/assets/*/Default/High Contrast/"
    git -C fluent checkout main
    curl -LO https://registry.npmjs.org/@phosphor-icons/core/-/core-2.1.1.tgz && tar -xzf core-2.1.1.tgz
    python packaging/build_icons.py --fluent fluent --phosphor package

색별 넓이(채널 색 다시 칠하기의 기준 색 선택)는 PySide6 SVG 렌더러로 그려서 잰다. 렌더러가 그리지 못하는 아이콘은 실패로 멈춘다.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "debutkit" / "overlay" / "static" / "vendor" / "icons"
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

CATEGORIES = {
    "animal": "동물", "face": "표정", "heart": "하트", "sky": "별과 하늘", "music": "음악과 방송", "game": "게임과 놀이",
    "food": "음식과 디저트", "nature": "꽃과 자연", "fantasy": "판타지", "item": "물건과 기호",
}

#: Fluent Emoji 폴더 이름 | 분류 | 한국어 이름 | 검색어(공백 구분)
FLUENT = """
Cat face|animal|고양이 얼굴|고양이 냥이 냥 얼굴 반려동물
Cat|animal|고양이|고양이 냥이 냥 반려동물
Black cat|animal|검은 고양이|고양이 냥이 검정 흑묘
Grinning cat|animal|웃는 고양이|고양이 냥이 웃음
Grinning cat with smiling eyes|animal|눈웃음 고양이|고양이 냥이 웃음 눈웃음
Smiling cat with heart-eyes|animal|하트 눈 고양이|고양이 냥이 하트 사랑
Kissing cat|animal|뽀뽀하는 고양이|고양이 냥이 뽀뽀
Cat with wry smile|animal|씩 웃는 고양이|고양이 냥이 미소
Cat with tears of joy|animal|웃다 우는 고양이|고양이 냥이 웃음 눈물
Crying cat|animal|우는 고양이|고양이 냥이 눈물 슬픔
Pouting cat|animal|뾰로통한 고양이|고양이 냥이 화남
Weary cat|animal|놀란 고양이|고양이 냥이 놀람
Dog face|animal|강아지 얼굴|강아지 개 멍멍이 댕댕이 얼굴 반려동물
Dog|animal|강아지|강아지 개 멍멍이 댕댕이
Poodle|animal|푸들|강아지 개 푸들
Fox|animal|여우|여우
Wolf|animal|늑대|늑대
Raccoon|animal|너구리|너구리 라쿤
Rabbit face|animal|토끼 얼굴|토끼 토깽이 얼굴
Rabbit|animal|토끼|토끼 토깽이
Hamster|animal|햄스터|햄스터 햄찌
Mouse face|animal|생쥐 얼굴|쥐 생쥐 얼굴
Bear|animal|곰|곰 곰돌이
Polar bear|animal|북극곰|곰 북극곰 흰곰
Panda|animal|판다|판다 곰
Koala|animal|코알라|코알라
Tiger face|animal|호랑이 얼굴|호랑이 범 얼굴
Tiger|animal|호랑이|호랑이 범
Lion|animal|사자|사자
Monkey face|animal|원숭이 얼굴|원숭이 얼굴
See-no-evil monkey|animal|눈 가린 원숭이|원숭이 부끄 부끄러움
Pig face|animal|돼지 얼굴|돼지 꿀꿀 얼굴
Pig|animal|돼지|돼지 꿀꿀
Cow face|animal|소 얼굴|소 젖소 얼굴
Horse face|animal|말 얼굴|말 얼굴
Frog|animal|개구리|개구리
Penguin|animal|펭귄|펭귄 새
Baby chick|animal|병아리|병아리 새 노랑
Front-facing baby chick|animal|정면 병아리|병아리 새 노랑
Hatching chick|animal|알 깨는 병아리|병아리 알 새
Bird|animal|새|새 파랑새
Owl|animal|부엉이|부엉이 올빼미 새 밤
Dove|animal|비둘기|비둘기 새 평화
Duck|animal|오리|오리 새
Swan|animal|백조|백조 새
Parrot|animal|앵무새|앵무새 새
Flamingo|animal|플라밍고|홍학 플라밍고 새
Eagle|animal|독수리|독수리 새
Chicken|animal|닭|닭 새
Hedgehog|animal|고슴도치|고슴도치
Otter|animal|수달|수달
Sloth|animal|나무늘보|나무늘보 느림
Seal|animal|물범|물범 바다표범
Dolphin|animal|돌고래|돌고래 바다
Whale|animal|고래|고래 바다
Spouting whale|animal|물 뿜는 고래|고래 바다
Fish|animal|물고기|물고기 생선 바다
Tropical fish|animal|열대어|물고기 열대어 바다
Blowfish|animal|복어|복어 물고기
Octopus|animal|문어|문어 바다
Jellyfish|animal|해파리|해파리 바다
Crab|animal|게|게 꽃게 바다
Turtle|animal|거북|거북 거북이
Snail|animal|달팽이|달팽이 느림
Butterfly|animal|나비|나비 곤충
Honeybee|animal|꿀벌|벌 꿀벌 곤충
Lady beetle|animal|무당벌레|무당벌레 곤충
Bat|animal|박쥐|박쥐 밤 할로윈
Deer|animal|사슴|사슴 순록
Chipmunk|animal|다람쥐|다람쥐
Beaver|animal|비버|비버
Llama|animal|라마|라마 알파카
Elephant|animal|코끼리|코끼리
Giraffe|animal|기린|기린
Ewe|animal|양|양 털
Snake|animal|뱀|뱀
Sauropod|animal|초식 공룡|공룡 초식공룡
T-rex|animal|티라노사우루스|공룡 티라노
Paw prints|animal|발자국|발바닥 발자국 고양이 강아지 냥젤리
Smiling face with smiling eyes|face|눈웃음|웃음 미소 표정 행복
Grinning face with big eyes|face|활짝 웃는 얼굴|웃음 표정 행복
Beaming face with smiling eyes|face|함박웃음|웃음 표정 행복
Slightly smiling face|face|살짝 미소|미소 표정
Face with tears of joy|face|웃다 우는 얼굴|웃음 눈물 표정
Rolling on the floor laughing|face|데굴데굴 웃음|웃음 표정
Winking face|face|윙크|윙크 표정 장난
Zany face|face|장난꾸러기|장난 표정 메롱
Squinting face with tongue|face|메롱|메롱 장난 표정
Smiling face with heart-eyes|face|하트 눈|하트 사랑 표정
Smiling face with hearts|face|하트 미소|하트 사랑 표정
Face blowing a kiss|face|손키스|뽀뽀 하트 사랑 표정
Star-struck|face|별 눈|별 반짝 감동 표정
Partying face|face|파티 얼굴|파티 축하 생일 표정
Smiling face with sunglasses|face|선글라스 얼굴|선글라스 멋짐 표정
Nerd face|face|안경 얼굴|안경 공부 너드 표정
Thinking face|face|생각하는 얼굴|생각 고민 표정
Pleading face|face|글썽이는 얼굴|부탁 애원 글썽 표정
Face holding back tears|face|눈물 참는 얼굴|눈물 감동 표정
Loudly crying face|face|엉엉 우는 얼굴|눈물 슬픔 울음 표정
Sleeping face|face|자는 얼굴|잠 졸림 표정
Zzz|face|쿨쿨|잠 졸림 쿨쿨
Hugging face|face|포옹|안아줘 포옹 표정
Shushing face|face|쉿|조용 비밀 표정
Melting face|face|녹는 얼굴|녹음 더위 표정
Exploding head|face|머리 폭발|충격 놀람 표정
Upside-down face|face|거꾸로 얼굴|거꾸로 장난 표정
Woozy face|face|어지러운 얼굴|어지러움 표정
Face with spiral eyes|face|빙글빙글 눈|어지러움 표정
Hot face|face|더운 얼굴|더위 표정
Cold face|face|추운 얼굴|추위 겨울 표정
Face savoring food|face|냠냠|맛있음 먹방 표정
Drooling face|face|침 흘리는 얼굴|먹방 표정
Saluting face|face|경례|경례 표정
Face with peeking eye|face|빼꼼|빼꼼 부끄 표정
Smirking face|face|씩 웃는 얼굴|미소 표정
Hundred points|face|100점|만점 백점 최고
Collision|face|쾅|충돌 효과 쾅
Anger symbol|face|화남 표시|화남 효과
Sweat droplets|face|땀방울|땀 효과
Dashing away|face|휙|빠름 효과 바람
Red heart|heart|빨간 하트|하트 사랑 빨강
Pink heart|heart|분홍 하트|하트 사랑 분홍 핑크
Orange heart|heart|주황 하트|하트 사랑 주황
Yellow heart|heart|노란 하트|하트 사랑 노랑
Green heart|heart|초록 하트|하트 사랑 초록
Light blue heart|heart|하늘색 하트|하트 사랑 하늘색
Blue heart|heart|파란 하트|하트 사랑 파랑
Purple heart|heart|보라 하트|하트 사랑 보라
Black heart|heart|검은 하트|하트 사랑 검정
White heart|heart|흰 하트|하트 사랑 하양
Sparkling heart|heart|반짝이는 하트|하트 반짝 사랑
Growing heart|heart|커지는 하트|하트 사랑
Beating heart|heart|두근두근 하트|하트 두근 사랑
Two hearts|heart|하트 두 개|하트 사랑
Revolving hearts|heart|빙글빙글 하트|하트 사랑
Heart with ribbon|heart|리본 하트|하트 리본 선물
Heart with arrow|heart|화살 하트|하트 큐피드 화살
Heart decoration|heart|하트 장식|하트 장식
Heart exclamation|heart|하트 느낌표|하트 느낌표
Heart on fire|heart|불타는 하트|하트 불 열정
Mending heart|heart|붕대 하트|하트 붕대 치유
Love letter|heart|러브레터|편지 하트 사랑
Kiss mark|heart|입술 자국|뽀뽀 키스 입술
Heart suit|heart|하트 카드 무늬|하트 카드 트럼프
Star|sky|별|별 노랑
Glowing star|sky|빛나는 별|별 반짝
Sparkles|sky|반짝임|반짝 빛 별
Sparkle|sky|반짝이|반짝 별
Dizzy|sky|빙글 별|별 어지러움
Shooting star|sky|별똥별|별 유성 소원
Comet|sky|혜성|혜성 별 우주
Eight-pointed star|sky|팔각 별|별 팔각
Crescent moon|sky|초승달|달 밤 초승달
Full moon|sky|보름달|달 밤 보름달
Full moon face|sky|보름달 얼굴|달 얼굴 밤
First quarter moon face|sky|반달 얼굴|달 반달 얼굴 밤
Night with stars|sky|별밤|밤 하늘 별
Milky way|sky|은하수|은하수 우주 별 밤
Ringed planet|sky|토성|행성 우주 토성
Sun|sky|해|해 태양
Sun with face|sky|해 얼굴|해 태양 얼굴
Sun behind cloud|sky|구름 속 해|해 구름 날씨
Cloud|sky|구름|구름 날씨
Rainbow|sky|무지개|무지개 날씨
Snowflake|sky|눈송이|눈 겨울 눈송이
High voltage|sky|번개|번개 전기 에너지
Fire|sky|불꽃|불 열정
Droplet|sky|물방울|물 물방울
Water wave|sky|파도|파도 바다 물결
Cyclone|sky|소용돌이|소용돌이 태풍
Rocket|sky|로켓|로켓 우주 발사
Satellite|sky|인공위성|위성 우주
Studio microphone|music|스튜디오 마이크|마이크 방송 녹음 노래 목소리
Microphone|music|마이크|마이크 노래 노래방 목소리
Headphone|music|헤드폰|헤드폰 음악 듣기
Musical note|music|음표|음악 노래 음표
Musical notes|music|음표들|음악 노래 음표
Musical keyboard|music|건반|피아노 건반 음악
Guitar|music|기타|기타 음악 밴드
Saxophone|music|색소폰|색소폰 음악 재즈
Trumpet|music|트럼펫|트럼펫 음악
Drum|music|북|드럼 북 음악
Radio|music|라디오|라디오 방송 음악
Loudspeaker|music|확성기|확성기 스피커 방송 공지
Megaphone|music|메가폰|메가폰 응원 공지
Speaker high volume|music|스피커|스피커 소리 볼륨
Bell|music|종|종 알림 구독
Television|music|텔레비전|텔레비전 TV 방송
Video camera|music|비디오 카메라|캠코더 영상 녹화 방송
Movie camera|music|영화 카메라|영상 촬영 영화
Camera|music|카메라|카메라 사진
Camera with flash|music|플래시 카메라|카메라 사진 촬영
Clapper board|music|슬레이트|영상 촬영 영화 액션
Film frames|music|필름|필름 영화 영상
Satellite antenna|music|안테나|안테나 방송 송출 위성
Mobile phone|music|휴대폰|휴대폰 스마트폰 전화
Laptop|music|노트북|노트북 컴퓨터
Desktop computer|music|컴퓨터|컴퓨터 PC 데스크톱
Keyboard|music|키보드|키보드 타자 컴퓨터
Computer mouse|music|마우스|마우스 컴퓨터
Speech balloon|music|말풍선|말풍선 채팅 대화
Thought balloon|music|생각 풍선|생각 말풍선
Left speech bubble|music|왼쪽 말풍선|말풍선 채팅 대화
Performing arts|music|연극 가면|가면 연극 공연
Artist palette|music|팔레트|팔레트 그림 미술
Paintbrush|music|붓|붓 그림 미술
Crayon|music|크레용|크레용 그림
Pencil|music|연필|연필 글쓰기 그림
Memo|music|메모|메모 글쓰기
Open book|music|책|책 공부 독서
Video game|game|게임 패드|게임 콘솔 패드 게이머
Joystick|game|조이스틱|게임 오락실 조이스틱
Game die|game|주사위|주사위 게임 보드게임
Puzzle piece|game|퍼즐 조각|퍼즐 게임
Chess pawn|game|체스 말|체스 게임 보드게임
Joker|game|조커 카드|카드 조커 트럼프
Spade suit|game|스페이드|카드 스페이드 트럼프
Diamond suit|game|다이아몬드 카드 무늬|카드 다이아몬드 트럼프
Club suit|game|클로버 카드 무늬|카드 클로버 트럼프
Slot machine|game|슬롯머신|슬롯 게임 행운
Bullseye|game|과녁|과녁 다트 명중
Trophy|game|트로피|트로피 우승 1등
1st place medal|game|금메달|메달 금메달 1등 우승
Sports medal|game|메달|메달 우승
Crossed swords|game|쌍검|검 칼 전투 RPG
Dagger|game|단검|단검 칼 RPG
Bow and arrow|game|활|활 화살 RPG
Shield|game|방패|방패 RPG
Teddy bear|game|곰 인형|곰 인형 장난감
Balloon|game|풍선|풍선 파티
Party popper|game|폭죽|축하 파티 폭죽
Confetti ball|game|축하 구슬|축하 파티
Wrapped gift|game|선물|선물 상자 생일
Ribbon|game|리본|리본 선물 장식
Ticket|game|티켓|티켓 입장권
Kite|game|연|연 놀이
Yo-yo|game|요요|요요 장난감
Soccer ball|game|축구공|축구 공 스포츠
Basketball|game|농구공|농구 공 스포츠
Baseball|game|야구공|야구 공 스포츠
Fireworks|game|불꽃놀이|불꽃놀이 축제 축하
Shortcake|food|조각 케이크|케이크 딸기 디저트
Birthday cake|food|생일 케이크|케이크 생일 디저트 축하
Cupcake|food|컵케이크|케이크 디저트
Doughnut|food|도넛|도넛 디저트
Cookie|food|쿠키|쿠키 과자 디저트
Chocolate bar|food|초콜릿|초콜릿 과자 디저트
Candy|food|사탕|사탕 과자 디저트
Lollipop|food|막대 사탕|사탕 롤리팝 디저트
Custard|food|푸딩|푸딩 커스터드 디저트
Ice cream|food|아이스크림|아이스크림 디저트
Soft ice cream|food|소프트 아이스크림|아이스크림 디저트
Shaved ice|food|빙수|빙수 디저트 여름
Dango|food|경단|경단 당고 떡 디저트
Pancakes|food|팬케이크|팬케이크 디저트 브런치
Waffle|food|와플|와플 디저트
Croissant|food|크루아상|빵 크루아상
Bread|food|빵|빵 식빵
Pie|food|파이|파이 디저트
Honey pot|food|꿀단지|꿀 꿀단지
Strawberry|food|딸기|딸기 과일
Cherries|food|체리|체리 과일
Peach|food|복숭아|복숭아 과일
Grapes|food|포도|포도 과일
Watermelon|food|수박|수박 과일 여름
Banana|food|바나나|바나나 과일
Tangerine|food|귤|귤 오렌지 과일
Lemon|food|레몬|레몬 과일
Red apple|food|사과|사과 과일
Green apple|food|풋사과|사과 과일 초록
Melon|food|멜론|멜론 과일
Pineapple|food|파인애플|파인애플 과일
Avocado|food|아보카도|아보카도
Bubble tea|food|버블티|버블티 밀크티 음료
Hot beverage|food|따뜻한 음료|커피 차 음료
Teacup without handle|food|찻잔|차 녹차 음료
Glass of milk|food|우유|우유 음료
Tropical drink|food|열대 음료|음료 여름
Rice ball|food|주먹밥|주먹밥 오니기리
Sushi|food|초밥|초밥 스시
Steaming bowl|food|라멘|라면 국수 라멘
Pizza|food|피자|피자
Hamburger|food|햄버거|햄버거
French fries|food|감자튀김|감자튀김 감튀
Popcorn|food|팝콘|팝콘 영화
Fried shrimp|food|새우튀김|새우 튀김
Fish cake with swirl|food|어묵|어묵 나루토
Carrot|food|당근|당근 채소
Mushroom|food|버섯|버섯
Cooking|food|달걀 프라이|달걀 계란 프라이
Cherry blossom|nature|벚꽃|벚꽃 꽃 봄
Blossom|nature|꽃|꽃 봄
Tulip|nature|튤립|튤립 꽃
Rose|nature|장미|장미 꽃
Sunflower|nature|해바라기|해바라기 꽃 여름
Hibiscus|nature|히비스커스|꽃 히비스커스
Bouquet|nature|꽃다발|꽃다발 꽃 축하
Four leaf clover|nature|네잎클로버|클로버 행운
Seedling|nature|새싹|새싹 식물 성장
Herb|nature|허브|허브 잎 식물
Maple leaf|nature|단풍잎|단풍 잎 가을
Fallen leaf|nature|낙엽|낙엽 잎 가을
Potted plant|nature|화분|화분 식물
Cactus|nature|선인장|선인장 식물
Palm tree|nature|야자수|야자수 여름 나무
Evergreen tree|nature|상록수|나무 소나무
Deciduous tree|nature|나무|나무
Christmas tree|nature|크리스마스 트리|크리스마스 나무 겨울
Feather|nature|깃털|깃털
Spiral shell|nature|소라|소라 조개 바다
Snowman without snow|nature|눈사람|눈사람 겨울
Ghost|fantasy|유령|유령 귀신 할로윈
Alien|fantasy|외계인|외계인 우주
Alien monster|fantasy|외계 괴물|외계인 우주 게임
Robot|fantasy|로봇|로봇 기계
Skull|fantasy|해골|해골 할로윈
Dragon face|fantasy|용 얼굴|용 드래곤
Dragon|fantasy|용|용 드래곤
Unicorn|fantasy|유니콘|유니콘 말
Smiling face with halo|fantasy|천사 얼굴|천사 착함 표정
Smiling face with horns|fantasy|작은 악마|악마 장난 표정
Angry face with horns|fantasy|화난 악마|악마 화남 표정
Ogre|fantasy|오니 가면|도깨비 오니 가면
Magic wand|fantasy|요술봉|마법 요술봉 마술
Crystal ball|fantasy|수정 구슬|수정 구슬 점 마법
Flying saucer|fantasy|비행접시|비행접시 UFO 외계인
Jack-o-lantern|fantasy|호박 등|호박 할로윈
Moai|fantasy|모아이|모아이 석상
Crown|item|왕관|왕관 왕 공주
Gem stone|item|보석|보석 다이아몬드
Ring|item|반지|반지 보석
Key|item|열쇠|열쇠
Old key|item|옛날 열쇠|열쇠
Light bulb|item|전구|전구 아이디어
Candle|item|양초|양초 촛불
Hourglass not done|item|모래시계|모래시계 시간
Alarm clock|item|알람 시계|시계 알람 시간
Envelope|item|편지 봉투|편지 봉투 우편
Shopping bags|item|쇼핑백|쇼핑 가방
Top hat|item|실크햇|모자 마술 신사
Womans hat|item|챙 모자|모자 리본
Graduation cap|item|학사모|학사모 졸업 공부
Glasses|item|안경|안경
Sunglasses|item|선글라스|선글라스 여름
Lipstick|item|립스틱|립스틱 화장
Handbag|item|핸드백|가방 핸드백
Money bag|item|돈주머니|돈 후원 주머니
Rosette|item|로제트|로제트 장식 꽃
Anchor|item|닻|닻 바다 배
Compass|item|나침반|나침반 여행
Umbrella|item|우산|우산 비
Check mark button|item|체크 표시|체크 확인 완료
Cross mark|item|엑스 표시|엑스 취소
Red question mark|item|물음표|물음표 질문
Red exclamation mark|item|느낌표|느낌표 주의
Infinity|item|무한|무한 반복
"""

#: Phosphor 아이콘 이름 | 분류 | 한국어 이름 | 검색어. 상표(유튜브, 트위치 등 로고) 아이콘은 넣지 않음
PHOSPHOR = """
cat|animal|고양이|고양이 냥이 냥
dog|animal|강아지|강아지 개 멍멍이 댕댕이
rabbit|animal|토끼|토끼
bird|animal|새|새
fish|animal|물고기|물고기 생선
butterfly|animal|나비|나비 곤충
horse|animal|말|말
cow|animal|소|소 젖소
paw-print|animal|발자국|발바닥 발자국 고양이 강아지
feather|animal|깃털|깃털 새
smiley|face|웃는 얼굴|웃음 미소 표정
smiley-wink|face|윙크|윙크 표정
smiley-sticker|face|스티커 얼굴|웃음 스티커 표정
smiley-melting|face|녹는 얼굴|녹음 표정
mask-happy|face|웃는 가면|가면 연극
heart|heart|하트|하트 사랑
heart-straight|heart|각진 하트|하트 사랑
hand-heart|heart|손 하트|하트 손 사랑
star|sky|별|별
star-four|sky|네 꼭짓점 별|별 반짝
sparkle|sky|반짝|반짝 별 빛
shooting-star|sky|별똥별|별 유성
moon|sky|달|달 밤
moon-stars|sky|달과 별|달 별 밤
sun|sky|해|해 태양
cloud|sky|구름|구름 날씨
rainbow|sky|무지개|무지개
lightning|sky|번개|번개 전기
fire|sky|불꽃|불 열정
snowflake|sky|눈송이|눈 겨울
drop|sky|물방울|물 물방울
planet|sky|행성|행성 우주 토성
rocket|sky|로켓|로켓 우주
microphone|music|마이크|마이크 노래 목소리 방송
microphone-stage|music|무대 마이크|마이크 노래 무대
headphones|music|헤드폰|헤드폰 음악
headset|music|헤드셋|헤드셋 게임 마이크
speaker-high|music|스피커|스피커 소리 볼륨
music-note|music|음표|음악 음표 노래
music-notes|music|음표들|음악 음표 노래
vinyl-record|music|레코드판|음반 레코드 음악
piano-keys|music|건반|피아노 건반
guitar|music|기타|기타 음악
radio|music|라디오|라디오 방송
broadcast|music|방송 신호|방송 송출 라이브
television|music|텔레비전|텔레비전 TV 방송
video-camera|music|비디오 카메라|캠코더 영상 녹화
camera|music|카메라|카메라 사진
monitor-play|music|모니터 재생|모니터 영상 재생
waveform|music|소리 파형|소리 파형 음성
chat-circle|music|말풍선|말풍선 채팅
chat-teardrop-dots|music|말풍선 점|말풍선 채팅 대화
palette|music|팔레트|팔레트 그림 미술
paint-brush|music|붓|붓 그림
pencil|music|연필|연필 글쓰기
book|music|책|책 공부
game-controller|game|게임 패드|게임 패드 콘솔
joystick|game|조이스틱|게임 조이스틱
sword|game|검|검 칼 RPG
shield|game|방패|방패 RPG
dice-five|game|주사위|주사위 게임
puzzle-piece|game|퍼즐 조각|퍼즐 게임
trophy|game|트로피|트로피 우승
medal|game|메달|메달 우승
crosshair|game|조준점|조준 FPS 게임
gift|game|선물|선물 상자
balloon|game|풍선|풍선 파티
confetti|game|축하|축하 파티 폭죽
flower|nature|꽃|꽃
flower-lotus|nature|연꽃|연꽃 꽃
flower-tulip|nature|튤립|튤립 꽃
leaf|nature|잎|잎 식물
plant|nature|새싹|새싹 식물
clover|nature|클로버|클로버 행운
tree|nature|나무|나무
cactus|nature|선인장|선인장
cake|food|케이크|케이크 디저트 생일
cookie|food|쿠키|쿠키 과자
ice-cream|food|아이스크림|아이스크림 디저트
coffee|food|커피|커피 음료 카페
pizza|food|피자|피자
hamburger|food|햄버거|햄버거
cherries|food|체리|체리 과일
orange|food|귤|귤 오렌지 과일
avocado|food|아보카도|아보카도
popcorn|food|팝콘|팝콘 영화
bowl-steam|food|김 나는 그릇|라면 국수 밥
ghost|fantasy|유령|유령 귀신 할로윈
skull|fantasy|해골|해골
alien|fantasy|외계인|외계인 우주
robot|fantasy|로봇|로봇 기계
magic-wand|fantasy|요술봉|마법 요술봉
crown|item|왕관|왕관 왕 공주
crown-simple|item|단순한 왕관|왕관
diamond|item|다이아몬드|보석 다이아몬드
lightbulb|item|전구|전구 아이디어
bell|item|종|종 알림 구독
sunglasses|item|선글라스|선글라스 멋짐
ticket|item|티켓|티켓 입장권
hand-waving|item|손 흔들기|인사 안녕 손
hands-clapping|item|박수|박수 축하 손
eye|item|눈|눈 시선
"""

PHOSPHOR_WEIGHTS = ("thin", "light", "regular", "bold", "fill", "duotone")
_NUMBER = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def entries(text: str) -> list[tuple[str, str, str, list[str]]]:
    rows = []
    for line in text.strip().splitlines():
        name, category, korean, tags = (part.strip() for part in line.split("|"))
        assert category in CATEGORIES, line
        rows.append((name, category, korean, tags.split()))
    names = [row[0] for row in rows]
    duplicate = {name for name in names if names.count(name) > 1}
    assert not duplicate, duplicate
    return rows


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def short_numbers(value: str, places: int) -> str:
    """경로의 숫자 자릿수 줄이기(32 격자에서 소수 둘째 자리면 눈으로 구분되지 않음)."""
    def shorten(match: re.Match[str]) -> str:
        number = round(float(match.group(0)), places)
        text = f"{number:.{places}f}".rstrip("0").rstrip(".") if places else str(int(number))
        if text in ("-0", ""):
            text = "0"
        if text.startswith("0.") and len(text) > 2:
            text = text[1:]
        elif text.startswith("-0.") and len(text) > 3:
            text = "-" + text[2:]
        return text

    out = _NUMBER.sub(lambda match: " " + shorten(match), value)
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r" ?([A-Za-z]) ?", r"\1", out)  # 명령 글자 앞뒤 공백
    out = re.sub(r" -", "-", out)  # 음수 앞 공백은 구분자로 필요 없음
    out = re.sub(r"(\.\d+) (\.\d)", r"\1\2", out)  # .5 .5 -> .5.5
    return out.strip()


def compact(svg_text: str, places: int) -> str:
    """주석, 줄바꿈, 크기 속성을 빼고 경로 숫자를 줄인 SVG 문자열."""
    root = ET.fromstring(svg_text)
    for key in ("width", "height"):
        root.attrib.pop(key, None)
    for element in root.iter():
        for key in ("d", "points"):
            if key in element.attrib:
                element.set(key, short_numbers(element.attrib[key], places))
        element.text = None if element.text is None or not element.text.strip() else element.text
        element.tail = None
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)


def colours(svg_text: str) -> list[str]:
    found = re.findall(r'(?:fill|stroke|stop-color)="(#[0-9A-Fa-f]{6})"', svg_text)
    return list(dict.fromkeys(colour.upper() for colour in found))


def render(svg_text: str, size: int = 96):
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    if not renderer.isValid():
        raise ValueError("Qt SVG 렌더러가 읽지 못함")
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    return image


def areas(svg_text: str) -> dict[str, float]:
    """색별 보이는 넓이 비율(렌더 결과 픽셀을 가장 가까운 원래 색으로 나눔). 채널 색 다시 칠하기의 기준 색 고르기에 사용."""
    palette = colours(svg_text)
    image = render(svg_text)
    counts = dict.fromkeys(palette, 0)
    solid = 0
    targets = [(colour, int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)) for colour in palette]
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixel(x, y)
            if (pixel >> 24) & 0xFF < 200:
                continue
            red, green, blue = (pixel >> 16) & 0xFF, (pixel >> 8) & 0xFF, pixel & 0xFF
            solid += 1
            nearest = min(targets, key=lambda item: (item[1] - red) ** 2 + (item[2] - green) ** 2 + (item[3] - blue) ** 2)
            counts[nearest[0]] += 1
    if solid == 0:
        raise ValueError("그려진 픽셀 없음")
    return {colour: round(count / solid, 3) for colour, count in counts.items() if count}


def fluent_folder(root: Path, name: str) -> Path:
    folder = root / "assets" / name
    if not folder.is_dir():
        raise SystemExit(f"Fluent Emoji에 없는 이름: {name}")
    return folder / "Default" if (folder / "Default").is_dir() else folder


def build_fluent(root: Path) -> dict:
    license_text = (root / "LICENSE").read_text(encoding="utf-8")
    if "MIT License" not in license_text or "Microsoft Corporation" not in license_text:
        raise SystemExit("Fluent Emoji LICENSE가 MIT가 아님: 다시 확인")
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    icons = []
    for name, category, korean, tags in entries(FLUENT):
        base = fluent_folder(root, name)
        meta = json.loads((base.parent if base.name == "Default" else base).joinpath("metadata.json").read_text(encoding="utf-8"))
        flat = next((base / "Flat").glob("*.svg"))
        flat_text = flat.read_text(encoding="utf-8")
        if any(word in flat_text for word in ("<filter", "Gradient", "<image", "<mask")):
            raise SystemExit(f"{name}: Flat에 필터, 그라데이션, 이미지가 있음(제외할 것)")
        flat_svg = compact(flat_text, 2)
        variants = {"flat": flat_svg}
        contrast = list((base / "High Contrast").glob("*.svg")) if (base / "High Contrast").is_dir() else []
        mono_text = contrast[0].read_text(encoding="utf-8") if contrast else ""
        if mono_text and not any(word in mono_text for word in ("<filter", "Gradient", "<image", "<mask")):  # 마스크 쓰는 단색판은 빼고 컬러만
            variants["mono"] = compact(mono_text, 2)
        for svg in variants.values():
            render(svg)
        icons.append({"id": f"fluent/{slug(name)}", "name": name, "ko": korean, "tags": list(dict.fromkeys(tags + meta.get("keywords", []))),
                      "category": category, "glyph": meta.get("glyph", ""), "svg": variants, "areas": areas(flat_svg)})
    return {"set": "fluent", "title": "Microsoft Fluent Emoji", "license": "MIT", "copyright": "Copyright (c) Microsoft Corporation.",
            "source": "https://github.com/microsoft/fluentui-emoji", "version": commit,
            "styles": {"flat": "컬러(Flat)", "mono": "단색(High Contrast)"}, "icons": icons}


def build_phosphor(root: Path) -> dict:
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    license_text = (root / "LICENSE").read_text(encoding="utf-8")
    if package.get("license") != "MIT" or "MIT License" not in license_text or "Phosphor Icons" not in license_text:
        raise SystemExit("Phosphor LICENSE가 MIT가 아님: 다시 확인")
    icons = []
    for name, category, korean, tags in entries(PHOSPHOR):
        variants = {}
        for weight in PHOSPHOR_WEIGHTS:
            file = root / "assets" / weight / (f"{name}.svg" if weight == "regular" else f"{name}-{weight}.svg")
            if not file.is_file():
                raise SystemExit(f"Phosphor에 없는 아이콘: {file}")
            svg = compact(file.read_text(encoding="utf-8"), 1)
            render(svg.replace("currentColor", "#000000"))
            variants[weight] = svg
        icons.append({"id": f"phosphor/{name}", "name": name, "ko": korean, "tags": tags, "category": category, "svg": variants})
    return {"set": "phosphor", "title": "Phosphor Icons", "license": "MIT", "copyright": "Copyright (c) 2023 Phosphor Icons",
            "source": "https://github.com/phosphor-icons/core", "version": package["version"],
            "styles": {weight: weight for weight in PHOSPHOR_WEIGHTS}, "icons": icons}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fluent", required=True, type=Path, help="fluentui-emoji 저장소(Flat, High Contrast 부분 받기)")
    parser.add_argument("--phosphor", required=True, type=Path, help="@phosphor-icons/core 묶음을 푼 package 폴더")
    args = parser.parse_args()
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    OUT.mkdir(parents=True, exist_ok=True)
    for name, bundle, license_file in (("fluent-emoji", build_fluent(args.fluent), args.fluent / "LICENSE"),
                                       ("phosphor", build_phosphor(args.phosphor), args.phosphor / "LICENSE")):
        bundle["categories"] = CATEGORIES
        data = (json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        packed = gzip.compress(data, compresslevel=9, mtime=0)  # 같은 입력이면 같은 파일(해시 고정)
        (OUT / f"{name}.json.gz").write_bytes(packed)
        (OUT / f"LICENSE-{name}.txt").write_text(license_text_of(license_file), encoding="utf-8", newline="\n")
        print(f"{name}: 아이콘 {len(bundle['icons'])}개, {len(data) / 1024:.0f} KB(압축 {len(packed) / 1024:.0f} KB), 버전 {bundle['version']}")
    for file in sorted(OUT.iterdir()):
        print(f"  {hashlib.sha256(file.read_bytes()).hexdigest()}  icons/{file.name}")
    return 0


def license_text_of(path: Path) -> str:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").strip().splitlines()]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
