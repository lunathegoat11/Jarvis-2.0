# PyInstaller recipe for Jarvis.app. Build from the packaging folder:
#     pyinstaller --noconfirm Jarvis.spec
# The GitHub workflow in .github/workflows/build-mac.yml does this and wraps
# the result in Jarvis.dmg.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is set by PyInstaller

datas = [(str(ROOT / "jarvis" / "app.html"), "jarvis")]
binaries = []
hiddenimports = [
    "AppKit", "Foundation", "WebKit", "Quartz", "objc", "PyObjCTools.AppHelper",
    "pynput.keyboard._darwin", "pynput.mouse._darwin",
]
# Packages with native libraries or data files PyInstaller can't find alone.
for package in [
    "faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "av",
    "kokoro_onnx", "espeakng_loader", "phonemizer", "language_tags", "segments", "csvw",
    "sounddevice", "_sounddevice_data", "pynput", "mss",
]:
    try:
        d, b, h = collect_all(package)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["jarvis_app.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Jarvis",
    console=False,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Jarvis")
app = BUNDLE(
    coll,
    name="Jarvis.app",
    icon=str(Path(SPECPATH) / "Jarvis.icns"),  # noqa: F821
    bundle_identifier="com.lunathegoat11.jarvis",
    info_plist={
        "CFBundleName": "Jarvis",
        "CFBundleDisplayName": "Jarvis",
        "CFBundleShortVersionString": "2.0.0",
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,  # lives in the notch and menu bar, no Dock icon
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Jarvis listens while you hold its key.",
        "NSAppleEventsUsageDescription": "Jarvis uses Calendar, Reminders and Mail when you ask it to.",
        "NSScreenCaptureUsageDescription": "Jarvis looks at your screen when you ask about it or ask it to click something.",
    },
)
