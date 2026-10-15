"""The Jarvis app window: the orb, a feed of what Jarvis heard and did, and
settings. It also adds a menu-bar icon for opening the window and quitting.

The window is a WKWebView showing app.html. Python sends it events with
send(); the page sends settings changes back through a script message
handler named "jarvis". Everything here runs on the main thread.
"""

import json
import threading
from pathlib import Path

import objc
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSColor,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSScreen,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSWindow,
)
from WebKit import WKUserContentController, WKWebView, WKWebViewConfiguration

from . import prefs, voice
from .config import config

HTML = Path(__file__).with_name("app.html")

# NSWindowStyleMask: titled, closable, miniaturizable, resizable.
WINDOW_STYLE = 1 | 2 | 4 | 8
WIDTH, HEIGHT = 420, 640

WKScriptMessageHandler = objc.protocolNamed("WKScriptMessageHandler")


class _MessageHandler(NSObject, protocols=[WKScriptMessageHandler]):
    def initWithApp_(self, app):
        self = objc.super(_MessageHandler, self).init()
        if self is None:
            return None
        self.app = app
        return self

    def userContentController_didReceiveScriptMessage_(self, controller, message):
        try:
            self.app.handle(json.loads(str(message.body())))
        except Exception as error:
            print(f"App message failed: {error}")


class _MenuTarget(NSObject):
    def initWithApp_(self, app):
        self = objc.super(_MenuTarget, self).init()
        if self is None:
            return None
        self.app = app
        return self

    def openWindow_(self, sender):
        self.app.show()

    def quit_(self, sender):
        NSApplication.sharedApplication().terminate_(None)


class JarvisApp:
    def __init__(self, brain_info: dict):
        self.info = brain_info
        self.ready = False
        self.pending: list[dict] = []

        content = WKUserContentController.alloc().init()
        self.handler = _MessageHandler.alloc().initWithApp_(self)
        content.addScriptMessageHandler_name_(self.handler, "jarvis")
        configuration = WKWebViewConfiguration.alloc().init()
        configuration.setUserContentController_(content)

        screen = NSScreen.mainScreen().visibleFrame()
        frame = NSMakeRect(
            screen.origin.x + screen.size.width - WIDTH - 24,
            screen.origin.y + screen.size.height - HEIGHT - 24,
            WIDTH,
            HEIGHT,
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, WINDOW_STYLE, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Jarvis")
        self.window.setTitlebarAppearsTransparent_(True)
        self.window.setBackgroundColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(4 / 255, 6 / 255, 10 / 255, 1))
        self.window.setReleasedWhenClosed_(False)  # closing just hides it
        self.window.setMinSize_((340, 420))

        self.webview = WKWebView.alloc().initWithFrame_configuration_(
            self.window.contentView().bounds(), configuration
        )
        self.webview.setAutoresizingMask_(2 | 16)  # follow the window's size
        self.webview.setValue_forKey_(False, "drawsBackground")  # no white flash
        self.window.contentView().addSubview_(self.webview)
        self.webview.loadHTMLString_baseURL_(HTML.read_text(), None)

        self._build_menu_bar_icon()

    def _build_menu_bar_icon(self):
        self.menu_target = _MenuTarget.alloc().initWithApp_(self)
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        button = self.status_item.button()
        try:
            from AppKit import NSImage

            image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "circle.hexagongrid.fill", "Jarvis"
            )
            button.setImage_(image)
        except Exception:
            button.setTitle_("J")
        menu = NSMenu.alloc().init()
        for title, action, key in (("Open Jarvis", "openWindow:", "o"), ("Quit Jarvis", "quit:", "q")):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
            item.setTarget_(self.menu_target)
            menu.addItem_(item)
        self.status_item.setMenu_(menu)

    # ---- window ------------------------------------------------------------

    def show(self):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)

    def send(self, event: dict) -> None:
        """Passes an event to the page. Main thread only."""
        if not self.ready:
            if event.get("type") != "level":
                self.pending.append(event)
            return
        self.webview.evaluateJavaScript_completionHandler_(
            f"window.jarvis && window.jarvis.receive({json.dumps(event)})", None
        )

    # ---- messages from the page ----------------------------------------------

    def handle(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "ready":
            self.ready = True
            self.send(
                {
                    "type": "init",
                    "settings": prefs.all_values(),
                    "voices": voice.available_voices(),
                    "info": {**self.info, "engine": voice.engine()},
                }
            )
            for event in self.pending:
                self.send(event)
            self.pending.clear()
        elif kind == "setup":
            from . import setup

            try:
                setup.write_settings(
                    message.get("provider", ""), message.get("key", ""), message.get("model", "")
                )
            except ValueError as error:
                self.send({"type": "setup_error", "text": str(error)})
                return
            self.send({"type": "setup_done"})
            setup.relaunch()
        elif kind == "set":
            prefs.set(message["key"], message["value"])
            if message["key"] == "voice":
                voice.warm_up()
        elif kind == "test_voice":
            threading.Thread(
                target=voice.speak,
                args=("Good evening. All systems are online, and I'm ready when you are.",),
                daemon=True,
            ).start()


def available() -> bool:
    return config.is_mac
