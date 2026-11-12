plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "org.bob.workflowfixture"
    compileSdk = 35
    defaultConfig { applicationId = "org.bob.workflowfixture"; minSdk = 26; targetSdk = 35; versionCode = 1; versionName = "test" }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}
