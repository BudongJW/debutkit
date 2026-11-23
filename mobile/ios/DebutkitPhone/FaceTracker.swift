import ARKit
import Foundation

/// ARKit 얼굴 추적(얼굴 인식 카메라 또는 A12 이상): 머리 회전과 표정 52개. 영상은 휴대폰 안에서만 처리하고 숫자 값만 보낸다.
final class FaceTracker: NSObject, ARSessionDelegate {
    static var isSupported: Bool { ARFaceTrackingConfiguration.isSupported }

    /// ARKit 이름 순서(PC와 같음)의 표정 위치.
    static let locations: [ARFaceAnchor.BlendShapeLocation] = [
        .browDownLeft, .browDownRight, .browInnerUp, .browOuterUpLeft, .browOuterUpRight, .cheekPuff, .cheekSquintLeft, .cheekSquintRight,
        .eyeBlinkLeft, .eyeBlinkRight, .eyeLookDownLeft, .eyeLookDownRight, .eyeLookInLeft, .eyeLookInRight, .eyeLookOutLeft, .eyeLookOutRight,
        .eyeLookUpLeft, .eyeLookUpRight, .eyeSquintLeft, .eyeSquintRight, .eyeWideLeft, .eyeWideRight, .jawForward, .jawLeft, .jawOpen,
        .jawRight, .mouthClose, .mouthDimpleLeft, .mouthDimpleRight, .mouthFrownLeft, .mouthFrownRight, .mouthFunnel, .mouthLeft,
        .mouthLowerDownLeft, .mouthLowerDownRight, .mouthPressLeft, .mouthPressRight, .mouthPucker, .mouthRight, .mouthRollLower,
        .mouthRollUpper, .mouthShrugLower, .mouthShrugUpper, .mouthSmileLeft, .mouthSmileRight, .mouthStretchLeft, .mouthStretchRight,
        .mouthUpperUpLeft, .mouthUpperUpRight, .noseSneerLeft, .noseSneerRight, .tongueOut,
    ]

    let session = ARSession()
    private let onFrame: (Frame) -> Void

    init(onFrame: @escaping (Frame) -> Void) {
        self.onFrame = onFrame
        super.init()
        session.delegate = self
        session.delegateQueue = DispatchQueue(label: "debutkit.face")
    }

    func start() {
        let configuration = ARFaceTrackingConfiguration()
        configuration.maximumNumberOfTrackedFaces = 1
        configuration.isLightEstimationEnabled = false
        session.run(configuration, options: [.resetTracking, .removeExistingAnchors])
    }

    func stop() { session.pause() }

    func session(_ session: ARSession, didUpdate anchors: [ARAnchor]) {
        guard let face = anchors.compactMap({ $0 as? ARFaceAnchor }).first, let camera = session.currentFrame?.camera else { return }
        guard face.isTracked else { return onFrame(Frame(found: false)) }
        // 세로 화면 기준 카메라 좌표의 얼굴 자세(정면을 보면 얼굴의 z가 카메라 쪽)
        let relative = camera.viewMatrix(for: .portrait) * face.transform
        let shapes = FaceTracker.locations.map { Float(truncating: face.blendShapes[$0] ?? 0) }
        onFrame(Frame(found: true, rotation: headRotation(relative), shapes: shapes))
    }

    func session(_ session: ARSession, didRemove anchors: [ARAnchor]) {
        if anchors.contains(where: { $0 is ARFaceAnchor }) { onFrame(Frame(found: false)) }
    }
}
