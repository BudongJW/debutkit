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
