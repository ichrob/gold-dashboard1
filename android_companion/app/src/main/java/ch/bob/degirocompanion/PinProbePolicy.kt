package ch.bob.degirocompanion

/** Only structural flags enter this model. No strings, values, labels or credentials. */
internal object PinProbePolicy {
    data class Field(val password: Boolean, val numeric: Boolean, val editable: Boolean,
        val enabled: Boolean, val setText: Boolean, val sensitive: Boolean)
    enum class Result { NO_INPUT, INPUT_PRESENT, NUMERIC_PASSWORD_INPUT, SET_TEXT_OFFERED, SENSITIVE_INPUT, INCOMPLETE, KEYPAD_VISIBLE, KEYPAD_CLICK_OFFERED, KEYPAD_AMBIGUOUS, LOGIN_SETUP_VISIBLE, LOGIN_DELETE_OFFERED, LOGIN_RESET_UNCONFIRMED, LOGIN_DELETE_AMBIGUOUS, LOGIN_DELETE_SHARED_TARGET, LOGIN_DELETE_NO_ACTION, LOGIN_DELETE_DISABLED, LOGIN_DELETE_LABEL_UNRECOGNIZED, SYMBOL_LAYOUT_UNCONFIRMED, SYMBOL_NODE_UNAVAILABLE, SYMBOL_NODES_MULTIPLE, SYMBOL_NO_ACTION, SYMBOL_LABELLED_ACTION, SYMBOL_UNLABELLED_ACTION, SYMBOL_DISABLED, SYMBOL_PARENT_ACTION_OBSERVED, SYMBOL_CLICK_FLAG_ONLY, SYMBOL_ACTION_ONLY, SYMBOL_LABELLED_PASSIVE, SYMBOL_UNLABELLED_PASSIVE }
    fun classify(fields: List<Field>, complete: Boolean): Result {
        if (!complete) return Result.INCOMPLETE
        if (fields.any { it.sensitive }) return Result.SENSITIVE_INPUT
        val pin = fields.filter { it.password && it.numeric && it.editable && it.enabled }
        if (pin.size == 1 && pin.single().setText) return Result.SET_TEXT_OFFERED
        if (pin.isNotEmpty()) return Result.NUMERIC_PASSWORD_INPUT
        return if (fields.any { it.editable || it.password }) Result.INPUT_PRESENT else Result.NO_INPUT
    }
}

/** Last observation belongs to this run only; an app switch is not a new DEGIRO result. */
internal class PinProbeHistory {
    var last: PinProbePolicy.Result? = null
        private set
    var symbolFlags: PinSymbolProbe.Flags? = null
        private set
    fun clear() { last = null; symbolFlags = null }
    fun observe(value: PinProbePolicy.Result?, flags: PinSymbolProbe.Flags? = null) {
        if (value != null) { last = value; symbolFlags = flags }
    }
}

