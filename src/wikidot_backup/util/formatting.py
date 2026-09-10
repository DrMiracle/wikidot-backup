"""Formatting helpers for user-facing output."""


def format_bytes(size: int) -> str:
    """Format a byte count using binary units."""
    value = float(size)

    for unit in (
            "B",
            "KiB",
            "MiB",
            "GiB",
            "TiB",
    ):
        if value < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(value)} {unit}"

            return f"{value:.1f} {unit}"

        value /= 1024

    raise AssertionError("Unreachable")
