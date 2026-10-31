package ch.bob.degirocompanion

/** Only fixed UI markers are retained; no account names, entered values or raw labels. */
internal object PinLoginEvidence {
    enum class Marker { NONE, LOGIN_HELP, DELETE_KEY, BIOMETRIC_SETUP }
    fun marker(value: CharSequence?): Marker {
        if (value == null || value.length > 160) return Marker.NONE
        val label = value.toString().trim().lowercase(java.util.Locale.ROOT).replace(Regex("\\s+"), " ")
        return when (label) {
            "haben sie ihren code vergessen?", "forgot your passcode?", "forgot your code?" -> Marker.LOGIN_HELP
            "löschen", "delete", "backspace", "rücktaste", "delete digit", "ziffer löschen", "⌫" -> Marker.DELETE_KEY
            "bitte geben sie ihren passcode ein, um touchid / faceid einzurichten" -> Marker.BIOMETRIC_SETUP
            else -> Marker.NONE
        }
    }
    fun classify(keypad: PinProbePolicy.Result, loginHelp: Boolean,
                 setup: Boolean, deleteTargets: Int): PinProbePolicy.Result {
        if (setup) return PinProbePolicy.Result.LOGIN_SETUP_VISIBLE
        if (keypad != PinProbePolicy.Result.KEYPAD_CLICK_OFFERED || !loginHelp) return keypad
        return if (deleteTargets == 1) PinProbePolicy.Result.LOGIN_DELETE_OFFERED
            else PinProbePolicy.Result.LOGIN_RESET_UNCONFIRMED
    }
}
