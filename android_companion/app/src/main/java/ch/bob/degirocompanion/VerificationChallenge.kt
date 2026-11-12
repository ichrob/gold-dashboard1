package ch.bob.degirocompanion

/** Visible challenge markers stop automation; never solve or dismiss challenges. */
internal object VerificationChallenge {
    private val marker = Regex(
        """(?iu)\b(?:captcha|recaptcha|hcaptcha)\b|(?:kein|not a)\s+(?:roboter|robot)|(?:verify|confirm)\s+(?:that you are|you are|you're)\s+(?:a )?human|bestätigen.{0,30}(?:mensch|roboter)|sicherheitsüberprüfung|security check|überprüfen.{0,30}(?:mensch|browser)|checking your browser"""
    )
    fun detected(text: String): Boolean =
        marker.containsMatchIn(text.replace(Regex("""[\s\p{Zs}]+"""), " "))
}
