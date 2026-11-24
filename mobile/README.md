# debutkit 휴대폰 앱

두 가지 방식으로 사용하는 앱.

- PC와 연결: 같은 Wi-Fi의 debutkit PC로 얼굴 추적 값이나 카메라 영상을 보낸다(카메라는 하나만 쓸 수 있어 둘 중 선택)
  - 얼굴 추적: 앞면 카메라로 머리 움직임과 ARKit 이름 표정 52개. PC의 캐릭터 화면(VRM, GLB, FBX, PNGTuber)이 그 값으로 움직이고, ARKit 이름 표정을 가진 모델(퍼펙트 싱크)은 얼굴 전체가 움직인다
  - 카메라 영상: 앞면이나 뒷면 카메라 영상을 WebRTC로 OBS 브라우저 소스(`/camera/view`, `[DK] 휴대폰 카메라(앱)`)에 직접. 연결 정보만 PC 서버를 거치고 영상은 휴대폰과 OBS 사이에서 직접 오간다(외부 서버 없음). 소리는 보내지 않는다
- 바로 방송(안드로이드): PC 없이 휴대폰에서 치지직, SOOP, YouTube, Twitch로 RTMP(S) 송출
  - 캐릭터 화면: 배경색 위에 debutkit 기본 캐릭터 또는 고른 그림 두 장(입 닫음, 입 엶). 마이크 소리에 맞춰 입을 움직이고 가끔 눈을 깜빡인다
  - 카메라 영상: 앞면이나 뒷면 카메라와 마이크 소리(휴대폰을 가로로 들고 방송)

| 폴더 | 내용 | 얼굴 추적 | 바로 방송 |
|---|---|---|---|
| `android/` | 안드로이드 8 이상, Kotlin, Jetpack Compose, CameraX | MediaPipe Face Landmarker(PC 웹캠 추적과 같은 모델) | RootEncoder(하드웨어 H.264, AAC, RTMP와 RTMPS) |
| `ios/` | iOS 15 이상, Swift, SwiftUI | ARKit(Face ID 카메라 또는 A12 이상) | 다음 버전 이후 |

## 연결 방식

- 등록: PC 오버레이 설정 화면의 휴대폰 연결에서 휴대폰 조작 화면을 켜고 새 휴대폰 QR 만들기. 앱에서 QR 코드 찍기(또는 `debutkit remote pair` 주소 붙여 넣기)
- 승인: 앱과 PC에 같은 4자리 확인 번호가 보이면 PC에서 승인. 브라우저 조작 화면과 같은 등록 기기 목록(최대 5대, 삭제 즉시 차단)
- 전송: PC 휴대폰 조작 화면과 같은 주소, 같은 번호의 UDP 포트(기본 8792). 초당 최대 30회, 뜨거우면 15회
- 보안: 기기 비밀값은 QR 코드로만 전달. 등록 확인 요청과 추적 패킷 모두 HMAC-SHA256 서명, PC는 승인된 기기의 서명과 시각(이전 패킷보다 새로운 값)만 사용
- 형식: `src/debutkit/overlay/remote.py` 머리말. 앱과 PC의 서명이 같은지는 양쪽 단위 테스트가 같은 기대값으로 확인
- 거울처럼 움직이기, 위아래 반전, 정면 맞추기는 PC 휴대폰 얼굴 추적 설정을 따른다
- 카메라 영상 연결: 앱이 연결 제안(SDP)을 서명 요청으로 보내고(`/remote/api/camera/offer`) OBS 수신 화면이 응답. PC는 브라우저가 감춘 주소(`.local`)를 내부 주소로 바꿔 전달(`src/debutkit/overlay/camcall.py`)

## 바로 방송(안드로이드)

- 송출 서버: YouTube(`rtmps://a.rtmps.youtube.com/live2`), Twitch(`rtmps://live.twitch.tv:443/app`) 기본값. 치지직과 SOOP은 방송 설정 화면의 서버 주소를 붙여 넣는다. 플랫폼마다 따로 기억(PC의 `broadcast.py`와 같은 규칙)
- 화질: 480p 30fps(1200 kbps), 720p 30fps(2500 kbps, 권장), 1080p 30fps(4500 kbps). 플랫폼 상한 이하, 연결이 느리면 자동으로 낮춤, 휴대폰이 뜨거우면 60%로
- 스트림 키: 안드로이드 키 저장소(AndroidKeyStore)의 AES-GCM 키로 암호화해 앱 전용 저장소에 보관. 백업 제외. 오류 문장에서 가리고, 송출 라이브러리 기록은 배포 빌드에서 끈다(기록에 키가 들어감)
- 방송 중에는 포그라운드 서비스(카메라, 마이크)로 다른 앱으로 바꾸거나 화면이 꺼져도 송출을 이어 가고, 알림의 방송 끝내기로 멈춘다
- 방송한 뒤 연결이 끊기면 5초 뒤 다시 연결(최대 5번). 시작하자마자 실패하면(주소, 키) 이유를 표시하고 멈춘다
- 코드: `Live.kt`(규칙, 입 움직임, 눈 깜빡임), `LiveStore.kt`(설정, 키 암호화), `CharacterSource.kt`(캐릭터 화면), `LiveSession.kt`(송출), `LiveService.kt`(포그라운드 서비스), `LiveScreen.kt`(화면)

## 안드로이드

빌드(JDK 17, Android SDK 36):

```
cd mobile/android
./gradlew :app:testDebugUnitTest :app:assembleRelease
```

- 결과: `app/build/outputs/apk/release/app-release.apk`. 서명 키 환경 변수(`DEBUTKIT_ANDROID_KEYSTORE`, `DEBUTKIT_ANDROID_KEYSTORE_PASSWORD`, `DEBUTKIT_ANDROID_KEY_ALIAS`, `DEBUTKIT_ANDROID_KEY_PASSWORD`)가 없으면 디버그 키로 서명
- 얼굴 인식 모델은 PC 프로그램의 `src/debutkit/overlay/static/vendor/mediapipe/face_landmarker.task`를 빌드할 때 복사
- 배포 빌드는 R8로 축소. MediaPipe와 그 로그 라이브러리(Flogger), WebRTC는 이름 유지(`app/proguard-rules.pro`)
- RootEncoder는 JitPack(`https://jitpack.io`)에만 배포되어 그 저장소를 RootEncoder 묶음에만 사용(`settings.gradle.kts`)
- 포함 CPU: arm64-v8a, armeabi-v7a, x86_64

에뮬레이터 시험(디버그 빌드만):

- 등록 주소 전달: `adb shell am start -n io.github.budongjw.debutkit.phone/.MainActivity --es link '<QR 주소>'`
- PC를 127.0.0.1로 등록하면 `adb reverse tcp:8792 tcp:8792`로 등록 확인 요청이, UDP 추적 값은 에뮬레이터의 PC 주소(10.0.2.2)로 간다
- 얼굴을 비출 수 없으면 `/sdcard/Android/data/io.github.budongjw.debutkit.phone/files/test-face.jpg`를 넣고 시험 이미지로 추적
- 바로 방송: PC에서 `ffmpeg -listen 1 -i rtmp://127.0.0.1:19350/live/시험키 -c copy 받은파일.flv`로 수신을 기다리고, 앱을 `--es live_server rtmp://10.0.2.2:19350/live --es live_key 시험키 --es live_mode character`(또는 `camera`)로 열어 방송 시작

## iOS

[ios/README.md](ios/README.md)

## 라이선스

- 앱: Apache-2.0(debutkit과 같음)
- 안드로이드: MediaPipe Tasks Vision(Apache-2.0), CameraX, Jetpack Compose, AndroidX(Apache-2.0), ZXing core(Apache-2.0, QR 코드 읽기), WebRTC(io.github.webrtc-sdk, BSD-3과 WebRTC 제3자 라이선스), RootEncoder(Apache-2.0, 바로 방송)
- iOS: 운영체제 기본 기능(ARKit, AVFoundation, CryptoKit, Network)과 WebRTC(stasel/WebRTC 배포 바이너리, WebRTC 라이선스 https://webrtc.org/support/license). 프로젝트 생성 도구 XcodeGen(MIT, 빌드에만 사용)
