"""Wrapper around :mod:`jsonschema`

Schemas are implicitly loaded from the /schema directory of this project.

Attributes:
    _cache: Cache of previously loaded schemas

Resources:
    http://json-schema.org/
    http://json-schema.org/latest/json-schema-core.html
    http://spacetelescope.github.io/understanding-json-schema/index.html

"""

import os
import re
import json
import logging

import jsonschema
import six

log_ = logging.getLogger(__name__)

ValidationError = jsonschema.ValidationError
SchemaError = jsonschema.SchemaError
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

_CACHED = False


def validate(data, schema=None):
    """Validate `data` with `schema`

    Arguments:
        data (dict): JSON-compatible data
        schema (str): DEPRECATED Name of schema. Now included in the data.

    Raises:
        ValidationError on invalid schema

    """
    if not _CACHED:
        _precache()

    root, schema = data["schema"].rsplit(":", 1)

    if isinstance(schema, six.string_types):
        schema = _cache[schema + ".json"]

    resolver = jsonschema.RefResolver(
        "",
        None,
        store=_cache,
        cache_remote=True
    )

    jsonschema.validate(data,
                        schema,
                        types={"array": (list, tuple)},
                        resolver=resolver)


_cache = {
    # A mock schema for docstring tests
    "_doctest.json": {
        "$schema": "http://json-schema.org/schema#",

        "title": "_doctest",
        "description": "A test schema",

        "type": "object",

        "additionalProperties": False,

        "required": ["key"],

        "properties": {
            "key": {
                "description": "A test key",
                "type": "string"
            }
        }
    }
}


def _precache():
    """Store available schemas in-memory for reduced disk access"""
    global _CACHED

    for schema in os.listdir(CURRENT_DIR):
        if schema.startswith(("_", ".")):
            continue
        if not schema.endswith(".json"):
            continue
        if not os.path.isfile(os.path.join(CURRENT_DIR, schema)):
            continue
        with open(os.path.join(CURRENT_DIR, schema)) as f:
            log_.debug("Installing schema '%s'.." % schema)
            _cache[schema] = json.load(f)
    _CACHED = True
