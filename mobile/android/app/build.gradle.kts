import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// 앱 버전은 debutkit(파이썬 패키지)과 같다: pyproject.toml의 version
val debutkitVersion: String = Regex("""(?m)^version = "([^"]+)"""")
    .find(rootDir.resolve("../../pyproject.toml").readText())!!.groupValues[1]

// 1.0.0rc14 -> 1000014, 1.0.0 -> 1000099 (사전 릴리스보다 정식이 큼)
fun versionCodeOf(version: String): Int {
    val match = Regex("""^(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?""").find(version)!!.groupValues
    return match[1].toInt() * 1_000_000 + match[2].toInt() * 10_000 + match[3].toInt() * 100 + (match[4].toIntOrNull() ?: 99)
}

// 얼굴 인식 모델은 PC 프로그램과 같은 파일(src/debutkit/overlay/static/vendor/mediapipe)을 빌드할 때 복사(저장소에 두 번 두지 않음)
val modelDir = layout.buildDirectory.dir("generated/model-assets")
val copyFaceModel by tasks.registering(Copy::class) {
    from(rootDir.resolve("../../src/debutkit/overlay/static/vendor/mediapipe/face_landmarker.task"))
    into(modelDir)
}

// 배포 서명: 환경 변수(CI 비밀값)가 있으면 그 키, 없으면 디버그 키(시험용, 업데이트 시 재설치 필요)
val keystore: String? = System.getenv("DEBUTKIT_ANDROID_KEYSTORE")

android {
    namespace = "io.github.budongjw.debutkit.phone"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.budongjw.debutkit.phone"
        minSdk = 26
        targetSdk = 36
        versionCode = versionCodeOf(debutkitVersion)
        versionName = debutkitVersion
    }

    signingConfigs {
        if (keystore != null) {
            create("release") {
                storeFile = file(keystore)
                storePassword = System.getenv("DEBUTKIT_ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("DEBUTKIT_ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("DEBUTKIT_ANDROID_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
            // 휴대폰(64, 32비트 ARM)과 에뮬레이터, 크롬북(x86_64). 오래된 32비트 x86은 제외(MediaPipe 22 MB)
            ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64") }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    androidResources {
        noCompress += "task" // MediaPipe는 모델을 압축하지 않은 상태로 읽는다
    }

    sourceSets {
        getByName("main").assets.srcDir(modelDir)
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

tasks.named("preBuild") { dependsOn(copyFaceModel) }

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.10.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.11.0")
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.9.4")

    val camerax = "1.7.0"
    implementation("androidx.camera:camera-core:$camerax")
    implementation("androidx.camera:camera-camera2:$camerax")
    implementation("androidx.camera:camera-lifecycle:$camerax")
    implementation("androidx.camera:camera-view:$camerax")

    implementation("com.google.mediapipe:tasks-vision:1.2.3") // Apache-2.0
    implementation("com.google.zxing:core:3.5.4") // Apache-2.0, QR 코드 읽기
    implementation("io.github.webrtc-sdk:android:150.7871.08") // WebRTC(BSD-3), 카메라 영상 전송
    implementation("com.github.pedroSG94.RootEncoder:library:2.8.2") // RootEncoder(Apache-2.0), 휴대폰만으로 방송(RTMP, RTMPS)

    testImplementation("junit:junit:4.13.2")
}
