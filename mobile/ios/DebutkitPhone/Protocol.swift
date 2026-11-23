import CryptoKit
import Foundation
import simd

/// debutkit PC와 주고받는 형식(PC의 src/debutkit/overlay/remote.py, 안드로이드 Protocol.kt와 같아야 한다).
///
/// - 등록: PC 휴대폰 연결 화면의 휴대폰 조작 QR(http://주소:포트/remote#d=기기&k=비밀값). 비밀값은 QR로만 전달
/// - 요청 서명: HMAC-SHA256(비밀값, "방식\n경로\n시각\n일회용 값\n본문 SHA-256")
/// - 얼굴 추적: 같은 주소, 같은 포트의 UDP. JSON 한 줄 + 줄바꿈 + HMAC-SHA256(비밀값, "udp\n" + JSON)
struct Pairing: Equatable, Codable {
    let host: String
    let port: Int
    let id: String
    let secret: String

    var base: String { "http://\(host):\(port)" }

    /// QR이나 붙여 넣은 주소에서 등록 정보. 형식이 아니면 nil.
    static func parse(_ text: String) -> Pairing? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let regex = try? NSRegularExpression(pattern: #"^http://(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})/remote#(.+)$"#),
              let match = regex.firstMatch(in: trimmed, range: NSRange(trimmed.startIndex..., in: trimmed)),
              let hostRange = Range(match.range(at: 1), in: trimmed), let portRange = Range(match.range(at: 2), in: trimmed),
              let fragmentRange = Range(match.range(at: 3), in: trimmed) else { return nil }
        let host = String(trimmed[hostRange])
        guard host.split(separator: ".").allSatisfy({ (Int($0) ?? 999) <= 255 }),
              let port = Int(trimmed[portRange]), (1...65535).contains(port) else { return nil }
        var params: [String: String] = [:]
        for part in trimmed[fragmentRange].split(separator: "&") {
            let pieces = part.split(separator: "=", maxSplits: 1).map(String.init)
            if pieces.count == 2 { params[pieces[0]] = pieces[1] }
        }
        guard let id = params["d"], id.range(of: "^[0-9a-f]{8}$", options: .regularExpression) != nil,
              let secret = params["k"], secret.count >= 32, secret.range(of: "^[A-Za-z0-9_-]+$", options: .regularExpression) != nil
        else { return nil }
        return Pairing(host: host, port: port, id: id, secret: secret)
    }
}

enum Signing {
    static func hex<D: Sequence>(_ bytes: D) -> String where D.Element == UInt8 { bytes.map { String(format: "%02x", $0) }.joined() }

    static func sha256Hex(_ data: Data) -> String { hex(SHA256.hash(data: data)) }

    static func hmacHex(_ key: String, _ message: Data) -> String {
        hex(HMAC<SHA256>.authenticationCode(for: message, using: SymmetricKey(data: Data(key.utf8))))
    }

    static func canonical(_ method: String, _ path: String, _ stamp: String, _ nonce: String, _ body: Data) -> String {
        "\(method.uppercased())\n\(path)\n\(stamp)\n\(nonce)\n\(sha256Hex(body))"
    }

    static func sign(_ secret: String, _ method: String, _ path: String, _ stamp: String, _ nonce: String, _ body: Data) -> String {
        hmacHex(secret, Data(canonical(method, path, stamp, nonce, body).utf8))
    }

    /// 휴대폰과 PC에 함께 보이는 4자리 확인 번호.
    static func confirmCode(_ secret: String) -> String {
        let digest = hmacHex(secret, Data("debutkit-confirm".utf8))
        let value = UInt64(digest.prefix(8), radix: 16) ?? 0
        return String(format: "%04d", value % 10000)
    }

    static func nonce() -> String {
        var bytes = [UInt8](repeating: 0, count: 16)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        return hex(bytes)
    }
}

/// ARKit 표정 52개(PC의 tracking.ARKIT_NAMES와 같은 순서).
let arkitNames = [
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight",
    "eyeLookUpLeft", "eyeLookUpRight", "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft", "eyeWideRight", "jawForward", "jawLeft", "jawOpen",
    "jawRight", "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight", "mouthFunnel", "mouthLeft",
    "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft", "mouthPressRight", "mouthPucker", "mouthRight", "mouthRollLower",
    "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthUpperUpLeft", "mouthUpperUpRight", "noseSneerLeft", "noseSneerRight", "tongueOut",
]

/// 한 프레임의 추적 값. rotation은 debutkit 기준(라디안 yaw, pitch, roll, 거울 처리 전).
struct Frame {
    var found: Bool
    var rotation: [Float] = [0, 0, 0]
    var shapes: [Float] = Array(repeating: 0, count: arkitNames.count)
}

enum Packets {
    private static func number(_ value: Float, _ digits: Int) -> String {
        String(format: "%.\(digits)f", locale: Locale(identifier: "en_US_POSIX"), Double(min(10, max(-10, value))))
    }

    static func json(_ pairing: Pairing, _ stamp: Int64, _ frame: Frame) -> String {
        var text = "{\"v\":1,\"d\":\"\(pairing.id)\",\"t\":\(stamp),\"f\":\(frame.found)"
        if frame.found {
            text += ",\"r\":[" + frame.rotation.map { number($0, 4) }.joined(separator: ",") + "]"
            text += ",\"b\":[" + frame.shapes.map { number(min(1, max(0, $0)), 3) }.joined(separator: ",") + "]"
        }
        return text + "}"
    }

    static func packet(_ pairing: Pairing, _ stamp: Int64, _ frame: Frame) -> Data {
        let json = json(pairing, stamp, frame)
        let signature = Signing.hmacHex(pairing.secret, Data("udp\n\(json)".utf8))
        return Data("\(json)\n\(signature)".utf8)
    }
}

/// 4x4 얼굴 변환(카메라 기준, 얼굴 좌표 x는 얼굴의 왼쪽, y 위, z 카메라 쪽)에서 머리 회전(라디안). PC 웹캠 추적과 같은 계산(R = Ry Rx Rz).
func headRotation(_ m: simd_float4x4) -> [Float] {
    func r(_ row: Int, _ col: Int) -> Float { m[col][row] }
    return [atan2(r(0, 2), r(2, 2)), asin(min(1, max(-1, -r(1, 2)))), atan2(r(1, 0), r(1, 1))]
}

/// PC 응답(JSON)에서 필요한 값.
enum Answers {
    static func object(_ data: Data) -> [String: Any] { (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:] }
}
