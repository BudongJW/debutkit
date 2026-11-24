package io.github.budongjw.debutkit.phone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat

/**
 * 방송 중 앱을 포그라운드로 유지(다른 앱으로 바꾸거나 화면이 꺼져도 송출 계속). 알림의 방송 끝내기로 멈출 수 있다.
 * 안드로이드 14 이상은 포그라운드 서비스 종류(카메라, 마이크)를 밝혀야 하고, 화면이 보이는 상태에서 시작해야 한다.
 */
class LiveService : Service() {
    private val main = Handler(Looper.getMainLooper())

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            LiveSession.stop()
            finish()
            return START_NOT_STICKY
        }
        val camera = intent?.getBooleanExtra(EXTRA_CAMERA, false) == true
        val types = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or (if (camera) ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA else 0)
        } else 0
        ServiceCompat.startForeground(this, NOTIFICATION, notification(), types)
        LiveSession.onEnded = { main.post { finish() } }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        LiveSession.onEnded = null
        if (LiveSession.streaming) LiveSession.stop()
        super.onDestroy()
    }

    private fun finish() {
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun notification(): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL, "방송", NotificationManager.IMPORTANCE_LOW).apply {
                description = "바로 방송 중 표시와 방송 끝내기"
            })
        }
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, LiveService::class.java).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_live)
            .setContentTitle("debutkit 방송 중")
            .setContentText("카메라와 마이크를 방송에 사용하고 있습니다")
            .setOngoing(true)
            .setContentIntent(open)
            .addAction(0, "방송 끝내기", stop)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    companion object {
        private const val CHANNEL = "live"
        private const val NOTIFICATION = 7
        private const val ACTION_STOP = "io.github.budongjw.debutkit.phone.STOP_LIVE"
        private const val EXTRA_CAMERA = "camera"

        fun start(context: Context, camera: Boolean) {
            ContextCompat.startForegroundService(context, Intent(context, LiveService::class.java).putExtra(EXTRA_CAMERA, camera))
        }

        fun stop(context: Context) {
            LiveSession.stop()
            context.stopService(Intent(context, LiveService::class.java))
        }
    }
}
