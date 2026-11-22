# 캐릭터 기능 참고 자료와 설계

캐릭터 등록, 제작, Live2D와 3D 방송 기능의 근거 자료와 debutkit의 처리 방식. 조사 기준일 2026-11-22(약관 항목 2026-11-23 보완). 가격과 약관은 바뀔 수 있으므로 사용 전 각 공식 페이지에서 다시 확인.

## 요약

| 캐릭터 종류 | 등록(업로드) | 방송 | debutkit 처리 |
|---|---|---|---|
| PNGTuber(이미지 2장에서 4장) | 이미지 형식, 크기 확인 | debutkit 캐릭터 화면(OBS 브라우저 소스)이 목소리 크기로 이미지 전환 | 직접 구현 |
| 3D(VRM 0.x, 1.0) | 파일 구조, 사용 조건, 미리보기 이미지 읽기 | debutkit 캐릭터 화면이 three-vrm으로 표시, 목소리로 입 움직임, 자동 눈 깜빡임과 호흡. 또는 Warudo, VSeeFace 등으로 전달 | 직접 구현과 연계 |
| 3D(GLB, FBX) | 뼈 이름으로 사람 모양 뼈 15개 확인, 표정 이름 대응, 외부 텍스처 확인 | debutkit 캐릭터 화면이 VRM과 같은 방식으로 표시(입, 눈, 머리, 호흡, 얼굴 추적) | 직접 구현(1.0.0rc6) |
| Live2D | model3.json과 참조 파일 확인 | VTube Studio로 전달(모델 폴더에 복사) | 연계. 직접 표시하지 않음(라이선스) |
| Inochi2D | 파일 머리글 확인 | Inochi Session 안내 | 안내 |

- 목소리 크기는 OBS WebSocket의 입력 음량(InputVolumeMeters)을 사용. OBS에 설정한 마이크와 필터를 그대로 쓰고 추가 장치 권한이 필요 없음
- 웹캠 얼굴 추적: OBS 브라우저 소스는 카메라를 쓸 수 없어(아래 참고) 일반 브라우저에서 여는 추적 화면(`/tracker`)이 MediaPipe로 값을 계산하고 캐릭터 화면으로 전달(1.0.0rc3)

## 1. 캐릭터 제작 도구

| 종류 | 도구 | 가격 | 방송 사용 조건 | 운영체제 | 비고 |
|---|---|---|---|---|---|
| 3D | VRoid Studio | 무료 | 출력 모델은 개인, 법인 모두 상업 이용 가능(샘플 모델, 구매 텍스처 등은 별도 조건) | Windows, macOS, iPad. Linux 없음 | 한국어 화면(v2.5.0부터). 초보자용. VRM 0.0과 1.0 선택(의상 기능은 1.0만). https://store.steampowered.com/app/1486350/VRoid_Studio/ |
| 3D | VRM Add-on for Blender | 무료(MIT 또는 GPL-3.0 이상) | 해당 없음 | Windows, macOS, Linux | 숙련자용. https://extensions.blender.org/add-ons/vrm/ |
| 3D | Vket Avatar Maker | 무료 | 개인의 방송, 상업적 출연 허용. 법인(소속사) 사용은 HIKKY 사전 확인 필요. 저작권은 HIKKY. 모델 데이터 판매, 배포, 앱 포함 금지 | 웹(Linux 포함) | 약관 버전 2(2025-04-03 갱신, 부칙 2025-06-12). https://account.vket.com/terms?locale=en |
| 3D | Mixamo(Adobe) | 무료(Adobe 계정) | 프로젝트 안 사용료 없음. 원본 캐릭터, 동작 파일 재배포 금지 | 웹 | 사람 모양 모델에 뼈 자동 추가(두 발 사람형). FBX로 받아 debutkit에 등록. https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html |
| 3D | Ready Player Me | 서비스 종료(2026-01-31) | 해당 없음 | 해당 없음 | https://techcrunch.com/2025/12/19/netflix-acquires-gaming-avatar-maker-ready-player-me/ |
| Live2D | Live2D Cubism Editor FREE | 무료 | 개인, 연매출 1,000만 엔 미만 사업자는 상업적 이용 가능 | Windows, macOS | 텍스처 1장(2048px), 아트메시 100개, 파라미터 30개 등 제한. https://www.live2d.com/en/cubism/comparison/ |
| Live2D | Live2D Cubism Editor PRO | 개인, 소규모 사업자 월 2,080엔(첫해 14,280엔) | 같음 | Windows, macOS | 42일 체험. https://store.live2d.com/en/ |
| 2D | Inochi Creator(Inochi2D) | Steam 32,000원(얼리 액세스) | BSD-2 | Windows, macOS, Linux | 2년 이상 갱신 없음. https://store.steampowered.com/app/2108550/ |
| PNGTuber | 일반 그림 도구 | 해당 없음 | 그린 사람의 조건 | 해당 없음 | 표정별 이미지 2장에서 4장 |

### VRM 0.0과 1.0 선택

- debutkit 캐릭터 화면, Warudo, VMagicMirror: 둘 다 사용
- VSeeFace: VRM 0.x만. VRoid Studio 의상(XWear) 기능: 1.0만
- VRM 0.x의 상업적 이용 허용(Allow)은 법인 사용 허용과 같지 않음. VRM 1.0은 `commercialUsage`가 `corporation`일 때만 법인 사용 허용
- 소속사 활동 예정이면 VRM 1.0으로 내보내고 사용 조건의 법인 사용 허용 여부를 제작자와 확인

### Linux 사용자의 3D 캐릭터 제작

- VRoid Studio는 Linux 판이 없음
- 대안: Vket Avatar Maker(웹, 법인 사용 조건 위 참고), Blender와 VRM Add-on for Blender, 다른 PC에서 만든 VRM 등록

### Live2D 의뢰 절차

- 일러스트 작가가 레이어를 나눈 PSD 제작, 리거가 Cubism Editor로 움직임 작업
- Live2D PSD 규칙: RGB 8비트 sRGB, 부위별 레이어와 고유 이름, 클리핑과 효과는 병합, 레이어 마스크 금지. https://docs.live2d.com/en/cubism-editor-manual/precautions-for-psd-data/

### PNGTuber 이미지 관례

- 상태별 이미지: 입 다묾, 입 벌림, 각각의 눈 감은 이미지(최대 4장)
- 같은 캔버스 크기의 투명 PNG(관례)
- 참고 프로그램: veadotube mini(가격 자율, Windows, macOS, Linux) https://olmewe.itch.io/veadotube-mini , PNGTuber Plus(Unlicense) https://github.com/kaiakairos/PNGTuber-Plus

## 2. 파일 형식과 확인 항목

### VRM

- glTF 바이너리(GLB). 파일 첫 4바이트 `glTF`, 버전 2, JSON 청크와 BIN 청크
- VRM 0.x: `extensions.VRM.meta`. 사용 조건 항목 `allowedUserName`, `commercialUssageName`, `violentUssageName`, `sexualUssageName`, `licenseName`. 미리보기 이미지 `texture`
- VRM 1.0: `extensions.VRMC_vrm`(`specVersion` 1.0). 사용 조건 항목 `avatarPermission`, `commercialUsage`(personalNonProfit, personalProfit, corporation), `allowExcessivelyViolentUsage` 등, `creditNotation`, `allowRedistribution`, `modification`. 미리보기 이미지 `thumbnailImage`. 값이 없으면 가장 제한적인 기본값
- 규격: https://github.com/vrm-c/vrm-specification
- debutkit 확인 항목: 형식, 버전, 이름, 제작자, 수익 방송과 법인(소속사) 사용 허용 여부, 미리보기 이미지

### 일반 3D 모델(GLB, FBX)

- GLB: VRM 확장이 없는 glTF 바이너리. 스킨 관절(`skins[].joints`)의 노드 이름을 뼈 이름으로, `meshes[].extras.targetNames`를 표정(형태 변형) 이름으로 사용. VRM 확장이 있는 `.glb`는 VRM으로 처리
- FBX: 7.0(FBX 2011) 이후. 바이너리는 노드 구조(`Objects`의 `Model` LimbNode, `Deformer` BlendShapeChannel, `Video`)를 읽고, ASCII는 같은 항목을 글자로 읽음. Autodesk FBX SDK 사용 안 함
- 사람 모양 뼈: VRM 1.0 필수 뼈 15개(엉덩이, 척추, 머리, 양쪽 위팔, 아래팔, 손, 허벅지, 종아리, 발). 지원하는 뼈 이름 방식: Mixamo, VRoid, Unreal, Blender(Rigify, 일반), MMD, Character Creator, 3ds Max Biped, VRM 뼈 이름. 표는 `src/debutkit/humanoid.py`이며 캐릭터 화면도 같은 표(`/character/humanoid.json`) 사용
- 표정: VRoid(`Fcl_MTH_A` 등), VRChat(`vrc.v_aa` 등), Ready Player Me(`viseme_aa` 등), MMD(あ, まばたき), 일반 이름(aa, blink). 이름이 맞지 않으면 ARKit 52개 표정(`jawOpen`, `eyeBlinkLeft` 등) 조합으로 대체(경험적 가중치). 입 모양이 없고 턱 뼈가 있으면 턱 뼈 회전으로 입 표현
- 캐릭터 화면 처리: 센티미터 단위 모델은 미터로 맞춤, 뒤를 보는 모델은 180도 회전, A자 자세는 팔 각도를 계산해 내림. three-vrm의 `VRMHumanoid`, `VRMExpressionManager`를 직접 만들어 VRM과 같은 움직임 코드 사용
- 텍스처: GLB는 파일 안 이미지. FBX는 파일 안 포함(Embed Media) 또는 FBX 폴더 안의 PNG, JPG, WebP를 함께 복사. TGA, 폴더 밖 텍스처는 표시하지 않음(등록 시 경고)
- 사용 조건 정보가 파일에 없으므로 수익 방송, 소속사 사용, 수정 허용 여부는 제작자, 판매처 조건으로 직접 확인. Mixamo 뼈 이름이면 Adobe 약관(원본 파일 재배포 금지) 안내
- 지원하지 않음: `.gltf`(GLB로 내보내기), PMX(Blender MMD Tools로 변환), 다른 방송 프로그램으로 보내기(VRM 변환 필요)

### Live2D

- `model3.json`: `Version`과 `FileReferences` 필수. `FileReferences`의 `Moc`(.moc3)와 `Textures` 필수, `Physics`, `Pose`, `Expressions`, `Motions`, `DisplayInfo` 선택. https://github.com/Live2D/CubismSpecs/blob/master/FileFormats/model3.json.md
- 최소 구성: model3.json, moc3, 텍스처 PNG. VTube Studio의 물리 효과에는 physics3.json 필요
- debutkit 확인 항목: model3.json 구조, 참조 파일 존재, moc3 머리글(`MOC3`)

### Inochi2D

- `.inp`: 머리글 `TRNSRTS` 뒤에 JSON과 텍스처. 규격은 1.0 전까지 변경 가능. https://github.com/Inochi2D/inochi2d-docs

## 3. 방송 프로그램 연계

| 프로그램 | 모델 | 불러오기 | 연계 방식 |
|---|---|---|---|
| VTube Studio | Live2D | 모델별 폴더를 `Live2DModels`에 넣으면 다음 실행 시 인식. 위치는 프로그램 안의 폴더 열기 버튼으로 확인 | debutkit이 모델 폴더 복사. 공개 API(ws://localhost:8001, MIT)로 인증, 모델 불러오기, 단축키 실행(후원 반응). 파일 가져오기는 API에 없음. https://github.com/DenchiSoft/VTubeStudio |
| Warudo | VRM | 데이터 폴더의 `Characters` 폴더 | debutkit이 VRM 복사. https://docs.warudo.app/docs/assets/character |
| VSeeFace | VRM 0.x만 | 아바타 목록에서 파일 선택 | 안내. VRM 1.0은 사용 불가 안내. https://www.vseeface.icu/ |
| VMagicMirror | VRM 0.x, 1.0 | 파일에서 불러오기 | 안내. https://malaybaku.github.io/VMagicMirror/en/ |
| Inochi Session | Inochi2D | 프로그램에서 불러오기 | 안내. https://kitsunebi-games.itch.io/inochi-session |

- VMC 프로토콜(OSC, UDP 39539)은 모델 불러오기 명령이 없어 파일 전달에는 사용하지 않음. https://protocol.vmc.info/english

## 4. 방송 화면 기술

| 구성 요소 | 버전 | 라이선스 | 용도 |
|---|---|---|---|
| three.js | 0.18x | MIT | 3D 표시 |
| @pixiv/three-vrm | 3.x | MIT | VRM 0.x, 1.0 불러오기, 표정(aa, blink 등), 시선 |
| OBS WebSocket InputVolumeMeters | OBS 28 이상 | GPL-2.0(OBS) | 마이크 음량으로 말하는 상태 판단 |

- three.js, three-vrm은 debutkit에 포함(외부 CDN 접속 없음)
- OBS 브라우저 소스는 카메라와 마이크 권한 요청을 거부. `--enable-media-stream` 실행 옵션은 모든 브라우저 소스와 도크에 권한을 주므로 권장하지 않음. https://github.com/obsproject/obs-browser
- 웹캠 얼굴 추적: MediaPipe Face Landmarker(@mediapipe/tasks-vision 1.2.3, 모델 float16 버전 1, Apache-2.0)를 포함. 52개 표정 값 중 눈 감음, 입 벌림, 웃음과 얼굴 변환 행렬의 머리 회전을 사용
- MediaPipe 웹 배포 파일에는 사용 기록을 `https://odml.pa.googleapis.com/v1/log`로 보내는 코드가 있음(2026-11-22 확인). 추적 화면에 콘텐츠 보안 정책(`connect-src 'self'`)을 적용해 차단하고, 브라우저에서 차단과 이 PC 밖 요청 없음을 확인

## 5. 라이선스 주의

- Live2D Cubism Core는 독점 라이선스로 Apache-2.0 프로젝트에 포함할 수 없음(재배포 제한, 오픈소스 라이선스 적용 금지). https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html
- 임의의 모델을 불러오는 프로그램은 Live2D의 확장형 앱 심사 대상이며 무료 앱은 원칙적으로 대상이 아님. https://www.live2d.com/en/sdk/license/expandable/
- 따라서 debutkit은 Live2D 모델을 직접 표시하지 않고 VTube Studio로 전달
- Live2D 샘플 모델은 재배포 금지. 링크만 안내
- VRM 사용 조건이 수익 방송이나 법인 사용을 허용하지 않으면 등록 시 경고
- VRM 제작자 정보에 Vket, HIKKY가 있으면 Vket Avatar Maker 약관(저작권 HIKKY, 법인 사용 사전 확인) 경고

### 제작 기능 관련 약관(2026-11 조사)

| 대상 | 내용 | debutkit 처리 |
|---|---|---|
| VRoid Studio 이용 약관(아바타 제작 앱 조항, 2026-06-24 개정 후 번호 이동) | VRoid 제공 요소나 이를 포함한 모델로 메시 변형, 메시나 텍스처 조합 방식의 아바타 제작 앱 개발 시 pixiv 별도 라이선스 필요. https://policies.pixiv.net/en.html#vroidstudio | VRoid 요소 기반 제작 기능 만들지 않음. 사용자 VRoid 출력 파일의 등록과 표시는 해당 없음 |
| Vket Avatar Maker 약관 제7조, 제8조 | 저작권 HIKKY, 법인 사용 사전 확인, 앱 포함과 모델 데이터 배포 금지 | 기본 캐릭터나 예제로 포함하지 않음, 등록 시 경고 |
| Mixamo | 원본 캐릭터, 동작 파일 재배포 금지 | 사용자가 받은 파일의 등록만 지원 |
| VRoid Hub SDK 지침 | 모델 데이터 자체 저장 기능 금지 | 로컬 파일 등록 방식과 충돌, 연동 보류 |
| Hunyuan3D 라이선스 | 사용 지역에서 한국 제외 | 사용, 안내하지 않음 |

## 6. debutkit 기본 캐릭터

- 즉시 시험할 수 있도록 debutkit 브랜드 캐릭터(고양이 귀 마이크)를 PNGTuber 형식(SVG 4장)으로 포함. Apache-2.0
