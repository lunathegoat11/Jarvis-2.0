import sys
import time

command = sys.argv[1:]

if command == ["models"]:
    # `python -m jarvis models` lists what the configured provider offers.
    from .brain import make_brain
    from .models import list_models

    brain = make_brain()
    if not hasattr(brain.client, "models"):
        raise SystemExit("This provider can't list its models.")
    for name in list_models(brain.client):
        print(name)

elif command == ["test"]:
    # `python -m jarvis test` checks the AI connection without a microphone.
    from .brain import make_brain
    from .config import config

    brain = make_brain()
    print(f"Provider: {config.provider}")
    print(f"Model: {brain.model}")
    print(f"Ask / screen model: {brain.vision_model}")
    for label, request in [
        ("Plain reply", lambda: brain.clean_dictation("um so this is uh a test")),
        ("Command with tools", lambda: brain.run_command("Save a note that says Jarvis test worked.")),
    ]:
        print(f"\n{label}...")
        started = time.monotonic()
        try:
            print(f"  -> {request()!r} ({time.monotonic() - started:.1f}s)")
        except Exception as error:
            print(f"  -> FAILED after {time.monotonic() - started:.1f}s: {error}")

else:
    from .main import main

    main()
