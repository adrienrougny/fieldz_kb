"""FalkorDB pylpg backend for fieldz_kb.

Re-exports Session and FalkorDBBackend for convenience.

Example:
    >>> from fieldz_kb.lpg.falkordb.pylpg import Session, FalkorDBBackend
    >>> with Session(FalkorDBBackend(hostname="localhost")) as session:
    ...     session.save_from_object(person)
"""

from fieldz_kb.lpg.pylpg.session import Session  # noqa: F401
from pylpg.backend.falkordb import FalkorDBBackend  # noqa: F401
