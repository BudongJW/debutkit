함께 배포하는 외부 라이브러리, 글꼴, 아이콘(캐릭터 화면의 VRM 표시, 동작 재생, 얼굴 추적, 후원 추첨 연출과 로고와 방송 스타일의 글꼴, 로고 심볼 아이콘).
라이브러리와 글꼴은 원본 파일을 수정하지 않고 포함. 아이콘은 일부만 골라 숫자 자릿수를 줄인 묶음(packaging/build_icons.py).

three 0.187.0 (MIT) https://github.com/mrdoob/three.js
  출처 https://cdn.jsdelivr.net/npm/three@0.187.0/ (build, examples/jsm 일부)
  examples/jsm: GLTFLoader, FBXLoader(GLB, FBX 캐릭터)와 의존 파일 libs/fflate.module.js(fflate 0.8.3, MIT), curves/NURBSCurve.js, NURBSUtils.js
@pixiv/three-vrm 3.5.5 (MIT) https://github.com/pixiv/three-vrm
  출처 https://cdn.jsdelivr.net/npm/@pixiv/three-vrm@3.5.5/lib/three-vrm.module.min.js
@pixiv/three-vrm-animation 3.5.5 (MIT) https://github.com/pixiv/three-vrm
  출처 https://cdn.jsdelivr.net/npm/@pixiv/three-vrm-animation@3.5.5/lib/three-vrm-animation.module.min.js (VRMA 동작 재생)
@mediapipe/tasks-vision 1.2.3 (Apache-2.0) https://github.com/google-ai-edge/mediapipe
  출처 https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.2.3/ (vision_bundle.mjs, wasm/vision_wasm_internal.*)
  사용 기록 전송 코드(odml.pa.googleapis.com)가 들어 있어 얼굴 추적 화면은 콘텐츠 보안 정책으로 외부 접속을 차단
Black Han Sans (SIL OFL 1.1, 예약 글꼴 이름 없음) https://github.com/zesstype/Black-Han-Sans
  출처 https://github.com/google/fonts/tree/main/ofl/blackhansans (BlackHanSans-Regular.ttf를 글리프 변경 없이 woff2로 변환), 라이선스 fonts/OFL-BlackHanSans.txt
Pretendard 1.3.9 (SIL OFL 1.1, 예약 글꼴 이름 Pretendard) https://github.com/orioncactus/pretendard
  출처 https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/web/static/woff2-subset/ (제작자 배포 파일 그대로, SemiBold, Bold), 라이선스 fonts/OFL-Pretendard.txt
Galmuri 2.40.4 (SIL OFL 1.1, 예약 글꼴 이름 없음, Copyright Lee Minseo) https://github.com/quiple/galmuri
  출처 https://raw.githubusercontent.com/quiple/galmuri/v2.40.4/dist/ (제작자 배포 파일 그대로, Galmuri11 보통, 굵게. 레트로 픽셀 스타일), 라이선스 fonts/OFL-Galmuri.txt
Gaegu (SIL OFL 1.1, 예약 글꼴 이름 없음, Copyright The Gaegu Project Authors) https://github.com/google/fonts/tree/main/ofl/gaegu
  출처 google/fonts 커밋 088df5c822dacc8fad9dd64dbbe5649cd6830e99의 Gaegu-Regular.ttf, Gaegu-Bold.ttf를 글리프 변경 없이 woff2로 변환(다이어리 스타일),
  라이선스 fonts/OFL-Gaegu.txt. 한글은 자주 쓰는 2,350자(KS X 1001)만 있어 그 밖의 글자는 다음 글꼴로 표시
한글 글꼴 14종(SIL OFL 1.1, 모두 예약 글꼴 이름 없음) https://github.com/google/fonts/tree/main/ofl
  출처 google/fonts 커밋 5026800714d07231937d92eb4cceabf06e05d74e 의 TTF를 packaging/build_fonts.py로 자주 쓰는 한글 2,350자(KS X 1001),
  영문, 문장 부호, 기호만 남기고 힌팅을 뺀 woff2로(*.subset.woff2). 2,350자 밖의 글자는 다음 글꼴로 표시. 라이선스 fonts/OFL-<글꼴>.txt
  도현(DoHyeon), 주아(Jua), 베이글 팻 원(BagelFatOne, Copyright The Bagel Fat Project Authors), 연성(YeonSung), 고운 돋움(GowunDodum),
  해바라기 Bold(Sunflower), 스타일리시(Stylish, Copyright AsiaSoft Inc.), 동글 Bold(Dongle), 귀여운 글꼴(CuteFont), 감자꽃(GamjaFlower, Copyright YoonDesign Inc.),
  기랑해랑(KirangHaerang), 동해 독도(EastSeaDokdo, Copyright YoonDesign Inc.), 고운 바탕 Bold(GowunBatang), 송명(SongMyung)
쓰지 않는 글꼴: 나눔손글씨 펜(OFL이지만 예약 글꼴 이름 Nanum이 있어 줄이거나 바꾸면 이름을 바꿔야 함)
MediaPipe Face Landmarker 모델 face_landmarker.task (float16, 버전 1, Apache-2.0)
  출처 https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
Microsoft Fluent Emoji (MIT, Copyright (c) Microsoft Corporation) https://github.com/microsoft/fluentui-emoji
  출처 커밋 1ffb34c752ecf5d402f04cfb4b392c77f57c54bc(2026-08-24)의 assets/*/Flat, High Contrast SVG에서 버튜버 주제 356개 선별.
  Color 판은 SVG 필터가 많아 쓰지 않고, 마스크를 쓰는 High Contrast 6개도 제외. 경로 숫자를 소수 둘째 자리로 줄이고
  한국어 이름과 검색어, 색별 넓이를 붙여 icons/fluent-emoji.json.gz로 저장, 라이선스 icons/LICENSE-fluent-emoji.txt
Phosphor Icons @phosphor-icons/core 2.1.1 (MIT, Copyright (c) 2023 Phosphor Icons) https://github.com/phosphor-icons/core
  출처 https://registry.npmjs.org/@phosphor-icons/core/-/core-2.1.1.tgz 의 assets(굵기 6종)에서 102개 선별(상표 로고 아이콘 제외).
  경로 숫자를 소수 첫째 자리로 줄이고 한국어 이름과 검색어를 붙여 icons/phosphor.json.gz로 저장, 라이선스 icons/LICENSE-phosphor.txt
쓰지 않는 아이콘 세트: OpenMoji(CC BY-SA, 동일조건), Remix Icon(라이선스가 로고 사용 금지), SVG Repo(아이콘별 라이선스 혼재),
  Iconify 공개 API(런타임 요청 제한, 표기 라이선스가 원본과 다른 사례)

SHA-256
  999152fa183e30112f2506d3c371e8edb2216163d6950a94f593d03a07fbd7b9  fonts/BlackHanSans-Regular.woff2
  c324192c8b3a988bae45a9a7e4ac1258b684739003bda114e0523423440457c9  fonts/OFL-BlackHanSans.txt
  b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e  fonts/OFL-Pretendard.txt
  bdabf8de5b6c1fe8aa6d018fdc664c9d9396306adcc5dea0632c14a9ecd56f3e  fonts/Gaegu-Bold.woff2
  fb3a27f6e84fb2a479c961354e001cab05777c3d4061fac670145012d0566c6c  fonts/Gaegu-Regular.woff2
  8643094f395aa2dbad6bc4385cc043314801eaec2e759d549435ec8ac4f2d078  fonts/Galmuri11-Bold.woff2
  f467d1b10e6b88dfa8399c9f93b38c7643e050abfe4fc15800ac0b000f5a57d6  fonts/Galmuri11.woff2
  53a9ce47085d9fef613c7ecb3730dc80d25962510bbea231b89564f58240f251  fonts/OFL-Gaegu.txt
  9a9e5a342c430c3fcf01a408b680f4405d5bf4ac659c931be35f8a1b27ea69c9  fonts/OFL-Galmuri.txt
  78eb71c33101ee7d4f8d1b777d193a12d00f8a296e712a8c417cf27abe946397  fonts/Pretendard-Bold.subset.woff2
  4247dc5e260b92640c2cbd0e75091154647b71e1d5884116655e2903468c54cc  fonts/Pretendard-SemiBold.subset.woff2
  646f8936b8ddcd14e13e578ff6857e368780b0d1a4f6066bee89211923a373e2  icons/LICENSE-fluent-emoji.txt
  b5b1f1da112d18ea2147decfd48ddc1bf2b5aeb6c265381579340e95b15a2bb2  icons/LICENSE-phosphor.txt
  c9ce8c46a48a748fbadfd9850daeb98df48218ef2652cf7e6d22feda23091163  icons/fluent-emoji.json.gz
  f5d5a1d0d705ca1424040eb979540cad5de17832b0b38ebc738bfa812da813e7  icons/phosphor.json.gz
  cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30  mediapipe/LICENSE
  64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff  mediapipe/face_landmarker.task
  fb0c02c296f44ce0cc324ba16bd646d8773eb4a7847db4019cc4d0430db7a9b5  mediapipe/vision_bundle.mjs
  2aa5fd3fdd3d8208cd7587df0bb19fb6925c4ea16a76dd025aedc1f64d6a6309  mediapipe/wasm/vision_wasm_internal.js
  225bc06c0f51a9cf31fea0e9e0b0243e9e01fb5ef332cc1a7fa6656dbdfdaabf  mediapipe/wasm/vision_wasm_internal.wasm
  279ec82987aec7e72ecb9850bb704a87e352d577bc7581454c30f3551a88ea92  three-vrm/LICENSE
  99f943e956e52dbf52bbe418899e8a8ae5e35f5c79a94ab8e404926afc620bf2  three-vrm/three-vrm.module.min.js
  279ec82987aec7e72ecb9850bb704a87e352d577bc7581454c30f3551a88ea92  three-vrm-animation/LICENSE
  31de9586a36a8ad806303b84358f11d74ce70ac1d2656b04e8a5da7a913aa907  three-vrm-animation/three-vrm-animation.module.min.js
  8b378ebe60e2fe500158cb0ac71cb5e8b7d92953c2abcc63a0eb90499653b5bc  three/LICENSE
  613e370f76638fdef83926642bf256dc9615684922de1ce1f63a8583e5d78578  three/build/three.core.js
  104f56145899722094556490d787aae0617cc2fc3382f31df02d724ea1aee341  three/build/three.module.js
  f5aaeff3ed9b659c3d9c599878ede3106d93665e3243e502a09375f2edaed7fa  three/examples/jsm/curves/NURBSCurve.js
  c6bd7c4137d585098923f189687898ea3e8762ea3ecbe255d749a56353894379  three/examples/jsm/curves/NURBSUtils.js
  4ab9828cf361a8009b71094ea251e076168de20f72eaa1e745da8aba88c725ac  three/examples/jsm/libs/fflate.module.js
  04daa9a7054f17838b78a114e7d400c05d08d72afa7b62f2fc1d508909a6df3c  three/examples/jsm/loaders/FBXLoader.js
  532ac726e120039acbcd6cf54328c57acbf7b438176afaa6951257126d11bff1  three/examples/jsm/loaders/GLTFLoader.js
  7bda2a8ba836b2bcf67cb938d4b9e1bb5d1b1bc616817103ed858c0b58296ce7  three/examples/jsm/utils/BufferGeometryUtils.js
  b1632a703206c3d830de9fcbe515696770d04b71a15ee6b50afa6d2c3298c86f  three/examples/jsm/utils/SkeletonUtils.js
  49a57c
  2db56779bdce42a835c329196b58f5ac933cab7635f64b5161aca5ad6648d68a  fonts/DoHyeon-Regular.subset.woff2
  de5ff32211a4340b01477af39ee339d639438955e409f79b666d4b9207f3c92c  fonts/OFL-DoHyeon.txt
  046371e151d8f868ab2d62288b3a7cde14bdd71b6cfb988ddd7bb336e024a3aa  fonts/Jua-Regular.subset.woff2
  44a7c6e4c5572392ae122d3b1d8c6ba6fd640a7797e675384585d947f2773e3c  fonts/OFL-Jua.txt
  19be393dc08deab18d55b1d0c696a03e9ae0e6abbcf90310a5e7f224deda30c2  fonts/BagelFatOne-Regular.subset.woff2
  4f40ab196ccf674056fed8b0e6d4f918eea183a149be8a67bff1239413ebada9  fonts/OFL-BagelFatOne.txt
  4ce87ac4c6ebb93e4d2146e9c931fb3728dfe6caff01111a56f922f57044c29a  fonts/GowunDodum-Regular.subset.woff2
  a7c73f9521cd646bbdfb6684c99a62311bbd7bce11898dc11ef0b3c69eda1aca  fonts/OFL-GowunDodum.txt
  8c821336dc2ec33525b72cf3ff4a5b48831b4ec355164d1e9f03d03d9b6ce9ee  fonts/Sunflower-Bold.subset.woff2
  a9b40759b5821a0c2ad07cbd2c2a61dca4b3e222e6370a7d5bfb6b373bf4fb10  fonts/OFL-Sunflower.txt
  19c8e890d03276b5989e0674d199229d3249d0f60ef5c05882d1b5d95d18e3e4  fonts/Dongle-Bold.subset.woff2
  f9e59049e824264bffd626d0901cfcaac9d5ba756988b904d3e3e0e233493607  fonts/OFL-Dongle.txt
  9626a1b4ab45f0d57e763053fbab9ee9911376ebe6d5f993c9c990a96d843725  fonts/CuteFont-Regular.subset.woff2
  1a2debd5ad8e656b26bb3b29213caa8f7e557a2f31454b11ebb6c3e3b59aa5d4  fonts/OFL-CuteFont.txt
  3e939447b3ac13340599f92728d58c9c316f83454dc83f75b010d636a6a4db55  fonts/GamjaFlower-Regular.subset.woff2
  39de3de5f1873f89bca4af37823ab22e28e88d0d8f7fe2f07e82e9e6e9bf7b70  fonts/OFL-GamjaFlower.txt
  87827a52dbd9b3c09e768d9c6419e8664dde570f511808786ee6706b6d1d429a  fonts/EastSeaDokdo-Regular.subset.woff2
  39de3de5f1873f89bca4af37823ab22e28e88d0d8f7fe2f07e82e9e6e9bf7b70  fonts/OFL-EastSeaDokdo.txt
  4448869c171c9a9d587afa3f8313a31941d46dd04b996f6685b5da4e10cf9b16  fonts/GowunBatang-Bold.subset.woff2
  49a57cc769fa9affd6eefb9070a61e3d3f6b757c97cafb15848bc6d1c81acc78  fonts/OFL-GowunBatang.txt
  9aaab8381d5a0e6d30fdf170a9d22df4b3caa744b010e454131ec9b988c3d043  fonts/SongMyung-Regular.subset.woff2
  40bd3f35477284c021978816e9d3b8723ff2283fd7065fafaa5bb3004e41b237  fonts/OFL-SongMyung.txt
  f6d142ecc88777346904211b1cefb4a4306a096937ed7d246e3dc2afb567b5ff  fonts/YeonSung-Regular.subset.woff2
  d7d8074c2dd46804990c184e25849947ab76c5ac7607fbf3966543455769bb73  fonts/OFL-YeonSung.txt
  af4f7acb2b06ccd2e23bd4eafe8b2fcb32e739ad6ae5427e902800b1991de0a5  fonts/KirangHaerang-Regular.subset.woff2
  7e896665d0863d2a17a671001dbe2528a5f9302f1dff9222af8b0834e9088d0c  fonts/OFL-KirangHaerang.txt
  e8d29fedd57192e7725433c725786aac39ee060da6fdb4e20e5e9afeac0db46e  fonts/Stylish-Regular.subset.woff2
  a9b3e7e1cf5735dc49d802b88b1858a2a50307ba2a877ddf3f0b27d8b1d0abc5  fonts/OFL-Stylish.txt
