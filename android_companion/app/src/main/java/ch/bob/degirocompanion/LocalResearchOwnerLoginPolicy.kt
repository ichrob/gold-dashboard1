package ch.bob.degirocompanion

/** Read-only classification of a DEGIRO login prompt during the owner's
 * original Gold-ISIN research session. This never authorizes entering a PIN,
 * password, opening another app, clicking, or submitting a broker order.
 */
internal object LocalResearchOwnerLoginPolicy {
    private val entry = Regex("(?iu)^(anmelden|einloggen|login|log in|sign in|passwort eingeben|password|passwort|pin eingeben|pin-code eingeben)$")
    private val strongPin = Regex("(?iu)^(pin eingeben|pin-code eingeben|passwort eingeben)$")
    private val protectedOrder = Regex("(?iu)^(order bestätigen|confirm order|orderart|ordertyp|limitpreis|stückzahl|anzahl kaufen|orderdetails|orderübersicht|orderzusammenfassung)$")

    fun visible(nodes: List<MorningReadPolicy.Node>): Boolean {
        if(nodes.isEmpty() || nodes.size>500)return false
        val labels=nodes.flatMap { listOf(it.text,it.description,it.hint) }
            .map { it.trim() }.filter { it.isNotEmpty() }
        if(labels.any(protectedOrder::matches))return false
        if(labels.any(strongPin::matches))return true
        val login=labels.any(entry::matches)
        val secret=nodes.any { it.password || (it.editable && it.sensitive) } ||
            labels.any { it.equals("Passwort",true) || it.equals("Password",true) }
        return login && secret
    }
}
