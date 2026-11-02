package br.com.marcelopera.eye_tracking.session

import br.com.marcelopera.eye_tracking.data.SessionEvent
import java.io.File

data class FinalizeInfo(
    val hasError: Boolean,
    val errorCode: Int,
)

interface Recording {
    suspend fun awaitStart(): Boolean
    suspend fun stopAndAwaitFinalize(): FinalizeInfo
    fun unbind()
    fun telemetry(): List<SessionEvent> = emptyList()
}

fun interface RecordingEngine {
    fun start(outputFile: File): Recording
}

fun interface RecordingEngineFactory {
    fun create(): RecordingEngine
}
