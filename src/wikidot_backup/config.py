"""Project-wide configuration defaults."""

TEXT_ENCODING = "utf-8"
TEXT_NEWLINE = "\n"

SOURCE_FORMAT = "wikidot"
SOURCE_FILENAME = "source.txt"

# Maximum number of page entries Wikidot ListPages returns on a single pagination page.
LIST_PAGES_PER_PAGE = 250

DEFAULT_OUTPUT_DIR = "backup"
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_REQUEST_DELAY = 0.5

# Network retry policy for transient Wikidot failures.
WIKIDOT_RETRY_ATTEMPTS = 4
WIKIDOT_RETRY_INITIAL_WAIT_SECONDS = 1.0
WIKIDOT_RETRY_MAX_WAIT_SECONDS = 10.0