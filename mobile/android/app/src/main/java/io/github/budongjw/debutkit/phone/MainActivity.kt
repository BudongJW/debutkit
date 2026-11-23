package io.github.budongjw.debutkit.phone

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.util.concurrent.Executors

private val Ink = Color(0xFF1E2327)
private val Paper = Color(0xFFFAF7F5)
private val Pink = Color(0xFFFF4F8B)
private val Ok = Color(0xFF1F7A4D)
private val Bad = Color(0xFFB3261E)

private enum class Step { Unpaired, Scanning, Connecting, Waiting, Ready }

class MainActivity : ComponentActivity() {
    val thermal = mutableIntStateOf(PowerManager.THERMAL_STATUS_NONE)

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT)) // 어두운 머리글 위 밝은 상태 표시줄 글자
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            getSystemService(PowerManager::class.java).addThermalStatusListener(mainExecutor) { thermal.intValue = it }
        }
        val store = Store(this)
        if (BuildConfig.DEBUG) intent.getStringExtra("link")?.let { if (Pairing.parse(it) != null) store.save(it) } // 개발용: adb로 등록 주소 전달
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = Ink, onPrimary = Color.White, background = Paper, surface = Paper)) {
                Surface(Modifier.fillMaxSize(), color = Paper) { App(this, store) }
            }
        }
    }

    fun keepAwake(on: Boolean) {
        if (on) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    fun dim(on: Boolean) {
        window.attributes = window.attributes.apply { screenBrightness = if (on) 0.02f else WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE }
    }

    /** 개발용: 에뮬레이터 등 얼굴을 비출 수 없는 환경에서 이 파일로 추적을 시험(디버그 빌드만). */
    fun testImage(): File? = if (BuildConfig.DEBUG) getExternalFilesDir(null)?.resolve("test-face.jpg")?.takeIf { it.isFile } else null
}

@Composable
private fun App(activity: MainActivity, store: Store) {
    var pairing by remember { mutableStateOf(store.load()) }
    var step by remember { mutableStateOf(if (pairing == null) Step.Unpaired else Step.Connecting) }
    var code by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }

    fun forget(reason: String) {
        store.clear()
        pairing = null
        step = Step.Unpaired
        message = reason
    }

    fun accept(link: String) {
        val parsed = Pairing.parse(link)
        if (parsed == null) {
            message = "debutkit 휴대폰 조작 QR 주소가 아님(http://PC주소:포트/remote#... 형식)"
            step = Step.Unpaired
            return
        }
        store.save(link)
        pairing = parsed
        code = Signing.confirmCode(parsed.secret)
        message = ""
        step = Step.Connecting
    }

    // 등록 확인: 승인될 때까지 2초마다
    LaunchedEffect(pairing, step) {
        val current = pairing ?: return@LaunchedEffect
        if (step != Step.Connecting && step != Step.Waiting) return@LaunchedEffect
        while (isActive) {
            try {
                val hello = withContext(Dispatchers.IO) { Client(current).hello(Build.MODEL.take(30)) }
                code = hello.code
                message = ""
                if (hello.approved) {
                    step = Step.Ready
                    return@LaunchedEffect
                }
                step = Step.Waiting
            } catch (error: PcError) {
                if (error.status == 401 && !error.message.orEmpty().contains("시각")) {
                    forget("${error.message}. 이 휴대폰의 등록 정보를 지웠습니다.")
                    return@LaunchedEffect
                }
                message = error.message.orEmpty()
            } catch (error: IOException) {
                message = "PC에 연결하지 못함: 같은 Wi-Fi인지, PC의 휴대폰 조작 화면이 켜져 있는지 확인(${error.message})"
            }
            delay(2000)
        }
    }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().background(Ink).statusBarsPadding().padding(16.dp, 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("debutkit 휴대폰", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 17.sp)
            Spacer(Modifier.weight(1f))
            pairing?.let { Text("${it.host}:${it.port}", color = Color.White.copy(alpha = 0.75f), fontSize = 12.sp) }
        }
        Column(Modifier.fillMaxSize().navigationBarsPadding().imePadding().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            when (step) {
                Step.Unpaired -> Unpaired(message, onScan = { step = Step.Scanning }, onLink = ::accept)
                Step.Scanning -> Scanning(onFound = ::accept, onCancel = { step = Step.Unpaired })
                Step.Connecting, Step.Waiting -> Waiting(step == Step.Waiting, code, message, onForget = { forget("") })
                Step.Ready -> Ready(activity, pairing!!, onForget = { forget("이 휴대폰의 등록 정보를 지웠습니다.") }, onLost = { reason ->
                    message = reason
                    step = Step.Connecting
                })
            }
        }
    }
}

@Composable
private fun Card(content: @Composable () -> Unit) {
    Surface(Modifier.fillMaxWidth(), color = Color.White, shape = MaterialTheme.shapes.small, tonalElevation = 0.dp, shadowElevation = 2.dp) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { content() }
    }
}

@Composable
private fun BigButton(text: String, onClick: () -> Unit, primary: Boolean = true, enabled: Boolean = true) {
    val modifier = Modifier.fillMaxWidth().height(52.dp)
    if (primary) Button(onClick, modifier, enabled = enabled) { Text(text, fontWeight = FontWeight.Bold) }
    else OutlinedButton(onClick, modifier, enabled = enabled) { Text(text, fontWeight = FontWeight.Bold, color = Ink) }
}

@Composable
private fun Unpaired(message: String, onScan: () -> Unit, onLink: (String) -> Unit) {
    var link by remember { mutableStateOf("") }
    Card {
        Text("PC와 연결", fontWeight = FontWeight.Bold, fontSize = 18.sp)
        Text("PC에서 debutkit 오버레이 설정 화면의 휴대폰 연결을 열고, 휴대폰 조작 화면을 켠 뒤 새 휴대폰 QR 만들기를 누르십시오. 휴대폰과 PC는 같은 Wi-Fi여야 합니다.")
        BigButton("QR 코드 찍기", onScan)
    }
    Card {
        Text("주소로 연결", fontWeight = FontWeight.Bold)
        Text("QR 코드를 찍을 수 없으면 PC의 debutkit remote pair 명령이 알려 주는 주소를 붙여 넣으십시오.", color = Color.DarkGray, fontSize = 14.sp)
        OutlinedTextField(link, { link = it }, Modifier.fillMaxWidth(), placeholder = { Text("http://192.168.0.5:8792/remote#d=...") }, singleLine = true)
        BigButton("연결", { onLink(link) }, primary = false, enabled = link.isNotBlank())
    }
    if (message.isNotEmpty()) Text(message, color = Bad)
    Card {
        Text("이 앱이 하는 일", fontWeight = FontWeight.Bold)
        Text("휴대폰 앞면 카메라로 얼굴을 추적해 머리 움직임과 표정 52개를 debutkit PC로 보냅니다. 카메라 영상은 휴대폰 안에서만 처리하고 숫자 값만 보내며, 저장하거나 인터넷으로 보내지 않습니다.",
            color = Color.DarkGray, fontSize = 14.sp)
    }
}

@Composable
private fun Scanning(onFound: (String) -> Unit, onCancel: () -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val lifecycle = androidx.lifecycle.compose.LocalLifecycleOwner.current
    var allowed by remember { mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed = it }
    LaunchedEffect(Unit) { if (!allowed) ask.launch(Manifest.permission.CAMERA) }
    Card {
        Text("PC 화면의 QR 코드를 비추십시오", fontWeight = FontWeight.Bold)
        if (!allowed) Text("QR 코드를 읽으려면 카메라 사용을 허용해야 합니다.", color = Bad)
        else {
            val view = remember { PreviewView(context) }
            val executor = remember { Executors.newSingleThreadExecutor() }
            AndroidView({ view }, Modifier.fillMaxWidth().aspectRatio(3f / 4f))
            DisposableEffect(Unit) {
                val future = ProcessCameraProvider.getInstance(context)
                future.addListener({
                    val provider = future.get()
                    val preview = Preview.Builder().build().also { it.surfaceProvider = view.surfaceProvider }
                    val analysis = ImageAnalysis.Builder().setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build()
                    analysis.setAnalyzer(executor, QrScanner { text -> view.post { onFound(text) } })
                    provider.unbindAll()
                    provider.bindToLifecycle(lifecycle, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
                }, ContextCompat.getMainExecutor(context))
                onDispose {
                    runCatching { future.get().unbindAll() }
                    executor.shutdown()
                }
            }
        }
        BigButton("취소", onCancel, primary = false)
    }
}

@Composable
private fun Waiting(waiting: Boolean, code: String, message: String, onForget: () -> Unit) {
    Card {
        Text(if (waiting) "PC에서 승인 필요" else "PC에 연결 중", fontWeight = FontWeight.Bold, fontSize = 18.sp)
        Text("PC의 휴대폰 연결 화면 등록 기기 목록에 같은 확인 번호가 보이면 승인을 누르십시오.")
        Text(code, Modifier.fillMaxWidth(), fontSize = 48.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center,
            letterSpacing = 8.sp)
        Text("승인되면 자동으로 추적 화면이 열립니다.", color = Color.DarkGray, fontSize = 14.sp)
        if (message.isNotEmpty()) Text(message, color = Bad, fontSize = 14.sp)
    }
    BigButton("등록 취소", onForget, primary = false)
}

/** 승인된 뒤: 얼굴 추적 또는 카메라 영상(카메라는 하나만 쓸 수 있어 둘 중 하나). */
@Composable
private fun Ready(activity: MainActivity, pairing: Pairing, onForget: () -> Unit, onLost: (String) -> Unit) {
    var camera by remember { mutableStateOf(false) }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        listOf(false to "얼굴 추적", true to "카메라 영상").forEach { (mode, label) ->
            val selected = camera == mode
            Button({ camera = mode }, Modifier.weight(1f).height(44.dp),
                colors = if (selected) ButtonDefaults.buttonColors() else ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Ink)) {
                Text(label, fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal)
            }
        }
    }
    if (camera) CameraVideo(activity, pairing, onForget, onLost) else Tracking(activity, pairing, onForget, onLost)
}

@Composable
private fun CameraVideo(activity: MainActivity, pairing: Pairing, onForget: () -> Unit, onLost: (String) -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    var allowed by remember { mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed = it }
    var running by remember { mutableStateOf(false) }
    var front by remember { mutableStateOf(false) }
    var dimmed by remember { mutableStateOf(false) }
    var state by remember { mutableStateOf<CameraSender.State?>(null) }
    val hot = activity.thermal.intValue >= PowerManager.THERMAL_STATUS_SEVERE
    WatchApproval(pairing, onLost)
    Card {
        Text("카메라 영상", fontWeight = FontWeight.Bold, fontSize = 18.sp)
        Text("휴대폰 카메라 영상을 PC OBS의 [DK] 휴대폰 카메라(앱) 소스로 보냅니다. 같은 Wi-Fi에서 직접 보내며 소리는 보내지 않습니다.", fontSize = 14.sp)
        val (label, color) = when (state) {
            CameraSender.State.Starting, CameraSender.State.Waiting -> "OBS 수신 화면과 연결 중" to Color.DarkGray
            CameraSender.State.Connected -> "보내는 중" to Ok
            CameraSender.State.Retrying -> "연결 끊김: 다시 연결 중" to Bad
            CameraSender.State.NoReceiver -> "수신 화면 응답 없음: PC 휴대폰 연결 화면에서 앱 영상용 OBS 소스 만들기, OBS 실행 확인" to Bad
            CameraSender.State.Failed -> "연결 실패: PC에서 이 휴대폰의 등록과 승인 확인" to Bad
            CameraSender.State.Stopped, null -> (if (running) "준비 중" else "멈춤") to Color.DarkGray
        }
        if (running) Text(label, color = color, fontWeight = FontWeight.Bold)
        if (hot) Text("휴대폰이 뜨거움: 해상도를 낮췄습니다. 충전기를 빼거나 케이스를 벗기고 그늘에 두십시오.", color = Bad, fontSize = 14.sp)
        if (!allowed) Text("카메라 영상에는 카메라 사용 허용이 필요합니다.", color = Bad, fontSize = 14.sp)
    }
    if (running && allowed) CameraSession(activity, pairing, front, hot) { state = it }
    BigButton(if (running) "보내기 멈춤" else "보내기 시작", {
        if (!running && !allowed) ask.launch(Manifest.permission.CAMERA) else { state = null; running = !running }
    })
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton({ front = !front }, Modifier.weight(1f).height(48.dp), enabled = !running) { Text(if (front) "앞면 카메라" else "뒷면 카메라", color = Ink) }
        OutlinedButton({ dimmed = !dimmed; activity.dim(dimmed) }, Modifier.weight(1f).height(48.dp)) { Text(if (dimmed) "밝게" else "화면 어둡게", color = Ink) }
    }
    OutlinedButton({ running = false; onForget() }, Modifier.fillMaxWidth().height(48.dp)) { Text("연결 해제", color = Ink) }
    Text("카메라를 바꾸려면 보내기를 멈춘 뒤 고르십시오. 앱을 닫거나 다른 앱으로 바꾸면 보내기가 멈춥니다. 영상은 PC로만 보내며 저장하지 않습니다.",
        color = Color.DarkGray, fontSize = 13.sp)
    DisposableEffect(Unit) { onDispose { activity.dim(false) } }
}

/** 보내기 실행: 화면이 사라지면 카메라와 연결을 정리한다. */
@Composable
private fun CameraSession(activity: MainActivity, pairing: Pairing, front: Boolean, hot: Boolean, onState: (CameraSender.State) -> Unit) {
    val onStateNow = rememberUpdatedState(onState)
    val holder = remember { mutableStateOf<CameraSender?>(null) }
    val renderer = remember { org.webrtc.SurfaceViewRenderer(activity) }
    AndroidView({ renderer }, Modifier.fillMaxWidth().aspectRatio(1f).background(Color.Black))
    DisposableEffect(front) {
        activity.keepAwake(true)
        val egl = org.webrtc.EglBase.create()
        renderer.init(egl.eglBaseContext, null)
        renderer.setMirror(front)
        renderer.setScalingType(org.webrtc.RendererCommon.ScalingType.SCALE_ASPECT_FIT)
        val sender = CameraSender(activity, pairing, egl) { state -> activity.runOnUiThread { onStateNow.value(state) } }
        holder.value = sender
        sender.preview(renderer)
        sender.start(front)
        onDispose {
            holder.value = null
            sender.preview(null)
            renderer.release()
            sender.close()
            activity.keepAwake(false)
        }
    }
    LaunchedEffect(hot) { holder.value?.lower(hot) }
}

/** 승인이 취소됐는지 10초마다 확인(PC에서 삭제하면 등록 화면으로). */
@Composable
private fun WatchApproval(pairing: Pairing, onLost: (String) -> Unit) {
    LaunchedEffect(pairing) {
        while (isActive) {
            delay(10_000)
            try {
                val hello = withContext(Dispatchers.IO) { Client(pairing).hello(Build.MODEL.take(30)) }
                if (!hello.approved) onLost("PC에서 승인이 취소되었습니다.")
            } catch (failure: PcError) {
                if (failure.status == 401 && !failure.message.orEmpty().contains("시각")) onLost(failure.message.orEmpty())
            } catch (_: IOException) {
                // 잠시 끊김
            }
        }
    }
}

@Composable
private fun Tracking(activity: MainActivity, pairing: Pairing, onForget: () -> Unit, onLost: (String) -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val lifecycle = androidx.lifecycle.compose.LocalLifecycleOwner.current
    var allowed by remember { mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { allowed = it }
    var running by remember { mutableStateOf(false) }
    var useTestImage by remember { mutableStateOf(false) }
    var dimmed by remember { mutableStateOf(false) }
    var found by remember { mutableStateOf(false) }
    var rate by remember { mutableIntStateOf(0) }
    var error by remember { mutableStateOf("") }
    val thermal = activity.thermal.intValue
    val hot = thermal >= PowerManager.THERMAL_STATUS_SEVERE
    val testFile = remember { activity.testImage() }

    WatchApproval(pairing, onLost)

    Card {
        Text("얼굴 추적", fontWeight = FontWeight.Bold, fontSize = 18.sp)
        if (running) {
            Text(if (found) "추적 중" else "얼굴을 찾지 못함: 화면을 정면으로 보십시오", color = if (found) Ok else Bad, fontWeight = FontWeight.Bold)
            Text("PC로 보내는 횟수: 초당 ${rate}회", fontSize = 14.sp)
        } else {
            Text("시작을 누르면 앞면 카메라로 얼굴을 추적해 PC로 보냅니다. 휴대폰을 얼굴 정면, 30에서 50cm 거리에 세워 두십시오.", fontSize = 14.sp)
        }
        if (hot) Text("휴대폰이 뜨거움: 보내는 횟수를 줄였습니다. 충전기를 빼거나 케이스를 벗기고 그늘에 두십시오.", color = Bad, fontSize = 14.sp)
        if (error.isNotEmpty()) Text(error, color = Bad, fontSize = 14.sp)
        if (!allowed) Text("얼굴 추적에는 카메라 사용 허용이 필요합니다.", color = Bad, fontSize = 14.sp)
    }

    if (running && !useTestImage && allowed) {
        val view = remember { PreviewView(context).apply { scaleType = PreviewView.ScaleType.FIT_CENTER } }
        AndroidView({ view }, Modifier.fillMaxWidth().aspectRatio(3f / 4f).background(Color.Black))
        TrackingSession(activity, pairing, view, null, lifecycle, hot, onFrame = { frame, sent -> found = frame.found; rate = sent }, onError = { error = it })
    } else if (running && useTestImage && testFile != null) {
        Box(Modifier.fillMaxWidth().height(80.dp).background(Color.Black), contentAlignment = Alignment.Center) {
            Text("시험 이미지로 추적 중(개발용)", color = Color.White)
        }
        TrackingSession(activity, pairing, null, testFile, lifecycle, hot, onFrame = { frame, sent -> found = frame.found; rate = sent }, onError = { error = it })
    }

    BigButton(if (running) "추적 멈춤" else "추적 시작", {
        if (!running && !allowed) ask.launch(Manifest.permission.CAMERA) else {
            error = ""
            useTestImage = false
            running = !running
        }
    })
    if (testFile != null && !running) BigButton("시험 이미지로 추적(개발용)", { useTestImage = true; running = true }, primary = false)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton({ dimmed = !dimmed; activity.dim(dimmed) }, Modifier.weight(1f).height(48.dp)) { Text(if (dimmed) "밝게" else "화면 어둡게", color = Ink) }
        OutlinedButton({ running = false; onForget() }, Modifier.weight(1f).height(48.dp)) { Text("연결 해제", color = Ink) }
    }
    Text("화면 어둡게는 배터리와 발열을 줄입니다. 추적 중에는 화면이 꺼지지 않습니다. 앱을 닫거나 다른 앱으로 바꾸면 추적이 멈춥니다.", color = Color.DarkGray, fontSize = 13.sp)
    DisposableEffect(Unit) { onDispose { activity.dim(false) } }
}

/** 추적 실행(카메라 또는 시험 이미지): 화면이 사라지면 카메라와 전송을 정리한다. */
@Composable
private fun TrackingSession(activity: MainActivity, pairing: Pairing, view: PreviewView?, testFile: File?, lifecycle: androidx.lifecycle.LifecycleOwner, hot: Boolean,
                            onFrame: (Frame, Int) -> Unit, onError: (String) -> Unit) {
    val hotNow = rememberUpdatedState(hot)
    val onFrameNow = rememberUpdatedState(onFrame)
    val onErrorNow = rememberUpdatedState(onError)
    DisposableEffect(view, testFile) {
        activity.keepAwake(true)
        val executor = Executors.newSingleThreadExecutor()
        val sender = Sender(pairing)
        val sentTimes = ArrayDeque<Long>()
        var shown = 0L
        val stopped = java.util.concurrent.atomic.AtomicBoolean(false)
        fun handle(frame: Frame) {
            if (stopped.get()) return
            val sentNow = runCatching { sender.send(frame, if (hotNow.value) 66 else 33) }.getOrElse { failure ->
                activity.runOnUiThread { onErrorNow.value("보내기 실패: ${failure.message}") }
                false
            }
            val now = System.currentTimeMillis()
            if (sentNow) sentTimes.addLast(now)
            while (sentTimes.isNotEmpty() && now - sentTimes.first() > 1000) sentTimes.removeFirst()
            if (now - shown > 250) {
                shown = now
                val rate = sentTimes.size
                activity.runOnUiThread { onFrameNow.value(frame, rate) }
            }
        }
        val tracker = try {
            FaceTracker(activity, onFrame = { frame -> if (!executor.isShutdown) executor.execute { handle(frame) } },
                onError = { message -> activity.runOnUiThread { onErrorNow.value(message) } })
        } catch (failure: Exception) {
            onErrorNow.value("얼굴 인식 준비 실패: ${failure.message}")
            null
        }
        var provider: ProcessCameraProvider? = null
        if (tracker != null && view != null) {
            val future = ProcessCameraProvider.getInstance(activity)
            future.addListener({
                if (stopped.get()) return@addListener
                val camera = future.get()
                provider = camera
                val preview = Preview.Builder().build().also { it.surfaceProvider = view.surfaceProvider }
                val analysis = ImageAnalysis.Builder()
                    .setResolutionSelector(ResolutionSelector.Builder()
                        .setResolutionStrategy(ResolutionStrategy(android.util.Size(640, 480), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)).build())
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                    .build()
                analysis.setAnalyzer(executor, tracker.analyzer)
                val selector = if (camera.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA)) CameraSelector.DEFAULT_FRONT_CAMERA else CameraSelector.DEFAULT_BACK_CAMERA
                camera.unbindAll()
                camera.bindToLifecycle(lifecycle, selector, preview, analysis)
            }, ContextCompat.getMainExecutor(activity))
        }
        val testThread = if (tracker != null && testFile != null) Thread {
            val bitmap = BitmapFactory.decodeFile(testFile.path)
            while (!stopped.get() && bitmap != null) {
                tracker.detect(bitmap)
                Thread.sleep(33)
            }
        }.also { it.start() } else null
        onDispose {
            stopped.set(true)
            provider?.unbindAll()
            testThread?.join(500)
            executor.execute {
                runCatching { sender.send(Frame(false)) }
                sender.close()
            }
            executor.shutdown()
            tracker?.close()
            activity.keepAwake(false)
        }
    }
}
