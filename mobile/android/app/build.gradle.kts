import java.util.Properties
import java.io.FileInputStream

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
    id("com.google.gms.google-services")
    id("com.google.firebase.crashlytics")
}

// Real release-signing key (android/upload-keystore.jks + key.properties,
// both gitignored — see android/.gitignore). Loaded from a properties file
// rather than hardcoded so the actual passwords never end up in a file
// that's ever committed. If key.properties is missing (e.g. a fresh clone
// without the keystore), release builds fail loudly here instead of
// silently falling back to debug signing, which Play Console would reject
// anyway.
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

android {
    namespace = "com.schoolqr.mobile"
    // Pinned above Flutter's default: mobile_scanner needs SDK 36, and
    // firebase_core/firebase_messaging/mobile_scanner all need NDK 27 —
    // surfaced by a real build attempt, not guessed.
    compileSdk = 36
    ndkVersion = "27.0.12077973"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_11.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.schoolqr.mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        // Flutter's default (21) is too low for mobile_scanner's camera
        // dependency (androidx.camera:camera-core requires 23) — surfaced
        // by a real build attempt.
        minSdk = 23
        // Pinned above Flutter 3.29's bundled default (35) — Play Console
        // now requires targeting at least API 36, surfaced by a real
        // upload attempt, not guessed. compileSdk is already 36 above, so
        // this doesn't need a separate bump there too.
        targetSdk = 36
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        create("release") {
            if (keystorePropertiesFile.exists()) {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    buildTypes {
        release {
            // Real upload key (android/app/upload-keystore.jks +
            // android/key.properties, both gitignored) — required for Play
            // Console, which rejects AABs signed with the debug keystore.
            signingConfig = signingConfigs.getByName("release")
            // Embeds full native (Flutter engine + plugin .so) debug symbols
            // directly in the AAB, so Play Console's crash/ANR reports for
            // native frames are symbolicated instead of raw addresses —
            // otherwise Play Console flags every upload with a warning
            // asking for a separate symbols file.
            ndk {
                debugSymbolLevel = "FULL"
            }
        }
    }
}

flutter {
    source = "../.."
}
