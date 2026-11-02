package br.com.marcelopera.eye_tracking

import br.com.marcelopera.eye_tracking.data.SessionEvent
import br.com.marcelopera.eye_tracking.data.SessionHandle
import br.com.marcelopera.eye_tracking.data.SessionStore
import br.com.marcelopera.eye_tracking.session.FailureReason
import br.com.marcelopera.eye_tracking.session.ClockSample
import br.com.marcelopera.eye_tracking.session.FinalizeInfo
import br.com.marcelopera.eye_tracking.session.Recording
import br.com.marcelopera.eye_tracking.session.RecordingEngine
import br.com.marcelopera.eye_tracking.session.RecordingEngineFactory
import br.com.marcelopera.eye_tracking.session.SessionConfig
import br.com.marcelopera.eye_tracking.session.SessionController
import br.com.marcelopera.eye_tracking.session.SessionHost
import br.com.marcelopera.eye_tracking.session.SessionPhase
import br.com.marcelopera.eye_tracking.session.SessionResult
import br.com.marcelopera.eye_tracking.session.TargetDisplay
import br.com.marcelopera.eye_tracking.session.VideoPlayback
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

@OptIn(ExperimentalCoroutinesApi::class)
class SessionControllerTest {
    @Test fun hostAndCameraTelemetrySurviveHostDestruction() = runTest {
        val cameraEvent = SessionEvent("camera_frame_v1", 41, "frameTimeNanos", "{}")
        val displayEvent = SessionEvent("display_v1", 40, "frameTimeNanos", "{}")
        val store = FakeStore()
        val listener = FakeListener()
        val recording = FakeRecording(measurements = listOf(cameraEvent))
        val host = FakeHost(videoGate = CompletableDeferred(), measurements = listOf(displayEvent))
        val controller = controller(store, host, recording, listener, this)
        controller.start(CONFIG, TOKEN)
        advanceUntilIdle()
        controller.onHostDestroyed()
        advanceUntilIdle()
        assertTrue(listener.result is SessionResult.Interrupted)
        assertTrue(store.savedEvents.contains(cameraEvent))
        assertTrue(store.savedEvents.contains(displayEvent))
    }


    @Test
    fun clockSamplesAreBoundedAndStopOnInterruption() = runTest {
        val store = FakeStore()
        val listener = FakeListener()
        var sample = 0L
        val controller = SessionController(
            store = store,
            listener = listener,
            recordingEngines = RecordingEngineFactory { RecordingEngine { FakeRecording() } },
            scope = this,
            timeSource = { 42L },
            clockSampleSource = { ClockSample(100L + sample, 200L + sample, 102L + sample).also { sample++ } },
        ).apply { attachHost(FakeHost()) }

        controller.start(CONFIG, TOKEN)
        runCurrent()
        advanceTimeBy(2_500)
        runCurrent()
        controller.interrupt()
        advanceUntilIdle()

        val samples = store.savedEvents.filter { it.name == "amostra_relogios_v1" }
        assertEquals(5, samples.size)
        assertEquals("200,100,102", samples.first().data)
        assertEquals("elapsedRealtimeNanos", samples.first().clock)
        assertEquals(100L, samples.first().timeNanos)
        assertTrue(listener.result is SessionResult.Interrupted)
    }

    @Test
    fun completionWaitsForRecordingFinalizeAndPersistence() = runTest {
        val finalize = CompletableDeferred<FinalizeInfo>()
        val recording = FakeRecording(finalize = finalize)
        val store = FakeStore()
        val listener = FakeListener()
        val controller = controller(store, FakeHost(), recording, listener, this)

        controller.start(CONFIG, TOKEN)
        advanceUntilIdle()

        assertNull(listener.result)
        assertEquals(SessionPhase.Finalizing, listener.phases.last())
        assertTrue(recording.stopped)

        finalize.complete(FinalizeInfo(false, 0))
        advanceUntilIdle()

        assertEquals(SessionResult.Completed("session-1"), listener.result)
        assertEquals(true, store.savedCompleted)
    }

    @Test
    fun recordingFinalizeErrorPreventsCompletion() = runTest {
        val recording = FakeRecording(
            finalize = CompletableDeferred(FinalizeInfo(true, 7)),
        )
        val store = FakeStore()
        val listener = FakeListener()
        val controller = controller(store, FakeHost(), recording, listener, this)

        controller.start(CONFIG, TOKEN)
        advanceUntilIdle()

        val result = listener.result as SessionResult.Failed
        assertEquals(FailureReason.Recording, result.reason)
        assertEquals(false, store.savedCompleted)
    }

    @Test
    fun persistenceFailurePreventsCompletion() = runTest {
        val store = FakeStore(saveResult = false)
        val listener = FakeListener()
        val controller = controller(store, FakeHost(), FakeRecording(), listener, this)

        controller.start(CONFIG, TOKEN)
        advanceUntilIdle()

        val result = listener.result as SessionResult.Failed
        assertEquals(FailureReason.Persistence, result.reason)
    }

    @Test
    fun interruptionCancelsProtocolAndSavesInterruptedMetadata() = runTest {
        val host = FakeHost(videoGate = CompletableDeferred())
        val recording = FakeRecording()
        val store = FakeStore()
        val listener = FakeListener()
        val controller = controller(store, host, recording, listener, this)

        controller.start(CONFIG, TOKEN)
        advanceUntilIdle()
        assertNull(listener.result)
        assertEquals(SessionPhase.Stimulus, listener.phases.last())
        assertFalse(recording.stopped)

        controller.interrupt()
        advanceUntilIdle()

        assertTrue(listener.result is SessionResult.Interrupted)
        assertTrue(recording.stopped)
        assertTrue(recording.unbound)
        assertEquals(false, store.savedCompleted)
        assertTrue(store.savedEvents.any { it.name == "interrompida" })
        assertEquals(1, store.savedEvents.count { it.name == "estimulo_inicio" })
        assertTrue(store.savedEvents.none { it.name == "estimulo_fim" })
    }

    @Test
    fun playbackErrorAfterStartKeepsStartEventWithoutCompletion() = runTest {
        val store = FakeStore()
        val listener = FakeListener()
        val host = FakeHost(playback = VideoPlayback.Failed(1, 2))
        val controller = controller(store, host, FakeRecording(), listener, this)
        controller.start(CONFIG, TOKEN)
        advanceUntilIdle()
        assertEquals(FailureReason.Video, (listener.result as SessionResult.Failed).reason)
        assertEquals(1, store.savedEvents.count { it.name == "estimulo_inicio" })
        assertTrue(store.savedEvents.none { it.name == "estimulo_fim" })
        assertEquals(false, store.savedCompleted)
    }

    @Test
    fun cameraStartFailureDoesNotComplete() = runTest {
        val store = FakeStore()
        val listener = FakeListener()
        val controller = controller(
            store,
            FakeHost(),
            FakeRecording(startResult = false),
            listener,
            this,
        )

        controller.start(CONFIG, TOKEN)
        advanceUntilIdle()

        val result = listener.result as SessionResult.Failed
        assertEquals(FailureReason.CameraUnavailable, result.reason)
        assertEquals(false, store.savedCompleted)
        assertTrue(store.savedEvents.any { it.name == "erro_camera" })
    }

    @Test
    fun successfulProtocolPreservesEventSequence() = runTest {
        val store = FakeStore()
        val listener = FakeListener()
        val controller = controller(store, FakeHost(), FakeRecording(), listener, this)

        controller.start(CONFIG, TOKEN)
        advanceUntilIdle()

        assertEquals(SessionResult.Completed("session-1"), listener.result)
        val events = store.savedEvents
        assertEquals("sessao_iniciada", events.first().name)
        assertEquals("gravacao_fim", events.last().name)
        assertEquals(2, events.count { it.name == "marcador_a_inicio" })
        assertEquals(2, events.count { it.name == "marcador_a_fim" })
        assertEquals(10, events.count { it.name == "calibracao" })
        assertEquals(1, events.count { it.name == "descanso" })
        assertEquals(1, events.count { it.name == "estimulo_inicio" })
        assertEquals(1, events.count { it.name == "estimulo_fim" })
        assertEquals(5, events.count { it.name == "validacao" })
        assertEquals(2, events.count { it.name == "marcador_b_inicio" })
        assertEquals(2, events.count { it.name == "marcador_b_fim" })
        assertEquals(true, store.savedCompleted)
    }

    private fun controller(
        store: FakeStore,
        host: FakeHost,
        recording: FakeRecording,
        listener: FakeListener,
        scope: CoroutineScope,
    ): SessionController {
        var clock = 0L
        return SessionController(
            store = store,
            listener = listener,
            recordingEngines = RecordingEngineFactory {
                RecordingEngine { recording }
            },
            scope = scope,
            timeSource = { clock++ },
        ).apply { attachHost(host) }
    }

    private class FakeListener : SessionController.Listener {
        val phases = mutableListOf<SessionPhase>()
        var result: SessionResult? = null

        override fun onPhase(token: Long, phase: SessionPhase) {
            phases += phase
        }

        override fun onFinished(token: Long, result: SessionResult) {
            this.result = result
        }
    }

    private class FakeRecording(
        val measurements: List<SessionEvent> = emptyList(),
        private val startResult: Boolean = true,
        private val finalize: CompletableDeferred<FinalizeInfo> =
            CompletableDeferred(FinalizeInfo(false, 0)),
    ) : Recording {
        override fun telemetry(): List<SessionEvent> = measurements
        var stopped = false
        var unbound = false

        override suspend fun awaitStart(): Boolean = startResult

        override suspend fun stopAndAwaitFinalize(): FinalizeInfo {
            stopped = true
            return finalize.await()
        }

        override fun unbind() {
            unbound = true
        }
    }

    private class FakeHost(
        val measurements: List<SessionEvent> = emptyList(),
        var playback: VideoPlayback = VideoPlayback.Finished(200),
        var videoGate: CompletableDeferred<VideoPlayback>? = null,
    ) : SessionHost {
        override fun telemetry(): List<SessionEvent> = measurements
        override suspend fun showPreparing() = Unit

        override suspend fun showMarker(flashOn: Boolean): Long = 10

        override suspend fun showTarget(x: Double, y: Double): TargetDisplay =
            TargetDisplay(20, 1080, 1920)

        override suspend fun showRest(): Long = 30

        override suspend fun playVideo(uri: String, onStarted: (Long) -> Unit): VideoPlayback {
            onStarted(100)
            return videoGate?.await() ?: playback
        }

        override suspend fun showFinalizing() = Unit
    }

    private class FakeStore(
        var saveResult: Boolean = true,
    ) : SessionStore {
        val handle = SessionHandle("session-1", File("/tmp/session-1"))
        var savedCompleted: Boolean? = null
        var savedEvents: List<SessionEvent> = emptyList()

        override suspend fun createSession(experimentId: String): SessionHandle = handle

        override suspend fun save(
            handle: SessionHandle,
            experimentId: String,
            completed: Boolean,
            events: List<SessionEvent>,
        ): Boolean {
            savedCompleted = completed
            savedEvents = events.toList()
            return saveResult
        }
    }

    private companion object {
        const val TOKEN = 1L
        val CONFIG = SessionConfig("exp-123", "content://videos/stimulus.mp4")
    }
}
