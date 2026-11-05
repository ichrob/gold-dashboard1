package ch.bob.degirocompanion

/** Restricted parity with the existing German-ISIN OCR rule on the server.
 * Keep raw optical text; canonical identities are only used for association.
 * Never apply this to accessibility text or alter an already valid DE000 ID. */
internal object MorningOcrIdentity {
    val tokens=Regex("\\b(?:[A-Z]{2}[A-Z0-9]{9}[0-9]|DE[0OQ]{3}[A-Z0-9]{7})\\b",RegexOption.IGNORE_CASE)
    fun canonical(raw:String):String? {
        val value=raw.uppercase(java.util.Locale.ROOT)
        if(value.length!=12)return null
        if(SeriesEvidence.validIsin(value) && value.startsWith("DE000"))return value
        if(!Regex("DE[0OQ]{3}[A-Z0-9]{7}").matches(value))
            return value.takeIf { SeriesEvidence.validIsin(it) }
        val candidate="DE000"+value.takeLast(7).replace('O','0').replace('I','1')
        return candidate.takeIf { SeriesEvidence.validIsin(it) }
    }
}
