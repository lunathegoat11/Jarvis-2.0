plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.lunathegoat11.jarvis"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.lunathegoat11.jarvis"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "2.0.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Signed with the debug key so the APK installs without a store.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    sourceSets["main"].assets.srcDir(layout.buildDirectory.dir("generated/webui"))
}

// The phone app shows the same page as the Mac app (orb, feed, settings).
val copyWebUi by tasks.registering(Copy::class) {
    from(rootProject.file("../jarvis/app.html"))
    into(layout.buildDirectory.dir("generated/webui"))
}
tasks.named("preBuild") { dependsOn(copyWebUi) }
