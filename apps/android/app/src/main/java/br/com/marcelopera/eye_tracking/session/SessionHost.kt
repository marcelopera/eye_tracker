package br.com.marcelopera.eye_tracking.session

import br.com.marcelopera.eye_tracking.data.SessionEvent
data class TargetDisplay(
    val frameTimeNanos: Long,
    val width: Int,
    val height: Int,
    val screenX: Double = Double.NaN,
    val screenY: Double = Double.NaN,
    val committed: Boolean = false,
)

sealed interface VideoPlayback {
    data class Finished(
        val endFrameNanos: Long,
    ) : VideoPlayback

    data class Failed(
        val what: Int,
        val extra: Int,
    ) : VideoPlayback
}

interface SessionHost {
    fun telemetry(): List<SessionEvent> = emptyList()
    suspend fun showPreparing()
    suspend fun showMarker(flashOn: Boolean): Long
    suspend fun showTarget(x: Double, y: Double): TargetDisplay
    suspend fun showRest(): Long
    suspend fun playVideo(uri: String, onStarted: (Long) -> Unit): VideoPlayback
    suspend fun showFinalizing()
}
