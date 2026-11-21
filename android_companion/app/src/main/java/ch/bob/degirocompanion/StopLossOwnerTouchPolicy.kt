package ch.bob.degirocompanion

/**
 * Owner interactions inside Bob Handy are not a broker touch and must never
 * prematurely revoke the local, one-order confirmation UI. Any external touch
 * during active form automation aborts. WAIT_OWNER is a passive review stage.
 */
internal object StopLossOwnerTouchPolicy {
    fun mustAbort(
        stage: StopLossPrefillPolicy.Stage,
        eventPackage: String?,
        ownPackage: String
    ): Boolean =
        stage != StopLossPrefillPolicy.Stage.WAIT_OWNER &&
            (eventPackage == null || eventPackage != ownPackage)
}
