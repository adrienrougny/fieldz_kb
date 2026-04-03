"""Neo4j backend for fieldz_kb.

Example:
    >>> import fieldz_kb.lpg.session
    >>> import fieldz_kb.lpg.backends.neo4j
    >>> backend = fieldz_kb.lpg.backends.neo4j.Neo4jBackend(hostname="localhost")
    >>> with fieldz_kb.lpg.session.Session(backend) as session:
    ...     session.save_from_object(person)
"""

import pylpg.backend.neo4j

Neo4jBackend = pylpg.backend.neo4j.Neo4jBackend
