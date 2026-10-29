package ch.bob.degirocompanion

/** Fixed, bounded operations only. Local session and device state always win. */
internal object PhoneRemotePolicy {
    val actions = setOf("READ_PAGE", "SEARCH_GOLD", "STOP")
    fun reject(action: String, active: Boolean, expired: Boolean, unlocked: Boolean, degiro: Boolean, busy: Boolean): String? = when {
        !active || expired -> "EXPIRED"
        action !in actions -> "REJECTED"
        action == "STOP" -> null
        !unlocked -> "LOCKED"
        !degiro -> "WRONG_APP"
        busy -> "BUSY"
        else -> null
    }
}
