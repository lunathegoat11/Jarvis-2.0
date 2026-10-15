package com.lunathegoat11.jarvis

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Path
import android.net.Uri
import android.os.Bundle
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Controls the phone for Jarvis: opens apps, taps, types, swipes, and reads
 * what's on screen. Works once the user turns it on in Settings >
 * Accessibility. Jarvis only uses it while carrying out a spoken request.
 */
class JarvisAccessibilityService : AccessibilityService(), DeviceActions {

    override fun onServiceConnected() {
        instance = this
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}
    override fun onInterrupt() {}

    // ---- DeviceActions -------------------------------------------------------

    override fun openApp(name: String): String {
        val pm = packageManager
        val wanted = name.trim().lowercase()
        val apps = pm.getInstalledApplications(0)
        val match = apps.firstOrNull {
            val label = pm.getApplicationLabel(it).toString().lowercase()
            label == wanted || label.contains(wanted) || wanted.contains(label)
        } ?: return "I couldn't find an app called $name."
        val launch = pm.getLaunchIntentForPackage(match.packageName)
            ?: return "I can't open $name."
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(launch)
        return "Opened $name."
    }

    override fun openUrl(url: String): String {
        val fixed = if (url.startsWith("http")) url else "https://$url"
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(fixed)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(intent)
        return "Opened $url."
    }

    override fun goHome(): String {
        performGlobalAction(GLOBAL_ACTION_HOME)
        return "Home."
    }

    override fun goBack(): String {
        performGlobalAction(GLOBAL_ACTION_BACK)
        return "Went back."
    }

    override fun readScreen(): String {
        val root = rootInActiveWindow ?: return "The screen is empty or I can't read it."
        val lines = mutableListOf<String>()
        collect(root, lines)
        if (lines.isEmpty()) return "Nothing readable on screen."
        return lines.distinct().take(80).joinToString("\n")
    }

    private fun collect(node: AccessibilityNodeInfo?, out: MutableList<String>) {
        if (node == null) return
        val text = node.text?.toString()?.trim()
        val desc = node.contentDescription?.toString()?.trim()
        val label = (text ?: desc)
        if (!label.isNullOrBlank()) {
            val bounds = android.graphics.Rect()
            node.getBoundsInScreen(bounds)
            val tag = if (node.isClickable) " [tap, at ${bounds.centerX()},${bounds.centerY()}]" else ""
            out.add(label + tag)
        }
        for (i in 0 until node.childCount) collect(node.getChild(i), out)
    }

    override fun tapText(text: String): String {
        val root = rootInActiveWindow ?: return "I can't see the screen."
        val node = findByText(root, text.trim().lowercase())
            ?: return "I couldn't find \"$text\" on the screen."
        var target: AccessibilityNodeInfo? = node
        while (target != null && !target.isClickable) target = target.parent
        return if (target != null && target.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
            "Tapped \"$text\"."
        } else {
            val bounds = android.graphics.Rect()
            node.getBoundsInScreen(bounds)
            tapAt(bounds.centerX(), bounds.centerY())
        }
    }

    private fun findByText(node: AccessibilityNodeInfo?, wanted: String): AccessibilityNodeInfo? {
        if (node == null) return null
        val label = (node.text?.toString() ?: node.contentDescription?.toString())?.lowercase()
        if (label != null && (label == wanted || label.contains(wanted))) return node
        for (i in 0 until node.childCount) {
            val found = findByText(node.getChild(i), wanted)
            if (found != null) return found
        }
        return null
    }

    override fun tapAt(x: Int, y: Int): String {
        val path = Path().apply { moveTo(x.toFloat(), y.toFloat()) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 60)).build()
        dispatchGesture(gesture, null, null)
        return "Tapped at $x, $y."
    }

    override fun typeText(text: String): String {
        val focused = rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
            ?: return "Tap a text box first, then I can type."
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return if (focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) "Typed it."
        else "I couldn't type there."
    }

    override fun swipe(direction: String): String {
        val metrics = resources.displayMetrics
        val w = metrics.widthPixels
        val h = metrics.heightPixels
        val path = Path()
        when (direction.lowercase()) {
            "up" -> { path.moveTo(w / 2f, h * 0.7f); path.lineTo(w / 2f, h * 0.3f) }
            "down" -> { path.moveTo(w / 2f, h * 0.3f); path.lineTo(w / 2f, h * 0.7f) }
            "left" -> { path.moveTo(w * 0.8f, h / 2f); path.lineTo(w * 0.2f, h / 2f) }
            "right" -> { path.moveTo(w * 0.2f, h / 2f); path.lineTo(w * 0.8f, h / 2f) }
            else -> return "Swipe up, down, left or right."
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 300)).build()
        dispatchGesture(gesture, null, null)
        return "Swiped $direction."
    }

    companion object {
        @Volatile
        var instance: JarvisAccessibilityService? = null

        /** The live service, or a stand-in that explains how to turn it on. */
        fun actions(): DeviceActions = instance ?: NoDevice()
    }
}
