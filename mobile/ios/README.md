# debutkit 휴대폰 앱(iOS)

앱 스토어 배포 전이므로 Mac에서 직접 빌드해 설치한다. 무료 Apple 계정으로도 본인 기기에 설치할 수 있다(7일마다 다시 설치).

## 필요 조건

- Mac, Xcode 15 이상, Homebrew
- iPhone 또는 iPad: iOS 15 이상, ARKit 얼굴 추적 지원(Face ID 카메라 또는 A12 이상)
- Apple 계정(Xcode의 Settings, Accounts에서 추가)

## 빌드와 설치

```
brew install xcodegen
cd mobile/ios
xcodegen generate
open DebutkitPhone.xcodeproj
```

1. Xcode에서 DebutkitPhone 대상의 Signing and Capabilities를 열고 Team에 본인 Apple 계정 선택
2. 번들 식별자가 이미 쓰이고 있다는 오류가 나오면 `io.github.budongjw.debutkit.phone` 뒤에 본인 이름 등을 붙여 변경
3. 휴대폰을 USB로 연결하고 실행 대상으로 선택한 뒤 Run
4. 처음 설치하면 휴대폰 설정의 일반, VPN 및 기기 관리에서 개발자 앱 신뢰

## 처음 실행

- 카메라, 로컬 네트워크 접근을 허용(로컬 네트워크를 거부하면 PC에 연결되지 않으며 설정의 개인정보 보호에서 다시 켤 수 있음)
- PC 오버레이 설정 화면의 휴대폰 연결에서 휴대폰 조작 화면을 켜고 새 휴대폰 QR 만들기, 앱에서 QR 코드 찍기, PC에서 승인

## 시험

```
xcodebuild test -project DebutkitPhone.xcodeproj -scheme DebutkitPhone -destination "platform=iOS Simulator,name=iPhone 16" CODE_SIGNING_ALLOWED=NO
```

- 단위 테스트는 PC와 같은 서명, 확인 번호, 패킷 형식인지 확인(기대값은 파이썬과 안드로이드 테스트와 같음)
- 시뮬레이터는 ARKit 얼굴 추적을 지원하지 않으므로 추적은 실기기에서만 확인
