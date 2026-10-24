package ch.bob.degirocompanion

import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Offline, authenticated remote handoff. NOT unattended remote control.
 * Only the owner starts a session and taps to approve each on-device action.
 * This class has no network, accessibility or broker access.
 * Secrets, pending commands and replay cache are volatile, never persisted.
 */
internal class RemoteCoupling(
    private val audit: (RemoteAuditEvent, PhoneTask?) -> Unit,
    private val random: SecureRandom = SecureRandom(),
    private val sessionTtlMs: Long = 30 * 60 * 1000L,
    private val proposalTtlMs: Long = 60 * 1000L
) {
    companion object {
        private const val VERSION = "BOB-FERN/1"
        private const val INVITE = "BOB-FERN-KOPPLUNG/1"
        private val SAFE = setOf(
            PhoneTask.OPEN_BOB, PhoneTask.OPEN_PRODUCTS,
            PhoneTask.OPEN_LONG_REVIEW, PhoneTask.OPEN_LEVERAGE_REVIEW,
            PhoneTask.OPEN_TRADE, PhoneTask.OPEN_SIMULATION, PhoneTask.OPEN_LEARNING,
            PhoneTask.OPEN_RESEARCH, PhoneTask.OPEN_MARKET
        )
        private val ID = Regex("[A-Za-z0-9_-]{12}")
        private val NONCE = Regex("[A-Za-z0-9_-]{16,32}")
        private val MAC = Regex("[A-Za-z0-9_-]{43}")
    }

    private var secret: ByteArray? = null
    private var sessionId: String? = null
    private var startedAt: Long? = null
    private var pending: Pair<PhoneTask, Long>? = null
    private val seenNonces = mutableSetOf<String>()

    private fun b64(input: ByteArray): String =
        Base64.getUrlEncoder().withoutPadding().encodeToString(input)

    /** A new session invalidates the previous secret and all proposals. */
    fun pair(nowElapsedMs: Long): String {
        revokeSilently()
        val key = ByteArray(32).also(random::nextBytes)
        val id = ByteArray(9).also(random::nextBytes)
        secret = key
        sessionId = b64(id)
        startedAt = nowElapsedMs
        audit(RemoteAuditEvent.PAIRED, null)
        // Capability secret: share only after a deliberate user action.
        return INVITE + "|" + sessionId + "|" + b64(key)
    }

    fun isActive(nowElapsedMs: Long): Boolean = ensureActive(nowElapsedMs)

    private fun ensureActive(nowElapsedMs: Long): Boolean {
        val started = startedAt ?: return false
        if (secret == null || nowElapsedMs < started ||
            nowElapsedMs - started >= sessionTtlMs) {
            revokeSilently()
            audit(RemoteAuditEvent.EXPIRED, null)
            return false
        }
        return true
    }

    /**
     * BOB-FERN/1|session|unix-ms|nonce|OPEN_PRODUCTS|base64url-hmac
     * Timestamp <=2 min old, nonce single use, exact HMAC, fixed safe actions.
     */
    fun receive(raw: String, nowElapsedMs: Long, nowWallMs: Long): PhoneTask? {
        pending = null
        if (!ensureActive(nowElapsedMs)) {
            audit(RemoteAuditEvent.REJECTED, null)
            return null
        }
        if (raw.length !in 90..220 || raw.any { it.isWhitespace() }) {
            audit(RemoteAuditEvent.REJECTED, null)
            return null
        }
        val parts = raw.split('|')
        if (parts.size != 6 || parts[0] != VERSION || parts[1] != sessionId ||
            !NONCE.matches(parts[3]) || !MAC.matches(parts[5]) ||
            !ID.matches(parts[1])) {
            audit(RemoteAuditEvent.REJECTED, null)
            return null
        }
        val timestamp = parts[2].toLongOrNull()
        if (timestamp == null || timestamp < 1 || nowWallMs < 1 ||
            timestamp > nowWallMs + 30_000L ||
            nowWallMs - timestamp > 120_000L) {
            audit(RemoteAuditEvent.REJECTED, null)
            return null
        }
        val task = SAFE.firstOrNull { it.name == parts[4] }
        if (task == null || parts[3] in seenNonces) {
            audit(if (parts[3] in seenNonces) RemoteAuditEvent.REPLAY
                else RemoteAuditEvent.REJECTED, null)
            return null
        }
        val signedMessage = parts.take(5).joinToString("|")
        val expected = signBytes(secret!!, signedMessage)
        val supplied = try {
            Base64.getUrlDecoder().decode(parts[5])
        } catch (_: IllegalArgumentException) {
            audit(RemoteAuditEvent.REJECTED, null)
            return null
        }
        if (!MessageDigest.isEqual(expected, supplied)) {
            audit(RemoteAuditEvent.REJECTED, null)
            return null
        }
        seenNonces.add(parts[3])
        pending = task to nowElapsedMs
        audit(RemoteAuditEvent.PREVIEWED, task)
        return task
    }

    /** ONLY call from the visible, explicit approval button on the device. */
    fun consume(task: PhoneTask?, nowElapsedMs: Long): Boolean {
        val proposal = pending
        pending = null
        val valid = ensureActive(nowElapsedMs) && proposal != null &&
            task != null && task in SAFE && proposal.first == task &&
            nowElapsedMs >= proposal.second &&
            nowElapsedMs - proposal.second < proposalTtlMs
        audit(if (valid) RemoteAuditEvent.APPROVED else RemoteAuditEvent.REJECTED, task)
        return valid
    }

    fun discardPending() {
        if (pending != null) audit(RemoteAuditEvent.DISCARDED, pending?.first)
        pending = null
    }

    fun stopped() {
        revokeSilently()
        audit(RemoteAuditEvent.STOPPED, null)
    }

    fun revoke() {
        revokeSilently()
        audit(RemoteAuditEvent.REVOKED, null)
    }

    private fun revokeSilently() {
        secret?.fill(0)
        secret = null
        sessionId = null
        startedAt = null
        pending = null
        seenNonces.clear()
    }

    fun recordLaunchResult(task: PhoneTask, launched: Boolean) {
        audit(if (launched) RemoteAuditEvent.LAUNCHED_NOT_VERIFIED
            else RemoteAuditEvent.LAUNCH_FAILED, task)
    }

    private fun signBytes(key: ByteArray, message: String): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return mac.doFinal(message.toByteArray(Charsets.UTF_8))
    }
}

internal enum class RemoteAuditEvent {
    PAIRED, PREVIEWED, APPROVED, LAUNCHED_NOT_VERIFIED, LAUNCH_FAILED,
    REJECTED, REPLAY, DISCARDED, EXPIRED, STOPPED, REVOKED
}
