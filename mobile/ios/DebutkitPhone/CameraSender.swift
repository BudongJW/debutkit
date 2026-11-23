import AVFoundation
import Foundation
import WebRTC

/// 휴대폰 카메라 영상을 WebRTC(libwebrtc)로 PC의 OBS 수신 화면(/camera/view)에 직접 보낸다(안드로이드 CameraSender.kt와 같은 흐름).
/// 연결 정보(SDP)만 PC의 휴대폰 조작 화면에 서명 요청으로 보내고, 영상은 같은 Wi-Fi에서 직접 오간다(외부 서버 없음). 소리는 보내지 않는다.
/// 연결이 3초 넘게 끊기면(OBS 소스를 다시 불러온 경우 등) 다시 연결한다.
final class CameraSender: NSObject, RTCPeerConnectionDelegate {
    enum State { case starting, waiting, connected, retrying, noReceiver, failed, stopped }

    private static let factory: RTCPeerConnectionFactory = {
        RTCInitializeSSL()
        return RTCPeerConnectionFactory(encoderFactory: RTCDefaultVideoEncoderFactory(), decoderFactory: RTCDefaultVideoDecoderFactory())
    }()

    private let client: Client
    private let onState: (State) -> Void
    private var capturer: RTCCameraVideoCapturer?
    private var source: RTCVideoSource?
    private(set) var track: RTCVideoTrack?
    private var peer: RTCPeerConnection?
    private var callId = ""
    private var running = false
    private var task: Task<Void, Never>?

    init(_ pairing: Pairing, onState: @escaping (State) -> Void) {
        client = Client(pairing: pairing)
        self.onState = onState
        super.init()
    }

    /// 카메라 시작과 연결. front: 앞면 카메라(셀카), 아니면 뒷면.
    func start(front: Bool) {
        running = true
        onState(.starting)
        let source = CameraSender.factory.videoSource()
        let capturer = RTCCameraVideoCapturer(delegate: source)
        let devices = RTCCameraVideoCapturer.captureDevices()
        guard let device = devices.first(where: { $0.position == (front ? .front : .back) }) ?? devices.first else {
            onState(.failed)
            return
        }
        let formats = RTCCameraVideoCapturer.supportedFormats(for: device)
        let width = { (format: AVCaptureDevice.Format) in Int(CMVideoFormatDescriptionGetDimensions(format.formatDescription).width) }
        guard let format = formats.min(by: { abs(width($0) - 1280) < abs(width($1) - 1280) }) else {
            onState(.failed)
            return
        }
        let fps = min(30, Int(format.videoSupportedFrameRateRanges.map(\.maxFrameRate).max() ?? 30))
        capturer.startCapture(with: device, format: format, fps: fps)
        self.source = source
        self.capturer = capturer
        track = CameraSender.factory.videoTrack(with: source, trackId: "camera")
        task = Task { [weak self] in await self?.loop() }
    }

    /// 발열 시 해상도, 초당 장면 수를 낮춘다.
    func lower(_ hot: Bool) {
        source?.adaptOutputFormat(toWidth: Int32(hot ? 960 : 1280), height: Int32(hot ? 540 : 720), fps: Int32(hot ? 24 : 30))
    }

    func stop() {
        running = false
        task?.cancel()
        let id = callId
        let client = self.client
        if !id.isEmpty { Task { try? await client.stopCall(id: id) } }
        peer?.close()
        peer = nil
        capturer?.stopCapture()
        capturer = nil
        track = nil
        source = nil
        onState(.stopped)
    }

    private func loop() async {
        while running && !Task.isCancelled {
            let result = await connectOnce()
            if result != .waiting {
                onState(result)
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                continue
            }
            var badSince: Date?
            while running && !Task.isCancelled { // 연결을 지켜보다 3초 넘게 끊기면 다시 연결
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                let state = peer?.connectionState ?? .closed
                if state == .failed || state == .disconnected || state == .closed {
                    badSince = badSince ?? Date()
                    if let since = badSince, Date().timeIntervalSince(since) >= 3 { break }
                } else {
                    badSince = nil
                }
            }
            if running { onState(.retrying) }
        }
    }

    private func connectOnce() async -> State {
        peer?.close()
        onState(.waiting)
        let config = RTCConfiguration()
        config.iceServers = []
        config.sdpSemantics = .unifiedPlan
        config.continualGatheringPolicy = .gatherOnce
        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)
        guard let track, let pc = CameraSender.factory.peerConnection(with: config, constraints: constraints, delegate: self) else { return .failed }
        peer = pc
        let sender = pc.add(track, streamIds: ["debutkit"])
        if let sender {
            let parameters = sender.parameters
            parameters.encodings.forEach { $0.maxBitrateBps = NSNumber(value: 4_000_000) }
            sender.parameters = parameters
        }
        do {
            let offer: RTCSessionDescription = try await withCheckedThrowingContinuation { done in
                pc.offer(for: constraints) { sdp, error in
                    if let sdp { done.resume(returning: sdp) } else { done.resume(throwing: error ?? PcError(message: "연결 정보 만들기 실패", status: 0)) }
                }
            }
            try await withCheckedThrowingContinuation { (done: CheckedContinuation<Void, Error>) in
                pc.setLocalDescription(offer) { error in if let error { done.resume(throwing: error) } else { done.resume() } }
            }
            for _ in 0..<30 where pc.iceGatheringState != .complete { // 외부 서버가 없어 금방 끝남
                try await Task.sleep(nanoseconds: 100_000_000)
            }
            guard let local = pc.localDescription?.sdp else { return .retrying }
            callId = try await client.offer(sdp: local)
            for _ in 0..<40 {
                guard running, peer === pc else { return .stopped }
                let answer = try await client.answer(id: callId)
                switch answer["state"] as? String {
                case "answered":
                    let remote = RTCSessionDescription(type: .answer, sdp: answer["sdp"] as? String ?? "")
                    try await withCheckedThrowingContinuation { (done: CheckedContinuation<Void, Error>) in
                        pc.setRemoteDescription(remote) { error in if let error { done.resume(throwing: error) } else { done.resume() } }
                    }
                    return .waiting
                case "ended":
                    return .noReceiver
                default:
                    try await Task.sleep(nanoseconds: 500_000_000)
                }
            }
            return .noReceiver
        } catch let error as PcError where (401...403).contains(error.status) {
            return .failed
        } catch {
            return .retrying
        }
    }

    // MARK: RTCPeerConnectionDelegate

    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCPeerConnectionState) {
        if newState == .connected { onState(.connected) }
    }

    func peerConnection(_ peerConnection: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didAdd stream: RTCMediaStream) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    func peerConnectionShouldNegotiate(_ peerConnection: RTCPeerConnection) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceConnectionState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceGatheringState) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}
    func peerConnection(_ peerConnection: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}
}

/// 카메라 영상 통화 요청(PC의 휴대폰 조작 화면, 서명).
extension Client {
    func offer(sdp: String) async throws -> String {
        let answer = try await post("/remote/api/camera/offer", ["sdp": sdp])
        guard let id = answer["id"] as? String else { throw PcError(message: "PC 응답 오류", status: 0) }
        return id
    }

    func answer(id: String) async throws -> [String: Any] { try await post("/remote/api/camera/answer", ["id": id]) }

    func stopCall(id: String) async throws { _ = try await post("/remote/api/camera/stop", ["id": id]) }
}
