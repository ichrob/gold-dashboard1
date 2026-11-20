package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class LocalResearchOwnerLoginPolicyTest {
    private fun node(s:String)=MorningReadPolicy.Node(s)

    @Test fun ownerPinOrPasswordScreenMayOnlyPauseRead() {
        assertTrue(LocalResearchOwnerLoginPolicy.visible(listOf(node("PIN eingeben"))))
        assertTrue(LocalResearchOwnerLoginPolicy.visible(listOf(
            node("Anmelden"),MorningReadPolicy.Node("",editable=true,password=true))))
        assertTrue(LocalResearchOwnerLoginPolicy.visible(listOf(
            node("Login"),node("Passwort"))))
        assertTrue(LocalResearchOwnerLoginPolicy.visible(listOf(
            node("Einloggen"),MorningReadPolicy.Node("",editable=true,sensitive=true))))
    }

    @Test fun productSearchMustNeverBeClassifiedAsLogin() {
        val product=listOf(node("Märkte"),node("Hebelprodukte"),
            node("Top Ergebnisse"),MorningReadPolicy.Node("Gold",editable=true,hint="Suche"),
            node("SG GOLD Turbo Mini Call DE000FB0A490"),
            node("Order platzieren"),node("Anmelden"))
        assertFalse(LocalResearchOwnerLoginPolicy.visible(product))
        assertFalse(LocalResearchOwnerLoginPolicy.visible(listOf(node("Anmelden"))))
        assertFalse(LocalResearchOwnerLoginPolicy.visible(listOf(node("Order platzieren"))))
        assertFalse(LocalResearchOwnerLoginPolicy.visible(emptyList()))
    }

    @Test fun actualOrderFormsNeverBecomeOwnerLoginWait() {
        val pin=listOf(node("PIN eingeben"))
        for(label in listOf("Order bestätigen","Orderart","Ordertyp",
                "Limitpreis","Stückzahl","Anzahl kaufen","Orderdetails",
                "Orderübersicht","Orderzusammenfassung"))
            assertFalse("Order field $label",LocalResearchOwnerLoginPolicy.visible(
                pin+node(label)))
    }

    @Test fun noLoginInputIsEverAnActionOrATicket() {
        val login=listOf(MorningReadPolicy.Node("",password=true),
            node("Anmelden"))
        assertTrue(LocalResearchOwnerLoginPolicy.visible(login))
        assertFalse(LocalResearchOwnerLoginPolicy.visible(listOf(
            MorningReadPolicy.Node("",password=true))))
    }
}
