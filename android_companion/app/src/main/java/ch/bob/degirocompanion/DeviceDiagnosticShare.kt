package ch.bob.degirocompanion

/**
 * A deliberately shared, ephemeral and privacy-minimal support note.
 * Never accepts transcripts, OCR payloads, account identifiers, ISINs,
 * image URIs, screenshots, clipboard content or credentials.
 * No network operation, persistence or automated sharing.
 */
internal object DeviceDiagnosticShare {
    enum class Outcome {
        NOT_TESTED, STARTED_NOT_VERIFIED, RECOGNIZED, REJECTED, FAILED, STOPPED, UNAVAILABLE
    }

    fun report(
        version: String,
        command: Outcome,
        voice: Outcome,
        images: Outcome,
        lastImageCount: Int,
        pendingSteps: Int
    ): String {
        val safeVersion = version.takeIf {
            it.length in 1..32 && Regex("[A-Za-z0-9._-]+").matches(it)
        } ?: "unknown"
        val safeImages = lastImageCount.takeIf { it in 0..4 } ?: 0
        val safeSteps = pendingSteps.takeIf { it in 0..5 } ?: 0
        return listOf(
            "BOB ANDROID – DIAGNOSE (NUR AUF EIGENEN WUNSCH GETEILT)",
            "Version: " + safeVersion,
            "Handy-Auftrag: " + command.name,
            "Sprache: " + voice.name,
            "Lokale Bildserie: " + images.name,
            "Anzahl zuletzt gewählter Bilder: " + safeImages,
            "Noch nicht ausgeführte, bestätigungspflichtige Schritte: " + safeSteps,
            "STARTED_NOT_VERIFIED bedeutet nur Android-Aktion angestoßen, nicht Browser-Erfolg.",
            "Keine Sprache, Bildinhalte, ISIN, Preise, Logins, Kontodaten oder Orderdaten enthalten.",
            "Keine automatische Übertragung, Fernsteuerung oder Handelsfreigabe."
        ).joinToString("\n")
    }
}
