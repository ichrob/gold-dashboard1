package ch.bob.degirocompanion

/** Return to Bob Handy after an explicitly authorized, completed product read.
 * This is an app-local status screen, NOT a BACK or any DEGIRO UI action.
 * Never trigger after a stopped/interrupted run, a locked screen, or a
 * different foreground window. No account data, quotes, or credentials.
 */
internal object FinalReadReturnPolicy {
    /** Aborted read: reveal the local status only, never navigate in DEGIRO.
     * The caller must independently attest a recognized, non-sensitive
     * read-only DEGIRO surface. This does not mark the run COMPLETE. */
    fun allowedAbort(
        code: String,
        foregroundPackage: String?,
        interactive: Boolean,
        locked: Boolean,
        authorizedSession: Boolean,
        safeSurface: Boolean
    ): Boolean =
        code == "RETURN_NOT_CONFIRMED" && authorizedSession &&
        interactive && !locked && safeSurface &&
        foregroundPackage == ProductScreenEvidence.PACKAGE

    /** A single native system BACK after the final, verified read. This
     * cannot click a broker UI element or start another read. It is allowed
     * only on the exact previously read, unprotected informational product
     * window, with the same strict owner/session and lock checks as the
     * app-local completion handoff. Sending BACK is not proof it succeeded.
     */
    fun safeLastProductBack(
        code: String,
        draft: String,
        expectedIsin: String,
        previousWindow: Int?,
        currentWindow: Int?,
        foregroundPackage: String?,
        interactive: Boolean,
        locked: Boolean,
        authorizedSession: Boolean,
        nodes: List<MorningReadPolicy.Node>
    ): Boolean =
        allowed(code,draft,expectedIsin,previousWindow,currentWindow,
            foregroundPackage,interactive,locked,authorizedSession) &&
        currentWindow != null &&
        MorningReadPolicy.safeStatusReturn(nodes,expectedIsin) &&
        MorningReadPolicy.returnAfterRead(nodes,expectedIsin,currentWindow,
            previousWindow,code)

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
