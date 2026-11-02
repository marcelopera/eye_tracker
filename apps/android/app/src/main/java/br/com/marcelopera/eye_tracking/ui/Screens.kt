package br.com.marcelopera.eye_tracking.ui

import android.content.Context
import android.graphics.Typeface
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.annotation.StringRes
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.core.widget.doAfterTextChanged
import br.com.marcelopera.eye_tracking.R

class IdentificationScreen(
    context: Context,
    initialState: SessionUiState,
    private val onInputChanged: (String) -> Unit,
    private val onContinue: () -> Unit,
) {
    val root: View
    private val input: EditText
    private val error: TextView
    private var writingText = false

    init {
        val page = buildPage(
            context = context,
            title = context.getString(R.string.identification_title),
            description = context.getString(R.string.identification_description),
        )
        root = page.first

        input = EditText(context).apply {
            setSingleLine(true)
            hint = context.getString(R.string.experiment_id_hint)
            setText(initialState.experimentInput)
            setSelection(text.length)
        }
        page.second.addView(input, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))

        error = label(
            context,
            text = context.getString(R.string.id_required_error),
            sizeSp = 14,
            color = ContextCompat.getColor(context, R.color.error),
        ).apply { isVisible = initialState.idError }
        page.second.addView(error)

        page.second.addView(
            buildButton(context, context.getString(R.string.continue_action), onContinue),
        )
        page.second.addView(
            label(
                context,
                text = context.getString(R.string.simulated_lookup_note),
                sizeSp = 13,
                color = ContextCompat.getColor(context, R.color.on_surface_variant),
            ),
        )

        input.doAfterTextChanged { text ->
            if (!writingText) onInputChanged(text?.toString().orEmpty())
        }
    }

    fun render(state: SessionUiState) {
        if (!input.hasFocus() && input.text.toString() != state.experimentInput) {
            writingText = true
            input.setText(state.experimentInput)
            input.setSelection(input.length())
            writingText = false
        }
        error.isVisible = state.idError
    }
}

class PreparationScreen(
    context: Context,
    initialState: SessionUiState,
    private val onSelectVideo: () -> Unit,
    private val onStart: () -> Unit,
    private val onChangeId: () -> Unit,
) {
    val root: View
    private val description: TextView
    private val videoStatus: TextView
    private val notice: TextView

    init {
        val page = buildPage(
            context = context,
            title = context.getString(R.string.preparation_title),
            description = null,
        )
        root = page.first
        val box = page.second

        description = label(
            context,
            text = "",
            sizeSp = 16,
            color = ContextCompat.getColor(context, R.color.on_surface_variant),
        )
        box.addView(description)

        box.addView(
            label(
                context,
                text = context.getString(R.string.step_calibration),
                sizeSp = 16,
                color = ContextCompat.getColor(context, R.color.on_surface_variant),
            ),
        )
        box.addView(
            label(
                context,
                text = context.getString(R.string.step_collection),
                sizeSp = 16,
                color = ContextCompat.getColor(context, R.color.on_surface_variant),
            ),
        )
        box.addView(
            label(
                context,
                text = context.getString(R.string.step_completion),
                sizeSp = 16,
                color = ContextCompat.getColor(context, R.color.on_surface_variant),
            ),
        )

        videoStatus = label(
            context,
            text = "",
            sizeSp = 14,
            color = ContextCompat.getColor(context, R.color.on_surface_variant),
        )
        box.addView(videoStatus)

        notice = label(
            context,
            text = "",
            sizeSp = 14,
            color = ContextCompat.getColor(context, R.color.error),
        )
        box.addView(notice)

        box.addView(
            buildButton(
                context,
                context.getString(R.string.select_video_action),
                onSelectVideo,
            ),
        )
        box.addView(buildButton(context, context.getString(R.string.start_action), onStart))
        box.addView(buildButton(context, context.getString(R.string.change_id_action), onChangeId))
        box.addView(
            label(
                context,
                text = context.getString(R.string.simulation_note),
                sizeSp = 13,
                color = ContextCompat.getColor(context, R.color.on_surface_variant),
            ),
        )

        render(initialState)
    }

    fun render(state: SessionUiState) {
        description.text = root.context.getString(
            R.string.preparation_description,
            state.experimentId.orEmpty(),
        )
        videoStatus.text = root.context.getString(
            if (state.videoUri == null) R.string.video_none else R.string.video_selected,
        )
        val noticeText = state.notice?.let { root.context.getString(it.messageRes()) }.orEmpty()
        notice.text = noticeText
        notice.isVisible = noticeText.isNotEmpty()
    }
}

class CompletionScreen(
    context: Context,
    initialState: SessionUiState,
    onBackToStart: () -> Unit,
) {
    val root: View
    private val sessionId: TextView

    init {
        val page = buildPage(
            context = context,
            title = context.getString(R.string.completion_title),
            description = context.getString(R.string.completion_description),
        )
        root = page.first

        sessionId = label(
            context,
            text = "",
            sizeSp = 16,
            color = ContextCompat.getColor(context, R.color.on_surface_variant),
        )
        page.second.addView(sessionId)

        page.second.addView(
            label(
                context,
                text = context.getString(R.string.completion_saved),
                sizeSp = 15,
                color = ContextCompat.getColor(context, R.color.on_surface_variant),
            ),
        )
        page.second.addView(
            buildButton(
                context,
                context.getString(R.string.back_to_start),
                onBackToStart,
            ),
        )

        render(initialState)
    }

    fun render(state: SessionUiState) {
        sessionId.text = root.context.getString(
            R.string.local_session_id,
            state.sessionId.orEmpty(),
        )
    }
}

@StringRes
internal fun PreparationNotice.messageRes(): Int = when (this) {
    PreparationNotice.VideoRequired -> R.string.notice_video_required
    PreparationNotice.VideoAccessLost -> R.string.notice_video_access_lost
    PreparationNotice.CameraPermissionDenied -> R.string.notice_camera_permission_denied
    PreparationNotice.Interrupted -> R.string.notice_interrupted
    PreparationNotice.CameraUnavailable -> R.string.notice_camera_unavailable
    PreparationNotice.RecordingFailed -> R.string.notice_recording_failed
    PreparationNotice.VideoFailed -> R.string.notice_video_failed
    PreparationNotice.PersistenceFailed -> R.string.notice_persistence_failed
}

private fun buildPage(
    context: Context,
    title: String,
    description: String?,
): Pair<ScrollView, LinearLayout> {
    val box = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(context.dp(28), context.dp(36), context.dp(28), context.dp(28))
        setBackgroundColor(ContextCompat.getColor(context, R.color.surface))
    }

    val heading = label(
        context,
        text = title,
        sizeSp = 28,
        color = ContextCompat.getColor(context, R.color.on_surface),
    ).apply {
        typeface = Typeface.create(typeface, Typeface.BOLD)
    }
    box.addView(heading)

    if (description != null) {
        val descriptionView = label(
            context,
            text = description,
            sizeSp = 16,
            color = ContextCompat.getColor(context, R.color.on_surface_variant),
        )
        box.addView(
            descriptionView,
            LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply {
                topMargin = context.dp(14)
                bottomMargin = context.dp(24)
            },
        )
    }

    val scroll = ScrollView(context).apply {
        isFillViewport = true
        setBackgroundColor(ContextCompat.getColor(context, R.color.surface))
        addView(box, MATCH_PARENT, WRAP_CONTENT)
    }
    return scroll to box
}

private fun label(
    context: Context,
    text: String,
    sizeSp: Int,
    color: Int,
): TextView = TextView(context).apply {
    this.text = text
    setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp.toFloat())
    setTextColor(color)
}

private fun buildButton(
    context: Context,
    text: String,
    action: () -> Unit,
): Button = Button(context).apply {
    this.text = text
    isAllCaps = false
    setOnClickListener { action() }
}

private fun Context.dp(value: Int): Int =
    (value * resources.displayMetrics.density + 0.5f).toInt()
