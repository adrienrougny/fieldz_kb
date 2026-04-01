"""FalkorDBLite pylpg backend for fieldz_kb.

Re-exports Session and FalkorDBLiteBackend for convenience.

Example:
    >>> from fieldz_kb.lpg.falkordblite.pylpg import Session, FalkorDBLiteBackend
    >>> with Session(FalkorDBLiteBackend(path="/tmp/mydb")) as session:
    ...     session.save_from_object(person)
"""

from fieldz_kb.lpg.pylpg.session import Session  # noqa: F401
from pylpg.backend.falkordblite import FalkorDBLiteBackend  # noqa: F401
