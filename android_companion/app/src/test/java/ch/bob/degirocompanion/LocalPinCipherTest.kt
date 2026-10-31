package ch.bob.degirocompanion

import javax.crypto.KeyGenerator
import org.junit.Assert.*
import org.junit.Test

class LocalPinCipherTest {
    private fun key() = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
    @Test fun roundTripUsesFreshIvAndKeepsLeadingZero() {
        val key = key(); val pin = byteArrayOf(48,49,50,51,52)
        val first = LocalPinCipher.encrypt(pin, key); val second = LocalPinCipher.encrypt(pin, key)
        assertEquals(34, first.size); assertFalse(first.contentEquals(second))
        assertArrayEquals(pin, LocalPinCipher.decrypt(first, key))
        assertArrayEquals(pin, LocalPinCipher.decrypt(second, key))
    }
    @Test fun everyTamperedByteWrongKeyAndWrongLengthIsRejected() {
        val key = key(); val blob = LocalPinCipher.encrypt(byteArrayOf(48,49,50,51,52), key)
        for (i in blob.indices) {
            val bad = blob.copyOf(); bad[i] = (bad[i].toInt() xor 1).toByte()
            assertThrows(Exception::class.java) { LocalPinCipher.decrypt(bad, key) }
        }
        assertThrows(Exception::class.java) { LocalPinCipher.decrypt(blob, key()) }
        assertThrows(Exception::class.java) { LocalPinCipher.decrypt(blob + byteArrayOf(0), key) }
        assertThrows(Exception::class.java) { LocalPinCipher.decrypt(blob.copyOf(33), key) }
    }
}
