package ch.bob.degirocompanion

import android.app.KeyguardManager
import android.content.Context
import android.os.Build
import android.os.PowerManager
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import java.io.File
import java.security.KeyStore
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

/** Device-private encrypted blob; no backup, transport, intents, analytics or plaintext preferences. */
internal object LocalPinVault {
    private const val ALIAS = "bob_local_degiro_pin_v1"
    private fun file(c: Context) = AtomicFile(File(c.noBackupFilesDir, "degiro-pin-v1.bin"))
    fun available(c: Context): Boolean {
        val lock = c.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        return Build.VERSION.SDK_INT >= 35 && lock.isDeviceSecure && !lock.isDeviceLocked && !lock.isKeyguardLocked &&
            (c.getSystemService(Context.POWER_SERVICE) as PowerManager).isInteractive
    }
    fun exists(c: Context) = file(c).baseFile.exists()
    private fun key(create: Boolean): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        check(create) { "Local key unavailable" }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setUnlockedDeviceRequired(true).build())
        return generator.generateKey()
    }
    fun save(c: Context, pin: ByteArray) {
        check(available(c)) { "Device unavailable" }
        val encrypted = LocalPinCipher.encrypt(pin, key(true))
        val atomic = file(c)
        val stream = atomic.startWrite()
        try {
            stream.write(encrypted)
            atomic.finishWrite(stream)
        } catch (e: Exception) { atomic.failWrite(stream); throw e }
        finally { encrypted.fill(0) }
    }
    fun load(c: Context): ByteArray {
        check(available(c)) { "Device unavailable" }
        val blob = file(c).openRead().use { stream ->
            val bytes = ByteArray(34)
            var read = 0
            while (read < bytes.size) { val n = stream.read(bytes, read, bytes.size - read); check(n > 0); read += n }
            check(stream.read() == -1); bytes
        }
        try {
            return LocalPinCipher.decrypt(blob, key(false))
        } finally { blob.fill(0) }
    }
    fun delete(c: Context) {
        file(c).delete()
        KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry(ALIAS) }
    }
}
