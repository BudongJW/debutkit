import simd
import XCTest
@testable import DebutkitPhone

/// PC(src/debutkit/overlay/remote.py)와 같은 결과인지: 기대값은 파이썬으로 계산한 값(안드로이드 ProtocolTest와 같음).
final class ProtocolTests: XCTestCase {
    private let secret = "ZcII2jarVh6UjJQLndvXBClKOvFiCIoffm-I0RoPBdM"
    private var pairing: Pairing { Pairing(host: "192.168.0.5", port: 8792, id: "f0f542b3", secret: secret) }

    func testParsesOnlyDebutkitLinks() {
        XCTAssertEqual(Pairing.parse(" http://192.168.0.5:8792/remote#d=f0f542b3&k=\(secret) "), pairing)
        XCTAssertNil(Pairing.parse("https://192.168.0.5:8792/remote#d=f0f542b3&k=\(secret)"))
        XCTAssertNil(Pairing.parse("http://192.168.0.300:8792/remote#d=f0f542b3&k=\(secret)"))
        XCTAssertNil(Pairing.parse("http://192.168.0.5:8792/remote#d=F0F542B3&k=\(secret)"))
        XCTAssertNil(Pairing.parse("http://192.168.0.5:8792/remote#d=f0f542b3&k=short"))
    }

    func testSignsLikeThePc() {
        let body = Data("{\"name\":\"Pixel 8\"}".utf8)
        XCTAssertEqual(Signing.sign(secret, "post", "/remote/api/hello", "1700000000000", "0123456789abcdef0123456789abcdef", body),
                       "afeb56db22324c3b723f8f2e263844d96144f4b96128262bf624158fb1b6f18f")
        XCTAssertEqual(Signing.confirmCode(secret), "8696")
        XCTAssertEqual(Signing.nonce().count, 32)
    }

    func testPacketIsSignedJsonLine() {
        let lost = String(decoding: Packets.packet(pairing, 1_700_000_000_000, Frame(found: false)), as: UTF8.self)
        XCTAssertEqual(lost, "{\"v\":1,\"d\":\"f0f542b3\",\"t\":1700000000000,\"f\":false}\nbd6b1091aa6cbdafe52ada3a5322d0f6d2aca1a2488b06a950a3ceae3fb2744d")
        var shapes = [Float](repeating: 0, count: 52)
        shapes[24] = 0.5
        shapes[0] = 1.7
        let json = Packets.json(pairing, 5, Frame(found: true, rotation: [0.1, -0.2, 0.05], shapes: shapes))
        XCTAssertTrue(json.hasPrefix("{\"v\":1,\"d\":\"f0f542b3\",\"t\":5,\"f\":true,\"r\":[0.1000,-0.2000,0.0500],\"b\":[1.000,"))
        XCTAssertTrue(json.contains(",0.500,"))
    }

    func testNamesMatchThePc() {
        XCTAssertEqual(arkitNames.count, 52)
        XCTAssertEqual(arkitNames, arkitNames.sorted())
        XCTAssertEqual(arkitNames.firstIndex(of: "jawOpen"), 24)
    }

    func testHeadRotation() {
        XCTAssertEqual(headRotation(matrix_identity_float4x4), [0, 0, 0])
        let angle = Float(20 * Double.pi / 180)
        let yaw = simd_float4x4(simd_quatf(angle: angle, axis: SIMD3<Float>(0, 1, 0)))
        let result = headRotation(yaw)
        XCTAssertEqual(result[0], angle, accuracy: 1e-5)
        XCTAssertEqual(result[1], 0, accuracy: 1e-5)
    }
}
