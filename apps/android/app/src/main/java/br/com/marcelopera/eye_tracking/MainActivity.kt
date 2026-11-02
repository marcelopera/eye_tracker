package br.com.marcelopera.eye_tracking

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.view.Choreographer
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.VideoView
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import br.com.marcelopera.eye_tracking.data.SessionRepository
import br.com.marcelopera.eye_tracking.session.CameraRecordingEngine
import br.com.marcelopera.eye_tracking.session.RecordingEngineFactory
import br.com.marcelopera.eye_tracking.session.SessionController
import br.com.marcelopera.eye_tracking.session.SessionHost
import br.com.marcelopera.eye_tracking.session.SessionPhase
import br.com.marcelopera.eye_tracking.session.SessionResult
import br.com.marcelopera.eye_tracking.session.TargetDisplay
import br.com.marcelopera.eye_tracking.session.VideoPlayback
import br.com.marcelopera.eye_tracking.ui.CompletionScreen
import br.com.marcelopera.eye_tracking.ui.Destination
import br.com.marcelopera.eye_tracking.ui.IdentificationScreen
import br.com.marcelopera.eye_tracking.ui.PreparationScreen
import br.com.marcelopera.eye_tracking.ui.SessionEffect
import br.com.marcelopera.eye_tracking.ui.SessionUiState
import br.com.marcelopera.eye_tracking.ui.SessionViewModel
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlin.coroutines.resume

class MainActivity : AppCompatActivity(), SessionHost {

    private val viewModel: SessionViewModel by viewModels {
        viewModelFactory {
            initializer { SessionViewModel(createSavedStateHandle()) }
        }
    }

    private lateinit var root: FrameLayout
    private lateinit var controller: SessionController

    private var currentDestination: Destination? = null
    private var identificationScreen: IdentificationScreen? = null
    private var preparationScreen: PreparationScreen? = null
    private var completionScreen: CompletionScreen? = null
    private var sessionContent: FrameLayout? = null

    private val pickVideo = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            runCatching {
                contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION,
                )
            }
            viewModel.onVideoSelected(uri.toString())
        }
    }

    private val cameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        viewModel.onCameraPermissionResult(granted)
    }

    private val backCallback = object : OnBackPressedCallback(false) {
        override fun handleOnBackPressed() {
            when (viewModel.uiState.value.destination) {
                Destination.Collecting -> {
                    if (viewModel.uiState.value.phase == SessionPhase.Finalizing) return
                    if (controller.isActive) controller.interrupt() else viewModel.cancelPendingStart()
                }

                Destination.Preparation -> viewModel.backToIdentification()
                Destination.Completed -> viewModel.resetToIdentification()
                Destination.Identification -> Unit
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        root = FrameLayout(this).apply {
            setBackgroundColor(color(R.color.surface))
        }
        setContentView(root)
        applySystemInsets()

        controller = SessionController(
            store = SessionRepository(applicationContext.filesDir),
            listener = object : SessionController.Listener {
                override fun onPhase(token: Long, phase: SessionPhase) {
                    viewModel.onPhase(token, phase)
                }

                override fun onFinished(token: Long, result: SessionResult) {
                    viewModel.onFinished(token, result)
                }
            },
            recordingEngines = RecordingEngineFactory {
                CameraRecordingEngine(this@MainActivity, this@MainActivity)
            },
        )
        controller.attachHost(this)
        onBackPressedDispatcher.addCallback(this, backCallback)

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.uiState.collect { state ->
                    render(state)
                    backCallback.isEnabled = state.destination != Destination.Identification
                }
            }
        }
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.effects.collect { effect ->
                    when (effect) {
                        SessionEffect.CheckCameraPermission -> requestCameraPermission()
                        is SessionEffect.StartSession -> {
                            if (viewModel.acceptsStart(effect.token)) {
                                // The state and effect collectors can run in either order.
                                // Attach the session screen before the controller uses it.
                                render(viewModel.uiState.value)
                                controller.start(effect.config, effect.token)
                            }
                        }
                    }
                }
            }
        }

        render(viewModel.uiState.value)
    }

    override fun onStart() {
        super.onStart()
        revalidateVideoAccess()
    }

    override fun onStop() {
        if (viewModel.uiState.value.destination == Destination.Collecting) {
            if (controller.isActive) controller.interrupt() else viewModel.cancelPendingStart()
        }
        super.onStop()
    }

    override fun onDestroy() {
        controller.onHostDestroyed()
        super.onDestroy()
    }

    override suspend fun showPreparing() {
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(color(R.color.surface))
        content.addView(
            sessionMessage(
                getString(R.string.preparing_camera_title),
                getString(R.string.preparing_camera_description),
            ),
            FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT),
        )
    }

    override suspend fun showMarker(flashOn: Boolean): Long {
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(color(if (flashOn) R.color.marker_light else R.color.marker_dark))
        return awaitNextFrame()
    }

    override suspend fun showTarget(x: Double, y: Double): TargetDisplay {
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(color(R.color.calibration_background))

        val size = dp(20)
        val dot = View(this).apply {
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(color(R.color.target))
            }
        }
        content.addView(dot, FrameLayout.LayoutParams(size, size))

        awaitNonEmptyLayout(content)
        dot.x = (x * content.width - size / 2.0).toFloat()
        dot.y = (y * content.height - size / 2.0).toFloat()
        return TargetDisplay(awaitNextFrame(), content.width, content.height)
    }

    override suspend fun showRest(): Long {
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(color(R.color.calibration_background))
        return awaitNextFrame()
    }

    override suspend fun playVideo(uri: String, onStarted: (Long) -> Unit): VideoPlayback = coroutineScope {
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(Color.BLACK)
        val player = VideoView(this@MainActivity)
        content.addView(player, MATCH_PARENT, MATCH_PARENT)

        val prepared = CompletableDeferred<Boolean>()
        val end = CompletableDeferred<PlaybackEnd>()
        player.setOnPreparedListener { prepared.complete(true) }
        player.setOnCompletionListener { end.complete(PlaybackEnd.Completed) }
        player.setOnErrorListener { _, what, extra ->
            if (!prepared.isCompleted) prepared.complete(false)
            end.complete(PlaybackEnd.Failed(what, extra))
            true
        }

        try {
            player.setVideoURI(uri.toUri())
            if (!prepared.await()) {
                val failure = end.await() as? PlaybackEnd.Failed ?: PlaybackEnd.Failed(-1, -1)
                VideoPlayback.Failed(failure.what, failure.extra)
            } else {
                player.start()
                onStarted(awaitNextFrame())
                when (val outcome = end.await()) {
                    PlaybackEnd.Completed -> {
                        val endFrameNanos = awaitNextFrame()
                        VideoPlayback.Finished(endFrameNanos)
                    }

                    is PlaybackEnd.Failed -> VideoPlayback.Failed(outcome.what, outcome.extra)
                }
            }
        } finally {
            player.setOnPreparedListener(null)
            player.setOnCompletionListener(null)
            player.setOnErrorListener(null)
            player.stopPlayback()
            content.removeView(player)
        }
    }

    override suspend fun showFinalizing() {
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(color(R.color.surface))
        content.addView(
            sessionMessage(getString(R.string.finalizing), null),
            FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT),
        )
    }

    private fun render(state: SessionUiState) {
        if (currentDestination != state.destination) {
            currentDestination = state.destination
            identificationScreen = null
            preparationScreen = null
            completionScreen = null
            if (state.destination != Destination.Collecting) sessionContent = null

            when (state.destination) {
                Destination.Identification -> {
                    val screen = IdentificationScreen(
                        context = this,
                        initialState = state,
                        onInputChanged = viewModel::onExperimentInputChanged,
                        onContinue = viewModel::continueFromIdentification,
                    )
                    identificationScreen = screen
                    replaceContent(screen.root)
                }

                Destination.Preparation -> {
                    val screen = PreparationScreen(
                        context = this,
                        initialState = state,
                        onSelectVideo = { pickVideo.launch(arrayOf("video/*")) },
                        onStart = viewModel::onStartClicked,
                        onChangeId = viewModel::backToIdentification,
                    )
                    preparationScreen = screen
                    replaceContent(screen.root)
                }

                Destination.Collecting -> {
                    val alreadyCreated = sessionContent != null
                    val content = ensureSessionScreen()
                    if (!alreadyCreated) when (state.phase) {
                        SessionPhase.Finalizing -> {
                            content.addView(
                                sessionMessage(getString(R.string.finalizing), null),
                                FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT),
                            )
                        }

                        else -> {
                            content.addView(
                                sessionMessage(
                                    getString(R.string.preparing_camera_title),
                                    getString(R.string.preparing_camera_description),
                                ),
                                FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT),
                            )
                        }
                    }
                }

                Destination.Completed -> {
                    val screen = CompletionScreen(
                        context = this,
                        initialState = state,
                        onBackToStart = viewModel::resetToIdentification,
                    )
                    completionScreen = screen
                    replaceContent(screen.root)
                }
            }
        }

        when (state.destination) {
            Destination.Identification -> identificationScreen?.render(state)
            Destination.Preparation -> preparationScreen?.render(state)
            Destination.Completed -> completionScreen?.render(state)
            Destination.Collecting -> Unit
        }
    }

    private fun ensureSessionScreen(): FrameLayout {
        sessionContent?.let { return it }
        val content = FrameLayout(this).apply {
            setBackgroundColor(color(R.color.surface))
        }
        sessionContent = content
        replaceContent(content)
        return content
    }

    private fun ensureSessionContent(): FrameLayout = ensureSessionScreen()

    private fun replaceContent(view: View) {
        root.removeAllViews()
        root.addView(view, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
    }

    private fun applySystemInsets() {
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or
                    WindowInsetsCompat.Type.displayCutout() or
                    WindowInsetsCompat.Type.ime(),
            )
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
    }

    private fun sessionMessage(title: String, detail: String?): View {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(28), dp(28), dp(28), dp(28))
            setBackgroundColor(color(R.color.surface))
        }
        box.addView(
            TextView(this).apply {
                text = title
                setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 24f)
                setTextColor(color(R.color.on_surface))
                gravity = Gravity.CENTER
            },
        )
        if (detail != null) {
            box.addView(
                TextView(this).apply {
                    text = detail
                    setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 16f)
                    setTextColor(color(R.color.on_surface_variant))
                    gravity = Gravity.CENTER
                },
            )
        }
        return box
    }

    private fun requestCameraPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            viewModel.onCameraPermissionResult(true)
        } else {
            cameraPermission.launch(Manifest.permission.CAMERA)
        }
    }

    private fun revalidateVideoAccess() {
        val state = viewModel.uiState.value
        val uri = state.videoUri ?: return
        if (state.destination != Destination.Preparation) return
        lifecycleScope.launch {
            val accessible = withContext(Dispatchers.IO) { canRead(uri.toUri()) }
            viewModel.onVideoAccessChecked(uri, accessible)
        }
    }

    private fun canRead(uri: Uri): Boolean = try {
        contentResolver.openAssetFileDescriptor(uri, "r")?.use { true } ?: false
    } catch (_: Exception) {
        false
    }

    private suspend fun awaitNextFrame(): Long =
        suspendCancellableCoroutine { continuation ->
            val callback = Choreographer.FrameCallback { frameTimeNanos ->
                if (continuation.isActive) continuation.resume(frameTimeNanos)
            }
            Choreographer.getInstance().postFrameCallback(callback)
            continuation.invokeOnCancellation {
                Choreographer.getInstance().removeFrameCallback(callback)
            }
        }

    private suspend fun awaitNonEmptyLayout(view: View) {
        if (view.isLaidOut && !view.isLayoutRequested && view.width > 0 && view.height > 0) return
        suspendCancellableCoroutine<Unit> { continuation ->
            val listener = object : View.OnLayoutChangeListener {
                override fun onLayoutChange(
                    changed: View, left: Int, top: Int, right: Int, bottom: Int,
                    oldLeft: Int, oldTop: Int, oldRight: Int, oldBottom: Int,
                ) {
                    if (right <= left || bottom <= top) return
                    changed.removeOnLayoutChangeListener(this)
                    if (continuation.isActive) continuation.resume(Unit)
                }
            }
            view.addOnLayoutChangeListener(listener)
            continuation.invokeOnCancellation { view.removeOnLayoutChangeListener(listener) }
        }
    }

    private fun color(resource: Int): Int = ContextCompat.getColor(this, resource)

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density + 0.5f).toInt()

    private sealed interface PlaybackEnd {
        data object Completed : PlaybackEnd
        data class Failed(val what: Int, val extra: Int) : PlaybackEnd
    }
}
