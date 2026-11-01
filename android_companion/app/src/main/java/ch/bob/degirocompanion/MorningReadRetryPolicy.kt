package ch.bob.degirocompanion

/** Retry a failed capture, not an already useful exact-ISIN observation
 * missing only an unlabelled leverage. A second DEGIRO visit cannot supply
 * a missing LV on a closed-market Mini-Future reliably; issuer/research
 * fallback must handle it separately. Never manufacture a leverage. */
internal object MorningReadRetryPolicy {
    fun retry(code: String, hasDraft: Boolean, missingFields: Collection<String>, attempt: Int): Boolean {
        if (code == "COMPLETE" || attempt >= 2) return false
        if (hasDraft && missingFields.isNotEmpty() && missingFields.all { it == "Hebel" }) return false
        return true
    }
}
