package ch.bob.degirocompanion

/** Only known negative actions; a cancel label alone never authorizes a click. */
internal object LoginDialogPolicy {
    enum class Kind { FINGERPRINT, NOTICE, OFFER }
    const val NOTICE = "Bitte geben Sie Ihren PassCode ein, um TouchID / FaceID einzurichten"
    const val OFFER = "TouchID / FaceID aktivieren"
    const val BODY = "Wenn Face/Touch ID aktiviert ist, können Sie sich mit Face/Touch ID anmelden."
    fun normalize(value: CharSequence?) = value?.toString()?.trim()?.replace(Regex("\\s+"), " ").orEmpty()
    fun identify(degiro: Boolean, trustedSystem: Boolean, associated: Boolean,
        labels: Set<String>, afterEntry: Boolean): Kind? {
        val cancel = labels.count { it == "Abbrechen" || it == "Cancel" } == 1
        val kinds = mutableListOf<Kind>()
        if (degiro && !afterEntry && NOTICE in labels && "Schließen" in labels) kinds += Kind.NOTICE
        if (degiro && afterEntry && OFFER in labels && BODY in labels && "Bestätigen" in labels && cancel)
            kinds += Kind.OFFER
        if (trustedSystem && associated && !afterEntry && "DEGIRO" in labels && cancel &&
            labels.any { it.contains("Fingerabdruck", ignoreCase = true) || it.contains("fingerprint", ignoreCase = true) })
            kinds += Kind.FINGERPRINT
        return kinds.singleOrNull()
    }
}

/** Reserve before dispatch; neither an accepted action nor a changing layout grants a retry. */
internal class LoginDialogBudget {
    private val used = mutableSetOf<LoginDialogPolicy.Kind>()
    private var signature: String? = null
    private var since = 0L
    private var samples = 0
    var waiting: LoginDialogPolicy.Kind? = null
        private set
    private var sentAt = 0L
    fun stable(value: String, now: Long): Boolean {
        if (signature != value) { signature = value; since = now; samples = 1; return false }
        return ++samples >= 3 && now - since >= 2_000
    }
    fun resetObservation() { signature = null; samples = 0 }
    fun reserve(kind: LoginDialogPolicy.Kind, now: Long): Boolean {
        if (waiting != null || !used.add(kind)) return false
        waiting = kind; sentAt = now; resetObservation(); return true
    }
    fun expired(now: Long) = waiting != null && now - sentAt >= 6_000
    fun gone() { waiting = null; resetObservation() }
}


/** Fixed metadata only: no package strings, screen text, identifiers, coordinates or input values. */
internal data class LoginDialogCheck private constructor(
    val phase: Phase, val owner: Owner, val stage: Stage,
    val systemVerified: Boolean = false, val degiroContext: Boolean = false,
    val degiroLabel: Boolean = false, val biometricLabel: Boolean = false,
    val cancelLabel: Boolean = false, val cancelAmbiguous: Boolean = false
) {
    enum class Phase { BEFORE_PIN, AFTER_PIN }
    enum class Owner { DEGIRO, SYSTEM_UI, SAMSUNG_BIOMETRICS, OTHER }
    enum class Stage { OWNER_CHECK, MARKER_CHECK }
    companion object {
        private fun phase(afterEntry: Boolean) = if (afterEntry) Phase.AFTER_PIN else Phase.BEFORE_PIN
        fun ownerRejected(owner: Owner, afterEntry: Boolean) =
            LoginDialogCheck(phase(afterEntry), owner, Stage.OWNER_CHECK)
        fun markersRejected(owner: Owner, afterEntry: Boolean, systemVerified: Boolean,
            degiroContext: Boolean, labels: Set<String>): LoginDialogCheck {
            val negatives = labels.count { it == "Abbrechen" || it == "Cancel" }
            return LoginDialogCheck(phase(afterEntry), owner, Stage.MARKER_CHECK,
                systemVerified, degiroContext, "DEGIRO" in labels,
                labels.any { it.contains("Fingerabdruck", ignoreCase = true) || it.contains("fingerprint", ignoreCase = true) },
                negatives == 1, negatives > 1)
        }
    }
}
