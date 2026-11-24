package io.github.budongjw.debutkit.phone

import android.Manifest
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.os.Build
import android.os.PowerManager
import android.view.SurfaceHolder
import android.view.SurfaceView
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.pedro.encoder.input.video.CameraHelper
import io.github.budongjw.debutkit.phone.LiveSession.Phase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

private val Backgrounds = listOf(0xFF2A1F3D.toInt() to "보라", 0xFF1E2327.toInt() to "검정", 0xFF00B140.toInt() to "초록(크로마키)", 0xFFFAF7F5.toInt() to "밝은 색")
private val Sensitivity = listOf(-48f to "민감", -40f to "보통", -32f to "둔감")

/** 바로 방송: PC 없이 이 휴대폰에서 방송 플랫폼으로 송출(캐릭터 화면 또는 카메라 영상). */
@Composable
internal fun LiveScreen(activity: MainActivity) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val store = remember { LiveStore(context) }
    var config by remember { mutableStateOf(store.load()) }
    val status by LiveSession.status.collectAsState()
    val busy = status.phase == Phase.Connecting || status.phase == Phase.Live || status.phase == Phase.Retrying
    var message by remember { mutableStateOf("") }
    var keyText by remember { mutableStateOf("") }
    var keyVersion by remember { mutableIntStateOf(0) }
    val keySaved = remember(config.platform, keyVersion) { store.hasKey(config.platform) }
    var imageVersion by remember { mutableIntStateOf(0) }
    val customReady = remember(imageVersion) { store.idleImage.isFile && store.talkImage.isFile }
    val hot = activity.thermal.intValue >= PowerManager.THERMAL_STATUS_SEVERE
    var dimmed by remember { mutableStateOf(false) }

    fun change(next: LiveConfig) {
        config = next
        store.save(next)
    }

    fun granted(permission: String) = ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED
    var cameraAllowed by remember { mutableStateOf(granted(Manifest.permission.CAMERA)) }
    var pendingStart by remember { mutableStateOf(false) }
    val askCamera = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { cameraAllowed = it }
    val askStart = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        cameraAllowed = granted(Manifest.permission.CAMERA)
        if (granted(Manifest.permission.RECORD_AUDIO) && (!config.camera || cameraAllowed)) pendingStart = true
        else message = if (config.camera) "방송에는 카메라와 마이크 사용 허용이 필요합니다." else "방송에는 마이크 사용 허용이 필요합니다."
    }
    var picking by remember { mutableStateOf<File?>(null) }
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        val target = picking ?: return@rememberLauncherForActivityResult
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            message = runCatching { withContext(Dispatchers.IO) { store.importImage(context, uri, target) }; "" }.getOrElse { it.message.orEmpty() }
            imageVersion++
        }
    }

    // 캐릭터 화면 그림과 입 움직임 민감도(방송 중에도 바로 반영), 발열 시 비트레이트 낮춤
    LaunchedEffect(config.background, config.title, imageVersion) {
        val images = withContext(Dispatchers.IO) { store.customImages() }
        LiveSession.painter = CharacterPainter(config.background, config.title, images)
    }
    LaunchedEffect(config.thresholdDb) { LiveSession.voice.thresholdDb = config.thresholdDb }
    LaunchedEffect(hot) { LiveSession.lower(hot) }
    DisposableEffect(busy) {
        activity.keepAwake(busy)
        onDispose { activity.keepAwake(false) }
    }
    // 카메라 영상은 가로 화면으로(휴대폰을 가로로 들고 방송)
    DisposableEffect(config.camera) {
        activity.requestedOrientation = if (config.camera) ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE else ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
        onDispose { activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT }
    }
    DisposableEffect(Unit) {
        onDispose {
            activity.dim(false)
            LiveSession.detach()
            if (!LiveSession.streaming) LiveSession.release()
        }
    }

    val orientation = LocalConfiguration.current.orientation
    val rotation = remember(config.camera, orientation) { if (config.camera) CameraHelper.getCameraOrientation(context) else 0 }
    val setup = LiveSession.Setup(config.camera, config.front, config.quality, Live.videoKbps(config.platform, config.quality), config.platform.keyframe, rotation)
    val canPreview = !config.camera || cameraAllowed
    // 카메라 영상은 화면이 가로로 바뀐 뒤에 준비(세로일 때 한 번, 가로로 바뀐 뒤 또 한 번 준비하지 않게)
    val settled = !config.camera || orientation == Configuration.ORIENTATION_LANDSCAPE
    LaunchedEffect(setup, canPreview, settled) {
        if (canPreview && settled) LiveSession.prepare(context, setup)?.let { message = it }
    }

    fun begin() {
        message = ""
        LiveSession.clearFailure()
        val key = store.loadKey(config.platform)
        if (key == null) {
            message = "${config.platform.label} 스트림 키를 먼저 저장: ${config.platform.hint}"
            return
        }
        val url = try {
            Live.publishUrl(config.platform, config.server, key)
        } catch (error: LiveError) {
            message = error.message.orEmpty()
            return
        }
        val required = listOfNotNull(Manifest.permission.RECORD_AUDIO, Manifest.permission.CAMERA.takeIf { config.camera })
        if (required.any { !granted(it) }) {
            val notify = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) listOf(Manifest.permission.POST_NOTIFICATIONS) else emptyList()
            askStart.launch((required + notify).toTypedArray())
            return
        }
        LiveSession.prepare(context, setup)?.let {
            message = it
            return
        }
        LiveService.start(context, config.camera)
        LiveSession.start(url, key)
    }
    LaunchedEffect(pendingStart) {
        if (pendingStart) {
            pendingStart = false
            begin()
        }
    }

    val notices: @Composable () -> Unit = {
        StatusLine(status)
        if (hot) Text("휴대폰이 뜨거움: 영상 비트레이트를 낮췄습니다. 충전기를 빼거나 케이스를 벗기고 그늘에 두십시오.", color = Bad, fontSize = 14.sp)
        if (message.isNotEmpty()) Text(message, color = Bad, fontSize = 14.sp)
        if (config.camera && !cameraAllowed) Text("카메라 영상에는 카메라 사용 허용이 필요합니다.", color = Bad, fontSize = 14.sp)
    }
    val preview: @Composable (Modifier) -> Unit = { modifier ->
        if (canPreview) PreviewSurface(modifier) else BigButton("카메라 사용 허용", { askCamera.launch(Manifest.permission.CAMERA) }, primary = false)
    }
    val controls: @Composable () -> Unit = {
        BigButton(if (busy) "방송 끝내기" else "방송 시작", { if (busy) LiveService.stop(context) else begin() })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (config.camera) {
                OutlinedButton({
                    change(config.copy(front = !config.front))
                    LiveSession.switchCamera()
                }, Modifier.weight(1f).height(48.dp)) { Text(if (config.front) "뒷면 카메라로" else "앞면 카메라로", color = Ink) }
            }
            OutlinedButton({ dimmed = !dimmed; activity.dim(dimmed) }, Modifier.weight(1f).height(48.dp)) { Text(if (dimmed) "밝게" else "화면 어둡게", color = Ink) }
        }
    }
    if (orientation == Configuration.ORIENTATION_LANDSCAPE) {
        // 가로 화면(카메라 영상): 미리보기 옆에 상태와 버튼을 두어 스크롤 없이 방송 시작
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.weight(1f)) { preview(Modifier.fillMaxWidth()) }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                notices()
                controls()
            }
        }
    } else {
        Card {
            Text("바로 방송", fontWeight = FontWeight.Bold, fontSize = 18.sp)
            Text("PC 없이 이 휴대폰에서 치지직, SOOP, YouTube, Twitch로 바로 송출합니다. 캐릭터 화면(마이크 소리에 맞춰 입 움직임) 또는 카메라 영상과 마이크 소리를 보냅니다.",
                fontSize = 14.sp)
            notices()
        }
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { preview(Modifier.widthIn(max = 560.dp).fillMaxWidth()) }
        controls()
    }

    Card {
        Text("방송 플랫폼과 스트림 키", fontWeight = FontWeight.Bold)
        Choices(Platform.entries.map { it to it.label }, config.platform, enabled = !busy) { change(config.copy(platform = it)) }
        OutlinedTextField(config.server, { text -> change(config.copy(servers = config.servers + (config.platform to text.trim()))) }, Modifier.fillMaxWidth(),
            enabled = !busy, singleLine = true, label = { Text("송출 서버 주소") },
            placeholder = { Text(config.platform.server.ifEmpty { "방송 플랫폼 화면의 서버 주소(rtmp://)" }) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
        OutlinedTextField(keyText, { keyText = it }, Modifier.fillMaxWidth(), enabled = !busy, singleLine = true, label = { Text("스트림 키") },
            visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedButton({
                message = runCatching { store.saveKey(config.platform, keyText); keyText = ""; "" }.getOrElse { it.message.orEmpty() }
                keyVersion++
            }, enabled = !busy && keyText.isNotBlank()) { Text("키 저장", color = Ink) }
            OutlinedButton({ store.clearKey(config.platform); keyVersion++ }, enabled = !busy && keySaved) { Text("키 삭제", color = Ink) }
            Text(if (keySaved) "저장됨" else "없음", color = if (keySaved) Ok else Bad, fontWeight = FontWeight.Bold, fontSize = 14.sp)
        }
        Text("키 위치: ${config.platform.hint}", color = Color.DarkGray, fontSize = 13.sp)
        Text("스트림 키는 이 휴대폰의 키 저장소로 암호화해 이 앱 안에만 보관합니다. 키가 알려지면 다른 사람이 내 채널로 방송할 수 있으므로 방송 화면에 띄우지 마십시오.",
            color = Color.DarkGray, fontSize = 13.sp)
    }

    Card {
        Text("방송 화면", fontWeight = FontWeight.Bold)
        Choices(listOf(false to "캐릭터 화면", true to "카메라 영상"), config.camera, enabled = !busy) { change(config.copy(camera = it)) }
        if (config.camera) {
            Text("카메라 영상은 휴대폰을 가로로 들고 방송합니다. 방송 중에도 앞면과 뒷면 카메라를 바꿀 수 있습니다.", color = Color.DarkGray, fontSize = 13.sp)
        } else {
            Text("배경색", fontWeight = FontWeight.Bold, fontSize = 14.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Backgrounds.forEach { (color, label) ->
                    Box(Modifier.size(40.dp).clip(CircleShape).background(Color(color))
                        .border(if (config.background == color) 3.dp else 1.dp, if (config.background == color) Pink else Color.Gray, CircleShape)
                        .clickable { change(config.copy(background = color)) })
                }
            }
            Text(Backgrounds.firstOrNull { it.first == config.background }?.second.orEmpty(), color = Color.DarkGray, fontSize = 13.sp)
            OutlinedTextField(config.title, { change(config.copy(title = it.take(40))) }, Modifier.fillMaxWidth(), singleLine = true,
                label = { Text("왼쪽 위 글자(방송 제목 등)") })
            Text("캐릭터 그림", fontWeight = FontWeight.Bold, fontSize = 14.sp)
            Text(if (customReady) "고른 그림 사용 중" else "debutkit 기본 캐릭터 사용 중. 입 닫은 그림과 입 연 그림을 모두 고르면 그 그림으로 바뀝니다(투명 배경 PNG 권장).",
                color = Color.DarkGray, fontSize = 13.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton({ picking = store.idleImage; pick.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                    Modifier.weight(1f)) { Text("입 닫은 그림", color = Ink) }
                OutlinedButton({ picking = store.talkImage; pick.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                    Modifier.weight(1f)) { Text("입 연 그림", color = Ink) }
            }
            if (store.idleImage.isFile || store.talkImage.isFile) OutlinedButton({ store.clearImages(); imageVersion++ }, Modifier.fillMaxWidth()) {
                Text("기본 캐릭터로", color = Ink)
            }
            Text("입 움직임 민감도", fontWeight = FontWeight.Bold, fontSize = 14.sp)
            Choices(Sensitivity, Sensitivity.minByOrNull { kotlin.math.abs(it.first - config.thresholdDb) }!!.first, enabled = true) {
                change(config.copy(thresholdDb = it))
            }
            Text("입은 방송 중 마이크 소리에 맞춰 움직입니다. 조용한데도 입이 움직이면 둔감, 말해도 움직이지 않으면 민감으로 바꾸십시오.", color = Color.DarkGray, fontSize = 13.sp)
        }
    }

    Card {
        Text("화질", fontWeight = FontWeight.Bold)
        Choices(Quality.entries.map { it to it.label }, config.quality, enabled = !busy) { change(config.copy(quality = it)) }
        Text("영상 ${Live.videoKbps(config.platform, config.quality).toThousands()} kbps, 소리 128 kbps. 모바일 데이터로 방송하면 720p 기준 1시간에 약 1.2 GB를 사용합니다. 연결이 느리면 자동으로 비트레이트를 낮춥니다.",
            color = Color.DarkGray, fontSize = 13.sp)
    }
    Text("방송 중에는 화면이 꺼지지 않으며, 다른 앱으로 바꿔도 송출은 이어집니다(알림에서 방송 끝내기). 영상은 지정한 방송 플랫폼으로만 보내며 저장하지 않습니다.",
        color = Color.DarkGray, fontSize = 13.sp)
}

/** 송출 화면 미리보기(16:9). 표면이 생기고 사라질 때 송출 라이브러리에 붙이고 뗀다. */
@Composable
private fun PreviewSurface(modifier: Modifier) {
    AndroidView({ ctx ->
        SurfaceView(ctx).apply {
            holder.addCallback(object : SurfaceHolder.Callback {
                override fun surfaceCreated(holder: SurfaceHolder) = Unit
                override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) = LiveSession.attach(holder.surface, width, height)
                override fun surfaceDestroyed(holder: SurfaceHolder) = LiveSession.detach()
            })
        }
    }, modifier.aspectRatio(16f / 9f).background(Color.Black))
}

@Composable
private fun StatusLine(status: LiveSession.Status) {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(status.phase) {
        while (status.phase == Phase.Live || status.phase == Phase.Retrying) {
            now = System.currentTimeMillis()
            delay(1000)
        }
    }
    val (text, color) = when (status.phase) {
        Phase.Idle -> "방송 꺼짐" to Color.DarkGray
        Phase.Connecting -> "송출 서버 연결 중" to Color.DarkGray
        Phase.Live -> "방송 중 ${clock((now - status.since) / 1000)}, ${status.kbps.toInt().toThousands()} kbps" to Pink
        Phase.Retrying -> status.message to Bad
        Phase.Failed -> status.message to Bad
    }
    Text(text, color = color, fontWeight = FontWeight.Bold)
}

@Composable
private fun <T> Choices(items: List<Pair<T, String>>, selected: T, enabled: Boolean, onSelect: (T) -> Unit) {
    Column {
        items.forEach { (value, label) ->
            Row(Modifier.fillMaxWidth().clickable(enabled = enabled) { onSelect(value) }, verticalAlignment = Alignment.CenterVertically) {
                RadioButton(selected = value == selected, onClick = { onSelect(value) }, enabled = enabled)
                Text(label, color = if (enabled) Ink else Color.Gray)
            }
        }
    }
}

private fun clock(seconds: Long): String = "%02d:%02d:%02d".format(seconds / 3600, seconds / 60 % 60, seconds % 60)

private fun Int.toThousands(): String = "%,d".format(this)
