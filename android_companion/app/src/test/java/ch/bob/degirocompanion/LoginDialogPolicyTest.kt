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
}
