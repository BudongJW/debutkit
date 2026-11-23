package io.github.budongjw.debutkit.phone

import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Locale
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import kotlin.math.asin
import kotlin.math.atan2

/**
 * debutkit PC와 주고받는 형식(PC의 src/debutkit/overlay/remote.py와 같아야 한다).
 *
 * - 등록: PC 휴대폰 연결 화면의 휴대폰 조작 QR(http://주소:포트/remote#d=기기&k=비밀값). 비밀값은 QR로만 전달
 * - 요청 서명: HMAC-SHA256(비밀값, "방식\n경로\n시각\n일회용 값\n본문 SHA-256")
 * - 얼굴 추적: 같은 주소, 같은 포트의 UDP. JSON 한 줄 + 줄바꿈 + HMAC-SHA256(비밀값, "udp\n" + JSON)
 */
data class Pairing(val host: String, val port: Int, val id: String, val secret: String) {
    val base: String get() = "http://$host:$port"

    companion object {
        private val link = Regex("""^http://(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})/remote#(.+)$""")

        /** QR이나 붙여 넣은 주소에서 등록 정보. 형식이 아니면 null. */
        fun parse(text: String): Pairing? {
            val match = link.find(text.trim()) ?: return null
            val host = match.groupValues[1]
            if (host.split('.').any { it.toInt() > 255 }) return null
            val port = match.groupValues[2].toIntOrNull()?.takeIf { it in 1..65535 } ?: return null
            val params = match.groupValues[3].split('&').mapNotNull { part ->
                part.split('=', limit = 2).takeIf { it.size == 2 }?.let { it[0] to it[1] }
            }.toMap()
            val id = params["d"]?.takeIf { Regex("^[0-9a-f]{8}$").matches(it) } ?: return null
            val secret = params["k"]?.takeIf { it.length >= 32 && Regex("^[A-Za-z0-9_-]+$").matches(it) } ?: return null
            return Pairing(host, port, id, secret)
        }
    }
}

object Signing {
    private val random = SecureRandom()

    fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }

    fun sha256Hex(bytes: ByteArray): String = hex(MessageDigest.getInstance("SHA-256").digest(bytes))

    fun hmacHex(key: String, message: ByteArray): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        return hex(mac.doFinal(message))
    }

    fun canonical(method: String, path: String, stamp: String, nonce: String, body: ByteArray): String =
        "${method.uppercase(Locale.ROOT)}\n$path\n$stamp\n$nonce\n${sha256Hex(body)}"

    fun sign(secret: String, method: String, path: String, stamp: String, nonce: String, body: ByteArray): String =
        hmacHex(secret, canonical(method, path, stamp, nonce, body).toByteArray(Charsets.UTF_8))

    /** 휴대폰과 PC에 함께 보이는 4자리 확인 번호. */
    fun confirmCode(secret: String): String =
        (hmacHex(secret, "debutkit-confirm".toByteArray()).substring(0, 8).toLong(16) % 10000).toString().padStart(4, '0')

    fun nonce(): String = ByteArray(16).also { random.nextBytes(it) }.let(::hex)
}

/** ARKit 표정 52개(PC의 tracking.ARKIT_NAMES와 같은 순서). MediaPipe도 같은 이름(tongueOut 제외). */
val ARKIT_NAMES = listOf(
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight",
    "eyeLookUpLeft", "eyeLookUpRight", "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft", "eyeWideRight", "jawForward", "jawLeft", "jawOpen",
    "jawRight", "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight", "mouthFunnel", "mouthLeft",
    "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft", "mouthPressRight", "mouthPucker", "mouthRight", "mouthRollLower",
    "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthUpperUpLeft", "mouthUpperUpRight", "noseSneerLeft", "noseSneerRight", "tongueOut",
)
val ARKIT_INDEX: Map<String, Int> = ARKIT_NAMES.withIndex().associate { it.value to it.index }

/** 한 프레임의 추적 값. rotation은 debutkit 기준(라디안 yaw, pitch, roll, 거울 처리 전). */
class Frame(val found: Boolean, val rotation: FloatArray = FloatArray(3), val shapes: FloatArray = FloatArray(ARKIT_NAMES.size))

object Packets {
    private fun number(value: Float, digits: Int): String = String.format(Locale.ROOT, "%.${digits}f", value.coerceIn(-10f, 10f))

    fun json(pairing: Pairing, stamp: Long, frame: Frame): String = buildString {
        append("{\"v\":1,\"d\":\"").append(pairing.id).append("\",\"t\":").append(stamp).append(",\"f\":").append(frame.found)
        if (frame.found) {
            append(",\"r\":[").append(frame.rotation.joinToString(",") { number(it, 4) }).append(']')
            append(",\"b\":[").append(frame.shapes.joinToString(",") { number(it.coerceIn(0f, 1f), 3) }).append(']')
        }
        append('}')
    }

    fun packet(pairing: Pairing, stamp: Long, frame: Frame): ByteArray {
        val json = json(pairing, stamp, frame)
        val signature = Signing.hmacHex(pairing.secret, ("udp\n$json").toByteArray(Charsets.UTF_8))
        return "$json\n$signature".toByteArray(Charsets.UTF_8)
    }
}

/**
 * 4x4 열 우선 얼굴 변환 행렬(MediaPipe facialTransformationMatrixes)에서 머리 회전(라디안). PC 웹캠 추적(tracker.js)과 같은 계산.
 * 얼굴 좌표: x는 얼굴의 왼쪽, y 위, z 카메라 쪽. R = Ry Rx Rz.
 */
fun headRotation(m: FloatArray): FloatArray {
    fun r(row: Int, col: Int) = m[col * 4 + row]
    return floatArrayOf(
        atan2(r(0, 2), r(2, 2)),
        asin((-r(1, 2)).coerceIn(-1f, 1f)),
        atan2(r(1, 0), r(1, 1)),
    )
}

/** PC 응답(JSON)에서 필요한 값만 읽는다(외부 라이브러리 없이). */
object Answers {
    fun bool(text: String, key: String): Boolean? = Regex("\"$key\"\\s*:\\s*(true|false)").find(text)?.groupValues?.get(1)?.toBoolean()
    fun string(text: String, key: String): String? = Regex("\"$key\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"").find(text)?.groupValues?.get(1)
        ?.replace("\\\"", "\"")?.replace("\\\\", "\\")
}
