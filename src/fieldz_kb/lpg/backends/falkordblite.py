"""FalkorDBLite backend for fieldz_kb.

Example:
    >>> import fieldz_kb.lpg.session
    >>> import fieldz_kb.lpg.backends.falkordblite
    >>> backend = fieldz_kb.lpg.backends.falkordblite.FalkorDBLiteBackend(path="/tmp/mydb")
    >>> with fieldz_kb.lpg.session.Session(backend) as session:
    ...     session.save_from_object(person)
"""

import pylpg.backend.falkordblite

FalkorDBLiteBackend = pylpg.backend.falkordblite.FalkorDBLiteBackend
