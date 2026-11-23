import ARKit
import AVFoundation
import SwiftUI
import WebRTC

private let ink = Color(red: 0x1E / 255, green: 0x23 / 255, blue: 0x27 / 255)
private let paper = Color(red: 0xFA / 255, green: 0xF7 / 255, blue: 0xF5 / 255)
private let ok = Color(red: 0x1F / 255, green: 0x7A / 255, blue: 0x4D / 255)
private let bad = Color(red: 0xB3 / 255, green: 0x26 / 255, blue: 0x1E / 255)

@main
struct DebutkitPhoneApp: App {
    @StateObject private var model = Model()

    var body: some Scene {
        WindowGroup { MainView().environmentObject(model) }
    }
}

/// 등록, 승인 대기, 추적 상태.
@MainActor
final class Model: ObservableObject {
    enum Step { case unpaired, scanning, connecting, waiting, ready }

    @Published var step: Step
    @Published var pairing: Pairing?
    @Published var code = ""
    @Published var message = ""
    @Published var tracking = false
    @Published var found = false
    @Published var rate = 0
    @Published var hot = ProcessInfo.processInfo.thermalState.rawValue >= ProcessInfo.ThermalState.serious.rawValue
    @Published var dimmed = false
    @Published var cameraMode = false
    @Published var sending = false
    @Published var front = false
    @Published var cameraState: CameraSender.State?

    private var sender: Sender?
    private var tracker: FaceTracker?
    private var camera: CameraSender?
    private var poll: Task<Void, Never>?
    private var shown = Date.distantPast
    private var brightness = UIScreen.main.brightness

    init() {
        let saved = Store.load()
        pairing = saved
        step = saved == nil ? .unpaired : .connecting
        NotificationCenter.default.addObserver(forName: ProcessInfo.thermalStateDidChangeNotification, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.hot = ProcessInfo.processInfo.thermalState.rawValue >= ProcessInfo.ThermalState.serious.rawValue }
        }
        if saved != nil { startPolling() }
    }

    func accept(_ link: String) {
        guard let parsed = Pairing.parse(link) else {
            message = "debutkit 휴대폰 조작 QR 주소가 아님(http://PC주소:포트/remote#... 형식)"
            step = .unpaired
            return
        }
        Store.save(link)
        pairing = parsed
        code = Signing.confirmCode(parsed.secret)
        message = ""
        step = .connecting
        startPolling()
    }

    func forget(_ reason: String) {
        stopTracking()
        stopCamera()
        poll?.cancel()
        Store.clear()
        pairing = nil
        step = .unpaired
        message = reason
    }

    /// 승인될 때까지 2초마다, 승인 뒤에는 10초마다(PC에서 삭제하면 등록 화면으로) 등록 확인.
    private func startPolling() {
        poll?.cancel()
        poll = Task { [weak self] in
            while !Task.isCancelled {
                guard let self, let pairing = self.pairing else { return }
                do {
                    let hello = try await Client(pairing: pairing).hello(name: UIDevice.current.model)
                    self.code = hello.code
                    if self.step != .ready { self.message = "" }
                    if hello.approved {
                        self.step = .ready
                    } else {
                        if self.step == .ready { self.stopTracking() }
                        self.step = .waiting
                    }
                } catch let error as PcError {
                    if error.status == 401 && !error.message.contains("시각") {
                        self.forget("\(error.message). 이 휴대폰의 등록 정보를 지웠습니다.")
                        return
                    }
                    self.message = error.message
                } catch {
                    if self.step != .ready {
                        self.message = "PC에 연결하지 못함: 같은 Wi-Fi인지, PC의 휴대폰 조작 화면이 켜져 있는지, 로컬 네트워크 허용 확인"
                    }
                }
                try? await Task.sleep(nanoseconds: (self.step == .ready ? 10 : 2) * 1_000_000_000)
            }
        }
    }

    func startTracking() {
        guard let pairing, FaceTracker.isSupported else {
            message = "이 기기는 ARKit 얼굴 추적을 지원하지 않음(Face ID 카메라 또는 A12 이상 필요)"
            return
        }
        let sender = Sender(pairing)
        self.sender = sender
        let tracker = FaceTracker { [weak self] frame in
            let hot = ProcessInfo.processInfo.thermalState.rawValue >= ProcessInfo.ThermalState.serious.rawValue
            sender.send(frame, interval: hot ? 66 : 33)
            let rate = sender.rate
            let found = frame.found
            Task { @MainActor [weak self] in self?.show(found: found, rate: rate) }
        }
        self.tracker = tracker
        tracker.start()
        tracking = true
        UIApplication.shared.isIdleTimerDisabled = true
    }

    /// 화면 표시(0.25초마다).
    private func show(found: Bool, rate: Int) {
        guard Date().timeIntervalSince(shown) > 0.25 else { return }
        shown = Date()
        self.found = found
        self.rate = rate
    }

    func stopTracking() {
        tracker?.stop()
        tracker = nil
        sender?.close()
        sender = nil
        tracking = false
        found = false
        UIApplication.shared.isIdleTimerDisabled = false
        if dimmed { toggleDim() }
    }

    var session: ARSession? { tracker?.session }
    var cameraTrack: RTCVideoTrack? { camera?.track }

    /// 얼굴 추적과 카메라 영상 중 하나(카메라는 하나만 쓸 수 있음).
    func setCameraMode(_ on: Bool) {
        guard on != cameraMode else { return }
        stopTracking()
        stopCamera()
        cameraMode = on
    }

    func startCamera() {
        guard let pairing else { return }
        AVCaptureDevice.requestAccess(for: .video) { granted in
            Task { @MainActor [weak self] in
                guard let self else { return }
                guard granted else {
                    self.message = "카메라 사용이 허용되지 않음: 설정에서 debutkit 휴대폰의 카메라 허용"
                    return
                }
                let sender = CameraSender(pairing) { state in
                    Task { @MainActor [weak self] in self?.cameraState = state }
                }
                self.camera = sender
                sender.start(front: self.front)
                sender.lower(self.hot)
                self.sending = true
                UIApplication.shared.isIdleTimerDisabled = true
            }
        }
    }

    func stopCamera() {
        camera?.stop()
        camera = nil
        sending = false
        cameraState = nil
        UIApplication.shared.isIdleTimerDisabled = tracking
    }

    func toggleDim() {
        dimmed.toggle()
        if dimmed {
            brightness = UIScreen.main.brightness
            UIScreen.main.brightness = 0.02
        } else {
            UIScreen.main.brightness = brightness
        }
    }
}

struct MainView: View {
    @EnvironmentObject var model: Model

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("debutkit 휴대폰").font(.headline).foregroundColor(.white)
                Spacer()
                if let pairing = model.pairing { Text("\(pairing.host):\(pairing.port)").font(.caption).foregroundColor(.white.opacity(0.75)) }
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .background(ink.ignoresSafeArea(edges: .top))
            ScrollView {
                VStack(spacing: 12) {
                    switch model.step {
                    case .unpaired: UnpairedView()
                    case .scanning: ScanningView()
                    case .connecting, .waiting: WaitingView()
                    case .ready: ReadyView()
                    }
                }
                .padding(16)
            }
        }
        .background(paper.ignoresSafeArea())
        .preferredColorScheme(.light)
    }
}

private struct Card<Content: View>: View {
    @ViewBuilder let content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 8) { content }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .background(Color.white)
            .cornerRadius(6)
            .shadow(color: .black.opacity(0.08), radius: 2, y: 1)
    }
}

private struct BigButton: View {
    let title: String
    var primary = true
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            Text(title).fontWeight(.bold).frame(maxWidth: .infinity, minHeight: 50)
                .foregroundColor(primary ? .white : ink)
                .background(primary ? ink : Color.white)
                .overlay(RoundedRectangle(cornerRadius: 25).stroke(ink.opacity(primary ? 0 : 0.3)))
                .cornerRadius(25)
        }
    }
}

private struct UnpairedView: View {
    @EnvironmentObject var model: Model
    @State private var link = ""

    var body: some View {
        Card {
            Text("PC와 연결").font(.title3).bold()
            Text("PC에서 debutkit 오버레이 설정 화면의 휴대폰 연결을 열고, 휴대폰 조작 화면을 켠 뒤 새 휴대폰 QR 만들기를 누르십시오. 휴대폰과 PC는 같은 Wi-Fi여야 합니다.")
            BigButton(title: "QR 코드 찍기") { model.step = .scanning }
        }
        Card {
            Text("주소로 연결").bold()
            Text("QR 코드를 찍을 수 없으면 PC의 debutkit remote pair 명령이 알려 주는 주소를 붙여 넣으십시오.").font(.footnote).foregroundColor(.secondary)
            TextField("http://192.168.0.5:8792/remote#d=...", text: $link)
                .textInputAutocapitalization(.never).disableAutocorrection(true).textFieldStyle(.roundedBorder)
            BigButton(title: "연결", primary: false) { model.accept(link) }.disabled(link.isEmpty)
        }
        if !model.message.isEmpty { Text(model.message).foregroundColor(bad) }
        Card {
            Text("이 앱이 하는 일").bold()
            Text("휴대폰 앞면 카메라(ARKit)로 얼굴을 추적해 머리 움직임과 표정 52개를 debutkit PC로 보냅니다. 카메라 영상은 휴대폰 안에서만 처리하고 숫자 값만 보내며, 저장하거나 인터넷으로 보내지 않습니다.")
                .font(.footnote).foregroundColor(.secondary)
        }
    }
}

private struct ScanningView: View {
    @EnvironmentObject var model: Model

    var body: some View {
        Card {
            Text("PC 화면의 QR 코드를 비추십시오").bold()
            QRScanner { model.accept($0) }.frame(height: 420).cornerRadius(6)
            BigButton(title: "취소", primary: false) { model.step = .unpaired }
        }
    }
}

private struct WaitingView: View {
    @EnvironmentObject var model: Model

    var body: some View {
        Card {
            Text(model.step == .waiting ? "PC에서 승인 필요" : "PC에 연결 중").font(.title3).bold()
            Text("PC의 휴대폰 연결 화면 등록 기기 목록에 같은 확인 번호가 보이면 승인을 누르십시오.")
            Text(model.code).font(.system(size: 48, weight: .bold, design: .monospaced)).kerning(8).frame(maxWidth: .infinity)
            Text("승인되면 자동으로 추적 화면이 열립니다.").font(.footnote).foregroundColor(.secondary)
            if !model.message.isEmpty { Text(model.message).font(.footnote).foregroundColor(bad) }
        }
        BigButton(title: "등록 취소", primary: false) { model.forget("") }
    }
}

/// 추적 중인 ARKit 화면 미리보기(얼굴이 화면 안에 들어오는지 확인).
private struct FacePreview: UIViewRepresentable {
    let session: ARSession
    func makeUIView(context: Context) -> ARSCNView {
        let view = ARSCNView()
        view.session = session
        view.automaticallyUpdatesLighting = false
        return view
    }
    func updateUIView(_ view: ARSCNView, context: Context) {}
}

/// 승인된 뒤: 얼굴 추적 또는 카메라 영상.
private struct ReadyView: View {
    @EnvironmentObject var model: Model

    var body: some View {
        Picker("방식", selection: Binding(get: { model.cameraMode }, set: { model.setCameraMode($0) })) {
            Text("얼굴 추적").tag(false)
            Text("카메라 영상").tag(true)
        }
        .pickerStyle(.segmented)
        if model.cameraMode { CameraView() } else { TrackingView() }
    }
}

/// 보내는 카메라 영상 미리보기(Metal).
private struct CameraPreview: UIViewRepresentable {
    let track: RTCVideoTrack
    let mirror: Bool

    func makeUIView(context: Context) -> RTCMTLVideoView {
        let view = RTCMTLVideoView()
        view.videoContentMode = .scaleAspectFit
        view.transform = mirror ? CGAffineTransform(scaleX: -1, y: 1) : .identity
        track.add(view)
        return view
    }

    func updateUIView(_ view: RTCMTLVideoView, context: Context) {}
}

private struct CameraView: View {
    @EnvironmentObject var model: Model

    private var label: (String, Color) {
        switch model.cameraState {
        case .starting, .waiting: return ("OBS 수신 화면과 연결 중", .secondary)
        case .connected: return ("보내는 중", ok)
        case .retrying: return ("연결 끊김: 다시 연결 중", bad)
        case .noReceiver: return ("수신 화면 응답 없음: PC 휴대폰 연결 화면에서 앱 영상용 OBS 소스 만들기, OBS 실행 확인", bad)
        case .failed: return ("연결 실패: PC에서 이 휴대폰의 등록과 승인 확인", bad)
        case .stopped, .none: return (model.sending ? "준비 중" : "멈춤", .secondary)
        }
    }

    var body: some View {
        Card {
            Text("카메라 영상").font(.title3).bold()
            Text("휴대폰 카메라 영상을 PC OBS의 [DK] 휴대폰 카메라(앱) 소스로 보냅니다. 같은 Wi-Fi에서 직접 보내며 소리는 보내지 않습니다.").font(.subheadline)
            if model.sending { Text(label.0).bold().foregroundColor(label.1) }
            if model.hot { Text("휴대폰이 뜨거움: 해상도를 낮췄습니다. 충전기를 빼거나 케이스를 벗기고 그늘에 두십시오.").font(.footnote).foregroundColor(bad) }
            if !model.message.isEmpty { Text(model.message).font(.footnote).foregroundColor(bad) }
        }
        if model.sending, let track = model.cameraTrack {
            CameraPreview(track: track, mirror: model.front).frame(height: 360).background(Color.black).cornerRadius(6)
        }
        BigButton(title: model.sending ? "보내기 멈춤" : "보내기 시작") { model.sending ? model.stopCamera() : model.startCamera() }
        HStack(spacing: 8) {
            BigButton(title: model.front ? "앞면 카메라" : "뒷면 카메라", primary: false) { model.front.toggle() }.disabled(model.sending)
            BigButton(title: model.dimmed ? "밝게" : "화면 어둡게", primary: false) { model.toggleDim() }
        }
        BigButton(title: "연결 해제", primary: false) { model.forget("이 휴대폰의 등록 정보를 지웠습니다.") }
        Text("카메라를 바꾸려면 보내기를 멈춘 뒤 고르십시오. 앱을 닫거나 다른 앱으로 바꾸면 보내기가 멈춥니다. 영상은 PC로만 보내며 저장하지 않습니다.")
            .font(.footnote).foregroundColor(.secondary)
    }
}

private struct TrackingView: View {
    @EnvironmentObject var model: Model

    var body: some View {
        Card {
            Text("얼굴 추적").font(.title3).bold()
            if model.tracking {
                Text(model.found ? "추적 중" : "얼굴을 찾지 못함: 화면을 정면으로 보십시오").bold().foregroundColor(model.found ? ok : bad)
                Text("PC로 보내는 횟수: 초당 \(model.rate)회").font(.subheadline)
            } else {
                Text("시작을 누르면 앞면 카메라로 얼굴을 추적해 PC로 보냅니다. 휴대폰을 얼굴 정면, 30에서 50cm 거리에 세워 두십시오.").font(.subheadline)
            }
            if model.hot { Text("휴대폰이 뜨거움: 보내는 횟수를 줄였습니다. 충전기를 빼거나 케이스를 벗기고 그늘에 두십시오.").font(.footnote).foregroundColor(bad) }
            if !model.message.isEmpty { Text(model.message).font(.footnote).foregroundColor(bad) }
        }
        if model.tracking, let session = model.session {
            FacePreview(session: session).frame(height: 360).cornerRadius(6)
        }
        BigButton(title: model.tracking ? "추적 멈춤" : "추적 시작") { model.tracking ? model.stopTracking() : model.startTracking() }
        HStack(spacing: 8) {
            BigButton(title: model.dimmed ? "밝게" : "화면 어둡게", primary: false) { model.toggleDim() }
            BigButton(title: "연결 해제", primary: false) { model.forget("이 휴대폰의 등록 정보를 지웠습니다.") }
        }
        Text("화면 어둡게는 배터리와 발열을 줄입니다. 추적 중에는 화면이 꺼지지 않습니다. 앱을 닫거나 다른 앱으로 바꾸면 추적이 멈춥니다.")
            .font(.footnote).foregroundColor(.secondary)
    }
}
