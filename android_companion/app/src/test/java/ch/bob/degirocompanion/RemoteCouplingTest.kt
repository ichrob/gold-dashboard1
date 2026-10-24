package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test
import java.util.Base64
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class RemoteCouplingTest {
    private val events = mutableListOf<RemoteAuditEvent>()
    private fun engine() = RemoteCoupling({ event, _ -> events.add(event) })
    private fun sign(invite: String, task: String, nonce: String, timestamp: Long): String {
        val parts = invite.split('|')
        val key = Base64.getUrlDecoder().decode(parts[2])
        val payload = listOf("BOB-FERN/1", parts[1], timestamp.toString(), nonce, task).joinToString("|")
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return payload + "|" +
            Base64.getUrlEncoder().withoutPadding().encodeToString(
                mac.doFinal(payload.toByteArray(Charsets.UTF_8)))
    }
    private val nonce = "abcdefghijklmnopqrstuv"
    private val now = 1_782_000_000_000L

    @Test fun defaultClosedAndPairedOnlyOnExplicitRequest() {
        val x = engine()
        assertFalse(x.isActive(200))
        assertNull(x.receive("anything", 200, now))
        val invite = x.pair(1000)
        assertTrue(invite.startsWith("BOB-FERN-KOPPLUNG/1|"))
        assertEquals(3, invite.split('|').size)
        assertTrue(x.isActive(1001))
    }

    @Test fun validSignedProposalStillRequiresVisibleTapAndIsOneShot() {
        val x = engine()
        val invite = x.pair(1_000L)
        val frame = sign(invite, "OPEN_PRODUCTS", nonce, now)
        assertEquals(PhoneTask.OPEN_PRODUCTS, x.receive(frame, 2_000, now))
        assertTrue(x.consume(PhoneTask.OPEN_PRODUCTS, 2_001))
        assertFalse(x.consume(PhoneTask.OPEN_PRODUCTS, 2_002))
        assertNull(x.receive(frame, 2_003, now))
        assertTrue(events.contains(RemoteAuditEvent.REPLAY))
    }

    @Test fun blockedBrokerActionsEvenWithValidMac() {
        val x = engine()
        val invite = x.pair(1_000)
        for (action in listOf("OPEN_SETTINGS", "PICK_IMAGES", "BUY_GOLD",
                "DEGIRO_LOGIN", "PLACE_ORDER", "OPEN_PRODUCTS;BUY")) {
            val frame = sign(invite, action, nonce, now)
            assertNull(x.receive(frame, 2_000, now))
            assertFalse(x.consume(PhoneTask.OPEN_PRODUCTS, 2_001))
        }
    }

    @Test fun tamperingStalenessAndWrongSessionAreRejected() {
        val x = engine()
        val invite = x.pair(1_000)
        val valid = sign(invite, "OPEN_BOB", nonce, now)
        assertNull(x.receive(valid.replace("OPEN_BOB", "OPEN_TRADE"), 1_001, now))
        assertNull(x.receive(valid, 1_002, now + 121_000))
        assertNull(x.receive(valid.replace(Regex("\\|[A-Za-z0-9_-]{12}\\|"),
            "|ZZZZZZZZZZZZ|"), 1_003, now))
        assertFalse(x.consume(PhoneTask.OPEN_BOB, 1_004))
    }

    @Test fun stopRevokeAndExpirationDestroyPermissions() {
        val x = engine()
        var invite = x.pair(1_000)
        var frame = sign(invite, "OPEN_MARKET", nonce, now)
        assertEquals(PhoneTask.OPEN_MARKET, x.receive(frame, 1_001, now))
        x.stopped()
        assertFalse(x.consume(PhoneTask.OPEN_MARKET, 1_002))
        assertNull(x.receive(frame, 1_003, now))
        invite = x.pair(2_000)
        frame = sign(invite, "OPEN_MARKET", nonce, now)
        x.revoke()
        assertNull(x.receive(frame, 2_001, now))
        invite = x.pair(3_000)
        frame = sign(invite, "OPEN_MARKET", nonce, now)
        assertFalse(x.isActive(3_000 + 30L * 60_000L))
        assertNull(x.receive(frame, 3_001 + 30L * 60_000L, now))
    }

    @Test fun approvalExpiresAndAppLeavingCancelsIt() {
        val x = engine()
        val invite = x.pair(10_000)
        assertEquals(PhoneTask.OPEN_PRODUCTS, x.receive(
            sign(invite, "OPEN_PRODUCTS", nonce, now), 10_001, now))
        assertFalse(x.consume(PhoneTask.OPEN_PRODUCTS, 70_001))
        val second = sign(invite, "OPEN_PRODUCTS", "zbcdefghijklmnopqrstuv", now)
        assertEquals(PhoneTask.OPEN_PRODUCTS, x.receive(second, 70_002, now))
        x.discardPending()
        assertFalse(x.consume(PhoneTask.OPEN_PRODUCTS, 70_003))
    }

    @Test fun newPairingInvalidatesOldSessionAndHasNoCrossSessionReplay() {
        val x = engine()
        val old = x.pair(100)
        val request = sign(old, "OPEN_TRADE", nonce, now)
        x.pair(200)
        assertNull(x.receive(request, 201, now))
    }
}
