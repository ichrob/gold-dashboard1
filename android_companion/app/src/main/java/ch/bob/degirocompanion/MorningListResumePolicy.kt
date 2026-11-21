package ch.bob.degirocompanion

/** Choose one bounded action only after the user explicitly restarts Bob Handy.
 * Never starts a phone session, browser action or product read on its own. */
internal object MorningListResumePolicy {
    enum class Mode { NEW_LIST, RETRY_TRANSFER, CHECK_RECEIPT_ONLY }
    private const val DAY_MS = 24L*60*60*1000
    private const val FRESH_MS = 15L*60*1000
    private const val RECEIPT_WINDOW_MS = 3L*60*60*1000

    fun verificationFailed(stage: String?, error: String?): Boolean =
        stage == "read-failed" && error == "ListVerificationError"

    /** The first optical verification failure may still be retried by the
     * server. Only a completed, unsuccessful enhanced pass is terminal and
     * can turn one explicit handset start into a fresh Gold capture. */
    fun terminalVerificationFailed(stage: String?, error: String?,
                                   enhancedVerification: Boolean): Boolean =
        verificationFailed(stage,error) && enhancedVerification

    /** An old receipt has no verifiable server response after bounded read-only
     * checks. Preserve its images, but do not monopolize a new explicit Gold run.
     * This is NOT a server verdict about list completeness. */
    fun receiptUnavailableForFreshCapture(attempt: Int, receiptOnly: Boolean,
                                          matchingBatch: Boolean, stage: String?): Boolean =
        receiptOnly && attempt >= 3 &&
            (!matchingBatch || stage.isNullOrBlank() ||
                stage in setOf("missing","not-found","unknown"))

    fun mode(ageMillis: Long, resumeCount: Int, verificationFailed: Boolean = false,
             receiptUnconfirmed: Boolean = false): Mode {
        if (verificationFailed || receiptUnconfirmed) return Mode.NEW_LIST
        if (ageMillis !in 0..DAY_MS || resumeCount !in 0..3)
            return Mode.NEW_LIST
        if (ageMillis<=FRESH_MS && resumeCount<2)
            return Mode.RETRY_TRANSFER
        // The image series may have become 'synced' while the handset was
        // offline. Query only its device-owned receipt, without re-uploading
        // or using the old/expired session ID to control the screen.
        if (ageMillis<=RECEIPT_WINDOW_MS && resumeCount<3)
            return Mode.CHECK_RECEIPT_ONLY
        return Mode.NEW_LIST
    }
}
