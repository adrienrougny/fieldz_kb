"""fieldz_kb - A library to store dataclass-like objects into knowledge bases.

This library provides functionality for converting Python dataclass-like objects
to graph database nodes and relationships, with support for:

- Basic types (int, str, float, bool)
- Collections (list, tuple, set, frozenset, dict)
- Enums
- Nested dataclasses
- Forward references
- Multiple backends (Neo4j via neomodel or pylpg, FalkorDB, FalkorDBLite)
- BioCypher integration

Example:
    >>> from dataclasses import dataclass
    >>> from fieldz_kb.lpg.neo4j.pylpg import Session, Neo4jBackend
    >>>
    >>> @dataclass
    >>> class Person:
    >>>     name: str
    >>>     age: int
    >>>
    >>> backend = Neo4jBackend(hostname="localhost")
    >>> with Session(backend) as session:
    >>>     person = Person(name="Alice", age=30)
    >>>     session.save_from_object(person)
"""
