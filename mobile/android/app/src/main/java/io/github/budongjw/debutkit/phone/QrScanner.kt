package io.github.budongjw.debutkit.phone

import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.NotFoundException
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.ReaderException
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeReader

/** 카메라 프레임에서 debutkit 등록 QR 코드 읽기(ZXing, Apache-2.0). 등록 정보가 담긴 QR만 넘긴다. */
class QrScanner(private val onFound: (String) -> Unit) : ImageAnalysis.Analyzer {
    private val reader = QRCodeReader()
    private val hints = mapOf(DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE), DecodeHintType.TRY_HARDER to true)
    @Volatile private var done = false

    override fun analyze(image: ImageProxy) {
        image.use {
            if (done) return
            val plane = it.planes[0] // 밝기(Y) 평면만으로 충분
            val buffer = plane.buffer
            val bytes = ByteArray(buffer.remaining()).also { array -> buffer.get(array) }
            val text = decode(bytes, plane.rowStride, it.width, it.height) ?: return
            if (Pairing.parse(text) != null) {
                done = true
                onFound(text)
            }
        }
    }

    fun decode(luminance: ByteArray, rowStride: Int, width: Int, height: Int): String? {
        val source = PlanarYUVLuminanceSource(luminance, rowStride, height, 0, 0, width, height, false)
        return try {
            reader.decode(BinaryBitmap(HybridBinarizer(source)), hints).text
        } catch (error: NotFoundException) {
            null
        } catch (error: ReaderException) {
            null
        } finally {
            reader.reset()
        }
    }
}
