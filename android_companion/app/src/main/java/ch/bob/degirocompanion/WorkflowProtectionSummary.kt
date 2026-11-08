package ch.bob.degirocompanion

/**
 * Owner's selected five persistent high-protection rules.
 *
 * This is an explanatory catalog, never an execution permission or policy
 * override. Operational limits and Android's permission model are enforced
 * independently in the existing services.
 */
internal object WorkflowProtectionSummary {
    val retained = linkedMapOf(
        2 to "Keine selbstständigen Überweisungen oder Zahlungen",
        3 to "Keine Weitergabe von Passwörtern, PINs oder TANs (gesicherte lokale Anmeldung bleibt möglich)",
        5 to "Keine Aufzeichnung oder Auswertung geschützter Bildschirme",
        6 to "Keine eigenmächtigen Systemrechte, App-Installationen oder Löschung fremder Daten",
        7 to "Keine mehrdeutigen Klicks und keine blinde Wiederholung unbestätigter Aktionen"
    )

    val otherConditions = linkedMapOf(
        1 to "Echtgeldorders: aktuell nicht implementiert/freigegeben. Eine spätere Handelsfunktion braucht eine gesonderte technische Freigabe je konkreter Aktion.",
        4 to "Gerätesperre: keine Umgehung. Der Besitzer darf die vorhandene sichere lokale Anmeldung verwenden.",
        8 to "Externe KI: per App bewusst freigebbar; keine Übertragung privater Konto- oder Zugangsdaten ohne entsprechende Berechtigung."
    )
}
