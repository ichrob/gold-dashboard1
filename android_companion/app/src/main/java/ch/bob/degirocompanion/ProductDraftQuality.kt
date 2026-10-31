package ch.bob.degirocompanion

/** Never discard a verified visible field just because a retry read a different one. */
internal object ProductDraftQuality {
    fun noRegression(previousMissing: Collection<String>, currentMissing: Collection<String>): Boolean =
        previousMissing.containsAll(currentMissing)
}
