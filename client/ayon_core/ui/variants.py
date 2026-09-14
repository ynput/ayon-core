from enum import Enum


# VARIANTS DEFINITIONS --------------------------------------------------------


class QPushButtonVariants(Enum):
    Surface = "surface"
    Filled = "filled"
    Nav = "nav"
    Nav_Small = "nav-small"
    Danger = "danger"
    Tertiary = "tertiary"
    Text = "text"
    Checked = "checked"
    Tonal = "tonal"
    Thumbnail = "thumbnail"
    Entity_Card = "entity-card"
    Tag = "tag"
    Tag_Menu = "tag-menu"
    Table_Filter = "table-filter"
    Optional_Action = "optional-action"


class QCheckBoxVariants(Enum):
    Default = "default"
    Secondary = "secondary"
    Tertiary = "tertiary"
    Button = "button"
    Menu = "menu"


class QTextEditVariants(Enum):
    Default = "default"
    Low = "low"
    High = "high"
    Debug_R = "debug-r"
    Debug_G = "debug-g"
    Debug_B = "debug-b"


class QLineEditVariants(Enum):
    Default = "default"
    Search_Field = "search-field"


class QComboBoxVariants(Enum):
    Default = "default"
    Low = "low"


class QScrollBarVariants(Enum):
    Default = "default"


class QScrollAreaVariants(Enum):
    Default = "default"


class QFrameVariants(Enum):
    Default = "default"
    Low = "low"
    Low_Square = "low-square"
    Low_Framed = "low-framed"
    Low_Framed_Thin = "low-framed-thin"
    Low_Table_Editor = "low-table-editor"
    High = "high"
    Tag = "tag"
    Item_View = "item-view"
    Criterion = "criterion"
    Entity_Card = "entity-card"
    Entity_Card_Tag = "entity-card-tag"
    Surface = "surface"
    Contextual_Menu = "contextual-menu"
    Debug_R = "debug-r"
    Debug_G = "debug-g"
    Debug_B = "debug-b"


class QToolTipVariants(Enum):
    Default = "default"


class QMenuVariants(Enum):
    Default = "default"
    Danger = "danger"


class QLabelVariants(Enum):
    Default = "default"
    Tag = "tag"
    Badge = "badge"
    Pill = "pill"
    Entity_Label = "entity-label"
    Entity_Label_Filled = "entity-label-filled"
    Order_Option = "order-option"
    Optional_Action = "optional-action"


class QTreeViewVariants(Enum):
    Default = "default"
    Low = "low"
    High = "high"


class QStyledItemDelegateVariants(Enum):
    Default = "default"


class AYTableViewVariants(Enum):
    Default = "default"
    Low = "low"
    High = "high"


class AYUserImageVariants(Enum):
    Default = "default"
    Entity_Card = "entity-card"


class AsyncTaskQueueMonitorVariants(Enum):
    Default = "default"


class AYSliderVariants(Enum):
    Default = "default"
    Low = "low"


class AYPageButtonVariants(Enum):
    Default = "default"


class AYCardViewVariants(Enum):
    Default = "default"
    Low = "low"
    High = "high"


# END OF VARIANTs DEFINITIONS -------------------------------------------------


if __name__ == "__main__":
    # NOTE: Execute this file to update the variants.py file with the current
    # style data:
    #    uv run python -m client.ayon_core.ui.variants

    def update_variants_file(style_data):
        """Update the variants.py file with the current style data."""
        import os
        import inspect
        import re

        # get the path of the current file
        current_file = inspect.getfile(inspect.currentframe())
        current_dir = os.path.dirname(current_file)

        # load the current variants.py file
        with open(os.path.join(current_dir, "variants.py"), "r") as f:
            current = f.read()

        # get the start and end of the variants definitions
        start = current.find("# VARIANTS DEFINITIONS")
        end = current.find("# END OF VARIANTs DEFINITIONS")
        if start == -1 or end == -1:
            raise RuntimeError(
                "Could not find variants definitions in variants.py"
            )
        # adjust start to the end of the line
        start = current.find("\n", start) + 1

        # get the part before and after the variants definitions
        before = current[:start]
        after = current[end:]

        # generate all variants enums from style data
        defs = []
        for widget in style_data.widget_list():
            json_variants = style_data.widget_variants(widget)
            if not json_variants:
                continue

            defs.append(f"class {widget}Variants(Enum):\n")
            for variant in json_variants:
                # remove spaces and special characters
                field_name = re.sub(r"[^a-zA-Z0-9]", "_", variant).title()
                # avoid empty strings
                if variant == "":
                    field_name = "Default"
                defs.append(f'    {field_name} = "{variant}"\n')
            defs.append("\n\n")

        new = before + "\n\n" + "".join(defs) + after
        # print("-" * 80 + "\n" + new + "\n" + "-" * 80 + "\n")

        # write the new variants.py file
        with open(os.path.join(current_dir, "variants.py"), "w") as f:
            f.write(new)

    def check_variants_sync():
        """Check if the variants.py file is in sync with the style data."""
        from .style_types import get_ayon_style

        # Runtime sync assertion at import
        style_data = get_ayon_style().model
        enum_desync = False
        report = ""

        for widget in style_data.widget_list():
            json_variants = style_data.widget_variants(widget)
            if not json_variants:
                continue

            enum_name = f"{widget}Variants"

            # check if the enum exists for that widget class
            if enum_name not in globals():
                report += f"    Missing enum for {widget}\n"
                enum_desync = True
                continue

            # check if the enum values match the style data
            enum = globals()[enum_name]
            if set(json_variants) != {v.value for v in enum}:
                report += (
                    f"    Desync for {widget}: {json_variants} != {enum}\n"
                )
                enum_desync = True

        # print the report
        print("-" * 80)
        if enum_desync:
            update_variants_file(style_data)
            print("Variants are not in sync with the style data.\n")
            print(f"VARIANTS ANALYSIS {'_' * 62}\n" + report)
        else:
            print("Variants are in sync with the style data.")
        print("-" * 80)

    check_variants_sync()
