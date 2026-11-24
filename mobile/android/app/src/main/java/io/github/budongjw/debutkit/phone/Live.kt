package io.github.budongjw.debutkit.phone

import java.net.URI
import kotlin.math.log10
import kotlin.math.min
import kotlin.math.sqrt
import kotlin.random.Random

/**
 * 휴대폰만으로 방송: 방송 플랫폼, 화질, 송출 주소와 스트림 키 확인(PC의 broadcast.py와 같은 규칙).
 * 안드로이드 기능을 쓰지 않아 JVM 단위 테스트로 확인한다.
 */
enum class Platform(val label: String, val server: String, val maxKbps: Int, val keyframe: Int, val hint: String) {
    Chzzk("치지직", "", 8000, 1, "치지직 스튜디오 방송 설정의 스트림 URL과 스트림 키"),
    Soop("SOOP", "", 8000, 2, "SOOP 방송 설정 외부 기기 방송의 서버 URL과 스트림 키"),
    YouTube("YouTube", "rtmps://a.rtmps.youtube.com/live2", 12000, 2, "YouTube Studio 라이브 스트리밍의 스트림 키"),
    Twitch("Twitch", "rtmps://live.twitch.tv:443/app", 6000, 2, "Twitch 크리에이터 대시보드 스트림 설정의 기본 스트림 키"),
    Custom("직접 입력", "", 20000, 2, "송출 서버 주소(rtmp:// 또는 rtmps://)와 스트림 키"),
}

/** 휴대폰 업로드(모바일 데이터 포함)를 고려해 PC보다 낮은 비트레이트. 가로 16:9. */
enum class Quality(val label: String, val width: Int, val height: Int, val fps: Int, val kbps: Int) {
    Low("480p 30fps(데이터 절약)", 848, 480, 30, 1200),
    Hd("720p 30fps(권장)", 1280, 720, 30, 2500),
    FullHd("1080p 30fps(Wi-Fi)", 1920, 1080, 30, 4500),
}

class LiveError(message: String) : Exception(message)

object Live {
    const val KEY_LIMIT = 256
    const val SERVER_LIMIT = 300

    /** 송출 서버 주소(rtmp://, rtmps://). 빈 값은 플랫폼 기본 서버. */
    fun checkServer(text: String): String {
        val value = text.trim().trimEnd('/')
        if (value.isEmpty()) return ""
        val host = runCatching { URI(value) }.getOrNull()?.takeIf { it.scheme == "rtmp" || it.scheme == "rtmps" }?.host
        if (host.isNullOrEmpty() || value.length > SERVER_LIMIT || value.any { it.isWhitespace() || it.code < 32 }) {
            throw LiveError("송출 서버 주소는 rtmp:// 또는 rtmps://로 시작하는 주소(방송 플랫폼의 방송 설정 화면에서 복사)")
        }
        return value
    }

    /** 스트림 키: 공백 없는 영문, 숫자, 기호(복사할 때 붙은 앞뒤 공백은 지운다). */
    fun checkKey(text: String): String {
        val value = text.trim()
        if (value.length !in 4..KEY_LIMIT || value.any { it.code !in 33..126 } || '/' in value) {
            throw LiveError("스트림 키가 올바르지 않음: 방송 플랫폼 화면의 스트림 키를 그대로 복사해 붙여 넣기")
        }
        return value
    }

    fun serverOf(platform: Platform, custom: String): String = custom.ifEmpty { platform.server }

    fun publishUrl(platform: Platform, custom: String, key: String): String {
        val server = serverOf(platform, checkServer(custom))
        if (server.isEmpty()) throw LiveError("${platform.label} 송출 서버 주소 필요: ${platform.hint}")
        return "$server/${checkKey(key)}"
    }

    fun videoKbps(platform: Platform, quality: Quality): Int = min(quality.kbps, platform.maxKbps)

    fun mask(text: String, vararg secrets: String): String = secrets.filter { it.isNotEmpty() }.fold(text) { acc, secret -> acc.replace(secret, "****") }

    /** 송출 라이브러리의 연결 실패 이유를 한국어 안내 한 줄로. */
    fun describeFailure(reason: String): String {
        val text = reason.lowercase()
        return when {
            "malformed" in text || "endpoint" in text -> "송출 서버 주소 형식 오류: rtmp://서버/앱 형식인지 확인"
            "refused" in text || "timeout" in text || "timed out" in text || "unable to resolve" in text || "unreachable" in text || "no route" in text ||
                "failed to connect" in text || "econnaborted" in text || "connection abort" in text ->
                "송출 서버에 연결하지 못함: 서버 주소와 인터넷 연결 확인"
            "publish" in text || "badname" in text || "reject" in text || "auth" in text || "denied" in text || "forbidden" in text ->
                "송출 서버가 거부함: 스트림 키와 서버 주소 확인(방송 플랫폼의 방송 설정 화면)"
            "ssl" in text || "tls" in text || "handshake" in text -> "보안 연결(rtmps) 실패: 서버 주소 확인, 휴대폰 날짜와 시각 확인"
            else -> "연결 실패: ${reason.take(160)}"
        }
    }
}

/**
 * 마이크 소리 크기로 말하는 중인지(캐릭터 입 움직임). 16비트 PCM(리틀 엔디언).
 * 소리가 잠깐 끊겨도 [holdMillis] 동안 입을 연 상태로 둔다(말할 때 입이 깜빡이지 않게).
 */
class Voice(@Volatile var thresholdDb: Float = -40f, private val holdMillis: Long = 200) {
    @Volatile var level = -90f
        private set
    @Volatile private var lastLoud = 0L

    fun feed(pcm: ByteArray, now: Long, size: Int = pcm.size) {
        var sum = 0.0
        var count = 0
        var index = 0
        while (index + 1 < size) {
            val sample = ((pcm[index].toInt() and 0xff) or (pcm[index + 1].toInt() shl 8)).toShort() / 32768.0
            sum += sample * sample
            count++
            index += 2
        }
        val rms = if (count == 0) 0.0 else sqrt(sum / count)
        level = if (rms <= 0.0) -90f else (20 * log10(rms)).toFloat().coerceAtLeast(-90f)
        if (level >= thresholdDb) lastLoud = now
    }

    fun talking(now: Long): Boolean = lastLoud > 0 && now - lastLoud <= holdMillis

    fun reset() {
        lastLoud = 0
        level = -90f
    }
}

/** 눈 깜빡임: 2.5에서 5.5초마다 0.15초. */
class Blink(private val random: Random = Random.Default) {
    private var next = 0L
    private var until = 0L

    fun closed(now: Long): Boolean {
        if (next == 0L) next = now + interval()
        if (now >= next) {
            until = now + 150
            next = now + interval()
        }
        return now < until
    }

    private fun interval() = 2500L + random.nextLong(3000)
}
