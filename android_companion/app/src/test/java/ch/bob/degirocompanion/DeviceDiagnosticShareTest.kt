package ch.bob.degirocompanion

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceDiagnosticShareTest {
    @Test fun onlyFixedCodesAndCountsAppear() {
        val report = DeviceDiagnosticShare.report(
            "0.10-safe", DeviceDiagnosticShare.Outcome.STARTED_NOT_VERIFIED,
            DeviceDiagnosticShare.Outcome.RECOGNIZED,
            DeviceDiagnosticShare.Outcome.REJECTED, 4, 2
        )
        assertTrue(report.contains("Version: 0.10-safe"))
        assertTrue(report.contains("Handy-Auftrag: STARTED_NOT_VERIFIED"))
        assertTrue(report.contains("Sprache: RECOGNIZED"))
        assertTrue(report.contains("Lokale Bildserie: REJECTED"))
        assertTrue(report.contains("Bilder: 4"))
        assertTrue(report.contains("Schritte: 2"))
        assertTrue(report.contains("Keine automatische Übertragung"))
        assertFalse(report.contains("password="))
    }

    @Test fun versionInjectionAndCountsCannotLeakOrMislead() {
        val report = DeviceDiagnosticShare.report(
            "0.10\\nISIN: CH0000000000, passwort=xyz",
            DeviceDiagnosticShare.Outcome.NOT_TESTED,
            DeviceDiagnosticShare.Outcome.NOT_TESTED,
            DeviceDiagnosticShare.Outcome.NOT_TESTED, 999, -300
        )
        assertTrue(report.contains("Version: unknown"))
        assertTrue(report.contains("Bilder: 0"))
        assertTrue(report.contains("Schritte: 0"))
        assertFalse(report.contains("CH0000000000"))
        assertFalse(report.contains("xyz"))
    }
}
