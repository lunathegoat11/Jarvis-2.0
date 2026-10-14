import sys

if sys.argv[1:] == ["models"]:
    # `python -m jarvis models` lists what the configured provider offers.
    from .brain import make_brain
    from .models import list_models

    brain = make_brain()
    if not hasattr(brain.client, "models"):
        raise SystemExit("This provider can't list its models.")
    for name in list_models(brain.client):
        print(name)
else:
    from .main import main

    main()
