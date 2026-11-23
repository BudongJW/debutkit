package io.github.budongjw.debutkit.phone

import android.content.Context
import java.io.IOException
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URL

/** 앱에 저장한 등록 정보(앱 전용 저장소, 백업 제외). */
class Store(context: Context) {
    private val prefs = context.getSharedPreferences("debutkit", Context.MODE_PRIVATE)

    fun load(): Pairing? = prefs.getString("link", null)?.let(Pairing::parse)

    fun save(link: String) = prefs.edit().putString("link", link.trim()).apply()

    fun clear() = prefs.edit().remove("link").apply()
}

data class Hello(val approved: Boolean, val code: String, val name: String)

class PcError(message: String, val status: Int) : IOException(message)

/** PC의 휴대폰 조작 화면(서명 요청). */
class Client(private val pairing: Pairing) {
    /** 등록 확인. 승인 전이면 approved=false와 확인 번호. 기기가 삭제됐으면 PcError(401). */
    fun hello(name: String): Hello {
        val body = "{\"name\":\"${name.replace("\\", "").replace("\"", "")}\"}"
        val text = request("POST", "/remote/api/hello", body)
        return Hello(Answers.bool(text, "approved") == true, Answers.string(text, "code") ?: Signing.confirmCode(pairing.secret),
            Answers.string(text, "name") ?: name)
    }

    private fun request(method: String, path: String, body: String): String {
        val bytes = body.toByteArray(Charsets.UTF_8)
        val stamp = System.currentTimeMillis().toString()
        val nonce = Signing.nonce()
        val connection = URL(pairing.base + path).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 4000
            connection.readTimeout = 4000
            connection.setRequestProperty("X-Debutkit-Device", pairing.id)
            connection.setRequestProperty("X-Debutkit-Time", stamp)
            connection.setRequestProperty("X-Debutkit-Nonce", nonce)
            connection.setRequestProperty("X-Debutkit-Sign", Signing.sign(pairing.secret, method, path, stamp, nonce, bytes))
            if (bytes.isNotEmpty()) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(bytes) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
            if (status !in 200..299) throw PcError(Answers.string(text, "error") ?: "PC 응답 오류($status)", status)
            return text
        } finally {
            connection.disconnect()
        }
    }
}

/** 얼굴 추적 값을 PC로(UDP, 초당 최대 30회). */
class Sender(private val pairing: Pairing) : AutoCloseable {
    private val socket = DatagramSocket()
    // 개발용(디버그 빌드만): 에뮬레이터에서 127.0.0.1로 등록하면(adb reverse) UDP는 PC를 가리키는 10.0.2.2로
    private val address: InetAddress = InetAddress.getByName(if (BuildConfig.DEBUG && pairing.host == "127.0.0.1") "10.0.2.2" else pairing.host)
    private var lastStamp = 0L
    private var lastSent = 0L
    var sent = 0
        private set

    private var lastFound = true

    /** 간격(밀리초)보다 빨리 오면 보내지 않는다. 얼굴을 놓친 순간은 바로, 계속 놓친 동안은 0.2초마다. */
    @Synchronized
    fun send(frame: Frame, interval: Long = 33): Boolean {
        val now = System.currentTimeMillis()
        if (frame.found && now - lastSent < interval) return false
        if (!frame.found && !lastFound && now - lastSent < 200) return false
        lastFound = frame.found
        val stamp = maxOf(now, lastStamp + 1) // PC는 이전 패킷보다 새로운 시각만 받는다
        lastStamp = stamp
        lastSent = now
        val data = Packets.packet(pairing, stamp, frame)
        socket.send(DatagramPacket(data, data.size, address, pairing.port))
        sent++
        return true
    }

    override fun close() = socket.close()
}
