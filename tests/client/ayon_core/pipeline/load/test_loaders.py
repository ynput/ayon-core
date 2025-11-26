"""Test loaders in the pipeline module."""

from ayon_core.pipeline.load import LoaderPlugin


def test_is_compatible_loader():
    """Test if a loader is compatible with a given representation."""
    from ayon_core.pipeline.load import is_compatible_loader

    # Create a mock representation context
    context = {
        "loader": "test_loader",
        "representation": {"name": "test_representation"},
    }

    # Create a mock loader plugin
    class MockLoader(LoaderPlugin):
        name = "test_loader"
        version = "1.0.0"

        def is_compatible_loader(self, context):
            return True

    # Check compatibility
    assert is_compatible_loader(MockLoader(), context) is True


def test_complex_is_compatible_loader():
    """Test if a loader is compatible with a complex representation."""
    from ayon_core.pipeline.load import is_compatible_loader

    # Create a mock complex representation context
    context = {
        "loader": "complex_loader",
        "representation": {
            "name": "complex_representation",
            "extension": "exr"
        },
        "additional_data": {"key": "value"},
        "product": {
            "name": "complex_product",
            "productType": "foo",
            "productBaseType": "bar",
        },
    }

    # Create a mock loader plugin
    class ComplexLoaderA(LoaderPlugin):
        name = "complex_loaderA"

    # False because the loader doesn't specify any compatibility (missing
    # wildcard for product type and product base type)
    assert is_compatible_loader(ComplexLoaderA(), context) is False

    class ComplexLoaderB(LoaderPlugin):
        name = "complex_loaderB"
        product_types = {"*"}
        representations = {"*"}

    # True, it is compatible with any product type
    assert is_compatible_loader(ComplexLoaderB(), context) is True

    class ComplexLoaderC(LoaderPlugin):
        name = "complex_loaderC"
        product_base_types = {"*"}
        representations = {"*"}

    # True, it is compatible with any product base type
    assert is_compatible_loader(ComplexLoaderC(), context) is True

    class ComplexLoaderD(LoaderPlugin):
        name = "complex_loaderD"
        product_types = {"foo"}
        representations = {"*"}

    # legacy loader defining compatibility only with product type
    # is compatible provided the same product type is defined in context
    assert is_compatible_loader(ComplexLoaderD(), context) is False

    class ComplexLoaderE(LoaderPlugin):
        name = "complex_loaderE"
        product_types = {"foo"}
        representations = {"*"}

    # remove productBaseType from context to simulate legacy behavior
    context["product"].pop("productBaseType", None)

    assert is_compatible_loader(ComplexLoaderE(), context) is True
