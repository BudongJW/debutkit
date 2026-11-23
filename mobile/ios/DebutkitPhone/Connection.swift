import Foundation
import Network

/// 앱에 저장한 등록 정보(앱 전용 저장소).
enum Store {
    private static let key = "debutkit.link"

    static func load() -> Pairing? { UserDefaults.standard.string(forKey: key).flatMap(Pairing.parse) }
    static func save(_ link: String) { UserDefaults.standard.set(link.trimmingCharacters(in: .whitespacesAndNewlines), forKey: key) }
    static func clear() { UserDefaults.standard.removeObject(forKey: key) }
}

struct Hello {
    let approved: Bool
    let code: String
    let name: String
}

struct PcError: Error, LocalizedError {
    let message: String
    let status: Int
    var errorDescription: String? { message }
}

/// PC의 휴대폰 조작 화면(서명 요청).
struct Client {
    let pairing: Pairing

    /// 등록 확인. 승인 전이면 approved=false와 확인 번호. 기기가 삭제됐으면 PcError(401).
    func hello(name: String) async throws -> Hello {
        let body = try JSONSerialization.data(withJSONObject: ["name": name])
        let answer = Answers.object(try await request("POST", "/remote/api/hello", body))
        return Hello(approved: answer["approved"] as? Bool ?? false, code: answer["code"] as? String ?? Signing.confirmCode(pairing.secret),
                     name: answer["name"] as? String ?? name)
    }

    /// 서명한 POST 요청(카메라 영상 통화 등). 응답 JSON.
    func post(_ path: String, _ body: [String: Any]) async throws -> [String: Any] {
        Answers.object(try await request("POST", path, try JSONSerialization.data(withJSONObject: body)))
    }

    private func request(_ method: String, _ path: String, _ body: Data) async throws -> Data {
        guard let url = URL(string: pairing.base + path) else { throw PcError(message: "잘못된 주소", status: 0) }
        let stamp = String(Int64(Date().timeIntervalSince1970 * 1000))
        let nonce = Signing.nonce()
        var request = URLRequest(url: url, timeoutInterval: 4)
        request.httpMethod = method
        request.setValue(pairing.id, forHTTPHeaderField: "X-Debutkit-Device")
        request.setValue(stamp, forHTTPHeaderField: "X-Debutkit-Time")
        request.setValue(nonce, forHTTPHeaderField: "X-Debutkit-Nonce")
        request.setValue(Signing.sign(pairing.secret, method, path, stamp, nonce, body), forHTTPHeaderField: "X-Debutkit-Sign")
        if !body.isEmpty {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200...299).contains(status) else {
            throw PcError(message: Answers.object(data)["error"] as? String ?? "PC 응답 오류(\(status))", status: status)
        }
        return data
    }
}

/// 얼굴 추적 값을 PC로(UDP, 초당 최대 30회).
final class Sender {
    private let pairing: Pairing
    private let connection: NWConnection
    private let lock = NSLock()
    private var lastStamp: Int64 = 0
    private var lastSent: Int64 = 0
    private var lastFound = true
    private(set) var sentTimes: [Int64] = []

    init(_ pairing: Pairing) {
        self.pairing = pairing
        connection = NWConnection(host: NWEndpoint.Host(pairing.host), port: NWEndpoint.Port(rawValue: UInt16(pairing.port))!, using: .udp)
        connection.start(queue: DispatchQueue(label: "debutkit.sender"))
    }

    /// 간격(밀리초)보다 빨리 오면 보내지 않는다. 얼굴을 놓친 순간은 바로, 계속 놓친 동안은 0.2초마다.
    @discardableResult
    func send(_ frame: Frame, interval: Int64 = 33) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        if frame.found && now - lastSent < interval { return false }
        if !frame.found && !lastFound && now - lastSent < 200 { return false }
        lastFound = frame.found
        let stamp = max(now, lastStamp + 1) // PC는 이전 패킷보다 새로운 시각만 받는다
        lastStamp = stamp
        lastSent = now
        sentTimes = sentTimes.filter { now - $0 < 1000 } + [now]
        connection.send(content: Packets.packet(pairing, stamp, frame), completion: .contentProcessed { _ in })
        return true
    }

    var rate: Int {
        lock.lock()
        defer { lock.unlock() }
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        return sentTimes.filter { now - $0 < 1000 }.count
    }

    func close() {
        send(Frame(found: false))
        connection.cancel()
    }
}
