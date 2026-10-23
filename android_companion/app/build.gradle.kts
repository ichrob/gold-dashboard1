plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// These values are supplied only to the trusted, manually triggered release
// workflow. A public debug/PR build never has a signing key and cannot overwrite
// a signed release. No signing material belongs in this repository.
val bobStoreFile = System.getenv("BOB_ANDROID_SIGNING_STORE_FILE")
val bobStorePassword = System.getenv("BOB_ANDROID_SIGNING_STORE_PASSWORD")
val bobKeyAlias = System.getenv("BOB_ANDROID_SIGNING_KEY_ALIAS")
val bobKeyPassword = System.getenv("BOB_ANDROID_SIGNING_KEY_PASSWORD")
val bobHasSigning = listOf(bobStoreFile, bobStorePassword, bobKeyAlias, bobKeyPassword)
    .all { !it.isNullOrBlank() }

android {
    namespace = "ch.bob.degirocompanion"
    compileSdk = 35

    defaultConfig {
        // The permanent user app: do not change between releases.
        // It installs alongside previously built test apps on first adoption.
        applicationId = "ch.bob.degirocompanion.stable"
        minSdk = 26
        targetSdk = 35
        versionCode = System.getenv("BOB_ANDROID_VERSION_CODE")?.toIntOrNull()
            ?.takeIf { it in 16..2100000000 } ?: 16
        versionName = "1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        manifestPlaceholders["bobAppLabel"] = "Bob – Handy"
    }
    signingConfigs {
        if (bobHasSigning) {
            create("bobStable") {
                storeFile = file(bobStoreFile!!)
                storePassword = bobStorePassword!!
                keyAlias = bobKeyAlias!!
                keyPassword = bobKeyPassword!!
            }
        }
    }
    buildTypes {
        getByName("debug") {
            // Disposable lab app only. Never suggest GitHub debug artifacts as
            // updates to the signed permanent app.
            applicationIdSuffix = ".voicetest"
            versionNameSuffix = "-lab"
            manifestPlaceholders["bobAppLabel"] = "Bob: Android-Labor (Test)"
        }
        getByName("release") {
            isMinifyEnabled = false
            if (bobHasSigning) {
                signingConfig = signingConfigs.getByName("bobStable")
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    // Bundled on-device OCR model: no image is uploaded to an OCR server.
    implementation("com.google.mlkit:text-recognition:16.0.1")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test:core:1.6.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.3.0")
}
