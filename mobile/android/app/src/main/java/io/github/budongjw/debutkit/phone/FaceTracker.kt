package io.github.budongjw.debutkit.phone

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.os.SystemClock
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarker
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarkerResult

/**
 * MediaPipe Face Landmarker(Apache-2.0)로 머리 회전과 ARKit 이름 표정을 계산한다. 영상은 휴대폰 안에서만 처리하고 숫자 값만 보낸다.
 * 카메라 프레임은 센서 방향 그대로 오므로 똑바로 세운 뒤(거울 처리 없음) 넣는다. 결과는 PC 웹캠 추적과 같은 기준.
 */
class FaceTracker(context: Context, private val onFrame: (Frame) -> Unit, private val onError: (String) -> Unit) : AutoCloseable {
    private val landmarker: FaceLandmarker = create(context)
    private var lastTimestamp = 0L

    private fun create(context: Context): FaceLandmarker {
        fun options(delegate: Delegate) = FaceLandmarker.FaceLandmarkerOptions.builder()
            .setBaseOptions(BaseOptions.builder().setModelAssetPath("face_landmarker.task").setDelegate(delegate).build())
            .setRunningMode(RunningMode.LIVE_STREAM)
            .setNumFaces(1)
            .setOutputFaceBlendshapes(true)
            .setOutputFacialTransformationMatrixes(true)
            .setResultListener { result: FaceLandmarkerResult, _ -> onFrame(toFrame(result)) }
            .setErrorListener { error -> onError(error.message ?: "얼굴 인식 오류") }
            .build()
        return try {
            FaceLandmarker.createFromOptions(context, options(Delegate.GPU))
        } catch (error: Exception) { // 그래픽 가속을 쓸 수 없는 기기(에뮬레이터 등)
            FaceLandmarker.createFromOptions(context, options(Delegate.CPU))
        }
    }

    /** 카메라 프레임 분석기(최신 프레임만, RGBA). */
    val analyzer = ImageAnalysis.Analyzer { image: ImageProxy ->
        image.use { detect(upright(it.toBitmap(), it.imageInfo.rotationDegrees)) }
    }

    /** 똑바로 선 이미지 한 장(카메라 프레임 또는 시험 이미지). */
    fun detect(bitmap: Bitmap) {
        val now = maxOf(SystemClock.uptimeMillis(), lastTimestamp + 1) // MediaPipe는 같거나 과거 시각을 받지 않음
        lastTimestamp = now
        try {
            landmarker.detectAsync(BitmapImageBuilder(bitmap).build(), now)
        } catch (error: RuntimeException) {
            onError(error.message ?: "얼굴 인식 오류")
        }
    }

    override fun close() = landmarker.close()

    companion object {
        fun upright(bitmap: Bitmap, degrees: Int): Bitmap {
            if (degrees == 0) return bitmap
            val matrix = Matrix().apply { postRotate(degrees.toFloat()) }
            return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
        }

        fun toFrame(result: FaceLandmarkerResult): Frame {
            val blendshapes = result.faceBlendshapes().orElse(null)?.firstOrNull()
            val matrix = result.facialTransformationMatrixes().orElse(null)?.firstOrNull()
            if (blendshapes == null || matrix == null) return Frame(false)
            val shapes = FloatArray(ARKIT_NAMES.size)
            for (category in blendshapes) {
                ARKIT_INDEX[category.categoryName()]?.let { shapes[it] = category.score() }
            }
            return Frame(true, headRotation(matrix), shapes)
        }
    }
}
