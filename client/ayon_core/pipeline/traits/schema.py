"""Export trait definitions as JSON Schema and fingerprint them.

Traits are defined client side as dataclasses. To render traits stored
with representations, the server and the frontend need to know their
data model. This module converts trait classes to definitions with
a JSON Schema of the trait data (the data stored by
`Representation.traits_as_dict()`) and computes hashes used to detect
changes of already released trait versions:

    * ``schema`` - data model (properties, types, required, defaults,
      enum values) without descriptions and titles.
    * ``behavior`` - code of the trait class and its bases up to
      `TraitBase`, without docstrings, comments and meta class
      variables (``name``, ``description``, ``ui_hints``).
    * ``meta`` - name, description, field descriptions and UI hints.

The behavior hash is computed from tokens and not from `ast.dump()`,
because `ast.dump()` output differs between Python versions and DCCs
run older Python than CI.

Note:
    Module level functions called by trait methods are not covered by
    the behavior hash. Keep logic specific to a trait version inside
    the trait class.

"""
from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import io
import json
import pkgutil
import re
import textwrap
import tokenize
from dataclasses import MISSING, Field, fields, is_dataclass
from enum import Enum
from pathlib import PurePath
from typing import (
    Any,
    Iterable,
    Optional,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from . import trait as trait_module
from .trait import TraitBase

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

# Format of an object holding traits keyed by trait id, e.g. one item
# of `Bundle.items` serialized by `Representation.traits_as_dict()`.
TRAITS_FORMAT = "ayon-traits"

# Class variables describing the trait. They are covered by the meta
# hash, so they are left out from the behavior hash.
META_CLASS_VARS = frozenset({"name", "description", "ui_hints"})

# JSON Schema keywords which do not change validation.
_SCHEMA_META_KEYS = frozenset({"title", "description", "examples", "$comment"})
# Keywords with a mapping of sub-schemas.
_SCHEMA_MAP_KEYS = frozenset({"properties", "$defs", "patternProperties"})
# Keywords with a sub-schema.
_SCHEMA_NODE_KEYS = frozenset({"items", "additionalProperties", "not"})
# Keywords with a list of sub-schemas.
_SCHEMA_LIST_KEYS = frozenset({"anyOf", "oneOf", "allOf", "prefixItems"})

_DOC_SECTION_REGEX = re.compile(
    r"^(Args|Arguments|Attributes|Parameters):\s*$")
_DOC_ITEM_REGEX = re.compile(
    r"^(?P<name>\*{0,2}\w+)\s*(?:\((?P<type>.*)\))?\s*:\s*(?P<desc>.*)$")

_STRUCTURE_TOKENS = frozenset({tokenize.INDENT, tokenize.DEDENT})
_IGNORED_TOKENS = frozenset({
    tokenize.COMMENT,
    tokenize.NL,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
})


class TraitSchemaError(TypeError):
    """Trait cannot be converted to JSON Schema."""


def canonical_json(data: Any) -> str:
    """Serialize data to canonical JSON used for hashing.

    Args:
        data (Any): JSON serializable data.

    Returns:
        str: JSON with sorted keys and compact separators.

    """
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_text(text: str) -> str:
    """Return prefixed SHA-256 hash of the text.

    Args:
        text (str): Text to hash.

    Returns:
        str: Hash in ``sha256:<hex>`` format.

    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def hash_data(data: Any) -> str:
    """Return prefixed SHA-256 hash of the canonical JSON of the data.

    Args:
        data (Any): JSON serializable data.

    Returns:
        str: Hash in ``sha256:<hex>`` format.

    """
    return hash_text(canonical_json(data))


def is_trait_class(obj: Any) -> bool:
    """Check if the object is a concrete trait class.

    Args:
        obj (Any): Object to check.

    Returns:
        bool: True if the object is a trait class with a trait id.

    """
    return (
        inspect.isclass(obj)
        and issubclass(obj, TraitBase)
        and obj is not TraitBase
        and not inspect.isabstract(obj)
        and isinstance(getattr(obj, "id", None), str)
    )


def collect_trait_classes(
        module_names: Iterable[str]) -> list[type[TraitBase]]:
    """Collect trait classes defined in modules.

    Packages are imported with all their submodules. Only traits defined
    in the given modules (or their submodules) are returned, not traits
    they import from elsewhere.

    Args:
        module_names (Iterable[str]): Names of modules or packages.

    Returns:
        list[type[TraitBase]]: Trait classes sorted by trait id.

    """
    prefixes = []
    for module_name in module_names:
        module = importlib.import_module(module_name)
        prefixes.append(module_name)
        if hasattr(module, "__path__"):
            for module_info in pkgutil.walk_packages(
                    module.__path__, prefix=f"{module_name}."):
                importlib.import_module(module_info.name)

    found: dict[str, type[TraitBase]] = {}
    to_process: list[type] = [TraitBase]
    while to_process:
        current = to_process.pop()
        for subclass in current.__subclasses__():
            to_process.append(subclass)
            if not is_trait_class(subclass):
                continue
            module_name = subclass.__module__
            if any(
                module_name == prefix or module_name.startswith(f"{prefix}.")
                for prefix in prefixes
            ):
                found[str(getattr(subclass, "id"))] = subclass
    return [found[trait_id] for trait_id in sorted(found)]


def parse_docstring(doc: Optional[str]) -> tuple[str, dict[str, str]]:
    """Parse summary and attribute descriptions from Google docstring.

    Descriptions are taken from ``Attributes:`` and ``Args:`` sections.

    Args:
        doc (Optional[str]): Docstring.

    Returns:
        tuple[str, dict[str, str]]: The first paragraph of the docstring
            and descriptions by attribute name.

    """
    if not doc:
        return "", {}

    lines = inspect.cleandoc(doc).splitlines()
    summary_lines = []
    for line in lines:
        if not line.strip():
            break
        summary_lines.append(line.strip())
    summary = " ".join(summary_lines)

    descriptions: dict[str, str] = {}
    in_section = False
    item_indent = None
    current = None
    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if not stripped:
            continue
        if indent == 0:
            in_section = bool(_DOC_SECTION_REGEX.match(stripped))
            item_indent = None
            current = None
            continue
        if not in_section:
            continue
        if item_indent is None:
            item_indent = indent
        if indent == item_indent:
            match = _DOC_ITEM_REGEX.match(stripped)
            current = None
            if match:
                current = match["name"]
                descriptions[current] = match["desc"].strip()
        elif current is not None:
            descriptions[current] = (
                f"{descriptions[current]} {stripped}".strip())
    return summary, descriptions


def _get_class_docstring(trait_class: type) -> Optional[str]:
    doc = trait_class.__dict__.get("__doc__")
    # Dataclass generates a signature as docstring if there is none
    if not doc or doc.startswith(f"{trait_class.__name__}("):
        return None
    return doc


def _to_json_value(value: Any) -> Any:
    """Convert a default value to its serialized form."""
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, re.Pattern):
        return value.pattern
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    msg = f"Value {value!r} is not JSON serializable"
    raise TraitSchemaError(msg)


class _SchemaBuilder:
    """Convert trait classes to JSON Schema, collecting nested traits."""

    def __init__(self):
        self.defs: dict[str, dict[str, Any]] = {}

    def trait_schema(self, trait_class: type[TraitBase]) -> dict[str, Any]:
        doc_summary, doc_fields = parse_docstring(
            _get_class_docstring(trait_class))
        schema: dict[str, Any] = {
            "type": "object",
            "title": str(trait_class.name),
        }
        if doc_summary:
            schema["description"] = doc_summary

        properties: dict[str, Any] = {}
        required = []
        if is_dataclass(trait_class):
            try:
                type_hints = get_type_hints(trait_class)
            except Exception as exc:
                msg = (
                    f"Unable to resolve type hints of {trait_class.id}: {exc}"
                )
                raise TraitSchemaError(msg) from exc

            for field in fields(trait_class):
                prop = self._field_schema(
                    trait_class, field, type_hints.get(field.name, Any))
                description = (
                    field.metadata.get("description")
                    or doc_fields.get(field.name)
                )
                if description:
                    prop["description"] = description
                if field.metadata.get("title"):
                    prop["title"] = field.metadata["title"]
                properties[field.name] = prop
                if (
                    field.default is MISSING
                    and field.default_factory is MISSING
                ):
                    required.append(field.name)

        schema["properties"] = properties
        if required:
            schema["required"] = required
        return schema

    def _field_schema(
            self,
            trait_class: type,
            field: Field,
            type_hint: Any) -> dict[str, Any]:
        try:
            schema = self.type_schema(type_hint)
        except TraitSchemaError as exc:
            trait_id = getattr(trait_class, "id", trait_class.__name__)
            msg = f"{trait_id}.{field.name}: {exc}"
            raise TraitSchemaError(msg) from exc

        if field.default is not MISSING:
            schema["default"] = _to_json_value(field.default)
        elif field.default_factory is not MISSING:
            schema["default"] = _to_json_value(field.default_factory())
        return schema

    def type_schema(self, type_hint: Any) -> dict[str, Any]:  # noqa: C901, PLR0911, PLR0912
        """Convert a type hint to JSON Schema of its serialized value."""
        if type_hint is Any:
            return {}

        origin = get_origin(type_hint)
        args = get_args(type_hint)

        if origin is Union:
            options = [arg for arg in args if arg is not type(None)]
            nullable = len(options) != len(args)
            if len(options) == 1:
                schema = self.type_schema(options[0])
                return _make_nullable(schema) if nullable else schema
            schemas = [self.type_schema(arg) for arg in options]
            if nullable:
                schemas.append({"type": "null"})
            return {"anyOf": schemas}

        if origin in (list, tuple, set, frozenset):
            if (
                origin is tuple
                and len(args) == 2  # noqa: PLR2004
                and args[1] is Ellipsis
            ):
                args = args[:1]
            if origin is tuple and len(args) > 1:
                return {
                    "type": "array",
                    "prefixItems": [self.type_schema(arg) for arg in args],
                    "items": False,
                }
            item_hint = args[0] if args else Any
            if item_hint is TraitBase:
                # List of traits is serialized as traits keyed by id
                # (see `Bundle.as_dict()`).
                return _traits_schema()
            array_schema: dict[str, Any] = {"type": "array"}
            item_schema = self.type_schema(item_hint)
            if item_schema:
                array_schema["items"] = item_schema
            if origin in (set, frozenset):
                array_schema["uniqueItems"] = True
            return array_schema

        if origin is dict:
            schema = {"type": "object"}
            if len(args) == 2:  # noqa: PLR2004
                value_schema = self.type_schema(args[1])
                if value_schema:
                    schema["additionalProperties"] = value_schema
            return schema

        if origin is re.Pattern or type_hint is re.Pattern:
            return {"type": "string", "format": "regex"}

        if not inspect.isclass(type_hint):
            msg = f"Unsupported type hint {type_hint!r}"
            raise TraitSchemaError(msg)

        if type_hint is bool:
            return {"type": "boolean"}
        if type_hint is int:
            return {"type": "integer"}
        if type_hint is float:
            return {"type": "number"}
        if type_hint is str:
            return {"type": "string"}
        if type_hint is dict:
            return {"type": "object"}
        if type_hint in (list, tuple, set, frozenset):
            return {"type": "array"}
        if issubclass(type_hint, PurePath):
            return {"type": "string", "format": "path"}
        if issubclass(type_hint, Enum):
            # Enums are serialized by their names (`prepare_for_json`)
            return {
                "type": "string",
                "enum": [member.name for member in type_hint],
            }
        if type_hint is TraitBase:
            return _traits_schema()
        if is_trait_class(type_hint):
            return self.trait_ref(type_hint)

        msg = f"Unsupported type {type_hint.__name__}"
        raise TraitSchemaError(msg)

    def trait_ref(self, trait_class: type[TraitBase]) -> dict[str, Any]:
        trait_id = str(trait_class.id)
        if trait_id not in self.defs:
            # Placeholder prevents infinite recursion
            self.defs[trait_id] = {}
            self.defs[trait_id] = self.trait_schema(trait_class)
        return {"$ref": f"#/$defs/{trait_id}"}


def _make_nullable(schema: dict[str, Any]) -> dict[str, Any]:
    schema_type = schema.get("type")
    if isinstance(schema_type, str) and "$ref" not in schema:
        schema = dict(schema)
        schema["type"] = [schema_type, "null"]
        if "enum" in schema:
            schema["enum"] = [*schema["enum"], None]
        return schema
    return {"anyOf": [schema, {"type": "null"}]}


def _traits_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "format": TRAITS_FORMAT,
        "additionalProperties": {"type": "object"},
    }


def get_trait_schema(trait_class: type[TraitBase]) -> dict[str, Any]:
    """Get JSON Schema of data stored for the trait.

    Nested traits are stored in ``$defs`` keyed by their trait id.

    Args:
        trait_class (type[TraitBase]): Trait class.

    Returns:
        dict[str, Any]: JSON Schema.

    Raises:
        TraitSchemaError: If a field type cannot be converted.

    """
    builder = _SchemaBuilder()
    schema: dict[str, Any] = {"$schema": JSON_SCHEMA_DIALECT}
    schema.update(builder.trait_schema(trait_class))
    if builder.defs:
        schema["$defs"] = {
            trait_id: builder.defs[trait_id]
            for trait_id in sorted(builder.defs)
        }
    return schema


def get_trait_definition(trait_class: type[TraitBase]) -> dict[str, Any]:
    """Get definition of the trait exposed to the server.

    Args:
        trait_class (type[TraitBase]): Trait class.

    Returns:
        dict[str, Any]: Trait definition.

    """
    definition: dict[str, Any] = {
        "id": trait_class.id,
        "versionlessId": trait_class.get_versionless_id(),
        "version": trait_class.get_version(),
        "name": str(trait_class.name),
        "description": str(trait_class.description),
        "persistent": bool(getattr(trait_class, "persistent", True)),
        "schema": get_trait_schema(trait_class),
    }
    ui_hints = getattr(trait_class, "ui_hints", None)
    if ui_hints:
        definition["ui"] = _to_json_value(ui_hints)
    return definition


def strip_schema_meta(schema: Any) -> Any:
    """Remove keywords not affecting validation from JSON Schema.

    Args:
        schema (Any): JSON Schema or its part.

    Returns:
        Any: Schema without titles, descriptions and examples.

    """
    if not isinstance(schema, dict):
        return schema
    result = {}
    for key, value in schema.items():
        if key in _SCHEMA_META_KEYS:
            continue
        if key in _SCHEMA_MAP_KEYS and isinstance(value, dict):
            value = {
                name: strip_schema_meta(item) for name, item in value.items()
            }
        elif key in _SCHEMA_NODE_KEYS:
            value = strip_schema_meta(value)
        elif key in _SCHEMA_LIST_KEYS and isinstance(value, list):
            value = [strip_schema_meta(item) for item in value]
        result[key] = value
    return result


def get_schema_hash(definition: dict[str, Any]) -> str:
    """Hash of the trait data model.

    Args:
        definition (dict[str, Any]): Trait definition.

    Returns:
        str: Hash of the schema without meta keywords.

    """
    return hash_data({
        "persistent": definition.get("persistent", True),
        "schema": strip_schema_meta(definition.get("schema") or {}),
    })


def get_meta_hash(definition: dict[str, Any]) -> str:
    """Hash of the description, titles and UI hints of the trait.

    Args:
        definition (dict[str, Any]): Trait definition.

    Returns:
        str: Hash of the meta information.

    """
    return hash_data({
        "name": definition.get("name"),
        "description": definition.get("description"),
        "ui": definition.get("ui"),
        "schema": definition.get("schema"),
    })


def get_source_tokens(
        obj: Any, skip_class_vars: Iterable[str] = ()) -> list[str]:
    """Get normalized tokens of the source code of a class or function.

    Comments, blank lines, docstrings (any string expression
    statement) and the name of the class or function are left out, so
    they do not affect the hash. Class variables listed in
    `skip_class_vars` are left out from the body of the class.

    Args:
        obj (Any): Class or function.
        skip_class_vars (Iterable[str]): Names of class variables
            to leave out.

    Returns:
        list[str]: Tokens.

    """
    source = textwrap.dedent(inspect.getsource(obj))
    tree = ast.parse(source)
    skip_class_vars = set(skip_class_vars)

    skipped_lines: set[int] = set()

    def skip_node(node: ast.stmt) -> None:
        end_lineno = getattr(node, "end_lineno", None) or node.lineno
        skipped_lines.update(range(node.lineno, end_lineno + 1))

    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for statement in body:
            if (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ):
                skip_node(statement)
        if not isinstance(node, ast.ClassDef) or node not in tree.body:
            continue
        for statement in body:
            targets: list[ast.expr] = []
            if isinstance(statement, ast.AnnAssign):
                targets = [statement.target]
            elif isinstance(statement, ast.Assign):
                targets = statement.targets
            if any(
                isinstance(target, ast.Name) and target.id in skip_class_vars
                for target in targets
            ):
                skip_node(statement)

    tokens = []
    rename_next = False
    renamed = False
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in _IGNORED_TOKENS:
            continue
        if token.type in _STRUCTURE_TOKENS:
            # Keep indentation even on skipped lines, so adding
            # a docstring as the first statement doesn't change tokens.
            tokens.append(tokenize.tok_name[token.type])
            continue
        if token.start[0] in skipped_lines:
            continue
        if token.type == tokenize.NEWLINE:
            tokens.append("NEWLINE")
            continue
        if rename_next and token.type == tokenize.NAME:
            # Name of the class or function does not affect behavior
            tokens.append("NAME:<name>")
            rename_next = False
            renamed = True
            continue
        if (
            not renamed
            and token.type == tokenize.NAME
            and token.string in ("class", "def")
        ):
            rename_next = True
        tokens.append(f"{tokenize.tok_name[token.type]}:{token.string}")
    return tokens


def get_behavior_hash(trait_class: type[TraitBase]) -> str:
    """Hash of the code of the trait class and its bases up to TraitBase.

    `TraitBase` itself is covered by `get_core_hash()`.

    Args:
        trait_class (type[TraitBase]): Trait class.

    Returns:
        str: Hash of the code.

    """
    parts = []
    for cls in trait_class.__mro__:
        if cls is TraitBase:
            break
        if cls.__module__ == "builtins":
            continue
        parts.append("\n".join(get_source_tokens(cls, META_CLASS_VARS)))
    return hash_text("\n\n".join(parts))


def get_core_hash() -> str:
    """Hash of the code shared by all traits.

    It covers `TraitBase` and the helpers used to restore traits
    from data. Changes there can affect every trait.

    Returns:
        str: Hash of the code.

    """
    objects = (
        TraitBase,
        trait_module._get_field_type_hints,  # noqa: SLF001
        trait_module._convert_value,  # noqa: SLF001
    )
    parts = [
        f"{obj.__qualname__}\n" + "\n".join(get_source_tokens(obj))
        for obj in objects
    ]
    return hash_text("\n\n".join(parts))


def get_trait_hashes(
        trait_class: type[TraitBase],
        definition: Optional[dict[str, Any]] = None) -> dict[str, str]:
    """Get all hashes of the trait.

    Args:
        trait_class (type[TraitBase]): Trait class.
        definition (Optional[dict[str, Any]]): Definition of the trait,
            created if not passed.

    Returns:
        dict[str, str]: Hashes by kind (``schema``, ``behavior``, ``meta``).

    """
    if definition is None:
        definition = get_trait_definition(trait_class)
    return {
        "schema": get_schema_hash(definition),
        "behavior": get_behavior_hash(trait_class),
        "meta": get_meta_hash(definition),
    }
