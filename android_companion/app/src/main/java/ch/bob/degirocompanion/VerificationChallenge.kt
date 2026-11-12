package ch.bob.degirocompanion

/** Explicit challenge prompts stop automation; informational security headings do not.
 * Generic headings cannot establish an active verification gate. Existing login,
 * sensitive-input and order guards still apply independently.
 */
internal object VerificationChallenge {
    private val marker = Regex(
        """(?iu)\b(?:captcha|recaptcha|hcaptcha)\b|(?:kein|not a)\s+(?:roboter|robot)|(?:verify|confirm)\s+(?:that you are|you are|you're)\s+(?:a )?human|bestätigen.{0,30}(?:mensch|roboter)|überprüfen.{0,30}(?:mensch|browser)|checking your browser"""
    )
    fun detected(text: String): Boolean =
        marker.containsMatchIn(text.replace(Regex("""[\s\p{Zs}]+"""), " "))
}
