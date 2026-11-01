import os
from pathlib import Path

# The app loads its config at import time and refuses to start without one,
# so point it at a test config before any test module imports it.
os.environ["SOCCER_WALLART_CONFIG"] = str(Path(__file__).parent / "config.test.yaml")
