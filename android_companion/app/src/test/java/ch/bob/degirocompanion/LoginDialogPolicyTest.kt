package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class LoginDialogPolicyTest {
    private val offer = setOf(LoginDialogPolicy.OFFER, LoginDialogPolicy.BODY, "Abbrechen", "Bestätigen")
    private val notice = setOf(LoginDialogPolicy.NOTICE, "Schließen")
    private val fingerprint = setOf("DEGIRO", "Fingerabdruck scannen", "Cancel")
    @Test fun knownDialogsRequireTheCorrectPhaseAndFullMarkers() {
        assertEquals(LoginDialogPolicy.Kind.NOTICE, LoginDialogPolicy.identify(true, false, true, notice, false))
        assertNull(LoginDialogPolicy.identify(true, false, true, notice, true))
        assertEquals(LoginDialogPolicy.Kind.OFFER, LoginDialogPolicy.identify(true, false, true, offer, true))
        assertNull(LoginDialogPolicy.identify(true, false, true, offer, false))
        for (label in offer) assertNull(LoginDialogPolicy.identify(true, false, true, offer - label, true))
        assertNull(LoginDialogPolicy.identify(false, false, true, offer, true))
        assertNull(LoginDialogPolicy.identify(true, false, true, setOf("Abbrechen"), true))
        assertNull(LoginDialogPolicy.identify(true, false, true, offer + "Cancel", true))
    }
    @Test fun fingerprintRequiresSystemOwnershipAndDegiroAssociation() {
        assertEquals(LoginDialogPolicy.Kind.FINGERPRINT, LoginDialogPolicy.identify(false, true, true, fingerprint, false))
        assertNull(LoginDialogPolicy.identify(false, false, true, fingerprint, false))
        assertNull(LoginDialogPolicy.identify(false, true, false, fingerprint, false))
        assertNull(LoginDialogPolicy.identify(false, true, true, fingerprint - "DEGIRO", false))
        assertNull(LoginDialogPolicy.identify(false, true, true, fingerprint, true))
        assertNull(LoginDialogPolicy.identify(false, true, true, setOf("DEGIRO", "Cancel"), false))
    }
    @Test fun stableObservationRequiresTimeAndResetsWhenTargetMoves() {
        val b = LoginDialogBudget()
        assertFalse(b.stable("a", 0)); assertFalse(b.stable("a", 1000)); assertTrue(b.stable("a", 2000))
        assertFalse(b.stable("b", 3000)); assertFalse(b.stable("b", 4000)); assertTrue(b.stable("b", 5000))
        b.resetObservation(); assertFalse(b.stable("b", 6000))
    }
    @Test fun acceptedActionNeverGrantsRetryOrDisappearanceProof() {
        val b = LoginDialogBudget()
        assertTrue(b.reserve(LoginDialogPolicy.Kind.FINGERPRINT, 1000))
        assertFalse(b.reserve(LoginDialogPolicy.Kind.NOTICE, 2000))
        assertFalse(b.expired(6999)); assertTrue(b.expired(7000))
        b.gone(); assertFalse(b.expired(8000))
        assertFalse(b.reserve(LoginDialogPolicy.Kind.FINGERPRINT, 8000))
        assertTrue(b.reserve(LoginDialogPolicy.Kind.NOTICE, 8000))
        b.gone(); assertTrue(b.reserve(LoginDialogPolicy.Kind.OFFER, 10000))
        b.gone(); assertFalse(b.reserve(LoginDialogPolicy.Kind.OFFER, 11000))
    }
    @Test fun normalizationOnlyCollapsesWhitespace() {
        assertEquals("TouchID / FaceID aktivieren", LoginDialogPolicy.normalize(" TouchID / FaceID\n aktivieren "))
        assertNotEquals("Abbrechen", LoginDialogPolicy.normalize("Bestätigen"))
    }
    @Test fun diagnosticKeepsAllMissingMarkersWithoutRetainingLabels() {
        val labels = setOf("Cancel", "Fingerabdruck scannen", "synthetic private text")
        val check = LoginDialogCheck.markersRejected(LoginDialogCheck.Owner.SAMSUNG_BIOMETRICS,
            false, true, false, labels)
        assertEquals(LoginDialogCheck.Stage.MARKER_CHECK, check.stage)
        assertEquals(LoginDialogCheck.Phase.BEFORE_PIN, check.phase)
        assertTrue(check.systemVerified); assertFalse(check.degiroContext); assertFalse(check.degiroLabel)
        assertTrue(check.biometricLabel); assertTrue(check.cancelLabel); assertFalse(check.cancelAmbiguous)
        assertFalse(check.toString().contains("synthetic private text"))
        assertFalse(check.toString().contains("Fingerabdruck scannen"))
        assertNull(LoginDialogPolicy.identify(false, true, false, labels, false))
    }
    @Test fun diagnosticDistinguishesOwnerFailureFromUnqueriedMarkersAndAmbiguity() {
        val owner = LoginDialogCheck.ownerRejected(LoginDialogCheck.Owner.OTHER, true)
        assertEquals(LoginDialogCheck.Stage.OWNER_CHECK, owner.stage)
        assertEquals(LoginDialogCheck.Phase.AFTER_PIN, owner.phase)
        assertFalse(owner.systemVerified); assertFalse(owner.degiroContext); assertFalse(owner.degiroLabel)
        assertFalse(owner.biometricLabel); assertFalse(owner.cancelLabel); assertFalse(owner.cancelAmbiguous)
        val ambiguous = LoginDialogCheck.markersRejected(LoginDialogCheck.Owner.SYSTEM_UI,
            false, true, true, fingerprint + "Abbrechen")
        assertTrue(ambiguous.cancelAmbiguous); assertFalse(ambiguous.cancelLabel)
        assertNull(LoginDialogPolicy.identify(false, true, true, fingerprint + "Abbrechen", false))
    }
    @Test fun observedSamsungPromptUsesItsVisibleDegiroLabelWithoutBackgroundWindow() {
        val owner = LoginDialogCheck.Owner.SAMSUNG_BIOMETRICS
        val diagnostic = LoginDialogCheck.markersRejected(owner, false, true, false, fingerprint)
        assertTrue(diagnostic.systemVerified); assertFalse(diagnostic.degiroContext)
        assertTrue(diagnostic.degiroLabel); assertTrue(diagnostic.biometricLabel)
        assertTrue(diagnostic.cancelLabel); assertFalse(diagnostic.cancelAmbiguous)
        assertEquals(LoginDialogPolicy.Kind.FINGERPRINT,
            LoginDialogPolicy.identify(false, true, false, fingerprint, false, owner))
    }
    @Test fun samsungVisibleContextStillRequiresEveryMarkerOwnerAndPreEntryPhase() {
        val samsung = LoginDialogCheck.Owner.SAMSUNG_BIOMETRICS
        for (owner in listOf(null, LoginDialogCheck.Owner.SYSTEM_UI, LoginDialogCheck.Owner.DEGIRO, LoginDialogCheck.Owner.OTHER))
            assertNull(LoginDialogPolicy.identify(false, true, false, fingerprint, false, owner))
        assertNull(LoginDialogPolicy.identify(false, false, false, fingerprint, false, samsung))
        assertNull(LoginDialogPolicy.identify(false, true, false, fingerprint, true, samsung))
        for (label in fingerprint)
            assertNull(LoginDialogPolicy.identify(false, true, false, fingerprint - label, false, samsung))
        assertNull(LoginDialogPolicy.identify(false, true, false, fingerprint + "Abbrechen", false, samsung))
        assertNull(LoginDialogPolicy.identify(false, true, false, (fingerprint - "Cancel") + "Cancel order", false, samsung))
        assertNull(LoginDialogPolicy.identify(false, true, false, (fingerprint - "DEGIRO") + "Other app", false, samsung))
        assertNull(LoginDialogPolicy.identify(false, true, false, (fingerprint - "Cancel") + "Bestätigen", false, samsung))
    }
}
