package ch.bob.degirocompanion

/** Match only a DEGIRO product-search *placeholder*, never typed input text. */
internal object MarketsSearchHintEvidence {
    const val PROMPT = "Mit Namen, ISIN oder Symbol suchen"

    fun isPromptHint(visible: Boolean, enabled: Boolean, editable: Boolean,
                     password: Boolean, sensitive: Boolean, hint: CharSequence?): Boolean {
        if (!visible || !enabled || !editable || password || sensitive) return false
        return LoginDialogPolicy.normalize(hint).equals(PROMPT, ignoreCase = true)
    }
}
