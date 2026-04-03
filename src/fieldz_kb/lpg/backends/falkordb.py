"""FalkorDB backend for fieldz_kb.

Example:
    >>> import fieldz_kb.lpg.session
    >>> import fieldz_kb.lpg.backends.falkordb
    >>> backend = fieldz_kb.lpg.backends.falkordb.FalkorDBBackend(hostname="localhost")
    >>> with fieldz_kb.lpg.session.Session(backend) as session:
    ...     session.save_from_object(person)
"""

import pylpg.backend.falkordb

FalkorDBBackend = pylpg.backend.falkordb.FalkorDBBackend
