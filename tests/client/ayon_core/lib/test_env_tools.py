import unittest
from unittest.mock import patch

from ayon_core.lib.env_tools import (
    CycleError,
    DynamicKeyClashError,
    parse_env_variables_structure,
    compute_env_variables_structure,
)

# --- Test data ---
COMPUTE_SRC_ENV = {
    "COMPUTE_VERSION": "1.0.0",
    # Will be available only for darwin
    "COMPUTE_ONE_PLATFORM": {
        "darwin": "Compute macOs",
    },
    "COMPUTE_LOCATION": {
        "darwin": "/compute-app-{COMPUTE_VERSION}",
        "linux": "/usr/compute-app-{COMPUTE_VERSION}",
        "windows": "C:/Program Files/compute-app-{COMPUTE_VERSION}"
    },
    "PATH_LIST": {
        "darwin": ["{COMPUTE_LOCATION}/bin", "{COMPUTE_LOCATION}/bin2"],
        "linux": ["{COMPUTE_LOCATION}/bin", "{COMPUTE_LOCATION}/bin2"],
        "windows": ["{COMPUTE_LOCATION}/bin", "{COMPUTE_LOCATION}/bin2"],
    },
    "PATH_STR": {
        "darwin": "{COMPUTE_LOCATION}/bin:{COMPUTE_LOCATION}/bin2",
        "linux": "{COMPUTE_LOCATION}/bin:{COMPUTE_LOCATION}/bin2",
        "windows": "{COMPUTE_LOCATION}/bin;{COMPUTE_LOCATION}/bin2",
    },
}

# --- RESULTS ---
# --- Parse results ---
PARSE_RESULT_WINDOWS = {
    "COMPUTE_VERSION": "1.0.0",
    "COMPUTE_LOCATION": "C:/Program Files/compute-app-{COMPUTE_VERSION}",
    "PATH_LIST": "{COMPUTE_LOCATION}/bin;{COMPUTE_LOCATION}/bin2",
    "PATH_STR": "{COMPUTE_LOCATION}/bin;{COMPUTE_LOCATION}/bin2",
}

PARSE_RESULT_LINUX = {
    "COMPUTE_VERSION": "1.0.0",
    "COMPUTE_LOCATION": "/usr/compute-app-{COMPUTE_VERSION}",
    "PATH_LIST": "{COMPUTE_LOCATION}/bin:{COMPUTE_LOCATION}/bin2",
    "PATH_STR": "{COMPUTE_LOCATION}/bin:{COMPUTE_LOCATION}/bin2",
}

PARSE_RESULT_DARWIN = {
    "COMPUTE_VERSION": "1.0.0",
    "COMPUTE_ONE_PLATFORM": "Compute macOs",
    "COMPUTE_LOCATION": "/compute-app-{COMPUTE_VERSION}",
    "PATH_LIST": "{COMPUTE_LOCATION}/bin:{COMPUTE_LOCATION}/bin2",
    "PATH_STR": "{COMPUTE_LOCATION}/bin:{COMPUTE_LOCATION}/bin2",
}

# --- Compute results ---
COMPUTE_RESULT_WINDOWS = {
    "COMPUTE_VERSION": "1.0.0", 
    "COMPUTE_LOCATION": "C:/Program Files/compute-app-1.0.0",
    "PATH_LIST": "C:/Program Files/compute-app-1.0.0/bin;C:/Program Files/compute-app-1.0.0/bin2", 
    "PATH_STR": "C:/Program Files/compute-app-1.0.0/bin;C:/Program Files/compute-app-1.0.0/bin2"
}

COMPUTE_RESULT_LINUX = {
    "COMPUTE_VERSION": "1.0.0",
    "COMPUTE_LOCATION": "/usr/compute-app-1.0.0",
    "PATH_LIST": "/usr/compute-app-1.0.0/bin:/usr/compute-app-1.0.0/bin2",
    "PATH_STR": "/usr/compute-app-1.0.0/bin:/usr/compute-app-1.0.0/bin2"
}

COMPUTE_RESULT_DARWIN = {
    "COMPUTE_VERSION": "1.0.0",
    "COMPUTE_ONE_PLATFORM": "Compute macOs",
    "COMPUTE_LOCATION": "/compute-app-1.0.0",
    "PATH_LIST": "/compute-app-1.0.0/bin:/compute-app-1.0.0/bin2",
    "PATH_STR": "/compute-app-1.0.0/bin:/compute-app-1.0.0/bin2"
}


class EnvParseCompute(unittest.TestCase):
    def test_parse_env(self):
        with patch("platform.system", return_value="windows"):
            result = parse_env_variables_structure(COMPUTE_SRC_ENV)
            assert result == PARSE_RESULT_WINDOWS

        with patch("platform.system", return_value="linux"):
            result = parse_env_variables_structure(COMPUTE_SRC_ENV)
            assert result == PARSE_RESULT_LINUX

        with patch("platform.system", return_value="darwin"):
            result = parse_env_variables_structure(COMPUTE_SRC_ENV)
            assert result == PARSE_RESULT_DARWIN

    def test_compute_env(self):
        with patch("platform.system", return_value="windows"):
            result = compute_env_variables_structure(
                parse_env_variables_structure(COMPUTE_SRC_ENV)
            )
            assert result == COMPUTE_RESULT_WINDOWS

        with patch("platform.system", return_value="linux"):
            result = compute_env_variables_structure(
                parse_env_variables_structure(COMPUTE_SRC_ENV)
            )
            assert result == COMPUTE_RESULT_LINUX

        with patch("platform.system", return_value="darwin"):
            result = compute_env_variables_structure(
                parse_env_variables_structure(COMPUTE_SRC_ENV)
            )
            assert result == COMPUTE_RESULT_DARWIN

    def test_cycle_error(self):
        with self.assertRaises(CycleError):
            compute_env_variables_structure({
                "KEY_1": "{KEY_2}",
                "KEY_2": "{KEY_1}",
            })

    def test_dynamic_key_error(self):
        with self.assertRaises(DynamicKeyClashError):
            compute_env_variables_structure({
                "KEY_A": "Occupied",
                "SUBKEY": "A",
                "KEY_{SUBKEY}": "Resolves as occupied key",
            })
