package ch.bob.degirocompanion

import javax.crypto.Cipher
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Fixed authenticated envelope. The key is supplied by Android Keystore in production. */
internal object LocalPinCipher {
    private val aad = "bob-local-degiro-pin-v1".toByteArray(Charsets.US_ASCII)
    fun encrypt(pin: ByteArray, key: SecretKey): ByteArray {
        require(pin.size == 5 && pin.all { it.toInt() in 48..57 }) { "Invalid local PIN format" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key); cipher.updateAAD(aad)
        val encrypted = cipher.doFinal(pin)
        try {
            check(cipher.iv.size == 12 && encrypted.size == 21)
            return byteArrayOf(1) + cipher.iv + encrypted
        } finally { encrypted.fill(0) }
    }
    fun decrypt(blob: ByteArray, key: SecretKey): ByteArray {
        require(blob.size == 34 && blob[0] == 1.toByte()) { "Invalid local envelope" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, blob.copyOfRange(1, 13)))
        cipher.updateAAD(aad)
        val plain = cipher.doFinal(blob, 13, 21)
        if (plain.size != 5 || plain.any { it.toInt() !in 48..57 }) { plain.fill(0); error("Invalid local PIN format") }
        return plain
    }
}
