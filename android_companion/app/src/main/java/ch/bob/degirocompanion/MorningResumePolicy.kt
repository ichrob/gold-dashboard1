package ch.bob.degirocompanion

/** A new local Start may continue a recent interrupted read, never an old run or login attempt. */
internal object MorningResumePolicy {
    fun eligible(ageMillis: Long, resumes: Int, code: String): Boolean =
        ageMillis in 0..900_000 && resumes in 0..1 && code in setOf(
            "READ_TIMEOUT", "RUN_TIMEOUT", "SERVICE_INTERRUPTED", "SCREEN_LOCKED", "RETURN_FAILED")
}
