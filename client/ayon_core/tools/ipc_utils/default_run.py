"""Run AYON Qt tools in an external process and control them via IPC events.

This is default script implementation. To allow custom handler use
    'IPCProcess' class as base to be able to change default behavior.
"""

import logging
from ayon_core.tools.ipc_utils.process import IPCProcess

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    """Entry-point of the external UI process."""
    process = IPCProcess()
    process.start_app()


if __name__ == "__main__":
    main()
