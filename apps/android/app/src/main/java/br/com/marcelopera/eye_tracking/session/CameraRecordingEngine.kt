package br.com.marcelopera.eye_tracking.session

import android.content.Context
import androidx.camera.core.CameraSelector
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Recorder
import androidx.camera.video.Recording as CameraXRecording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import kotlinx.coroutines.CompletableDeferred
import java.io.File

class CameraRecordingEngine(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
) : RecordingEngine {

    override fun start(outputFile: File): Recording {
        val handle = CameraRecording()
        val providerFuture = ProcessCameraProvider.getInstance(context)
        providerFuture.addListener({
            try {
                val provider = providerFuture.get()
                handle.provider = provider
                val recorder = Recorder.Builder().build()
                val capture = VideoCapture.withOutput(recorder)
                provider.unbindAll()
                provider.bindToLifecycle(
                    lifecycleOwner,
                    CameraSelector.DEFAULT_FRONT_CAMERA,
                    capture,
                )
                if (handle.unbindRequested) {
                    provider.unbindAll()
                    return@addListener
                }

                val options = FileOutputOptions.Builder(outputFile).build()
                val activeRecording = recorder
                    .prepareRecording(context, options)
                    .start(ContextCompat.getMainExecutor(context)) { event ->
                        when (event) {
                            is VideoRecordEvent.Start -> {
                                handle.startSignal.complete(true)
                                if (handle.stopRequested) handle.requestStop()
                            }

                            is VideoRecordEvent.Finalize -> {
                                if (!handle.startSignal.isCompleted) {
                                    handle.startSignal.complete(false)
                                }
                                handle.finalizeSignal.complete(
                                    FinalizeInfo(event.hasError(), event.error),
                                )
                            }

                            else -> Unit
                        }
                    }
                handle.recording = activeRecording
                if (handle.stopRequested) handle.requestStop()
            } catch (error: Throwable) {
                if (!handle.startSignal.isCompleted) handle.startSignal.complete(false)
                if (!handle.finalizeSignal.isCompleted) {
                    handle.finalizeSignal.complete(FinalizeInfo(true, FINALIZE_ERROR_UNKNOWN))
                }
            }
        }, ContextCompat.getMainExecutor(context))
        return handle
    }

    private class CameraRecording : Recording {
        val startSignal = CompletableDeferred<Boolean>()
        val finalizeSignal = CompletableDeferred<FinalizeInfo>()
        var recording: CameraXRecording? = null
        var provider: ProcessCameraProvider? = null
        var stopRequested = false
        var unbindRequested = false
        private var stopIssued = false

        fun requestStop() {
            stopRequested = true
            val active = recording ?: return
            if (stopIssued) return
            stopIssued = true
            active.stop()
        }

        override suspend fun awaitStart(): Boolean = startSignal.await()

        override suspend fun stopAndAwaitFinalize(): FinalizeInfo {
            requestStop()
            return finalizeSignal.await()
        }

        override fun unbind() {
            unbindRequested = true
            provider?.unbindAll()
            provider = null
        }
    }

    private companion object {
        const val FINALIZE_ERROR_UNKNOWN = -1
    }
}
