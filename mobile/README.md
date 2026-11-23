# debutkit 휴대폰 앱

같은 Wi-Fi의 debutkit PC로 두 가지를 보내는 앱(카메라는 하나만 쓸 수 있어 둘 중 선택).

- 얼굴 추적: 앞면 카메라로 머리 움직임과 ARKit 이름 표정 52개. PC의 캐릭터 화면(VRM, GLB, FBX, PNGTuber)이 그 값으로 움직이고, ARKit 이름 표정을 가진 모델(퍼펙트 싱크)은 얼굴 전체가 움직인다
- 카메라 영상: 앞면이나 뒷면 카메라 영상을 WebRTC로 OBS 브라우저 소스(`/camera/view`, `[DK] 휴대폰 카메라(앱)`)에 직접. 연결 정보만 PC 서버를 거치고 영상은 휴대폰과 OBS 사이에서 직접 오간다(외부 서버 없음). 소리는 보내지 않는다

| 폴더 | 내용 | 얼굴 추적 |
|---|---|---|
| `android/` | 안드로이드 8 이상, Kotlin, Jetpack Compose, CameraX | MediaPipe Face Landmarker(PC 웹캠 추적과 같은 모델) |
| `ios/` | iOS 15 이상, Swift, SwiftUI | ARKit(Face ID 카메라 또는 A12 이상) |

## 연결 방식

- 등록: PC 오버레이 설정 화면의 휴대폰 연결에서 휴대폰 조작 화면을 켜고 새 휴대폰 QR 만들기. 앱에서 QR 코드 찍기(또는 `debutkit remote pair` 주소 붙여 넣기)
- 승인: 앱과 PC에 같은 4자리 확인 번호가 보이면 PC에서 승인. 브라우저 조작 화면과 같은 등록 기기 목록(최대 5대, 삭제 즉시 차단)
- 전송: PC 휴대폰 조작 화면과 같은 주소, 같은 번호의 UDP 포트(기본 8792). 초당 최대 30회, 뜨거우면 15회
- 보안: 기기 비밀값은 QR 코드로만 전달. 등록 확인 요청과 추적 패킷 모두 HMAC-SHA256 서명, PC는 승인된 기기의 서명과 시각(이전 패킷보다 새로운 값)만 사용
- 형식: `src/debutkit/overlay/remote.py` 머리말. 앱과 PC의 서명이 같은지는 양쪽 단위 테스트가 같은 기대값으로 확인
- 거울처럼 움직이기, 위아래 반전, 정면 맞추기는 PC 휴대폰 얼굴 추적 설정을 따른다
- 카메라 영상 연결: 앱이 연결 제안(SDP)을 서명 요청으로 보내고(`/remote/api/camera/offer`) OBS 수신 화면이 응답. PC는 브라우저가 감춘 주소(`.local`)를 내부 주소로 바꿔 전달(`src/debutkit/overlay/camcall.py`)

## 안드로이드

빌드(JDK 17, Android SDK 36):

```
cd mobile/android
./gradlew :app:testDebugUnitTest :app:assembleRelease
```

- 결과: `app/build/outputs/apk/release/app-release.apk`. 서명 키 환경 변수(`DEBUTKIT_ANDROID_KEYSTORE`, `DEBUTKIT_ANDROID_KEYSTORE_PASSWORD`, `DEBUTKIT_ANDROID_KEY_ALIAS`, `DEBUTKIT_ANDROID_KEY_PASSWORD`)가 없으면 디버그 키로 서명
- 얼굴 인식 모델은 PC 프로그램의 `src/debutkit/overlay/static/vendor/mediapipe/face_landmarker.task`를 빌드할 때 복사
- 배포 빌드는 R8로 축소. MediaPipe와 그 로그 라이브러리(Flogger)는 이름 유지(`app/proguard-rules.pro`)
- 포함 CPU: arm64-v8a, armeabi-v7a, x86_64

에뮬레이터 시험(디버그 빌드만):

- 등록 주소 전달: `adb shell am start -n io.github.budongjw.debutkit.phone/.MainActivity --es link '<QR 주소>'`
- PC를 127.0.0.1로 등록하면 `adb reverse tcp:8792 tcp:8792`로 등록 확인 요청이, UDP 추적 값은 에뮬레이터의 PC 주소(10.0.2.2)로 간다
- 얼굴을 비출 수 없으면 `/sdcard/Android/data/io.github.budongjw.debutkit.phone/files/test-face.jpg`를 넣고 시험 이미지로 추적

## iOS

[ios/README.md](ios/README.md)

## 라이선스

- 앱: Apache-2.0(debutkit과 같음)
- 안드로이드: MediaPipe Tasks Vision(Apache-2.0), CameraX, Jetpack Compose, AndroidX(Apache-2.0), ZXing core(Apache-2.0, QR 코드 읽기), WebRTC(io.github.webrtc-sdk, BSD-3과 WebRTC 제3자 라이선스)
- iOS: 운영체제 기본 기능(ARKit, AVFoundation, CryptoKit, Network)과 WebRTC(stasel/WebRTC 배포 바이너리, WebRTC 라이선스 https://webrtc.org/support/license). 프로젝트 생성 도구 XcodeGen(MIT, 빌드에만 사용)
