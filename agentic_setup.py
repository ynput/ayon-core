#!/usr/bin/env python
"""Set up agentic instructions and Spec Kit integration for this repo.

Requires Python 3.9+.

Cross-platform one-time setup for agentic development, replacing the
manual steps documented in ``SPEC_KIT.md``:

- ensure the shared AYON agent instructions repository
  (``ayon-agentic-instructions``) is cloned next to this repository
- link it as ``.agents-main`` (symlink on macOS/Linux; directory
  junction on Windows, which needs no administrator privileges)
- repair the tracked constitution link ``.specify/memory/constitution.md``
  (on Windows a real symlink is attempted first; if Developer Mode is
  not available the user is asked to enable it, copy the files
  instead, or skip)
- optionally install the ``specify`` CLI (via ``uv``) and run the
  integration install for the chosen agent harness (``--specify``)
- ensure ``.agents-main`` is ignored by git (``.git/info/exclude``)

Usage::

    python agentic_setup.py install
    python agentic_setup.py install --specify --integration=goose

Windows notes:

- ``.agents-main`` is created as a directory junction via
  ``cmd /c mklink /J`` — junctions need no administrator rights and
  no Developer Mode. Do **not** use ``ln -s`` in Git Bash: it copies
  instead of linking.
- The tracked ``.specify/memory/constitution.md`` symlink checks out
  as a plain text file on default Windows clones (Git probes and sets
  ``core.symlinks=false``). A real symlink is attempted first (works
  when Developer Mode is enabled); otherwise the user is asked to
  enable Developer Mode and retry, copy the constitution files
  instead (they are added to ``.gitignore`` and must be refreshed by
  re-running this script after shared-repo amendments), or skip —
  which also skips the specify installation.
"""

import argparse
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
from typing import List, Optional

CURRENT_ROOT: str = os.path.dirname(os.path.abspath(__file__))
IS_WINDOWS: bool = platform.system().lower() == "windows"


SHARED_REPO_URL: str = "https://github.com/ynput/ayon-agentic-instructions"
SHARED_REPO_DIR: str = os.path.join(
    CURRENT_ROOT, "..", "ayon-agentic-instructions"
)
AGENTS_MAIN: str = os.path.join(CURRENT_ROOT, ".agents-main")
AGENTS_MAIN_REL: str = "../ayon-agentic-instructions"
SPECIFY_CLI_URL: str = "git+https://github.com/github/spec-kit.git"
# Files of the shared constitution memory (names kept as in the shared
# repository). The first one is the tracked symlink target.
MEMORY_FILES: List[str] = [
    "ayon-constitution.md",
    "ayon-constitution-evidence.md",
]
CONSTITUTION_LINK: str = os.path.join(
    CURRENT_ROOT, ".specify", "memory", "constitution.md"
)
CONSTITUTION_REL_TARGET: str = "../../.agents-main/memory/{}"
GITIGNORE_COPIED: List[str] = [
    ".specify/memory/constitution.md",
    ".specify/memory/ayon-constitution-evidence.md",
]
DEFAULT_INTEGRATION: str = "copilot"

LOG = logging.getLogger("agentic_setup")


# ---------------------------------------------------------------------------
# Low level helpers
# ---------------------------------------------------------------------------

def _is_reparse_point(path: str) -> bool:
    """Check if a path is a Windows junction/reparse point."""
    if not IS_WINDOWS:
        return False
    try:
        st_attrs = os.lstat(path).st_file_attributes
    except OSError:
        return False
    return bool(st_attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _same_target(link_path: str, target_path: str) -> bool:
    """Check if a link (symlink or junction) points to target path."""
    try:
        real_link = os.path.realpath(link_path)
        real_target = os.path.realpath(target_path)
    except OSError:
        return False
    return os.path.normcase(real_link) == os.path.normcase(real_target)


def _remove_link(path: str) -> None:
    """Remove a symlink (or junction) without touching its target."""
    if IS_WINDOWS:
        # 'rmdir' removes the reparse point only, never the target.
        os.rmdir(path)
    else:
        os.remove(path)


def _run(
    args: List[str],
    cwd: Optional[str] = None,
    capture: bool = False,
) -> int:
    """Run a subprocess, streaming its output, return its exit code."""
    LOG.debug("Running: %s", " ".join(args))
    try:
        return subprocess.run(
            args,
            cwd=cwd or CURRENT_ROOT,
            check=False,
            **({"capture_output": True, "text": True} if capture else {}),
        ).returncode
    except OSError as error:
        LOG.error("Failed to run %r: %s", args[0], error)
        return 1


def _print(text: str) -> None:
    """Print to stdout and flush (for interactive prompts)."""
    print(text)
    sys.stdout.flush()


def _ask(question: str, default: str) -> str:
    """Ask the user a question, return their (lowercased) answer."""
    if not sys.stdin.isatty():
        return default
    try:
        return input("{}: ".format(question)).strip().lower()
    except EOFError:
        return default


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def ensure_shared_repo() -> bool:
    """Clone the shared instructions repository if it is missing."""
    if os.path.isfile(os.path.join(SHARED_REPO_DIR, "AGENTS.md")):
        LOG.info("Shared instructions found: %s", SHARED_REPO_DIR)
        return True
    if os.path.exists(SHARED_REPO_DIR):
        LOG.error(
            "%s exists but does not look like the shared instructions "
            "repository (no AGENTS.md). Fix or remove it manually.",
            SHARED_REPO_DIR,
        )
        return False
    if shutil.which("git") is None:
        LOG.error(
            "'git' not found. Install git or clone manually:\n"
            "    git clone %s %s", SHARED_REPO_URL, AGENTS_MAIN_REL,
        )
        return False
    LOG.info("Cloning shared instructions repository...")
    if _run(["git", "clone", SHARED_REPO_URL, SHARED_REPO_DIR]) != 0:
        LOG.error("Cloning of shared instructions failed.")
        return False
    return True


def setup_agents_main(force: bool = False) -> bool:
    """Create the '.agents-main' link to the shared instructions repo.

    Symlink on macOS/Linux, directory junction on Windows (junctions
    can be created by non-admin users and need no Developer Mode).
    """
    if os.path.exists(AGENTS_MAIN) or os.path.islink(AGENTS_MAIN):
        if os.path.islink(AGENTS_MAIN) or _is_reparse_point(AGENTS_MAIN):
            if _same_target(AGENTS_MAIN, SHARED_REPO_DIR):
                LOG.info("'.agents-main' link already OK, skipping.")
                return True
            if not force:
                LOG.warning(
                    "'.agents-main' exists but points elsewhere. "
                    "Re-run with --force to replace it."
                )
                return False
            _remove_link(AGENTS_MAIN)
        elif os.path.isdir(AGENTS_MAIN):
            LOG.error(
                "'.agents-main' is a REAL DIRECTORY (probably created by "
                "'ln -s' in Git Bash, which copies instead of linking). "
                "It will NOT receive shared-repo amendments. Re-run with "
                "--force to replace it with a proper link."
            )
            return False
        else:
            if not force:
                LOG.warning(
                    "'.agents-main' exists as a file. "
                    "Re-run with --force to replace it."
                )
                return False
            os.remove(AGENTS_MAIN)

    if IS_WINDOWS:
        result = _run([
            "cmd", "/c", "mklink", "/J", ".agents-main",
            os.path.abspath(SHARED_REPO_DIR),
        ])
    else:
        try:
            os.symlink(AGENTS_MAIN_REL, AGENTS_MAIN)
            result = 0
        except OSError as error:
            LOG.error("Could not create symlink: %s", error)
            result = 1
    if result == 0 and _same_target(AGENTS_MAIN, SHARED_REPO_DIR):
        LOG.info("'.agents-main' linked to shared instructions.")
        return True
    LOG.error("Failed to create '.agents-main' link.")
    return False


def _constitution_link_paths() -> List[str]:
    """Full paths of constitution memory files inside .specify/memory."""
    return [
        os.path.join(CURRENT_ROOT, ".specify", "memory", name)
        for name in MEMORY_FILES
    ]


def _ensure_gitignore_entries(paths: List[str]) -> None:
    """Add paths to the repository .gitignore (idempotent)."""
    path = os.path.join(CURRENT_ROOT, ".gitignore")
    lines = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    existing = {line.strip() for line in lines}
    missing = [p for p in paths if p not in existing]
    if not missing:
        return
    with open(path, "a", encoding="utf-8") as handle:
        if lines and lines[-1].strip():
            handle.write("\n")
        for entry in missing:
            handle.write(entry + "\n")
            LOG.info("Added %r to .gitignore", entry)


def _copy_constitution() -> None:
    """Copy constitution files from shared repo into .specify/memory."""
    for source_name, dest_path in zip(
        MEMORY_FILES, _constitution_link_paths()
    ):
        source = os.path.join(SHARED_REPO_DIR, "memory", source_name)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(source, dest_path)
        LOG.info("Copied %s", dest_path)
    # Copied files are 'tracked' in git - ignore them to avoid accidental
    # commits of machine-local copies.
    _ensure_gitignore_entries(GITIGNORE_COPIED)


def _create_constitution_links() -> bool:
    """Symlink constitution memory files into .specify/memory."""
    for source_name, dest_path in zip(
        MEMORY_FILES, _constitution_link_paths()
    ):
        target = CONSTITUTION_REL_TARGET.format(source_name)
        if os.path.islink(dest_path):
            if os.path.exists(dest_path):
                continue
            _remove_link(dest_path)
        elif os.path.exists(dest_path):
            os.remove(dest_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        try:
            os.symlink(target, dest_path)
        except OSError as error:
            LOG.error("Symlink for %s failed: %s", source_name, error)
            return False
    LOG.info("Constitution links created in .specify/memory.")
    return True


def _ask_constitution_fallback() -> str:
    """Ask what to do when a real symlink is not possible on Windows.

    Returns one of: 'retry', 'copy', 'skip'.
    """
    _print(
        "\nCould not create a real symlink for the constitution.\n"
        "This usually means Developer Mode is disabled.\n"
        "Options:\n"
        "  1) I enabled Developer Mode (Settings > System > For\n"
        "     developers) - retry the symlink\n"
        "  2) Copy the constitution files instead (amendments will not\n"
        "     propagate automatically; re-run this script after updates)\n"
        "  3) Skip (the specify installation will be skipped too)"
    )
    answer = _ask("Choose [1/2/3] (Enter = 3)", "3")
    if answer in ("1", "retry"):
        return "retry"
    if answer in ("2", "copy"):
        return "copy"
    return "skip"


def setup_constitution(mode: str) -> bool:
    """Repair the tracked constitution link '.specify/memory/...'.

    On macOS/Linux a symlink is used. On Windows a real symlink is
    attempted first (works when Developer Mode is enabled); otherwise
    the user chooses to retry after enabling Developer Mode, copy the
    files instead, or skip.
    """
    if os.path.islink(CONSTITUTION_LINK) and os.path.exists(
        CONSTITUTION_LINK
    ):
        LOG.info("Constitution link already OK, skipping.")
        return True

    if IS_WINDOWS:
        if os.path.islink(CONSTITUTION_LINK) and os.path.exists(
            CONSTITUTION_LINK
        ):
            LOG.info("Constitution symlink already OK, skipping.")
            return True
        while True:
            # Remove a plain-text/junk checked-out file first, then try
            # a real symlink (needs Developer Mode or elevation).
            if os.path.lexists(CONSTITUTION_LINK) and not os.path.islink(
                CONSTITUTION_LINK
            ):
                os.remove(CONSTITUTION_LINK)
            if _create_constitution_links():
                return True
            if mode == "symlink":
                LOG.error(
                    "Symlink creation failed. Enable Developer Mode "
                    "(Settings > System > For developers), or re-run "
                    "with --constitution=copy|skip."
                )
                return False
            choice = _ask_constitution_fallback()
            if choice == "retry":
                continue
            if choice == "copy":
                _copy_constitution()
                return True
            LOG.warning("Skipping constitution setup.")
            return False

    # macOS/Linux: fix only if the tracked symlink is missing or broken.
    if os.path.islink(CONSTITUTION_LINK):
        if os.path.exists(CONSTITUTION_LINK):
            LOG.info("Constitution link already OK, skipping.")
            return True
        _remove_link(CONSTITUTION_LINK)
    if os.path.exists(CONSTITUTION_LINK):
        LOG.warning(
            "'.specify/memory/constitution.md' exists but is not a "
            "symlink - replacing it with the correct symlink."
        )
        os.remove(CONSTITUTION_LINK)
    return _create_constitution_links()


def install_specify(integration: str, skills: bool) -> bool:
    """Install the 'specify' CLI (via uv) and the agent integration."""
    if shutil.which("specify") is None:
        uv_path = shutil.which("uv")
        if uv_path is None:
            LOG.error(
                "Neither 'specify' nor 'uv' was found on PATH.\n"
                "Install uv first, e.g.:\n"
                "  - macOS/Linux:  curl -LsSf "
                "https://astral.sh/uv/install.sh | sh\n"
                "  - Windows (PowerShell):  irm "
                "https://astral.sh/uv/install.ps1 | iex\n"
                "then re-run this command."
            )
            return False
        LOG.info("Installing 'specify' CLI via uv...")
        if _run([
            uv_path, "tool", "install", "specify-cli",
            "--from", SPECIFY_CLI_URL,
        ]) != 0:
            LOG.error("'specify' CLI installation failed.")
            return False
    else:
        LOG.info("'specify' CLI already installed, skipping.")

    args = ["specify", "integration", "install", integration]
    if skills:
        args.append("--integration-options=--skills")
    LOG.info("Installing integration: %s", integration)
    if _run(args) != 0:
        LOG.error(
            "Integration install failed. Check available integrations "
            "with: specify integration list"
        )
        return False
    LOG.info(
        "Integration installed. Verify the expected harness folder "
        "(e.g. .goose/, .github/skills/, ...) was created."
    )
    return True


def ensure_git_exclude() -> None:
    """Ensure '.agents-main' is ignored by git.

    No-op when .gitignore already ignores it; otherwise append it to
    '.git/info/exclude'.
    """
    if _run(["git", "check-ignore", "-q", "--", ".agents-main"]) == 0:
        LOG.debug("'.agents-main' already ignored via .gitignore.")
        return
    info_dir = os.path.join(CURRENT_ROOT, ".git", "info")
    os.makedirs(info_dir, exist_ok=True)
    exclude_path = os.path.join(info_dir, "exclude")
    lines = []
    if os.path.isfile(exclude_path):
        with open(exclude_path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    if "/.agents-main" in {line.strip() for line in lines}:
        return
    with open(exclude_path, "a", encoding="utf-8") as handle:
        if lines and lines[-1].strip():
            handle.write("\n")
        handle.write("/.agents-main\n")
    LOG.info("Added '/.agents-main' to .git/info/exclude")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def command_install(args: argparse.Namespace) -> int:
    """Handle the 'install' command."""
    if not ensure_shared_repo():
        return 1
    if not setup_agents_main(force=args.force):
        return 1
    if not setup_constitution(args.constitution):
        LOG.warning(
            "Constitution is not linked - skipping the specify "
            "installation step."
        )
        return 1
    ensure_git_exclude()
    if args.specify:
        if not install_specify(args.integration, args.skills):
            return 1
    LOG.info("Done.")
    return 0


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Set up agentic instructions and Spec Kit "
                    "integration for this repository."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser(
        "install",
        help="Clone/link shared instructions and set up the "
             "constitution.",
    )
    install.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing '.agents-main' link/directory.",
    )
    install.add_argument(
        "--specify",
        action="store_true",
        help="Also install the 'specify' CLI (via uv) and run the "
             "agent integration install.",
    )
    install.add_argument(
        "--integration",
        default=DEFAULT_INTEGRATION,
        help="Agent harness for 'specify integration install' "
             "(default: {}, see 'specify integration list').".format(
                 DEFAULT_INTEGRATION
             ),
    )
    install.add_argument(
        "--skills",
        action="store_true",
        help="Pass '--integration-options=--skills' to the specify "
             "install (for agents supporting skills mode).",
    )
    install.add_argument(
        "--constitution",
        default="ask",
        choices=["ask", "symlink", "copy", "skip"],
        help="Windows-only: what to do when a real constitution "
             "symlink cannot be created (Developer Mode disabled). "
             "'ask' prompts interactively; 'skip' also skips the "
             "specify installation. (default: ask)",
    )
    return parser.parse_args(argv)


def main() -> int:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s: %(message)s"
    )
    args = _parse_args()
    if args.command == "install":
        return command_install(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
