package ch.bob.degirocompanion

/** Strictly a decision to SEND existing, already cropped list evidence for
 * independent server verification, never a claim that ten products were read.
 * No extra screen capture, scrolling on an order form, or broker action.
 */
internal object MorningListEndPolicy {
    private val footer = Regex(
        "(?iu)(?:flatexDEGIRO\\s+Bank\\s+Dutch\\s+Branch|Datenquellen\\s+und\\s+-anbieter)"
    )

    fun hasVerifiedFooter(nodes: List<MorningReadPolicy.Node>): Boolean =
        nodes.any { n -> !n.editable && !n.password && !n.sensitive &&
            footer.containsMatchIn(n.text) }

    fun maySubmitAtEnd(nodes: List<MorningReadPolicy.Node>,
                       capturedImages: Int, seen: Set<String>,
                       current: List<String>, action: MorningReadPolicy.Action): Boolean =
        capturedImages in 2..4 && seen.size in 5..9 &&
        seen.all(SeriesEvidence::validIsin) &&
        current.isNotEmpty() && current.size <= 10 &&
        current.distinct() == current &&
        current.all { SeriesEvidence.validIsin(it) && it in seen } &&
        action.kind == MorningReadPolicy.Kind.COLLECT && action.isins == current &&
        hasVerifiedFooter(nodes) &&
        !nodes.any { it.password || it.sensitive || it.editable }

    /** Ten visible ISIN labels do not prove ten complete product rows.
     * Permit at most one additional cropped, read-only edge capture when
     * independent on-device row text has not confirmed all ten labels.
     * This never marks a server import successful or loosens its parser. */
    fun needsEdgeCapture(capturedImages: Int, seen: Set<String>,
                         covered: Set<String>): Boolean =
        capturedImages in 1..3 && seen.size==10 &&
        seen.all(SeriesEvidence::validIsin) &&
        covered.all { it in seen } && covered.size<10

    fun maySubmitAtCaptureLimit(capturedImages: Int, seen: Set<String>): Boolean =
        capturedImages == 4 && seen.size in 5..9 && seen.all(SeriesEvidence::validIsin)
}
