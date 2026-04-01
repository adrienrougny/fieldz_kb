"""Neo4j pylpg backend for fieldz_kb.

Re-exports Session and Neo4jBackend for convenience.

Example:
    >>> from fieldz_kb.lpg.neo4j.pylpg import Session, Neo4jBackend
    >>> with Session(Neo4jBackend(hostname="localhost")) as session:
    ...     session.save_from_object(person)
"""

from fieldz_kb.lpg.pylpg.session import Session  # noqa: F401
from pylpg.backend.neo4j import Neo4jBackend  # noqa: F401
