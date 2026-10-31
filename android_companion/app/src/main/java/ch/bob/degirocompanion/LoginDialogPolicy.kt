package ch.bob.degirocompanion

/** Only known negative actions; a cancel label alone never authorizes a click. */
internal object LoginDialogPolicy {
    enum class Kind { FINGERPRINT, NOTICE, OFFER }
    const val NOTICE = "Bitte geben Sie Ihren PassCode ein, um TouchID / FaceID einzurichten"
    const val OFFER = "TouchID / FaceID aktivieren"
    const val BODY = "Wenn Face/Touch ID aktiviert ist, können Sie sich mit Face/Touch ID anmelden."
    fun normalize(value: CharSequence?) = value?.toString()?.trim()?.replace(Regex("\\s+"), " ").orEmpty()
    fun identify(degiro: Boolean, trustedSystem: Boolean, associated: Boolean,
        labels: Set<String>, afterEntry: Boolean, owner: LoginDialogCheck.Owner? = null): Kind? {
        val cancel = labels.count { it == "Abbrechen" || it == "Cancel" } == 1
        val kinds = mutableListOf<Kind>()
        if (degiro && !afterEntry && NOTICE in labels && "Schließen" in labels) kinds += Kind.NOTICE
        if (degiro && afterEntry && OFFER in labels && BODY in labels && "Bestätigen" in labels && cancel)
            kinds += Kind.OFFER
        // The observed Samsung-owned prompt exposes its DEGIRO label and negative action,
        // while the underlying app-window association is unavailable. Only this verified
        // biometric component may use the visible dialog label as app context.
        val fingerprintContext = associated || owner == LoginDialogCheck.Owner.SAMSUNG_BIOMETRICS
        if (trustedSystem && fingerprintContext && !afterEntry && "DEGIRO" in labels && cancel &&
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
    private var actionAccepted = false
    private var fingerprintAccepted = false
    fun stable(value: String, now: Long): Boolean {
        if (signature != value) { signature = value; since = now; samples = 1; return false }
        return ++samples >= 3 && now - since >= 2_000
    }
    fun resetObservation() { signature = null; samples = 0 }
    fun reserve(kind: LoginDialogPolicy.Kind, now: Long): Boolean {
        if (waiting != null || !used.add(kind)) return false
        waiting = kind; sentAt = now; actionAccepted = false; resetObservation(); return true
    }
    fun accepted(kind: LoginDialogPolicy.Kind) {
        if (waiting == kind) {
            actionAccepted = true
            if (kind == LoginDialogPolicy.Kind.FINGERPRINT) fingerprintAccepted = true
        }
    }
    // Wait without reading labels or acting on an unknown owner during the native
    // fingerprint dismissal. Reservation alone never grants this grace period.
    fun awaitingFingerprintReturn(now: Long, afterEntry: Boolean) = !afterEntry &&
        waiting == LoginDialogPolicy.Kind.FINGERPRINT && actionAccepted && now - sentAt in 0L until 3_000L
    fun fingerprintProgress(now: Long): LoginOwnerContext.FingerprintProgress = when {
        LoginDialogPolicy.Kind.FINGERPRINT !in used -> LoginOwnerContext.FingerprintProgress.NOT_REQUESTED
        !fingerprintAccepted -> LoginOwnerContext.FingerprintProgress.REQUESTED
        waiting != LoginDialogPolicy.Kind.FINGERPRINT -> LoginOwnerContext.FingerprintProgress.RETURNED
        awaitingFingerprintReturn(now, false) -> LoginOwnerContext.FingerprintProgress.ACCEPTED_WAIT
        else -> LoginOwnerContext.FingerprintProgress.ACCEPTED_EXPIRED
    }
    fun expired(now: Long) = waiting != null && now - sentAt >= 6_000
    fun gone() { waiting = null; actionAccepted = false; resetObservation() }
}


/** Fixed metadata only: no package strings, screen text, identifiers, coordinates or input values. */
internal data class LoginDialogCheck private constructor(
    val phase: Phase, val owner: Owner, val stage: Stage,
    val systemVerified: Boolean = false, val degiroContext: Boolean = false,
    val degiroLabel: Boolean = false, val biometricLabel: Boolean = false,
    val cancelLabel: Boolean = false, val cancelAmbiguous: Boolean = false,
    val ownerContext: LoginOwnerContext? = null
) {
    enum class Phase { BEFORE_PIN, AFTER_PIN }
    enum class Owner { DEGIRO, SYSTEM_UI, SAMSUNG_BIOMETRICS, OTHER }
    enum class Stage { OWNER_CHECK, MARKER_CHECK }
    companion object {
        private fun phase(afterEntry: Boolean) = if (afterEntry) Phase.AFTER_PIN else Phase.BEFORE_PIN
        fun ownerRejected(owner: Owner, afterEntry: Boolean, context: LoginOwnerContext? = null) =
            LoginDialogCheck(phase(afterEntry), owner, Stage.OWNER_CHECK, ownerContext = context)
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

/** Package names are reduced locally to fixed categories. No labels or input values. */
internal data class LoginOwnerContext(
    val rootKind: RootKind, val focusedKind: RootKind,
    val sameWindow: Boolean, val fingerprintProgress: FingerprintProgress
) {
    enum class RootKind { EMPTY, BOB, DEGIRO, SYSTEM_UI, SAMSUNG_BIOMETRICS, ANDROID_FRAMEWORK, PERMISSION_CONTROLLER, OTHER, UNAVAILABLE, AMBIGUOUS }
    enum class FingerprintProgress { NOT_REQUESTED, REQUESTED, ACCEPTED_WAIT, ACCEPTED_EXPIRED, RETURNED }
    companion object {
        fun classify(pkg: String?, ownPackage: String): RootKind = when {
            pkg.isNullOrEmpty() -> RootKind.EMPTY
            pkg == ownPackage -> RootKind.BOB
            pkg == "nl.degiro.trader" -> RootKind.DEGIRO
            pkg == "com.android.systemui" -> RootKind.SYSTEM_UI
            pkg == "com.samsung.android.biometrics.app.setting" -> RootKind.SAMSUNG_BIOMETRICS
            pkg == "android" -> RootKind.ANDROID_FRAMEWORK
            pkg in setOf("com.android.permissioncontroller", "com.google.android.permissioncontroller") -> RootKind.PERMISSION_CONTROLLER
            else -> RootKind.OTHER
        }
    }
}
