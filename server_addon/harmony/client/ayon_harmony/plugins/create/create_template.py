from ayon_harmony.api import plugin


class CreateTemplate(plugin.Creator):
    """Composite node for publishing to templates."""

    name = "templateDefault"
    label = "Template"
    product_type = "harmony.template"

    def __init__(self, *args, **kwargs):
        super(CreateTemplate, self).__init__(*args, **kwargs)
