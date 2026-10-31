package ch.bob.degirocompanion

/**
 * Positive, time-stable evidence for a *foreground* DEGIRO Markets view.
 * The Android caller supplies only exact fixed UI markers, never screen content.
 * No login, PIN, or order action is authorized by this class.
 */
internal class LoginMarketsReadiness {
    enum class State { ABSENT, SETTLING, VERIFIED }
    private var window = -1
    private var since = -1L

    fun observe(now: Long, windowId: Int, foreground: Boolean, markers: Set<String>): State {
        if (!foreground || windowId < 0 ||
            !LoginDialogPolicy.verifiedMarkets(markers, afterEntry = false)) {
            clear()
            return State.ABSENT
        }
        if (window != windowId || since < 0 || now < since) {
            window = windowId
            since = now
            return State.SETTLING
        }
        return if (now - since >= 1_000L) State.VERIFIED else State.SETTLING
    }

    fun clear() { window = -1; since = -1L }
}
