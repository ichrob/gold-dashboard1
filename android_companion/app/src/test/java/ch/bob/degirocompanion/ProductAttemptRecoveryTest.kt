package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductAttemptRecoveryTest {
    private val isin="DE000FD0S0G4"
    private val header=listOf(
        MorningReadPolicy.Node("12345678 • Societe Generale OTC | R"),
        MorningReadPolicy.Node("Übersicht"),
        MorningReadPolicy.Node("SG Gold Turbo Unlimited Mini Call BAR 3900 BP 3800 Bv 10 LV 20"),
        MorningReadPolicy.Node("Order platzieren",clickable=true))
    private val footer=listOf("Übersicht","Notizen","Notiz hinzufügen").map { MorningReadPolicy.Node(it) }+
        MorningReadPolicy.Node("Order platzieren",clickable=true)
    @Test fun oldNumericPageCannotStartNextAttemptBeforeExactResultIsOpened() {
        assertEquals(MorningReadPolicy.Kind.BACK,
            MorningReadPolicy.detailDecision(header,isin,true,resultOpened=false).kind)
        assertEquals(MorningReadPolicy.Kind.READ,
            MorningReadPolicy.detailDecision(header,isin,true,resultOpened=true).kind)
    }
    @Test fun knownFooterCanReturnOnceAfterFailedReadButUnknownWindowCannot() {
        assertTrue(MorningReadPolicy.returnAfterRead(footer,isin,7,7,"RETURN_FAILED"))
        assertTrue(MorningReadPolicy.returnAfterRead(footer,isin,7,7,"SEEK_LIMIT"))
        assertFalse(MorningReadPolicy.returnAfterRead(footer,isin,7,null,"SEEK_LIMIT"))
        assertFalse(MorningReadPolicy.returnAfterRead(footer,isin,8,7,"RETURN_FAILED"))
        assertFalse(MorningReadPolicy.returnAfterRead(footer,isin,7,7,"IDENTITY_CHANGED"))
        assertFalse(MorningReadPolicy.returnAfterRead(footer,isin,7,7,"UNSAFE_VIEW"))
        // The same footer is still not allowed to initiate a product read.
        assertEquals(MorningReadPolicy.Kind.BLOCK,
            MorningReadPolicy.detailDecision(footer,isin,true,resultOpened=false).kind)
    }
    @Test fun recoveryNeverLeavesOrClicksAnOrderLoginOrChangedProduct() {
        for(extra in listOf(MorningReadPolicy.Node("Order bestätigen"),
            MorningReadPolicy.Node("Limitpreis"),MorningReadPolicy.Node("Passwort"),
            MorningReadPolicy.Node("",editable=true),MorningReadPolicy.Node("",sensitive=true),
            MorningReadPolicy.Node("DE000FE2JJ20"))) {
            assertFalse(MorningReadPolicy.returnAfterRead(footer+extra,isin,7,7,"RETURN_FAILED"))
        }
        assertFalse(MorningReadPolicy.returnAfterRead(header+MorningReadPolicy.Node("Order bestätigen"),isin,7,7,"READ"))
    }
}
