package ch.bob.degirocompanion

/** Pure choice between the previously pinned list and the latest saved run.
 * The caller validates provenance, ISIN identity and upload timestamp before
 * passing a timestamp. An invalid candidate never wins over a valid one.
 */
internal object RefreshSourceChoice {
    fun choose(pinned: String?, current: String?, validUploadedAt: (String) -> Long?): String? =
        listOfNotNull(pinned, current)
            .mapNotNull { raw -> validUploadedAt(raw)?.let { it to raw } }
            .maxByOrNull { it.first }?.second
}
