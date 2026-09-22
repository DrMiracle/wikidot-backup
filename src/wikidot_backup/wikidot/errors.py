"""Expected remote failures that may fail one page without aborting a crawl."""
import httpx
from wikidot.common.exceptions import (
    AMCHttpStatusCodeException,
    ForbiddenException,
    NotFoundException,
    WikidotStatusCodeException,
)


class WikidotResourceError(RuntimeError):
    """A requested remote resource is unavailable or has changed identity."""


PAGE_COLLECTION_ERRORS = (
    WikidotResourceError, httpx.TransportError, httpx.HTTPStatusError,
    AMCHttpStatusCodeException, WikidotStatusCodeException,
    ForbiddenException, NotFoundException,
)
