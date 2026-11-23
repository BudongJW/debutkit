package io.github.budongjw.debutkit.phone

import android.content.Context
import org.json.JSONObject
import org.webrtc.Camera2Enumerator
import org.webrtc.CameraVideoCapturer
import org.webrtc.DataChannel
import org.webrtc.DefaultVideoDecoderFactory
import org.webrtc.DefaultVideoEncoderFactory
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpReceiver
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.SurfaceTextureHelper
import org.webrtc.VideoSink
import org.webrtc.VideoSource
import org.webrtc.VideoTrack
import java.io.IOException
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * 휴대폰 카메라 영상을 WebRTC(libwebrtc, BSD-3)로 PC의 OBS 수신 화면(/camera/view)에 직접 보낸다.
 * 연결 정보(SDP)만 PC의 휴대폰 조작 화면에 서명 요청으로 보내고(PC의 camcall.py가 중계), 영상은 같은 Wi-Fi에서 직접 오간다(외부 서버 없음).
 * 소리는 보내지 않는다(PC 마이크 사용). 연결이 끊기면(OBS 소스를 다시 불러온 경우 등) 3초 뒤 다시 연결한다.
 */
class CameraSender(
    private val context: Context,
    private val pairing: Pairing,
    val egl: EglBase,
    private val onState: (State) -> Unit,
) : AutoCloseable {
    enum class State { Starting, Waiting, Connected, Retrying, NoReceiver, Failed, Stopped }

    private val factory: PeerConnectionFactory
    private val worker = Executors.newSingleThreadScheduledExecutor()
    private val client = Client(pairing)
    private var capturer: CameraVideoCapturer? = null
    private var helper: SurfaceTextureHelper? = null
    private var source: VideoSource? = null
    private var track: VideoTrack? = null
    private var peer: PeerConnection? = null
    private var callId = ""
    private var retry: ScheduledFuture<*>? = null
    private var sink: VideoSink? = null
    @Volatile private var running = false

    init {
        initialize(context)
        factory = PeerConnectionFactory.builder()
            .setVideoEncoderFactory(DefaultVideoEncoderFactory(egl.eglBaseContext, true, true)) // 하드웨어 인코더 우선
            .setVideoDecoderFactory(DefaultVideoDecoderFactory(egl.eglBaseContext))
            .createPeerConnectionFactory()
    }

    /** 카메라 시작과 연결. front: 앞면 카메라(셀카), 아니면 뒷면. */
    fun start(front: Boolean, width: Int = 1280, height: Int = 720, fps: Int = 30) {
        running = true
        onState(State.Starting)
        val enumerator = Camera2Enumerator(context)
        val names = enumerator.deviceNames
        val name = names.firstOrNull { enumerator.isFrontFacing(it) == front } ?: names.firstOrNull()
            ?: return onState(State.Failed)
        val camera = enumerator.createCapturer(name, null)
        val textures = SurfaceTextureHelper.create("debutkit-capture", egl.eglBaseContext)
        val video = factory.createVideoSource(false)
        camera.initialize(textures, context, video.capturerObserver)
        camera.startCapture(width, height, fps)
        capturer = camera
        helper = textures
        source = video
        track = factory.createVideoTrack("camera", video).also { created -> sink?.let(created::addSink) }
        worker.execute { connect() }
    }

    /** 미리보기 화면 연결. */
    fun preview(target: VideoSink?) {
        sink?.let { track?.removeSink(it) }
        sink = target
        target?.let { track?.addSink(it) }
    }

    /** 발열 시 해상도, 초당 장면 수를 낮춘다. */
    fun lower(hot: Boolean) {
        if (hot) capturer?.changeCaptureFormat(960, 540, 24) else capturer?.changeCaptureFormat(1280, 720, 30)
    }

    private fun connect() {
        if (!running) return
        peer?.dispose()
        peer = null
        onState(State.Waiting)
        val gathered = CountDownLatch(1)
        val config = PeerConnection.RTCConfiguration(emptyList()).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_ONCE
        }
        val pc = factory.createPeerConnection(config, object : PeerConnection.Observer {
            override fun onIceGatheringChange(state: PeerConnection.IceGatheringState) {
                if (state == PeerConnection.IceGatheringState.COMPLETE) gathered.countDown()
            }

            override fun onConnectionChange(state: PeerConnection.PeerConnectionState) {
                when (state) {
                    PeerConnection.PeerConnectionState.CONNECTED -> onState(State.Connected)
                    PeerConnection.PeerConnectionState.FAILED, PeerConnection.PeerConnectionState.DISCONNECTED -> scheduleRetry(State.Retrying)
                    else -> Unit
                }
            }

            override fun onSignalingChange(state: PeerConnection.SignalingState) = Unit
            override fun onIceConnectionChange(state: PeerConnection.IceConnectionState) = Unit
            override fun onIceConnectionReceivingChange(receiving: Boolean) = Unit
            override fun onIceCandidate(candidate: IceCandidate) = Unit
            override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>) = Unit
            override fun onAddStream(stream: MediaStream) = Unit
            override fun onRemoveStream(stream: MediaStream) = Unit
            override fun onDataChannel(channel: DataChannel) = Unit
            override fun onRenegotiationNeeded() = Unit
            override fun onAddTrack(receiver: RtpReceiver, streams: Array<out MediaStream>) = Unit
        }) ?: return scheduleRetry(State.Failed)
        peer = pc
        val sender = pc.addTrack(track, listOf("debutkit"))
        sender.parameters = sender.parameters.apply { encodings.forEach { it.maxBitrateBps = 4_000_000 } }
        try {
            val offer = Sdp.create { pc.createOffer(it, MediaConstraints()) }
            Sdp.set { pc.setLocalDescription(it, offer) }
            gathered.await(3, TimeUnit.SECONDS) // 외부 서버가 없어 금방 끝남
            callId = client.offer(pc.localDescription.description)
            for (attempt in 0 until 40) {
                if (!running || peer !== pc) return
                val answer = client.answer(callId)
                when (answer.optString("state")) {
                    "answered" -> {
                        Sdp.set { pc.setRemoteDescription(it, SessionDescription(SessionDescription.Type.ANSWER, answer.getString("sdp"))) }
                        return
                    }
                    "ended" -> return scheduleRetry(State.NoReceiver)
                }
                Thread.sleep(500)
            }
            scheduleRetry(State.NoReceiver)
        } catch (error: Exception) {
            scheduleRetry(if (error is PcError && error.status in 401..403) State.Failed else State.Retrying)
        }
    }

    private fun scheduleRetry(state: State) {
        if (!running) return
        onState(state)
        retry?.cancel(false)
        retry = worker.schedule({ connect() }, 3, TimeUnit.SECONDS)
    }

    fun stop() {
        running = false
        retry?.cancel(false)
        worker.execute {
            if (callId.isNotEmpty()) runCatching { client.stopCall(callId) }
            peer?.dispose()
            peer = null
            runCatching { capturer?.stopCapture() }
            capturer?.dispose()
            capturer = null
            track?.dispose()
            track = null
            source?.dispose()
            source = null
            helper?.dispose()
            helper = null
            onState(State.Stopped)
        }
    }

    override fun close() {
        stop()
        worker.execute {
            factory.dispose()
            egl.release()
        }
        worker.shutdown()
    }

    /** SDP 만들기, 적용 결과를 기다린다(WebRTC 콜백을 동기 호출로). */
    private object Sdp {
        fun create(call: (SdpObserver) -> Unit): SessionDescription {
            val done = CountDownLatch(1)
            var result: SessionDescription? = null
            var failure: String? = null
            call(object : SdpObserver {
                override fun onCreateSuccess(description: SessionDescription) { result = description; done.countDown() }
                override fun onCreateFailure(error: String) { failure = error; done.countDown() }
                override fun onSetSuccess() = Unit
                override fun onSetFailure(error: String) = Unit
            })
            done.await(5, TimeUnit.SECONDS)
            return result ?: throw IOException(failure ?: "연결 정보 만들기 실패")
        }

        fun set(call: (SdpObserver) -> Unit) {
            val done = CountDownLatch(1)
            var failure: String? = null
            call(object : SdpObserver {
                override fun onCreateSuccess(description: SessionDescription) = Unit
                override fun onCreateFailure(error: String) = Unit
                override fun onSetSuccess() { done.countDown() }
                override fun onSetFailure(error: String) { failure = error; done.countDown() }
            })
            done.await(5, TimeUnit.SECONDS)
            failure?.let { throw IOException(it) }
        }
    }

    companion object {
        @Volatile private var initialized = false

        @Synchronized
        fun initialize(context: Context) {
            if (initialized) return
            PeerConnectionFactory.initialize(PeerConnectionFactory.InitializationOptions.builder(context.applicationContext).createInitializationOptions())
            initialized = true
        }
    }
}

/** 카메라 영상 통화 요청(PC의 휴대폰 조작 화면, 서명). JSON은 안드로이드 기본 org.json. */
fun Client.offer(sdp: String): String = JSONObject(post("/remote/api/camera/offer", JSONObject().put("sdp", sdp).toString())).getString("id")

fun Client.answer(id: String): JSONObject = JSONObject(post("/remote/api/camera/answer", JSONObject().put("id", id).toString()))

fun Client.stopCall(id: String) {
    post("/remote/api/camera/stop", JSONObject().put("id", id).toString())
}
