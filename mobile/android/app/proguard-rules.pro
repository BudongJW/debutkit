# MediaPipe는 네이티브 코드(JNI)와 리플렉션으로 자바 클래스를 찾으므로 이름을 유지한다
-keep class com.google.mediapipe.** { *; }
-keep class com.google.protobuf.** { *; }
-dontwarn com.google.mediapipe.**
-dontwarn com.google.protobuf.**
-dontwarn com.google.auto.value.**
-dontwarn javax.annotation.**
-dontwarn javax.lang.model.**
# MediaPipe의 로그(Flogger)는 호출한 클래스 이름으로 찾으므로 이름 유지(없으면 Graph 초기화 실패)
-keep class com.google.common.flogger.** { *; }
-dontwarn com.google.common.flogger.**
# WebRTC(libwebrtc)는 네이티브 코드가 자바 클래스와 메서드를 이름으로 찾는다
-keep class org.webrtc.** { *; }
-dontwarn org.webrtc.**
-keep class org.jni_zero.** { *; }
-dontwarn org.jni_zero.**
# 바로 방송: 송출 라이브러리(RootEncoder)는 기록 끄기 설정과 상관없이 RTMP 명령(스트림 키 포함)을 정보 수준으로 기록하므로
# 배포 빌드에서는 정보, 디버그, 상세 기록 호출을 지운다(경고와 오류 기록은 남김)
-assumenosideeffects class android.util.Log {
    public static int v(...);
    public static int d(...);
    public static int i(...);
}
