package br.com.marcelopera.eye_tracking.session

import android.os.SystemClock
import br.com.marcelopera.eye_tracking.data.SessionEvent
import br.com.marcelopera.eye_tracking.data.SessionHandle
import br.com.marcelopera.eye_tracking.data.SessionStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.io.File

class SessionController(
    private val store: SessionStore,
    private val listener: Listener,
    private val recordingEngines: RecordingEngineFactory,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate),
    private val timeSource: () -> Long = { SystemClock.elapsedRealtimeNanos() },
) {
    interface Listener {
        fun onPhase(token: Long, phase: SessionPhase)
        fun onFinished(token: Long, result: SessionResult)
    }

    private var host: SessionHost? = null
    private var active: ActiveSession? = null
    private var setupJob: Job? = null
    private var protocolJob: Job? = null

    val isActive: Boolean
        get() = active != null

    fun attachHost(host: SessionHost) {
        this.host = host
    }

    fun start(config: SessionConfig, token: Long) {
        if (active != null) return
        val session = ActiveSession(config, token)
        active = session
        listener.onPhase(token, SessionPhase.PreparingCamera)

        setupJob = scope.launch {
            try {
                setupSession(session, config)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                if (session.handle == null) {
                    log(session, "erro_camera", error.toString())
                    finishWithoutMetadata(session)
                } else {
                    log(
                        session,
                        if (session.recordingStarted) "erro_video" else "erro_camera",
                        error.toString(),
                    )
                    finalizeSession(
                        session,
                        completedProtocol = false,
                        logInterrupted = false,
                        cameraFailure = !session.recordingStarted,
                    )
                }
            }
        }
    }

    private suspend fun setupSession(session: ActiveSession, config: SessionConfig) {
        requireHost().showPreparing()
        val handle = store.createSession(config.experimentId)
        if (handle == null) {
            finishWithoutMetadata(session)
            return
        }
        session.handle = handle
        log(session, "sessao_iniciada")
        store.save(handle, config.experimentId, completed = false, events = session.events.toList())

        val engine = recordingEngines.create()
        val recording = try {
            engine.start(File(handle.directory, "face.mp4"))
        } catch (error: Throwable) {
            log(session, "erro_camera", error.toString())
            finalizeSession(session, false, logInterrupted = false, cameraFailure = true)
            return
        }
        session.recording = recording
        session.recordingStarted = try {
            recording.awaitStart()
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Throwable) {
            false
        }
        if (!session.recordingStarted) {
            log(session, "erro_camera", "Não foi possível iniciar a gravação frontal.")
            finalizeSession(session, false, logInterrupted = false, cameraFailure = true)
            return
        }

        log(session, "gravacao_inicio")
        protocolJob = scope.launch { runProtocol(session, config.videoUri) }
    }

    fun interrupt() {
        val session = active ?: return
        if (session.finalizeStarted) return
        session.interrupted = true
        setupJob?.cancel()
        protocolJob?.cancel()
        scope.launch {
            finalizeSession(session, completedProtocol = false, logInterrupted = true, cameraFailure = false)
        }
    }

    fun onHostDestroyed() {
        if (active != null && active?.finalizeStarted != true) interrupt()
        host = null
        if (active == null) scope.cancel()
    }

    private suspend fun runProtocol(session: ActiveSession, videoUri: String) {
        try {
            showMarker(session, first = true)
            showPoints(session, CALIBRATION, "calibracao", SessionPhase.Calibration)
            showRest(session)
            if (!playStimulus(session, videoUri)) {
                finalizeSession(session, false, logInterrupted = true, cameraFailure = false)
                return
            }
            showPoints(session, VALIDATION, "validacao", SessionPhase.Validation)
            showMarker(session, first = false)
            finalizeSession(session, true, logInterrupted = false, cameraFailure = false)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Throwable) {
            log(session, "erro_video", error.toString())
            finalizeSession(session, false, logInterrupted = true, cameraFailure = false)
        }
    }

    private suspend fun showMarker(session: ActiveSession, first: Boolean) {
        val name = if (first) "marcador_a" else "marcador_b"
        listener.onPhase(session.token, if (first) SessionPhase.MarkerA else SessionPhase.MarkerB)
        repeat(2) {
            val start = requireHost().showMarker(true)
            logFrame(session, "${name}_inicio", null, start)
            delay(FLASH_ON_MS)
            val end = requireHost().showMarker(false)
            logFrame(session, "${name}_fim", null, end)
            delay(FLASH_OFF_MS)
        }
        delay(MARKER_PAUSE_MS)
    }

    private suspend fun showPoints(
        session: ActiveSession,
        positions: Array<DoubleArray>,
        eventName: String,
        phase: SessionPhase,
    ) {
        listener.onPhase(session.token, phase)
        positions.forEachIndexed { index, position ->
            val display = requireHost().showTarget(position[0], position[1])
            logFrame(
                session,
                eventName,
                "$index,${position[0]},${position[1]},${display.width},${display.height}",
                display.frameTimeNanos,
            )
            delay(POINT_MS)
        }
    }

    private suspend fun showRest(session: ActiveSession) {
        listener.onPhase(session.token, SessionPhase.Rest)
        val frameTime = requireHost().showRest()
        logFrame(session, "descanso", null, frameTime)
        delay(REST_MS)
    }

    private suspend fun playStimulus(session: ActiveSession, videoUri: String): Boolean {
        listener.onPhase(session.token, SessionPhase.Stimulus)
        return when (val playback = requireHost().playVideo(videoUri) { frameTime ->
            if (active === session && !session.finalizeStarted) {
                logFrame(session, "estimulo_inicio", null, frameTime)
            }
        }) {
            is VideoPlayback.Finished -> {
                logFrame(session, "estimulo_fim", null, playback.endFrameNanos)
                true
            }

            is VideoPlayback.Failed -> {
                log(session, "erro_video", "${playback.what},${playback.extra}")
                false
            }
        }
    }

    private suspend fun finalizeSession(
        session: ActiveSession,
        completedProtocol: Boolean,
        logInterrupted: Boolean,
        cameraFailure: Boolean,
    ) {
        if (session.finalizeStarted) return
        session.finalizeStarted = true
        listener.onPhase(session.token, SessionPhase.Finalizing)
        host?.showFinalizing()

        if (logInterrupted) log(session, "interrompida")

        var recordingError = session.recordingError
        val recording = session.recording
        if (recording != null) {
            val finalize = try {
                recording.stopAndAwaitFinalize()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Throwable) {
                FinalizeInfo(true, FINALIZE_ERROR_UNKNOWN)
            }
            if (session.recordingStarted) {
                if (finalize.hasError) {
                    log(session, "erro_gravacao", finalize.errorCode.toString())
                    recordingError = true
                }
                log(session, "gravacao_fim")
            } else if (finalize.hasError) {
                recordingError = true
            }
        }
        session.recordingError = recordingError
        session.recording?.unbind()

        val completed = completedProtocol &&
            session.recordingStarted &&
            !recordingError &&
            !cameraFailure
        val saved = when (val handle = session.handle) {
            null -> session.interrupted
            else -> store.save(
                handle,
                session.config.experimentId,
                completed,
                session.events.toList(),
            )
        }

        val sessionId = session.handle?.sessionId
        val result = when {
            !saved -> SessionResult.Failed(sessionId, FailureReason.Persistence)
            completed -> SessionResult.Completed(requireNotNull(sessionId))
            session.interrupted -> SessionResult.Interrupted(sessionId)
            cameraFailure -> SessionResult.Failed(sessionId, FailureReason.CameraUnavailable)
            recordingError -> SessionResult.Failed(sessionId, FailureReason.Recording)
            else -> SessionResult.Failed(sessionId, FailureReason.Video)
        }

        active = null
        listener.onFinished(session.token, result)
    }

    private fun finishWithoutMetadata(session: ActiveSession) {
        active = null
        listener.onFinished(
            session.token,
            SessionResult.Failed(session.handle?.sessionId, FailureReason.Persistence),
        )
    }

    private fun requireHost(): SessionHost =
        host ?: throw CancellationException("A tela da sessão foi encerrada.")

    private fun log(session: ActiveSession, name: String, data: String? = null) {
        session.events += SessionEvent(name, timeSource(), ELAPSED_CLOCK, data)
    }

    private fun logFrame(
        session: ActiveSession,
        name: String,
        data: String?,
        frameTimeNanos: Long,
    ) {
        session.events += SessionEvent(name, frameTimeNanos, FRAME_CLOCK, data)
    }

    private class ActiveSession(
        val config: SessionConfig,
        val token: Long,
    ) {
        val events = mutableListOf<SessionEvent>()
        var handle: SessionHandle? = null
        var recording: Recording? = null
        var recordingStarted = false
        var recordingError = false
        var interrupted = false
        var finalizeStarted = false
    }

    private companion object {
        const val POINT_MS = 2_000L
        const val REST_MS = 2_000L
        const val FLASH_ON_MS = 200L
        const val FLASH_OFF_MS = 1_000L
        const val MARKER_PAUSE_MS = 2_000L
        const val ELAPSED_CLOCK = "elapsedRealtimeNanos"
        const val FRAME_CLOCK = "frameTimeNanos"
        const val FINALIZE_ERROR_UNKNOWN = -1

        val CALIBRATION = arrayOf(
            doubleArrayOf(.5, .5),
            doubleArrayOf(.1, .1),
            doubleArrayOf(.9, .1),
            doubleArrayOf(.9, .9),
            doubleArrayOf(.1, .9),
            doubleArrayOf(.5, .5),
            doubleArrayOf(.9, .9),
            doubleArrayOf(.1, .1),
            doubleArrayOf(.1, .9),
            doubleArrayOf(.9, .1),
        )

        val VALIDATION = arrayOf(
            doubleArrayOf(.5, .15),
            doubleArrayOf(.85, .5),
            doubleArrayOf(.5, .85),
            doubleArrayOf(.15, .5),
            doubleArrayOf(.65, .65),
        )
    }
}
