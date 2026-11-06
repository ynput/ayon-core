from __future__ import annotations

from fnmatch import fnmatchcase
import math
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

_WILDCARD_CHARS = ("*", "?")


def get_pretty_milliseconds(value: float) -> str:
    """Convert milliseconds to human readable string.

    Keeps roughly 3 significant digits so values have similar width.
        Breakpoints are compared against rounded values, so e.g. 999.6ms
        is shown as '1.00s' and not as '1000ms'.

    | Range       | Example  |
    |-------------|----------|
    | < 1ms       | 0.42ms   |
    | 1ms - 10ms  | 4.2ms    |
    | 10ms - 1s   | 42ms     |
    | 1s - 10s    | 4.20s    |
    | 10s - 1m    | 42.0s    |
    | 1m - 1h     | 4m 05s   |
    | >= 1h       | 1h 04m   |

    Args:
        value (float): Time in milliseconds.

    Returns:
        str: Human readable time.

    """
    value = max(value, 0.0)
    if value < 0.995:
        return f"{value:.2f}ms"
    if value < 9.95:
        return f"{value:.1f}ms"
    if value < 999.5:
        return f"{value:.0f}ms"

    seconds = value / 1000
    if seconds < 9.995:
        return f"{seconds:.2f}s"
    if seconds < 59.95:
        return f"{seconds:.1f}s"

    total_seconds = round(seconds)
    if total_seconds < 3600:
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}m {seconds:02d}s"

    hours, minutes = divmod(round(seconds / 60), 60)
    return f"{hours}h {minutes:02d}m"


def text_filter_matches(
    filter_text: str, values: Iterable[str | None]
) -> bool:
    """Check if any of the values matches the filter text.

    Matching is case-insensitive. Filter text without wildcard characters
    matches anywhere in a value (substring). If the filter text contains
    '*' or '?', it is matched against the whole value, e.g. 'foo*'
    matches only values starting with 'foo'. Other characters, including
    '[' and ']', are matched literally.

    Args:
        filter_text (str): Text to filter by. Empty text matches anything.
        values (Iterable[str | None]): Values to check, 'None' and empty
            values are ignored.

    Returns:
        bool: True if filter text is empty or any value matches.

    """
    filter_text = filter_text.strip().lower()
    if not filter_text:
        return True

    use_fnmatch = any(char in filter_text for char in _WILDCARD_CHARS)
    # Escape '[' so it is matched literally, only '*' and '?' are wildcards
    pattern = filter_text.replace("[", "[[]")
    for value in values:
        if not value:
            continue
        value = value.lower()
        if use_fnmatch:
            if fnmatchcase(value, pattern):
                return True
        elif filter_text in value:
            return True
    return False


# Process time range (milliseconds) mapped to the color gradient,
#   values are mapped on logarithmic scale and clamped.
PROCESS_TIME_FAST_MS = 10
PROCESS_TIME_SLOW_MS = 10_000  # 10 seconds

# Color stops of process time gradient (ratio, color). Stays grey until
#   about 1 second, then goes to orange and red.
PROCESS_TIME_COLOR_STOPS: list[tuple[float, str]] = [
    # '#888888' at 25% opacity over background '#2c313a'
    (0.0, "#43474e"),
    # Background hue ('#2c313a') with higher lightness
    (0.6, "#6e7a91"),
    (0.8, "#ff9900"),
    (1.0, "#ff4a4a"),
]


def get_process_time_ratio(process_time: float) -> float:
    """Map process time to 0.0 (fast) - 1.0 (slow) on logarithmic scale.

    Args:
        process_time (float): Process time in milliseconds.

    Returns:
        float: Ratio in range 0.0 - 1.0.

    """
    if process_time <= PROCESS_TIME_FAST_MS:
        return 0.0
    if process_time >= PROCESS_TIME_SLOW_MS:
        return 1.0

    low = math.log10(PROCESS_TIME_FAST_MS)
    high = math.log10(PROCESS_TIME_SLOW_MS)
    return (math.log10(process_time) - low) / (high - low)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
    )


def get_process_time_rgb(process_time: float) -> tuple[int, int, int]:
    """Get color for process time from the gradient.

    Args:
        process_time (float): Process time in milliseconds.

    Returns:
        tuple[int, int, int]: RGB color.

    """
    stops = PROCESS_TIME_COLOR_STOPS
    ratio = get_process_time_ratio(process_time)

    prev_pos, prev_color = stops[0]

    # value is lower than min
    if ratio <= prev_pos:
        return _hex_to_rgb(prev_color)

    for pos, color in stops[1:]:
        if ratio <= pos:

            start = _hex_to_rgb(prev_color)
            end = _hex_to_rgb(color)

            # blend ration
            span = pos - prev_pos
            t = (ratio - prev_pos) / span if span else 1.0

            # blend colors
            r = start[0] + (end[0] - start[0]) * t
            g = start[1] + (end[1] - start[1]) * t
            b = start[2] + (end[2] - start[2]) * t
            return round(r), round(g), round(b)

        prev_pos, prev_color = pos, color

    # value is higher than max
    return _hex_to_rgb(prev_color)
