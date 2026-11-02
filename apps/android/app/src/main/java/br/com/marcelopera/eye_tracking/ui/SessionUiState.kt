package br.com.marcelopera.eye_tracking.ui

import br.com.marcelopera.eye_tracking.session.FailureReason
import br.com.marcelopera.eye_tracking.session.SessionConfig
import br.com.marcelopera.eye_tracking.session.SessionPhase

enum class Destination {
    Identification,
    Preparation,
    Collecting,
    Completed,
}

enum class PreparationNotice {
    VideoRequired,
    VideoAccessLost,
    CameraPermissionDenied,
    Interrupted,
    CameraUnavailable,
    RecordingFailed,
    VideoFailed,
    PersistenceFailed,
}

data class SessionUiState(
    val destination: Destination = Destination.Identification,
    val experimentInput: String = "",
    val experimentId: String? = null,
    val videoUri: String? = null,
    val phase: SessionPhase = SessionPhase.Idle,
    val sessionId: String? = null,
    val notice: PreparationNotice? = null,
    val idError: Boolean = false,
)

sealed interface SessionEffect {
    data object CheckCameraPermission : SessionEffect
    data class StartSession(
        val token: Long,
        val config: SessionConfig,
    ) : SessionEffect
}

internal fun FailureReason.toNotice(): PreparationNotice = when (this) {
    FailureReason.CameraUnavailable -> PreparationNotice.CameraUnavailable
    FailureReason.Recording -> PreparationNotice.RecordingFailed
    FailureReason.Video -> PreparationNotice.VideoFailed
    FailureReason.Persistence -> PreparationNotice.PersistenceFailed
}
