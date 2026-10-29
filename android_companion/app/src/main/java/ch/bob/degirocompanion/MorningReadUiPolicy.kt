package ch.bob.degirocompanion

/** One primary action and finite, opt-out automatic diagnostic handoff. */
internal object MorningReadUiPolicy {
    enum class Action { OPEN, SEND, SETUP, START }
    fun action(running:Boolean,pending:Boolean,enabled:Boolean,connected:Boolean):Action = when {
        running -> Action.OPEN
        pending -> Action.SEND
        !enabled || !connected -> Action.SETUP
        else -> Action.START
    }
    fun automatic(enabled:Boolean,autoReturn:Boolean,running:Boolean,interactive:Boolean,locked:Boolean,
                  version:String,lastAttempt:String):Boolean = enabled && autoReturn && !running && interactive && !locked &&
        version.isNotEmpty() && version!=lastAttempt
    fun reason(code:String):String=when(code) {
        "STOPPED" -> "Prüfung angehalten; genauer Auslöser nicht protokolliert"
        "SEARCH_MISSING" -> "DEGIRO-Suche nicht erkannt"
        "SEARCH_TREE_EMPTY" -> "Android liefert keine lesbare Suchbeschriftung"
        "SEARCH_NOT_ACTIONABLE" -> "Suchbeschriftung erkannt, aber keine bedienbare Suchfläche"
        "GOLD_IDENTITIES_MISSING" -> "Goldsuche geöffnet; noch keine eindeutigen Goldhebel-Treffer mit sichtbarer ISIN"
        "SEARCH_AMBIGUOUS" -> "Suchfläche nicht eindeutig"
        "RESULT_MISSING" -> "Kein eindeutiger ISIN-Treffer"
        "READ_TIMEOUT" -> "Zeitlimit beim Lesen erreicht"
        "SCREEN_LOCKED" -> "Bildschirm wurde gesperrt"
        "USER_INTERRUPTED", "USER_STOP" -> "Prüfung durch Bedienung beendet"
        "PROTECTED_PASSWORD" -> "Passwortfeld sichtbar; zuerst selbst in DEGIRO anmelden"
        "PROTECTED_LOGIN" -> "Anmeldemerkmal sichtbar; Lesen sicher angehalten"
        "PROTECTED_ORDER" -> "Ordermerkmal erkannt; Lesen sicher angehalten"
        "PROTECTED_ORDER_CONFIRM" -> "Merkmal für Orderbestätigung erkannt; Lesen angehalten"
        "PROTECTED_ORDER_TYPE" -> "Merkmal für Ordertyp erkannt; Lesen angehalten"
        "PROTECTED_ORDER_PRICE" -> "Merkmal für Limitpreis erkannt; Lesen angehalten"
        "PROTECTED_ORDER_QUANTITY" -> "Merkmal für Stückzahl erkannt; Lesen angehalten"
        "PROTECTED_SENSITIVE_INPUT" -> "Android kennzeichnet ein Eingabefeld als sensibel"
        "PROTECTED_SENSITIVE_CONTENT" -> "Android kennzeichnet einen Ansichtsbereich als sensibel"
        "UNRECOGNIZED_INPUT" -> "Eingabefeld nicht sicher als Produktsuche erkannt"
        "PROTECTED_VIEW", "UNSAFE_VIEW" -> "Geschützte Ansicht; Lesen angehalten"
        "IDENTITY_CHANGED" -> "Produktkennung hat gewechselt"
        "PARTIAL" -> "Produkt teilweise gelesen"
        "COMPLETE" -> "Produkt vollständig gelesen"
        "RUN_TIMEOUT" -> "Zeitlimit des Listenlaufs erreicht"
        "SERVICE_INTERRUPTED" -> "Android-Lesedienst unterbrochen"
        "NAVIGATION_REJECTED" -> "DEGIRO hat den Suchschritt nicht ausgeführt"
        else -> "Leseschritt nicht abgeschlossen ($code)"
    }
}
