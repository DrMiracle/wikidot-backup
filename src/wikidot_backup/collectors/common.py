from wikidot_backup.models.common import UserRef
from wikidot_backup.wikidot.models import WikidotUserData


def user_to_ref(
    user: WikidotUserData | None,
) -> UserRef | None:
    """Convert integration-layer user data into archive user metadata."""
    if user is None:
        return None

    return UserRef(
        id=user.id,
        name=user.name,
        unix_name=user.unix_name,
    )
