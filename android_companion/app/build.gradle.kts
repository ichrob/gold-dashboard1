plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
android {
    namespace = "ch.bob.degirocompanion"
    compileSdk = 35
    defaultConfig {
        applicationId = "ch.bob.degirocompanion"
        minSdk = 26
        targetSdk = 35
        versionCode = 15
        versionName = "0.12.1-samsung-address"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        manifestPlaceholders["bobAppLabel"] = "Bob: Android-Labor (nur Test)"
    }
    // GitHub-hosted debug builds may be signed with a different transient key
    // than the installed Android lab. Install this test APK SIDE BY SIDE instead
    // of colliding with or replacing the user's existing signed package.
    buildTypes {
        getByName("debug") {
            applicationIdSuffix = ".parallel"
            versionNameSuffix = "-parallel"
            manifestPlaceholders["bobAppLabel"] = "Bob: Android-Labor (Paralleltest)"
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
