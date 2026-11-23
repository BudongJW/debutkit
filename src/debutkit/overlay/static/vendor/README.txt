함께 배포하는 외부 라이브러리와 글꼴(캐릭터 화면의 VRM 표시, 동작 재생, 얼굴 추적, 후원 추첨 연출의 글꼴). 원본 파일을 수정하지 않고 포함.

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
MediaPipe Face Landmarker 모델 face_landmarker.task (float16, 버전 1, Apache-2.0)
  출처 https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task

SHA-256
  999152fa183e30112f2506d3c371e8edb2216163d6950a94f593d03a07fbd7b9  fonts/BlackHanSans-Regular.woff2
  c324192c8b3a988bae45a9a7e4ac1258b684739003bda114e0523423440457c9  fonts/OFL-BlackHanSans.txt
  b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e  fonts/OFL-Pretendard.txt
  78eb71c33101ee7d4f8d1b777d193a12d00f8a296e712a8c417cf27abe946397  fonts/Pretendard-Bold.subset.woff2
  4247dc5e260b92640c2cbd0e75091154647b71e1d5884116655e2903468c54cc  fonts/Pretendard-SemiBold.subset.woff2
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
