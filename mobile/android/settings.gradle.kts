pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // RootEncoder(Apache-2.0, 휴대폰만으로 방송)는 JitPack에만 배포. 이 저장소에서는 RootEncoder만 받는다
        maven("https://jitpack.io") { content { includeGroupByRegex("com\\.github\\.pedroSG94.*") } }
    }
}

rootProject.name = "debutkit-phone"
include(":app")
