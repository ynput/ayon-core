"""conftest.py: pytest configuration file."""
import sys
from pathlib import Path

from dotenv import load_dotenv

tests_path = Path(__file__).resolve().parent
client_path = tests_path.parent / "client"

# add client path to sys.path
sys.path.append(str(client_path))

# e.g. AYON_SERVER_URL and AYON_API_KEY for tests using a live server,
# variables already set in the environment take precedence
load_dotenv(tests_path / ".env", override=False)
