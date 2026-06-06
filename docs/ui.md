# AYON Core UI (`ayon_core.ui`)

`ayon_core.ui` is the Qt widget library for AYON, designed to override Qt stylesheets of host
applications and preserve our UIs appearance.

It provides AYON-styled widgets, data models, and utility components for
building consistent desktop tools.

Most widgets use variants that can be defined and tweaked in `ayon_style.json`.

## Overview

`ayon_core.ui` packages reusable UI building blocks that mirror AYON's visual
language while staying native to Qt. It includes:

- A custom `QStyle` implementation (`AYONStyle`) and style helpers
- Component widgets (buttons, form controls, containers, cards, filters)
- Data-driven views and models for paginated tables and lazy trees
- Async task queue utilities for non-blocking model/view updates

## Quick Start

```python
from qtpy.QtWidgets import QApplication

from ayon_core.ui.style import get_ayon_style, style_widget_and_siblings
from ayon_core.ui.components.buttons import AYButton
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel

app = QApplication([])
app.setStyle(get_ayon_style())

container = AYContainer(
      layout=AYContainer.Layout.VBox,
      variant=AYContainer.Variants.Low,
      layout_margin=10,
      layout_spacing=8,
)

container.add_widget(
      AYButton("Run", variant=AYButton.Variants.Filled, icon="play_arrow")
)
container.add_widget(
      AYLabel("Ready", icon="check_circle", icon_color="#60c689")
)

style_widget_and_siblings(container)
container.show()
app.exec()
```

## Paginated Model API

`PaginatedTableModel` expects a page fetch callback with this signature:

```python
def fetch_page(
      page: int,
      page_size: int,
      sort_key: str | None,
      descending: bool,
      parent_id: str | None,
) -> list[dict]:
      ...
```

Optional batch callback (tree mode child fetches):

```python
from ayon_core.ui.components.table_model import BatchFetchRequest


def fetch_page_batch(
      requests: list[BatchFetchRequest],
) -> dict[str | None, list[dict]]:
      ...
```

Notes:

- Root-level fetch uses `fetch_page`
- Child-node fetches can be coalesced per event-loop tick using
   `fetch_page_batch`
- Use `reset_data()` when external context changes (project/folder/filter)

## Component Catalog

### Core Widgets

| Module | Main classes |
| --- | --- |
| `buttons.py` | `AYButton`, `AYButtonMenu` |
| `check_box.py` | `AYCheckBox` |
| `combo_box.py` | `AYComboBox`, `AYComboBoxModel` |
| `line_edit.py` | `AYLineEdit` |
| `text_edit.py` | `AYTextEdit` |
| `text_box.py` | `AYTextBox`, `AYTextEditor` |
| `label.py` | `AYLabel` |
| `frame.py` | `AYFrame` |
| `container.py` | `AYContainer` |
| `scroll_area.py` | `AYScrollArea`, `AYScrollBar` |

### Data Views and Models

| Module | Main classes |
| --- | --- |
| `table_model.py` | `PaginatedTableModel`, `TableColumn`, `BatchFetchRequest` |
| `table_view.py` | `AYTableView`, `AYTableHeader` |
| `table_filter.py` | `AYTableFilter`, `AYTableFilterProxyModel` |
| `tree_model.py` | `LazyTreeModel`, `TreeNode` |
| `tree_view.py` | `AYTreeView` |
| `card_view.py` | `AYCardView` |

### Entity and Content Widgets

| Module | Main classes |
| --- | --- |
| `entity_card.py` | `AYEntityCard` |
| `entity_path.py` | `AYEntityPath`, `AYEntityPathSegment` |
| `entity_thumbnail.py` | `AYEntityThumbnail` |
| `comment.py` | `AYComment` and related comment widgets |
| `comment_completion.py` | Comment completion helpers |
| `gallery_dialog.py` | `AYGalleryDialog` |
| `user_image.py` | `AYUserImage` |

### Filtering, Tags, and Selection

| Module | Main classes |
| --- | --- |
| `filter.py` | `AYFilter`, `AYFilterByCategory`, `FilterItem` |
| `filterable_list.py` | `AYFilterableList` |
| `tag.py` | `AYTag` |
| `tag_selector.py` | `AYTagSelector`, `TagData` |
| `slicer.py` | `AYSlicer` |
| `dropdown.py` | `AYDropdownPopup` |

### Layout and Utility Components

| Module | Main classes |
| --- | --- |
| `layouts.py` | `AYHBoxLayout`, `AYVBoxLayout`, `AYGridLayout`, `AYFlowLayout` |
| `task_queue.py` | `AsyncTaskQueue`, `AsyncTask`, queue helpers |
| `task_queue_monitor.py` | `AsyncTaskQueueMonitor` |
| `qss_override.py` | QSS/style event filter helpers |
| `checkbox_handler.py` | Checkbox event/data helpers |
| `screenshot_capture.py` | Widget screenshot capture helpers |

## Project Structure

```text
client/ayon_core/ui/
├── __init__.py
├── style.py
├── variants.py
├── image_cache.py
├── data_models.py
├── components/
│   ├── buttons.py
│   ├── check_box.py
│   ├── combo_box.py
│   ├── ...
├── resources/
│   └── ayon_style.json
└── vendor/
    └── qtmaterialsymbols/
```

## Variants Management

The concept of variants is borrowed from AYON's REACT library. A variant is a
version of a component with a different appearance. They act like preset
stylesheets.

Variants are defined in 2 files:

- `ayon_style.json` - defines the styles for each variant
  - This file contains:
    - global settings like the base font or the style's palette.
    - Per base class variants to modify the appearance of the component.
- `variants.py` - defines the variants and their properties
  - This file contains enums reflecting all available variants from `ayon_style.json`.
  - The enums can be automatically updated by running `variants.py`. The code
  in `__main__` will read `ayon_style.json` and update the enums if need be. It will also print a summary of the changes.

> [!IMPORTANT]
> Always run `variants.py` after modifying `ayon_style.json` to ensure the enums are up to date.

## Migration from `ayon-ui-qt` addon

This module was previously shipped as the standalone `ayon-ui-qt` addon. All
imports have moved:

```python
# Before (standalone addon)
from ayon_core.ui.components.buttons import AYButton
from ayon_core.ui.style import get_ayon_style

# After (integrated into core)
from ayon_core.ui.components.buttons import AYButton
from ayon_core.ui.style import get_ayon_style
```

## License

Apache-2.0

