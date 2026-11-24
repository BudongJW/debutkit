package io.github.budongjw.debutkit.phone

import android.content.Context
import android.os.SystemClock
import android.view.Surface
import com.pedro.common.ConnectChecker
import com.pedro.encoder.input.audio.CustomAudioEffect
import com.pedro.encoder.input.sources.audio.MicrophoneSource
import com.pedro.encoder.input.sources.video.Camera2Source
import com.pedro.encoder.input.video.CameraHelper
import com.pedro.library.generic.GenericStream
import com.pedro.library.util.BitrateAdapter
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * 바로 방송 한 건(앱 전체에서 하나): 송출 라이브러리(RootEncoder) 준비, 미리보기, 시작, 멈춤, 다시 연결, 상태.
 * 화면(LiveScreen)이 미리보기를 붙이고, 방송 중에는 LiveService가 앱을 포그라운드로 유지한다.
 * 송출 라이브러리의 알림(ConnectChecker)은 라이브러리 스레드에서 오므로 잠금 없이 처리한다(stopStream 중 교착 방지).
 */
object LiveSession : ConnectChecker {
    enum class Phase { Idle, Connecting, Live, Retrying, Failed }

    data class Status(val phase: Phase = Phase.Idle, val message: String = "", val kbps: Long = 0, val since: Long = 0)

    /** 영상 입력과 인코더 설정. 바뀌면(방송 중이 아닐 때) 다시 만든다. */
    data class Setup(val camera: Boolean, val front: Boolean, val quality: Quality, val kbps: Int, val keyframe: Int, val rotation: Int)

    private val state = MutableStateFlow(Status())
    val status: StateFlow<Status> = state
    val voice = Voice()

    @Volatile var painter = CharacterPainter(0xFF2A1F3D.toInt(), "", null) // 방송 중에도 바꿀 수 있는 캐릭터 화면
    @Volatile var onEnded: (() -> Unit)? = null // 방송이 끝나거나 실패하면(LiveService가 스스로 멈춤)

    @Volatile private var stream: GenericStream? = null
    @Volatile private var adapter: BitrateAdapter? = null
    @Volatile private var secret = ""
    @Volatile private var wasLive = false
    @Volatile private var stopping = false
    private var setup: Setup? = null
    private var preview: Triple<Surface, Int, Int>? = null
    private var hot = false

    val streaming: Boolean get() = stream?.isStreaming == true

    /**
     * 이 설정의 송출 준비(미리보기 가능 상태). 방송 중이면 그대로 둔다. 실패하면 안내 문장.
     * 송출 객체는 하나를 계속 쓴다: 카메라와 캐릭터 화면은 영상 입력만 바꾸고(changeVideoSource), 화질이 바뀌면 미리보기를 멈추고
     * 인코더만 다시 준비한다(송출 객체를 짧은 간격으로 다시 만들면 미리보기 정리와 겹쳐 그래픽 표면을 두 번 지워 앱이 종료됨).
     */
    @Synchronized
    fun prepare(context: Context, wanted: Setup): String? {
        val current = stream
        if (current != null && (current.isStreaming || setup == wanted)) return null
        val app = context.applicationContext
        val old = setup
        val target = current ?: GenericStream(app, this, if (wanted.camera) Camera2Source(app) else CharacterSource({ painter }, voice), MicrophoneSource()).also {
            it.getStreamClient().setLogs(BuildConfig.DEBUG) // 송출 라이브러리 기록에는 스트림 키(publish 이름)가 들어가므로 배포 빌드에서는 끈다
        }
        if (current != null && old != null && old.camera != wanted.camera) {
            val changed = runCatching { target.changeVideoSource(if (wanted.camera) Camera2Source(app) else CharacterSource({ painter }, voice)) }
            if (changed.isFailure) return "영상 입력을 바꾸지 못함: 앱을 다시 열어 시도"
        }
        if (old == null || old.quality != wanted.quality || old.kbps != wanted.kbps || old.keyframe != wanted.keyframe || old.rotation != wanted.rotation) {
            if (target.isOnPreview) target.stopPreview()
            val q = wanted.quality
            val ready = runCatching {
                target.prepareVideo(q.width, q.height, wanted.kbps * 1000, q.fps, wanted.keyframe, wanted.rotation) &&
                    (old != null || target.prepareAudio(44100, true, 128_000, false, true))
            }.getOrDefault(false)
            if (!ready) {
                if (current == null) target.release()
                return "인코더 준비 실패: 화질을 낮춰 다시 시도"
            }
        }
        if (current == null) {
            (target.audioSource as? MicrophoneSource)?.setAudioEffect(object : CustomAudioEffect() {
                override fun process(pcmBuffer: ByteArray): ByteArray {
                    voice.feed(pcmBuffer, SystemClock.elapsedRealtime())
                    return pcmBuffer
                }
            })
        }
        val video = target.videoSource
        if (video is Camera2Source && wanted.front != (video.getCameraFacing() == CameraHelper.Facing.FRONT)) runCatching { video.switchCamera() }
        stream = target
        setup = wanted
        if (!target.isOnPreview) preview?.let { (surface, width, height) -> runCatching { target.startPreview(surface, width, height) } }
        return null
    }

    @Synchronized
    fun attach(surface: Surface, width: Int, height: Int) {
        preview = Triple(surface, width, height)
        stream?.let {
            if (it.isOnPreview) it.stopPreview()
            runCatching { it.startPreview(surface, width, height) }
        }
    }

    @Synchronized
    fun detach() {
        preview = null
        stream?.let { if (it.isOnPreview) it.stopPreview() }
    }

    @Synchronized
    fun switchCamera() {
        (stream?.videoSource as? Camera2Source)?.let { runCatching { it.switchCamera() } }
    }

    /** 송출 시작. [key]는 오류 문장에서 가린다. */
    @Synchronized
    fun start(url: String, key: String): Boolean {
        val current = stream ?: return false
        if (current.isStreaming) return true
        secret = key
        wasLive = false
        stopping = false
        voice.reset()
        val limit = (setup?.kbps ?: 2500) * 1000
        adapter = BitrateAdapter { bitrate -> stream?.setVideoBitrateOnFly(bitrate) }.apply { setMaxBitrate(if (hot) limit * 6 / 10 else limit) }
        current.getStreamClient().setReTries(5)
        state.value = Status(Phase.Connecting, "송출 서버 연결 중")
        current.startStream(url)
        return true
    }

    fun stop() {
        stopping = true
        stream?.let { if (it.isStreaming) it.stopStream() }
        voice.reset()
        if (state.value.phase != Phase.Failed) state.value = Status()
        onEnded?.invoke()
    }

    /** 휴대폰이 뜨거우면 영상 비트레이트를 60%로(다시 식으면 원래대로). */
    @Synchronized
    fun lower(on: Boolean) {
        if (hot == on) return
        hot = on
        val limit = (setup?.kbps ?: return) * 1000
        val target = if (on) limit * 6 / 10 else limit
        adapter?.setMaxBitrate(target)
        stream?.takeIf { it.isStreaming }?.setVideoBitrateOnFly(target)
    }

    /** 미리보기와 인코더 정리(방송 중이 아닐 때 화면을 떠나면). release가 송출과 미리보기도 멈춘다. */
    @Synchronized
    fun release() {
        stream?.release()
        stream = null
        setup = null
    }

    fun clearFailure() {
        if (state.value.phase == Phase.Failed) state.value = Status()
    }

    override fun onConnectionStarted(url: String) {
        if (state.value.phase != Phase.Retrying) state.value = Status(Phase.Connecting, "송출 서버 연결 중")
    }

    override fun onConnectionSuccess() {
        val since = if (wasLive) state.value.since else System.currentTimeMillis()
        wasLive = true
        adapter?.reset()
        state.value = Status(Phase.Live, "방송 중", state.value.kbps, since)
    }

    override fun onConnectionFailed(reason: String) {
        val masked = Live.mask(reason, secret)
        val current = stream
        // 한동안 방송한 뒤 끊긴 경우만 다시 연결(처음부터 실패하면 키, 주소 문제이므로 바로 알림)
        if (wasLive && !stopping && current != null && current.getStreamClient().reTry(5000, masked)) {
            state.value = Status(Phase.Retrying, "연결 끊김: 5초 뒤 다시 연결", 0, state.value.since)
            return
        }
        stopping = true
        current?.let { if (it.isStreaming) it.stopStream() }
        state.value = Status(Phase.Failed, Live.describeFailure(masked))
        onEnded?.invoke()
    }

    override fun onNewBitrate(bitrate: Long) {
        adapter?.adaptBitrate(bitrate, stream?.getStreamClient()?.hasCongestion() == true)
        val current = state.value
        if (current.phase == Phase.Live) state.value = current.copy(kbps = bitrate / 1000)
    }

    override fun onDisconnect() {
        if (stopping && state.value.phase != Phase.Failed) state.value = Status()
    }

    override fun onAuthError() {
        stopping = true
        stream?.let { if (it.isStreaming) it.stopStream() }
        state.value = Status(Phase.Failed, "송출 서버가 인증을 거부함: 스트림 키 확인")
        onEnded?.invoke()
    }

    override fun onAuthSuccess() = Unit
}
