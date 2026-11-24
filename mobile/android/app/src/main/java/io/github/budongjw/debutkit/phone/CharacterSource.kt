package io.github.budongjw.debutkit.phone

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.SurfaceTexture
import android.graphics.Typeface
import android.os.SystemClock
import android.view.Surface
import com.pedro.encoder.input.sources.video.VideoSource

/**
 * 캐릭터 화면(PNGTuber): 배경색 위에 캐릭터를 그리고 마이크 소리에 맞춰 입을 움직이며 가끔 눈을 깜빡인다.
 * 그림을 고르지 않으면 debutkit 기본 캐릭터(PC의 src/debutkit/overlay/static/character/sample 폴더 SVG와 같은 모양)를 그린다.
 */
class CharacterPainter(private val background: Int, private val title: String, private val images: Pair<Bitmap, Bitmap>?) {
    private val ink = Color.parseColor("#1E2327")
    private val pink = Color.parseColor("#FF4F8B")
    private val cheek = Color.parseColor("#FF8FB3")
    private val paper = Color.parseColor("#FAF7F5")
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val bitmapPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        typeface = Typeface.DEFAULT_BOLD
        setShadowLayer(8f, 0f, 2f, 0x99000000.toInt())
    }
    private val stand = Path().apply {
        moveTo(24f, 54f)
        lineTo(24f, 60f)
        arcTo(RectF(24f, 24f, 96f, 96f), 180f, -180f, false)
        lineTo(96f, 54f)
        moveTo(60f, 96f)
        lineTo(60f, 106f)
        moveTo(45f, 106f)
        lineTo(75f, 106f)
    }
    private val ears = Path().apply {
        moveTo(38f, 32f); lineTo(42f, 9f); lineTo(56f, 21f); close()
        moveTo(82f, 32f); lineTo(78f, 9f); lineTo(64f, 21f); close()
    }
    private val closedEyes = Path().apply {
        moveTo(45f, 45f); quadTo(49.5f, 49f, 54f, 45f)
        moveTo(66f, 45f); quadTo(70.5f, 49f, 75f, 45f)
    }
    private val smile = Path().apply { moveTo(55f, 60f); quadTo(60f, 64f, 65f, 60f) }

    fun draw(canvas: Canvas, width: Int, height: Int, talking: Boolean, blinking: Boolean) {
        canvas.drawColor(background)
        val bounce = if (talking) -height * 0.015f else 0f // 말할 때 살짝 들썩임
        val size = height * 0.8f
        val left = (width - size) / 2f
        val top = height - size + bounce
        if (images != null) {
            val picture = if (talking) images.second else images.first
            val scale = minOf(size / picture.width, size / picture.height)
            val w = picture.width * scale
            val h = picture.height * scale
            canvas.drawBitmap(picture, null, RectF((width - w) / 2f, height - h + bounce, (width + w) / 2f, height + bounce), bitmapPaint)
        } else {
            canvas.save()
            canvas.translate(left, top)
            canvas.scale(size / 120f, size / 120f)
            drawDefault(canvas, talking, blinking)
            canvas.restore()
        }
        if (title.isNotEmpty()) {
            text.textSize = height * 0.06f
            canvas.drawText(title, height * 0.05f, height * 0.05f + text.textSize, text)
        }
    }

    /** viewBox 0 0 120 120 기준(기본 캐릭터 SVG와 같은 좌표). */
    private fun drawDefault(canvas: Canvas, talking: Boolean, blinking: Boolean) {
        canvas.translate(0f, 4f)
        line.color = paper; line.strokeWidth = 11f
        canvas.drawPath(stand, line)
        line.color = ink; line.strokeWidth = 7f
        canvas.drawPath(stand, line)
        fill.color = pink
        canvas.drawPath(ears, fill)
        line.color = pink; line.strokeWidth = 6f
        canvas.drawPath(ears, line)
        canvas.drawRoundRect(RectF(36f, 18f, 84f, 82f), 24f, 24f, fill)
        fill.color = cheek
        canvas.drawCircle(44f, 58f, 4.5f, fill)
        canvas.drawCircle(76f, 58f, 4.5f, fill)
        fill.color = ink
        line.color = ink; line.strokeWidth = 3f
        if (blinking) canvas.drawPath(closedEyes, line)
        else {
            canvas.drawRoundRect(RectF(45.5f, 38f, 53.5f, 51f), 4f, 4f, fill)
            canvas.drawRoundRect(RectF(66.5f, 38f, 74.5f, 51f), 4f, 4f, fill)
        }
        if (talking) {
            canvas.drawOval(RectF(54f, 55f, 66f, 69f), fill)
            fill.color = cheek
            canvas.drawOval(RectF(56f, 63.4f, 64f, 68.6f), fill)
        } else canvas.drawPath(smile, line)
    }
}

/** 방송 영상 입력: [painter]가 정한 캐릭터 화면을 초당 fps장 그린다. 그림 설정은 방송 중에도 바꿀 수 있다. */
class CharacterSource(private val painter: () -> CharacterPainter, private val voice: Voice) : VideoSource() {
    @Volatile private var running = false
    private var thread: Thread? = null
    private var surface: Surface? = null

    override fun create(width: Int, height: Int, fps: Int, rotation: Int): Boolean = true

    override fun start(surfaceTexture: SurfaceTexture) {
        surfaceTexture.setDefaultBufferSize(width, height)
        val target = Surface(surfaceTexture)
        surface = target
        running = true
        val blink = Blink()
        val frame = 1000L / fps.coerceAtLeast(1)
        thread = Thread({
            while (running) {
                val began = SystemClock.elapsedRealtime()
                runCatching {
                    val canvas = target.lockHardwareCanvas()
                    try {
                        painter().draw(canvas, width, height, voice.talking(began), blink.closed(began))
                    } finally {
                        target.unlockCanvasAndPost(canvas)
                    }
                }
                val spent = SystemClock.elapsedRealtime() - began
                if (spent < frame) runCatching { Thread.sleep(frame - spent) }
            }
        }, "character-source").also { it.start() }
    }

    override fun stop() {
        running = false
        thread?.join(500)
        thread = null
        surface?.release()
        surface = null
    }

    override fun release() = stop()

    override fun isRunning(): Boolean = running
}
