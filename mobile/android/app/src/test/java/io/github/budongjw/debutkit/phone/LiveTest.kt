package io.github.budongjw.debutkit.phone

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

/** 바로 방송 규칙: PC의 broadcast.py와 같은 주소, 키 확인과 비트레이트 상한, 실패 안내, 입 움직임, 눈 깜빡임. */
class LiveTest {
    @Test
    fun serverAddresses() {
        assertEquals("", Live.checkServer("  "))
        assertEquals("rtmp://rtmp.example.kr/live", Live.checkServer(" rtmp://rtmp.example.kr/live/ "))
        assertEquals("rtmps://live.twitch.tv:443/app", Live.checkServer("rtmps://live.twitch.tv:443/app"))
        for (bad in listOf("http://example.com/live", "rtmp://", "rtmp://a b/live", "srt://x:9000", "live/abc")) {
            assertThrows(LiveError::class.java) { Live.checkServer(bad) }
        }
    }

    @Test
    fun streamKeys() {
        assertEquals("live_123-abc?bandwidthtest=true", Live.checkKey("  live_123-abc?bandwidthtest=true \n"))
        for (bad in listOf("", "abc", "has space", "a/b/c/d", "키값키값", "x".repeat(300))) {
            assertThrows(LiveError::class.java) { Live.checkKey(bad) }
        }
    }

    @Test
    fun publishUrlsUseDefaultsAndRequireServerForKoreanPlatforms() {
        assertEquals("rtmps://live.twitch.tv:443/app/live_abcd1234", Live.publishUrl(Platform.Twitch, "", "live_abcd1234"))
        assertEquals("rtmps://a.rtmps.youtube.com/live2/abcd-efgh", Live.publishUrl(Platform.YouTube, "", " abcd-efgh "))
        assertEquals("rtmp://my.server/app/key1234", Live.publishUrl(Platform.Custom, "rtmp://my.server/app/", "key1234"))
        val missing = assertThrows(LiveError::class.java) { Live.publishUrl(Platform.Chzzk, "", "key1234") }
        assertTrue(missing.message!!.startsWith("치지직 송출 서버 주소 필요"))
        assertThrows(LiveError::class.java) { Live.publishUrl(Platform.Soop, "rtmp://soop.example/app", "bad key") }
    }

    @Test
    fun bitrateCapsAndMasking() {
        assertEquals(2500, Live.videoKbps(Platform.Chzzk, Quality.Hd))
        assertEquals(4500, Live.videoKbps(Platform.Twitch, Quality.FullHd))
        assertEquals(1200, Live.videoKbps(Platform.YouTube, Quality.Low))
        Quality.entries.forEach { assertTrue(it.name, it.width % 16 == 0 && it.height % 8 == 0 && it.width * 9 / 16 in it.height - 4..it.height + 4) }
        assertEquals("rtmp://x/app/**** failed ****", Live.mask("rtmp://x/app/live_key1 failed live_key1", "live_key1", ""))
    }

    @Test
    fun failureMessages() {
        assertTrue(Live.describeFailure("Endpoint malformed, should be: rtmp://ip:port/appname/streamname").startsWith("송출 서버 주소 형식 오류"))
        assertTrue(Live.describeFailure("java.net.ConnectException: Connection refused").startsWith("송출 서버에 연결하지 못함"))
        assertTrue(Live.describeFailure("Unable to resolve host \"x\"").startsWith("송출 서버에 연결하지 못함"))
        assertTrue(Live.describeFailure("Error configure stream, failed to connect to 10.0.2.2/10.0.2.2 (port 19350) after 5000ms: isConnected failed: " +
            "ECONNABORTED (Software caused connection abort)").startsWith("송출 서버에 연결하지 못함"))
        assertTrue(Live.describeFailure("Error configure stream, publish NetStream.Publish.BadName").startsWith("송출 서버가 거부함"))
        assertTrue(Live.describeFailure("SSLHandshakeException").startsWith("보안 연결(rtmps) 실패"))
        assertEquals("연결 실패: something", Live.describeFailure("something"))
    }

    @Test
    fun voiceOpensMouthAboveThresholdAndHolds() {
        val voice = Voice(thresholdDb = -40f, holdMillis = 200)
        assertFalse(voice.talking(1000))
        voice.feed(pcm(0.0), 1000)
        assertEquals(-90f, voice.level)
        assertFalse(voice.talking(1000))
        voice.feed(pcm(0.001), 1000) // -60 dBFS: 조용함
        assertFalse(voice.talking(1000))
        voice.feed(pcm(0.1), 2000) // -20 dBFS: 말함
        assertEquals(-20f, voice.level, 0.1f)
        assertTrue(voice.talking(2000))
        assertTrue(voice.talking(2199)) // 잠깐 끊겨도 유지
        assertFalse(voice.talking(2201))
        voice.thresholdDb = -10f
        voice.feed(pcm(0.1), 3000)
        assertFalse(voice.talking(3000))
        voice.reset()
        assertEquals(-90f, voice.level)
    }

    @Test
    fun blinksBriefly() {
        val blink = Blink(Random(7))
        val closed = (0L..20_000L step 10).count { blink.closed(it) }
        assertTrue("closed $closed", closed in 45..140) // 20초에 깜빡임 3에서 8번, 한 번 0.15초
        assertFalse(Blink(Random(1)).closed(0))
    }

    /** 진폭 [amplitude]의 일정한 16비트 PCM(실효값 = 진폭). */
    private fun pcm(amplitude: Double): ByteArray {
        val value = (amplitude * 32768).toInt().coerceIn(-32768, 32767)
        return ByteArray(2048) { index -> if (index % 2 == 0) (value and 0xff).toByte() else (value shr 8).toByte() }
    }
}
