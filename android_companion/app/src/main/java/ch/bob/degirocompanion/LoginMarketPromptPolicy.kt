package ch.bob.degirocompanion

/** Exact, non-secret accessibility metadata for the DEGIRO Markets search.
 * An input's hint is not necessarily included in findAccessibilityNodeInfosByText().
 * No PIN values, user text, account data, or screen contents are collected. */
internal object LoginMarketPromptPolicy {
    private const val PROMPT = "Mit Namen, ISIN oder Symbol suchen"
    fun isExactPrompt(hint: CharSequence?, description: CharSequence?,
                      shownHintText: CharSequence?, editable: Boolean,
                      password: Boolean, sensitive: Boolean): Boolean {
        if (!editable || password || sensitive) return false
        return listOf(hint, description, shownHintText).any {
            LoginDialogPolicy.normalize(it).equals(PROMPT, ignoreCase = true)
        }
    }

    /** Only fixed, exact navigation/dialog labels may leave a local traversal.
     * Balance and free-form screen text are never retained or exported. */
    fun exactFixedLabel(value: CharSequence?, allowed: Set<String>): String? =
        LoginDialogPolicy.normalize(value).takeIf { it in allowed }

    fun usable(found: Boolean, complete: Boolean, protectedInput: Boolean): Boolean =
        found && complete && !protectedInput
}
