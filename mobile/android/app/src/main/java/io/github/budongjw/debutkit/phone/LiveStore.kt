package io.github.budongjw.debutkit.phone

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlin.math.max

/** 바로 방송 설정. 송출 서버는 플랫폼마다 따로 기억한다. */
data class LiveConfig(
    val platform: Platform = Platform.Chzzk,
    val servers: Map<Platform, String> = emptyMap(),
    val quality: Quality = Quality.Hd,
    val camera: Boolean = false, // false: 캐릭터 화면, true: 카메라 영상
    val front: Boolean = false,
    val background: Int = 0xFF2A1F3D.toInt(),
    val title: String = "",
    val thresholdDb: Float = -40f,
) {
    val server: String get() = servers[platform].orEmpty()
}

/**
 * 설정은 앱 전용 저장소(SharedPreferences), 스트림 키는 안드로이드 키 저장소(AndroidKeyStore)의 AES-GCM 키로 암호화해 저장.
 * 키 저장소의 키는 기기 밖으로 꺼낼 수 없고 앱을 지우면 함께 지워진다. 백업은 꺼져 있다(allowBackup false).
 */
class LiveStore(context: Context) {
    private val prefs = context.getSharedPreferences("live", Context.MODE_PRIVATE)
    private val files = context.filesDir

    fun load(): LiveConfig {
        val platform = Platform.entries.firstOrNull { it.name == prefs.getString("platform", null) } ?: Platform.Chzzk
        val servers = Platform.entries.mapNotNull { item -> prefs.getString("server.${item.name}", null)?.takeIf { it.isNotEmpty() }?.let { item to it } }.toMap()
        return LiveConfig(
            platform = platform,
            servers = servers,
            quality = Quality.entries.firstOrNull { it.name == prefs.getString("quality", null) } ?: Quality.Hd,
            camera = prefs.getBoolean("camera", false),
            front = prefs.getBoolean("front", false),
            background = prefs.getInt("background", 0xFF2A1F3D.toInt()),
            title = prefs.getString("title", "").orEmpty(),
            thresholdDb = prefs.getFloat("threshold", -40f),
        )
    }

    fun save(config: LiveConfig) {
        prefs.edit().apply {
            putString("platform", config.platform.name)
            Platform.entries.forEach { item -> config.servers[item]?.takeIf { it.isNotEmpty() }?.let { putString("server.${item.name}", it) } ?: remove("server.${item.name}") }
            putString("quality", config.quality.name)
            putBoolean("camera", config.camera)
            putBoolean("front", config.front)
            putInt("background", config.background)
            putString("title", config.title)
            putFloat("threshold", config.thresholdDb)
        }.apply()
    }

    fun saveKey(platform: Platform, key: String) {
        val sealed = seal(Live.checkKey(key).toByteArray(Charsets.US_ASCII))
        prefs.edit().putString("key.${platform.name}", Base64.encodeToString(sealed, Base64.NO_WRAP)).apply()
    }

    /** 저장한 스트림 키. 없거나 풀지 못하면(키 저장소 초기화 등) null. */
    fun loadKey(platform: Platform): String? {
        val sealed = prefs.getString("key.${platform.name}", null) ?: return null
        return runCatching { Live.checkKey(String(open(Base64.decode(sealed, Base64.NO_WRAP)), Charsets.US_ASCII)) }.getOrNull()
    }

    fun hasKey(platform: Platform): Boolean = prefs.contains("key.${platform.name}")

    fun clearKey(platform: Platform) = prefs.edit().remove("key.${platform.name}").apply()

    // 캐릭터 그림(입 닫음, 입 엶). 고르지 않으면 debutkit 기본 캐릭터
    val idleImage: File get() = File(files, "character-idle.png")
    val talkImage: File get() = File(files, "character-talk.png")

    fun customImages(): Pair<Bitmap, Bitmap>? {
        if (!idleImage.isFile || !talkImage.isFile) return null
        val idle = BitmapFactory.decodeFile(idleImage.path) ?: return null
        val talk = BitmapFactory.decodeFile(talkImage.path) ?: return null
        return idle to talk
    }

    /** 고른 그림을 1080픽셀 이하로 줄여 PNG로 보관(투명 배경 유지). */
    fun importImage(context: Context, uri: Uri, target: File) {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) throw LiveError("그림을 읽지 못함(PNG, JPG, WEBP)")
        var sample = 1
        while (max(bounds.outWidth, bounds.outHeight) / (sample * 2) >= 1080) sample *= 2
        val bitmap = context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample }) }
            ?: throw LiveError("그림을 읽지 못함(PNG, JPG, WEBP)")
        val largest = max(bitmap.width, bitmap.height)
        val scaled = if (largest > 1080) Bitmap.createScaledBitmap(bitmap, bitmap.width * 1080 / largest, bitmap.height * 1080 / largest, true) else bitmap
        target.outputStream().use { scaled.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    fun clearImages() {
        idleImage.delete()
        talkImage.delete()
    }

    private fun secretKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build())
        return generator.generateKey()
    }

    private fun seal(plain: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, secretKey()) }
        return cipher.iv + cipher.doFinal(plain)
    }

    private fun open(sealed: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, sealed, 0, 12)) }
        return cipher.doFinal(sealed, 12, sealed.size - 12)
    }

    private companion object {
        const val ALIAS = "debutkit-stream-keys"
    }
}
