package br.com.marcelopera.eye_tracking.session

enum class SessionPhase {
    Idle,
    AwaitingPermission,
    PreparingCamera,
    MarkerA,
    Calibration,
    Rest,
    Stimulus,
    Validation,
    MarkerB,
    Finalizing,
    Completed,
}

data class SessionConfig(
    val experimentId: String,
    val videoUri: String,
)

enum class FailureReason {
    CameraUnavailable,
    Recording,
    Video,
    Persistence,
}

sealed interface SessionResult {
    val sessionId: String?

    data class Completed(override val sessionId: String) : SessionResult
    data class Failed(
        override val sessionId: String?,
        val reason: FailureReason,
    ) : SessionResult
    data class Interrupted(override val sessionId: String?) : SessionResult
}
