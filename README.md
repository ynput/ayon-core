
AYON Core Addon
===============

AYON core provides the base building blocks for all other AYON addons and integrations and is responsible for discovery and initialization of other addons.

- Some of its key functions include:
- It is used as the main command line handler in [ayon-launcher](https://github.com/ynput/ayon-launcher) application.
- Provides publishing plugins that are available to all AYON integrations.
- Defines the base classes for new pipeline integrations
- Provides global hooks
- Provides universally available loaders and launcher actions
- Defines pipeline API used by other integrations
- Provides all graphical tools for artists
- Defines AYON QT styling
- A bunch more things

Together with [ayon-launcher](https://github.com/ynput/ayon-launcher) , they form the base of AYON pipeline and is one of few compulsory addons for AYON pipeline to be useful in a meaningful way.

AYON-core is a successor to [OpenPype repository](https://github.com/ynput/OpenPype) (minus all the addons) and still in the process of cleaning up of all references. Please bear with us during this transitional phase.

Logging
-------
AYON core configures logging of the process it runs in (AYON launcher CLI, tray, DCC hosts, publish jobs). Logging is structured ([structlog](https://www.structlog.org)), each record has a message and additional fields. Configuration uses the same environment variables as [ayon-launcher](https://github.com/ynput/ayon-launcher#logging), which configures logging before `ayon_core` is started.

### Usage
```python
from ayon_core.lib import Logger, log_span

log = Logger.get_logger(__name__)

# Message template, fields are rendered into the message
#   'Published modelMain v003', template is kept in 'message_template' field
log.info(
    "Published {product} v{version:03d}",
    product=product_name,
    version=version,
)
# '%s' style arguments are supported too, the message is not a template then
log.info("Loaded %s", product_name)

# Measure a block of code, logged as one record when the block ends
with log_span("thumbnail.fetch", key=key) as span:
    path = cache.get(key)
    span.set(cache_hit=bool(path))

# Works as a decorator, slow calls are logged at least as WARNING
@log_span("activities.load", slow_threshold=2.0)
def load_activities():
    ...
```
- Records of plain `logging` loggers are handled as well, without additional fields.

### Message templates
Message is a [Python format string](https://docs.python.org/3/library/string.html#format-string-syntax) with named fields, rendered with fields of the record. Log file and Vector contain the rendered message in `event`, the template in `message_template` and all fields, so records of the same message can be grouped (similar to [Serilog message templates](https://messagetemplates.org)).
- `{name}` - value of field `name`. Any field of the record can be used, also context fields.
- `{name:spec}` - value formatted by [format spec](https://docs.python.org/3/library/string.html#formatspec), e.g. `{duration:.2f}`, `{name:>10}`.
- `{name!r}`, `{name!s}`, `{name!a}` - `repr`, `str` or `ascii` of the value.
- `{{` and `}}` - literal braces.

Unlike `str.format`, rendering never raises and each field is handled on its own:
- Field without a value is kept as written, e.g. `{missing:03d}`. Fields not used by the template are only in log file and Vector.
- Value not matching its format spec is rendered by `str`.
- Only fields looked up by name are rendered, positional (`{}`, `{0}`), attribute (`{obj.name}`) and index (`{data[key]}`) fields are kept as written.
- Message without any field, or not valid format string (e.g. `Unclosed {`), is not a template and is kept as it is.

Templates are parsed once and cached. Prefer templates (or `%s` arguments) over f-strings: a disabled log level skips the call before formatting, while an f-string is always formatted, e.g. `log.debug(f"Data {anatomy_data}")` formats the whole dictionary even when DEBUG is disabled. An f-string message also has no `message_template` and no fields for grouping.


### Outputs
There are three outputs, additive to each other:
1. **Console** - human readable output to stderr.
2. **Log file** - one JSON object per line (NDJSON), enabled with `AYON_LOG_TO_FILE=1`.
3. **Vector** - JSON records sent to a [Vector](https://vector.dev) HTTP source, enabled by setting `AYON_VECTOR_LOG_URL`.


- Only the message is shown, additional fields (`key=value`) are not. Use message template to show them. Log file and Vector always contain all fields.
- Logger name is shown only with `DEBUG` log level.
- Message of spans contains their duration, e.g. `launcher.bootstrap (duration 3.65s)`. Log file and Vector keep the span name as `event` and the duration in `duration_ms`.
- Context fields (`site_id`, `session_id`, `trace_id`, `span_id`, `parent_span_id` and process context) are never shown in console.
- Timestamps are in local time. Log file and Vector use ISO 8601 in UTC.

### Environment variables
| Variable | Description | Default |
| --- | --- | --- |
| `AYON_LOG_LEVEL` | Log level of all outputs, a name (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) or a number (`10`). | `INFO`, or `DEBUG` when `AYON_DEBUG` is `1` |
| `AYON_LOG_CONSOLE` | `1` always adds console handler, `0` never adds it. | added when root logger has no handlers |
| `AYON_LOG_CONSOLE_STYLE` | `ayon` - compact layout, `structlog` - default structlog layout with padded log level, logger name and all fields always shown. | `ayon` |
| `AYON_LOG_CONSOLE_TIME_FORMAT` | [strftime](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes) format of console timestamps, e.g. `%H:%M:%S.%f`. Invalid format falls back to the default. | `%Y/%m/%d %H:%M:%S` |
| `AYON_LOG_TO_FILE` | Write logs to a file when set to `1`. | - |
| `AYON_LOG_RETENTION_DAYS` | Days after which old log files are removed, at least `1`. | `3` |
| `AYON_VECTOR_LOG_URL` | URL of Vector HTTP source, e.g. `http://localhost:8686`. | - |
| `AYON_SITE_ID` | Added to records as `site_id`. | `unknown` |
| `AYON_SESSION_ID` | Added to records as `session_id`, correlates records of related processes. | - |

Log files are stored in `logs` subfolder of AYON launcher local directory (`AYON_LAUNCHER_LOCAL_DIR`), e.g. `%LOCALAPPDATA%\Ynput\AYON\logs` on Windows. Each process writes its own file `ayon_<YYYYMMDD-HHMMSS>_<pid>.ndjson`, rotated at midnight.

Records are sent to Vector in batches as JSON arrays. When Vector is unreachable, records are dropped and sending is paused for a while. 

Development and testing notes
-----------------------------
There is `pyproject.toml` file in the root of the repository. This file is used to define the development environment and is used by `poetry` to create a virtual environment.
This virtual environment is used to run tests and to develop the code, to help with
linting and formatting. Dependencies defined here are not used in actual addon
deployment - for that you need to edit `./client/pyproject.toml` file. That file
will be then processed [ayon-dependencies-tool](https://github.com/ynput/ayon-dependencies-tool)
to create dependency package.

Right now, this file needs to by synced with dependencies manually, but in the future
we plan to automate process of development environment creation.
