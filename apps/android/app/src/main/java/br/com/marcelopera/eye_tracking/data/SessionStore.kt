package br.com.marcelopera.eye_tracking.data

import java.io.File

data class SessionHandle(
    val sessionId: String,
    val directory: File,
)

data class SessionEvent(
    val name: String,
    val timeNanos: Long,
    val clock: String,
    val data: String? = null,
)

interface SessionStore {
    suspend fun createSession(experimentId: String): SessionHandle?
    suspend fun save(
        handle: SessionHandle,
        experimentId: String,
        completed: Boolean,
        events: List<SessionEvent>,
    ): Boolean
}
