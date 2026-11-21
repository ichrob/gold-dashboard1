package ch.bob.degirocompanion

/** A saved PIN is NEVER a mandatory prerequisite for an already owner-opened
 * read-only Gold product run. Only a tested, unlocked local keypad may use it;
 * otherwise allow the existing user-initiated reader with manual broker login.
 * This decision grants neither credential entry nor broker orders. */
internal object LocalPinReadStartPolicy {
    fun useVerifiedPin(stored:Boolean, keypadTested:Boolean, keyAvailable:Boolean):Boolean =
        stored && keypadTested && keyAvailable
}
