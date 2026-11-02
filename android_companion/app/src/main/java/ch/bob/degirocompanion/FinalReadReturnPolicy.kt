package ch.bob.degirocompanion

/** Return to Bob Handy after an explicitly authorized, completed product read.
 * This is an app-local status screen, NOT a BACK or any DEGIRO UI action.
 * Never trigger after a stopped/interrupted run, a locked screen, or a
 * different foreground window. No account data, quotes, or credentials.
 */
internal object FinalReadReturnPolicy {
    fun allowed(
        code: String,
        draft: String,
        expectedIsin: String,
        previousWindow: Int?,
        currentWindow: Int?,
        foregroundPackage: String?,
        interactive: Boolean,
        locked: Boolean,
        authorizedSession: Boolean
    ): Boolean =
        code == "READ" && authorizedSession && interactive && !locked &&
        foregroundPackage == ProductScreenEvidence.PACKAGE &&
        previousWindow != null && previousWindow == currentWindow &&
        SeriesEvidence.validIsin(expectedIsin) &&
        draft.lineSequence().any { it == "ISIN: $expectedIsin" }
}
