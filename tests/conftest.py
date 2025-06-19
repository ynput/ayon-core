"""conftest.py: pytest configuration file."""
import sys
from pathlib import Path

client_path = Path(__file__).resolve().parent.parent / "client"

# add client path to sys.path
sys.path.append(str(client_path))
