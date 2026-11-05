plugins { id("com.android.application") }
val keyFile = System.getenv("BOB_ANDROID_SIGNING_STORE_FILE")
val keyStorePassword = System.getenv("BOB_ANDROID_SIGNING_STORE_PASSWORD")
val signingAlias = System.getenv("BOB_ANDROID_SIGNING_KEY_ALIAS")
val signingPassword = System.getenv("BOB_ANDROID_SIGNING_KEY_PASSWORD")
val hasSigning = listOf(keyFile, keyStorePassword, signingAlias, signingPassword).all { !it.isNullOrBlank() }
android {
    namespace = "ch.bob.zentrale"
    compileSdk = 35
    defaultConfig {
        applicationId = "ch.bob.zentrale"
        minSdk = 26
        targetSdk = 35
        versionCode = System.getenv("BOB_ANDROID_VERSION_CODE")?.toIntOrNull()?.takeIf { it in 1..2100000000 } ?: 1
        versionName = "1.0"
    }
    signingConfigs {
        if (hasSigning) create("stable") {
            storeFile = file(keyFile!!)
            storePassword = keyStorePassword!!
            keyAlias = signingAlias!!
            keyPassword = signingPassword!!
        }
    }
    buildTypes {
        getByName("debug") { applicationIdSuffix = ".debug" }
        getByName("release") { if (hasSigning) signingConfig = signingConfigs.getByName("stable") }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
dependencies { testImplementation("junit:junit:4.13.2") }
