package ch.bob.degirocompanion

/** Choose one bounded action only after the user explicitly restarts Bob Handy.
 * Never starts a phone session, browser action or product read on its own. */
internal object MorningListResumePolicy {
    enum class Mode { NEW_LIST, RETRY_TRANSFER, CHECK_RECEIPT_ONLY }
    private const val DAY_MS = 24L*60*60*1000
    private const val FRESH_MS = 15L*60*1000
    private const val RECEIPT_WINDOW_MS = 3L*60*60*1000

    fun mode(ageMillis: Long, resumeCount: Int): Mode {
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
