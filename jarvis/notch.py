"""The notch panel: a black island that grows out of the MacBook notch while
Jarvis listens, with a Liquid Glass card below it for what you said and the
reply.

Liquid Glass (NSGlassEffectView) needs macOS 26 or newer. On older macOS the
card falls back to the frosted-glass blur those versions have.

Everything that touches AppKit runs on the main thread. The public methods
can be called from any thread; they hand their work to the main thread.
"""

import math
import random
from collections.abc import Callable

import objc
from AppKit import (
    NSAnimationContext,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontWeightMedium,
    NSFontWeightSemibold,
    NSMakeRect,
    NSPanel,
    NSRunLoop,
    NSRunLoopCommonModes,
    NSScreen,
    NSStatusWindowLevel,
    NSTextAlignmentRight,
    NSTextField,
    NSTimer,
    NSView,
    NSVisualEffectView,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)

# NSWindowSharingType: not visible to screen capture.
NSWindowSharingNone = 0
from PyObjCTools import AppHelper

from .hud import MODE_LABELS
from .notch_layout import CARD_MAX_BODY_HEIGHT, CARD_PADDING, CARD_WIDTH, EAR, card_frame, island_frames

# NSWindowCollectionBehavior: show on every Space and over full-screen apps,
# and keep out of Cmd+` window cycling.
CAN_JOIN_ALL_SPACES = 1 << 0
STATIONARY = 1 << 4
IGNORES_CYCLE = 1 << 6
FULL_SCREEN_AUXILIARY = 1 << 8

# CALayer masked corners: only round the bottom of the island so its top
# stays flush with the screen edge, like the notch itself.
BOTTOM_CORNERS = (1 << 0) | (1 << 1)

# NSVisualEffectView settings for the pre-macOS 26 fallback.
MATERIAL_HUD_WINDOW = 13
BLENDING_BEHIND_WINDOW = 0
STATE_ACTIVE = 1

AUTORESIZE_MIN_X_MARGIN = 1
AUTORESIZE_WIDTH_HEIGHT = 2 | 16

BARS = 5
# Middle bars move more than the outer ones.
BAR_SHAPE = [0.55, 0.8, 1.0, 0.8, 0.55]


def _rgb(r, g, b):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r / 255, g / 255, b / 255, 1.0)


MODE_COLORS = {
    "dictate": _rgb(90, 200, 250),
    "ask": _rgb(191, 90, 242),
    "command": _rgb(255, 159, 10),
}
ERROR_COLOR = _rgb(255, 69, 58)
POINTER_COLOR = _rgb(255, 159, 10)
POINTER_SIZE = 34


class WaveView(NSView):
    """Five rounded bars that follow the microphone level."""

    def initWithFrame_(self, frame):
        self = objc.super(WaveView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.levels = [0.0] * BARS
        self.color = NSColor.whiteColor()
        return self

    def drawRect_(self, rect):
        bounds = self.bounds()
        bar_w, gap = 3.0, 3.0
        x = (bounds.size.width - (BARS * bar_w + (BARS - 1) * gap)) / 2
        self.color.setFill()
        for level in self.levels:
            h = 4.0 + level * (bounds.size.height - 4.0)
            y = (bounds.size.height - h) / 2
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x, y, bar_w, h), bar_w / 2, bar_w / 2
            ).fill()
            x += bar_w + gap


class FlippedView(NSView):
    """A view whose y axis runs downwards, so text lays out from the top."""

    def isFlipped(self):
        return True


def _label(size, weight, color):
    field = NSTextField.wrappingLabelWithString_("")
    field.setFont_(NSFont.systemFontOfSize_weight_(size, weight))
    field.setTextColor_(color)
    field.setSelectable_(False)
    field.cell().setTruncatesLastVisibleLine_(True)
    return field


def _text_height(field, width):
    return field.cell().cellSizeForBounds_(NSMakeRect(0, 0, width, 10_000)).height


def _rect(frame):
    return NSMakeRect(*frame)


class NotchHUD:
    def __init__(self):
        self.app = NSApplication.sharedApplication()
        # No Dock icon and no menu bar; Jarvis lives in the notch.
        self.app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        self._level: Callable[[], float] = lambda: 0.0
        self._state = "hidden"
        self._generation = 0
        self._phase = 0.0
        self._card_visible = False

        self._measure_screen()
        self._build_island()
        self._build_card()
        self._build_pointer()

        timer = NSTimer.timerWithTimeInterval_repeats_block_(1 / 30, True, self._tick)
        NSRunLoop.mainRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)

    # ---- setup -------------------------------------------------------------

    def _measure_screen(self):
        # The first screen is the one with the menu bar, which on a MacBook
        # is normally the built-in display with the notch.
        screen = NSScreen.screens()[0]
        frame = screen.frame()
        notch_w = notch_h = 0
        if screen.respondsToSelector_("safeAreaInsets"):
            notch_h = screen.safeAreaInsets().top
            if notch_h > 0:
                left = screen.auxiliaryTopLeftArea().size.width
                right = screen.auxiliaryTopRightArea().size.width
                notch_w = frame.size.width - left - right
        self.screen_x = frame.origin.x
        self.screen_w = frame.size.width
        self.screen_top = frame.origin.y + frame.size.height
        self.collapsed, self.expanded = island_frames(
            self.screen_x, self.screen_w, self.screen_top, notch_w, notch_h
        )

    def _panel(self, frame, shadow):
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            _rect(frame),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        # Above the menu bar, so the island can sit over the notch.
        panel.setLevel_(NSStatusWindowLevel + 1)
        panel.setCollectionBehavior_(
            CAN_JOIN_ALL_SPACES | STATIONARY | IGNORES_CYCLE | FULL_SCREEN_AUXILIARY
        )
        panel.setIgnoresMouseEvents_(True)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(shadow)
        panel.setAlphaValue_(0.0)
        # Keep Jarvis's own panels out of screenshots, so Ask mode and screen
        # control see the screen, not the notch card or the pointer.
        panel.setSharingType_(NSWindowSharingNone)
        return panel

    def _build_island(self):
        _, _, w, h = self.expanded
        self.island = self._panel(self.expanded, shadow=False)

        body = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        body.setWantsLayer_(True)
        body.layer().setBackgroundColor_(NSColor.blackColor().CGColor())
        body.layer().setCornerRadius_(min(14.0, h * 0.45))
        body.layer().setMaskedCorners_(BOTTOM_CORNERS)

        self.wave = WaveView.alloc().initWithFrame_(NSMakeRect(18, (h - 18) / 2, 36, 18))
        body.addSubview_(self.wave)

        self.mode_label = _label(12, NSFontWeightSemibold, NSColor.whiteColor())
        self.mode_label.setMaximumNumberOfLines_(1)
        self.mode_label.setAlignment_(NSTextAlignmentRight)
        self.mode_label.setFrame_(NSMakeRect(w - EAR, (h - 16) / 2, EAR - 14, 16))
        self.mode_label.setAutoresizingMask_(AUTORESIZE_MIN_X_MARGIN)
        body.addSubview_(self.mode_label)

        self.island.setContentView_(body)
        self.island.setFrame_display_(_rect(self.collapsed), False)

    def _build_card(self):
        start = card_frame(self.screen_x, self.screen_w, self.collapsed[1], 16, 20)
        self.card = self._panel(start, shadow=True)
        bounds = NSMakeRect(0, 0, start[2], start[3])

        self.card_content = FlippedView.alloc().initWithFrame_(bounds)
        self.card_content.setAutoresizingMask_(AUTORESIZE_WIDTH_HEIGHT)
        self.title_label = _label(12, NSFontWeightMedium, NSColor.secondaryLabelColor())
        self.title_label.setMaximumNumberOfLines_(2)
        self.body_label = _label(15, NSFontWeightMedium, NSColor.labelColor())
        self.card_content.addSubview_(self.title_label)
        self.card_content.addSubview_(self.body_label)

        try:
            glass = objc.lookUpClass("NSGlassEffectView").alloc().initWithFrame_(bounds)
            glass.setCornerRadius_(22.0)
            glass.setContentView_(self.card_content)
            root = glass
        except objc.nosuchclass_error:
            root = NSVisualEffectView.alloc().initWithFrame_(bounds)
            root.setMaterial_(MATERIAL_HUD_WINDOW)
            root.setBlendingMode_(BLENDING_BEHIND_WINDOW)
            root.setState_(STATE_ACTIVE)
            root.setWantsLayer_(True)
            root.layer().setCornerRadius_(22.0)
            root.layer().setMasksToBounds_(True)
            root.addSubview_(self.card_content)
        self.card.setContentView_(root)

    def _build_pointer(self):
        """A glowing ring that shows where Jarvis is about to click."""
        size = POINTER_SIZE
        self.pointer_panel = self._panel((0, 0, size, size), shadow=False)
        # Above the notch panel and everything else.
        self.pointer_panel.setLevel_(NSStatusWindowLevel + 2)
        ring = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, size, size))
        ring.setWantsLayer_(True)
        layer = ring.layer()
        layer.setCornerRadius_(size / 2)
        layer.setBorderWidth_(3.0)
        layer.setBorderColor_(POINTER_COLOR.CGColor())
        layer.setBackgroundColor_(POINTER_COLOR.colorWithAlphaComponent_(0.22).CGColor())
        dot = NSView.alloc().initWithFrame_(NSMakeRect(size / 2 - 3, size / 2 - 3, 6, 6))
        dot.setWantsLayer_(True)
        dot.layer().setCornerRadius_(3.0)
        dot.layer().setBackgroundColor_(POINTER_COLOR.CGColor())
        ring.addSubview_(dot)
        self.pointer_panel.setContentView_(ring)
        self._pointer_visible = False
        # Screen points are measured from the top of the menu-bar screen;
        # AppKit measures from the bottom.
        self._primary_height = NSScreen.screens()[0].frame().size.height

    # ---- animation ---------------------------------------------------------

    @staticmethod
    def _animate(window, frame=None, alpha=None, duration=0.32):
        def changes(context):
            context.setDuration_(duration)
            context.setAllowsImplicitAnimation_(True)
            if frame is not None:
                window.animator().setFrame_display_(_rect(frame), True)
            if alpha is not None:
                window.animator().setAlphaValue_(alpha)

        NSAnimationContext.runAnimationGroup_(changes)

    def _tick(self, timer):
        if self._state == "hidden":
            return
        if self._state == "listening":
            level = self._level()
            self.wave.levels = [
                min(1.0, level * shape * random.uniform(0.7, 1.15)) for shape in BAR_SHAPE
            ]
        elif self._state == "thinking":
            self._phase += 0.18
            self.wave.levels = [
                0.25 + 0.25 * math.sin(self._phase + i * 0.9) for i in range(BARS)
            ]
        else:
            self.wave.levels = [0.0] * BARS
        self.wave.setNeedsDisplay_(True)

    # ---- states (main thread only) ------------------------------------------

    def _set_island(self, state, label, color):
        self._generation += 1
        self._state = state
        self.wave.color = color
        self.mode_label.setStringValue_(label)
        self.mode_label.setTextColor_(color)
        self.island.orderFrontRegardless()
        self._animate(self.island, frame=self.expanded, alpha=1.0)

    def _show_card(self, title, body):
        inner = CARD_WIDTH - 2 * CARD_PADDING
        self.title_label.setStringValue_(title)
        self.body_label.setStringValue_(body)
        title_h = _text_height(self.title_label, inner) if title else 0
        body_h = min(_text_height(self.body_label, inner), CARD_MAX_BODY_HEIGHT)
        frame = card_frame(self.screen_x, self.screen_w, self.expanded[1], title_h, body_h)

        self.title_label.setFrame_(NSMakeRect(CARD_PADDING, CARD_PADDING, inner, title_h))
        self.body_label.setFrame_(
            NSMakeRect(CARD_PADDING, CARD_PADDING + title_h + 6, inner, body_h)
        )

        if not self._card_visible:
            # Start a little higher so the card drops into place.
            x, y, w, h = frame
            self.card.setFrame_display_(NSMakeRect(x, y + 12, w, h), True)
            self.card.orderFrontRegardless()
            self._card_visible = True
        self._animate(self.card, frame=frame, alpha=1.0)

    def _hide_card(self):
        if self._card_visible:
            self._card_visible = False
            self._animate(self.card, alpha=0.0, duration=0.2)

    def _listening(self, mode):
        self._set_island("listening", MODE_LABELS[mode], MODE_COLORS[mode])
        self._hide_card()

    def _thinking(self, heard):
        self._set_island("thinking", "Thinking", NSColor.whiteColor())
        if heard:
            self._show_card("You said", heard)
        else:
            self._hide_card()

    def _reply(self, text, heard):
        self._set_island("reply", "Jarvis", NSColor.whiteColor())
        self._show_card(heard, text)

    def _flash(self, text):
        self._set_island("reply", text, NSColor.whiteColor())
        self._hide_card()
        self._schedule_hide(1.2)

    def _error(self, text):
        self._set_island("reply", "Error", ERROR_COLOR)
        self._show_card("Something went wrong", text)
        self._schedule_hide(8.0)

    def _schedule_hide(self, after):
        generation = self._generation
        AppHelper.callLater(after, self._hide, generation)

    def _hide(self, generation):
        # Something newer has been shown since this hide was scheduled.
        if generation != self._generation:
            return
        self._state = "hidden"
        self._hide_card()
        self._animate(self.island, frame=self.collapsed, alpha=0.0, duration=0.28)

    def _status(self, title, body):
        self._set_island("thinking", "Working", NSColor.whiteColor())
        self._show_card(title, body)

    def _pointer_frame(self, x, y, size):
        return (x - size / 2, self._primary_height - y - size / 2, size, size)

    def _pointer(self, x, y, click):
        frame = self._pointer_frame(x, y, POINTER_SIZE)
        if not self._pointer_visible:
            self.pointer_panel.setFrame_display_(_rect(frame), True)
            self.pointer_panel.orderFrontRegardless()
            self._pointer_visible = True
            self._animate(self.pointer_panel, alpha=1.0, duration=0.15)
        else:
            self._animate(self.pointer_panel, frame=frame, alpha=1.0, duration=0.35)
        if click:
            # A quick pulse as the click lands.
            big = self._pointer_frame(x, y, POINTER_SIZE * 1.6)
            AppHelper.callLater(0.4, self._animate, self.pointer_panel, big, None, 0.1)
            AppHelper.callLater(0.52, self._animate, self.pointer_panel, frame, None, 0.15)

    def _pointer_hide(self):
        if self._pointer_visible:
            self._pointer_visible = False
            self._animate(self.pointer_panel, alpha=0.0, duration=0.3)

    # ---- public API (any thread) --------------------------------------------

    def status(self, title: str, body: str) -> None:
        AppHelper.callAfter(self._status, title, body)

    def pointer(self, x: float, y: float, click: bool = False) -> None:
        """Shows the pointer ring at screen point (x, y), measured from the top left."""
        AppHelper.callAfter(self._pointer, x, y, click)

    def pointer_hide(self) -> None:
        AppHelper.callAfter(self._pointer_hide)

    def run(self, main: Callable[[], None]) -> None:
        # AppKit needs the main thread, so the event loop takes it over
        # instead of `main`; the hotkey listener keeps running on its own.
        AppHelper.runEventLoop(installInterrupt=True)

    def set_level_source(self, level: Callable[[], float]) -> None:
        self._level = level

    def listening(self, mode: str) -> None:
        AppHelper.callAfter(self._listening, mode)

    def thinking(self, heard: str) -> None:
        AppHelper.callAfter(self._thinking, heard)

    def reply(self, text: str, heard: str = "") -> None:
        AppHelper.callAfter(self._reply, text, heard)

    def flash(self, text: str) -> None:
        AppHelper.callAfter(self._flash, text)

    def error(self, text: str) -> None:
        AppHelper.callAfter(self._error, text)

    def hide(self, after: float = 0.0) -> None:
        AppHelper.callAfter(self._schedule_hide, after)
