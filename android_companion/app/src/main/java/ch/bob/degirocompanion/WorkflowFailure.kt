package ch.bob.degirocompanion

internal object WorkflowFailure {
    fun code(reason: String): String = when {
        reason == "Gestoppt" -> "USER_STOP"
        reason.contains("Bildschirm gesperrt",true) -> "SCREEN_LOCKED"
        reason.contains("eigene Bildschirmbedienung",true) -> "USER_INTERRUPTED"
        reason.contains("andere App",true) -> "APP_CHANGED"
        reason.contains("geschützte Ansicht",true) -> "PROTECTED_VIEW"
        reason.contains("Verbindungsfehler",true) -> "CONNECTION_ERROR"
        reason.contains("Zeitlimit",true) || reason == "Sitzung beendet" -> "TIMEOUT"
        reason.contains("mehrdeutig",true) -> "AMBIGUOUS_TARGET"
        reason.contains("Aktion abgelehnt",true) -> "ACTION_REJECTED"
        reason.contains("Dienst",true) -> "SERVICE_INTERRUPTED"
        reason.contains("Lokal kein passender Ablauf") -> "NO_LOCAL_PLAN"
        reason.contains("KI",true) -> "AI_UNCONFIRMED"
        reason.contains("stabiler",true) -> "SCREEN_UNSTABLE"
        else -> "OTHER"
    }
}
