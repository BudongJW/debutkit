package io.github.budongjw.debutkit.phone

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** PC(src/debutkit/overlay/remote.py)와 같은 결과인지: 기대값은 파이썬으로 계산한 값. */
class ProtocolTest {
    private val secret = "ZcII2jarVh6UjJQLndvXBClKOvFiCIoffm-I0RoPBdM"
    private val pairing = Pairing("192.168.0.5", 8792, "f0f542b3", secret)

    @Test
    fun parsesOnlyDebutkitLinks() {
        assertEquals(pairing, Pairing.parse(" http://192.168.0.5:8792/remote#d=f0f542b3&k=$secret "))
        assertNull(Pairing.parse("https://192.168.0.5:8792/remote#d=f0f542b3&k=$secret"))
        assertNull(Pairing.parse("http://example.com:8792/remote#d=f0f542b3&k=$secret"))
        assertNull(Pairing.parse("http://192.168.0.300:8792/remote#d=f0f542b3&k=$secret"))
        assertNull(Pairing.parse("http://192.168.0.5:8792/remote#d=F0F542B3&k=$secret"))
        assertNull(Pairing.parse("http://192.168.0.5:8792/remote#d=f0f542b3&k=short"))
        assertNull(Pairing.parse("http://192.168.0.5:99999/remote#d=f0f542b3&k=$secret"))
    }

    @Test
    fun signsLikeThePc() {
        val body = "{\"name\":\"Pixel 8\"}".toByteArray()
        assertEquals("afeb56db22324c3b723f8f2e263844d96144f4b96128262bf624158fb1b6f18f",
            Signing.sign(secret, "post", "/remote/api/hello", "1700000000000", "0123456789abcdef0123456789abcdef", body))
        assertEquals("8696", Signing.confirmCode(secret))
        assertEquals(32, Signing.nonce().length)
    }

    @Test
    fun packetIsSignedJsonLine() {
        val lost = String(Packets.packet(pairing, 1_700_000_000_000, Frame(false)))
        assertEquals("{\"v\":1,\"d\":\"f0f542b3\",\"t\":1700000000000,\"f\":false}\nbd6b1091aa6cbdafe52ada3a5322d0f6d2aca1a2488b06a950a3ceae3fb2744d", lost)
        val shapes = FloatArray(ARKIT_NAMES.size).also { it[ARKIT_INDEX.getValue("jawOpen")] = 0.5f; it[0] = 1.7f }
        val json = Packets.json(pairing, 5, Frame(true, floatArrayOf(0.1f, -0.2f, 0.05f), shapes))
        assertTrue(json.startsWith("{\"v\":1,\"d\":\"f0f542b3\",\"t\":5,\"f\":true,\"r\":[0.1000,-0.2000,0.0500],\"b\":[1.000,"))
        assertEquals(52, json.substringAfter("\"b\":[").substringBefore(']').split(',').size)
        assertTrue(json.contains(",0.500,")) // jawOpen
    }

    @Test
    fun arkitNamesMatchThePc() {
        assertEquals(52, ARKIT_NAMES.size)
        assertEquals(ARKIT_NAMES.sorted(), ARKIT_NAMES) // PC와 같은 알파벳 순서
        assertEquals(24, ARKIT_INDEX.getValue("jawOpen"))
    }

    @Test
    fun headRotationFromMatrix() {
        val identity = floatArrayOf(1f, 0f, 0f, 0f, 0f, 1f, 0f, 0f, 0f, 0f, 1f, 0f, 0f, 0f, 0f, 1f)
        assertArrayEquals(floatArrayOf(0f, 0f, 0f), headRotation(identity), 1e-6f)
        val angle = (20 * PI / 180).toFloat() // y축 20도(얼굴 기준 왼쪽으로 돌림)
        val yaw = floatArrayOf(cos(angle), 0f, -sin(angle), 0f, 0f, 1f, 0f, 0f, sin(angle), 0f, cos(angle), 0f, 0f, 0f, 0f, 1f)
        assertArrayEquals(floatArrayOf(angle, 0f, 0f), headRotation(yaw), 1e-5f)
    }

    @Test
    fun readsAnswers() {
        val text = "{\"approved\": false, \"code\": \"8696\", \"name\": \"Pixel \\\"8\\\"\", \"error\": \"승인 필요\"}"
        assertEquals(false, Answers.bool(text, "approved"))
        assertEquals("8696", Answers.string(text, "code"))
        assertEquals("Pixel \"8\"", Answers.string(text, "name"))
        assertEquals("승인 필요", Answers.string(text, "error"))
        assertNull(Answers.bool(text, "missing"))
    }
}
