package ch.bob.degirocompanion

/** Ephemeral single-digit button observations, never entered values or a PIN sequence. */
internal object PinKeypadPolicy {
    data class Key(val digit: Int, val clickOffered: Boolean)
    fun digit(label: CharSequence?): Int? =
        if (label != null && label.length == 1 && label[0] in '0'..'9') label[0] - '0' else null
    fun classify(keys: List<Key>): PinProbePolicy.Result? {
        if (keys.map { it.digit }.toSet() != (0..9).toSet()) return null
        if (keys.size != 10) return PinProbePolicy.Result.KEYPAD_AMBIGUOUS
        return if (keys.all { it.clickOffered }) PinProbePolicy.Result.KEYPAD_CLICK_OFFERED
            else PinProbePolicy.Result.KEYPAD_VISIBLE
    }
}
