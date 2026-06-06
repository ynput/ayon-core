"""Tests for StyleDict class."""


from ayon_core.ui.style import StyleDict


class MockContext:
    """Mock context object for testing StyleDict."""

    def __init__(self):
        self.fg_color = "#FFFFFF"
        self.bg_color = "#000000"
        self.font_size = 12
        self.enabled = True
        self.missing_attr = None


class TestStyleDictBasics:
    """Test basic StyleDict functionality."""

    def test_init_empty(self):
        """Test initialization with no arguments."""
        d = StyleDict()
        assert len(d) == 0
        assert object.__getattribute__(d, "_context") is None

    def test_init_with_dict(self):
        """Test initialization with a dict."""
        d = StyleDict({"key": "value"})
        assert d["key"] == "value"

    def test_init_with_kwargs(self):
        """Test initialization with keyword arguments."""
        d = StyleDict(key="value", another="test")
        assert d["key"] == "value"
        assert d["another"] == "test"

    def test_init_with_context(self):
        """Test initialization with a context object."""
        ctx = MockContext()
        d = StyleDict(_context=ctx)
        assert object.__getattribute__(d, "_context") is ctx

    def test_init_with_dict_and_context(self):
        """Test initialization with both dict and context."""
        ctx = MockContext()
        d = StyleDict({"color": "@fg_color"}, _context=ctx)
        assert d["color"] == "#FFFFFF"

    def test_init_with_kwargs_and_context(self):
        """Test initialization with both kwargs and context."""
        ctx = MockContext()
        d = StyleDict(_context=ctx, color="@fg_color")
        assert d["color"] == "#FFFFFF"


class TestStyleDictNesting:
    """Test nested dict handling in StyleDict."""

    def test_nested_dict_conversion(self):
        """Test that nested dicts are converted to StyleDict."""
        d = StyleDict({"nested": {"key": "value"}})
        assert isinstance(d["nested"], StyleDict)

    def test_nested_dict_preserves_context(self):
        """Test that nested StyleDicts inherit parent context."""
        ctx = MockContext()
        d = StyleDict({"nested": {"color": "@fg_color"}}, _context=ctx)
        nested = d["nested"]
        assert isinstance(nested, StyleDict)
        assert nested["color"] == "#FFFFFF"

    def test_deeply_nested_dicts(self):
        """Test multiple levels of nesting."""
        ctx = MockContext()
        d = StyleDict(
            {"level1": {"level2": {"color": "@fg_color"}}}, _context=ctx
        )
        assert d["level1"]["level2"]["color"] == "#FFFFFF"

    def test_multiple_nested_dicts(self):
        """Test multiple nested dicts at the same level."""
        ctx = MockContext()
        d = StyleDict(
            {
                "style1": {"color": "@fg_color"},
                "style2": {"bg": "@bg_color"},
            },
            _context=ctx,
        )
        assert d["style1"]["color"] == "#FFFFFF"
        assert d["style2"]["bg"] == "#000000"


class TestStyleDictResolution:
    """Test @ reference resolution."""

    def test_resolve_attribute_reference(self):
        """Test that @ references are resolved via getattr."""
        ctx = MockContext()
        d = StyleDict({"color": "@fg_color"}, _context=ctx)
        assert d["color"] == "#FFFFFF"

    def test_resolve_multiple_references(self):
        """Test resolving multiple references."""
        ctx = MockContext()
        d = StyleDict(
            {"fg": "@fg_color", "bg": "@bg_color"}, _context=ctx
        )
        assert d["fg"] == "#FFFFFF"
        assert d["bg"] == "#000000"

    def test_resolve_non_string_value(self):
        """Test that non-string values are not affected."""
        ctx = MockContext()
        d = StyleDict(
            {"size": 12, "enabled": True, "items": [1, 2, 3]}, _context=ctx
        )
        assert d["size"] == 12
        assert d["enabled"] is True
        assert d["items"] == [1, 2, 3]

    def test_resolve_without_context(self):
        """Test that @ references are returned as-is without context."""
        d = StyleDict({"color": "@fg_color"})
        assert d["color"] == "@fg_color"

    def test_resolve_missing_attribute(self):
        """Test that missing attributes are returned as @ reference."""
        ctx = MockContext()
        d = StyleDict({"color": "@missing_attribute"}, _context=ctx)
        # getattr returns default if not found, so it returns "@missing_attribute"
        assert d["color"] == "@missing_attribute"

    def test_resolve_attribute_with_none_value(self):
        """Test resolving an attribute that has None value."""
        ctx = MockContext()
        d = StyleDict({"value": "@missing_attr"}, _context=ctx)
        # missing_attr is set to None on MockContext
        assert d["value"] is None

    def test_string_without_at_prefix(self):
        """Test that string values without @ are not resolved."""
        ctx = MockContext()
        d = StyleDict({"color": "red"}, _context=ctx)
        assert d["color"] == "red"

    def test_string_with_at_in_middle(self):
        """Test that @ in the middle of string is not special."""
        ctx = MockContext()
        d = StyleDict({"email": "test@example.com"}, _context=ctx)
        assert d["email"] == "test@example.com"


class TestStyleDictGet:
    """Test the get() method."""

    def test_get_existing_key(self):
        """Test get() with existing key."""
        d = StyleDict({"key": "value"})
        assert d.get("key") == "value"

    def test_get_missing_key_default_none(self):
        """Test get() with missing key returns None by default."""
        d = StyleDict({"key": "value"})
        assert d.get("missing") is None

    def test_get_missing_key_custom_default(self):
        """Test get() with missing key and custom default."""
        d = StyleDict({"key": "value"})
        assert d.get("missing", "default") == "default"

    def test_get_with_resolution(self):
        """Test get() resolves @ references."""
        ctx = MockContext()
        d = StyleDict({"color": "@fg_color"}, _context=ctx)
        assert d.get("color") == "#FFFFFF"

    def test_get_missing_key_with_resolution_does_not_fail(self):
        """Test get() on missing key doesn't try to resolve."""
        ctx = MockContext()
        d = StyleDict({"color": "@fg_color"}, _context=ctx)
        assert d.get("missing", "@undefined") == "@undefined"


class TestStyleDictSetContext:
    """Test the set_context() method."""

    def test_set_context(self):
        """Test setting context after initialization."""
        ctx1 = MockContext()
        ctx2 = MockContext()
        ctx2.fg_color = "#FF0000"

        d = StyleDict({"color": "@fg_color"}, _context=ctx1)
        assert d["color"] == "#FFFFFF"

        d.set_context(ctx2)
        assert d["color"] == "#FF0000"

    def test_set_context_to_none(self):
        """Test setting context to None."""
        ctx = MockContext()
        d = StyleDict({"color": "@fg_color"}, _context=ctx)
        assert d["color"] == "#FFFFFF"

        d.set_context(None)
        assert d["color"] == "@fg_color"

    def test_set_context_affects_nested_dicts(self):
        """Test that set_context affects nested StyleDicts."""
        ctx1 = MockContext()
        ctx2 = MockContext()
        ctx2.fg_color = "#FF0000"

        d = StyleDict(
            {"nested": {"color": "@fg_color"}}, _context=ctx1
        )
        assert d["nested"]["color"] == "#FFFFFF"

        d.set_context(ctx2)
        nested = d["nested"]
        nested_context = object.__getattribute__(nested, "_context")
        assert nested_context is ctx2


class TestStyleDictRepr:
    """Test the __repr__() method."""

    def test_repr_empty(self):
        """Test __repr__ for empty StyleDict."""
        d = StyleDict()
        repr_str = repr(d)
        assert "StyleDict" in repr_str
        assert "context=None" in repr_str

    def test_repr_with_data(self):
        """Test __repr__ with data."""
        d = StyleDict({"key": "value"})
        repr_str = repr(d)
        assert "StyleDict" in repr_str
        assert "key" in repr_str
        assert "value" in repr_str

    def test_repr_with_context(self):
        """Test __repr__ with context."""
        ctx = MockContext()
        d = StyleDict(_context=ctx)
        repr_str = repr(d)
        assert "StyleDict" in repr_str
        assert "context=" in repr_str


class TestStyleDictDictMethods:
    """Test dict-like behavior."""

    def test_contains(self):
        """Test 'in' operator."""
        d = StyleDict({"key": "value"})
        assert "key" in d
        assert "missing" not in d

    def test_keys(self):
        """Test keys() method."""
        d = StyleDict({"key1": "value1", "key2": "value2"})
        assert set(d.keys()) == {"key1", "key2"}

    def test_values(self):
        """Test values() method."""
        ctx = MockContext()
        d = StyleDict({"color": "@fg_color"}, _context=ctx)
        # values() returns raw values from dict, not resolved
        values_list = list(d.values())
        assert "@fg_color" in values_list

    def test_items(self):
        """Test items() method."""
        d = StyleDict({"key": "value"})
        items_list = list(d.items())
        assert ("key", "value") in items_list

    def test_len(self):
        """Test len() function."""
        d = StyleDict({"a": 1, "b": 2, "c": 3})
        assert len(d) == 3

    def test_iteration(self):
        """Test iterating over keys."""
        d = StyleDict({"a": 1, "b": 2, "c": 3})
        keys = [k for k in d]
        assert set(keys) == {"a", "b", "c"}

    def test_setitem(self):
        """Test setting items."""
        d = StyleDict()
        d["key"] = "value"
        assert super(StyleDict, d).__getitem__("key") == "value"

    def test_setitem_dict_converted_to_styledict(self):
        """Test that setting a dict value doesn't auto-convert to StyleDict."""
        d = StyleDict()
        d["nested"] = {"key": "value"}
        # Direct assignment doesn't convert, only in __init__
        assert isinstance(d["nested"], dict)
        assert not isinstance(d["nested"], StyleDict)


class TestStyleDictEdgeCases:
    """Test edge cases and error conditions."""

    def test_at_symbol_only(self):
        """Test value that is just '@'."""
        ctx = MockContext()
        d = StyleDict({"value": "@"}, _context=ctx)
        # @ with no attribute name - getattr should fail and return default
        assert d["value"] == "@"

    def test_numeric_attribute_name(self):
        """Test @ reference to numeric-looking attribute."""
        ctx = MockContext()
        d = StyleDict({"value": "@123"}, _context=ctx)
        assert d["value"] == "@123"  # No such attribute

    def test_complex_nested_structure(self):
        """Test complex nested structure with mixed references."""
        ctx = MockContext()
        d = StyleDict(
            {
                "style": {
                    "fg": "@fg_color",
                    "bg": "@bg_color",
                    "nested": {
                        "size": 12,
                        "color": "red",
                    },
                },
                "properties": {
                    "enabled": "@enabled",
                    "static": "static_value",
                },
            },
            _context=ctx,
        )
        assert d["style"]["fg"] == "#FFFFFF"
        assert d["style"]["bg"] == "#000000"
        assert d["style"]["nested"]["size"] == 12
        assert d["properties"]["enabled"] is True

    def test_dict_with_numeric_values(self):
        """Test that numeric values are preserved."""
        d = StyleDict({
            "int": 42,
            "float": 3.14,
            "negative": -10,
            "zero": 0,
        })
        assert d["int"] == 42
        assert d["float"] == 3.14
        assert d["negative"] == -10
        assert d["zero"] == 0

    def test_dict_with_none_values(self):
        """Test handling of None values."""
        d = StyleDict({
            "explicit_none": None,
            "implicit_none": None,
        })
        assert d["explicit_none"] is None
        assert d["implicit_none"] is None

    def test_empty_string_value(self):
        """Test empty string values."""
        d = StyleDict({"empty": ""})
        assert d["empty"] == ""

    def test_special_string_values(self):
        """Test special string values."""
        d = StyleDict({
            "newline": "line1\nline2",
            "tab": "col1\tcol2",
            "quote": 'He said "hello"',
        })
        assert d["newline"] == "line1\nline2"
        assert d["tab"] == "col1\tcol2"
        assert d["quote"] == 'He said "hello"'
