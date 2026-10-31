package ch.bob.degirocompanion

/** Owns a short-lived copy. No serialization, rendering, retry or login-success inference. */
internal class LocalPinSequence(pin: ByteArray) {
    private val secret: ByteArray
    private var index = 0
    private var stopped = false
    var pending = false
        private set
    var complete = false
        private set
    val lastReserved get() = index == 5
    val ticket get() = index
    init {
        require(pin.size == 5 && pin.all { it.toInt() in 48..57 }) { "Invalid local PIN format" }
        secret = pin.copyOf()
    }
    fun reserve(valid: Boolean): Int? {
        if (!valid) { cancel(); return null }
        if (stopped || complete || pending) return null
        pending = true
        val digit = secret[index].toInt() - 48
        secret[index++] = 0
        return digit
    }
    fun completed(ticket: Int, ok: Boolean) {
        if (stopped || complete || !pending || ticket != index) return
        pending = false
        if (!ok) cancel()
        else if (index == 5) { complete = true; secret.fill(0) }
    }
    fun cancel() { stopped = true; pending = false; secret.fill(0) }
}
