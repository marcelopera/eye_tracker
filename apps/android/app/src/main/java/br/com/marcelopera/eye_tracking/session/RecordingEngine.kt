package br.com.marcelopera.eye_tracking.session

import java.io.File

data class FinalizeInfo(
    val hasError: Boolean,
    val errorCode: Int,
)

interface Recording {
    suspend fun awaitStart(): Boolean
    suspend fun stopAndAwaitFinalize(): FinalizeInfo
    fun unbind()
}

fun interface RecordingEngine {
    fun start(outputFile: File): Recording
}

fun interface RecordingEngineFactory {
    fun create(): RecordingEngine
}
