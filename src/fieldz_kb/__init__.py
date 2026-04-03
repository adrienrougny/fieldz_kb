"""fieldz_kb - A library to store dataclass-like objects into knowledge bases.

This library provides functionality for converting Python dataclass-like objects
to graph database nodes and relationships, with support for:

- Basic types (int, str, float, bool)
- Collections (list, tuple, set, frozenset, dict)
- Enums
- Nested dataclasses
- Forward references
- Multiple backends (Neo4j, FalkorDB, FalkorDBLite)
- BioCypher integration

Example:
    >>> import dataclasses
    >>> import fieldz_kb.lpg.session
    >>> import fieldz_kb.lpg.backends.neo4j
    >>>
    >>> @dataclasses.dataclass
    >>> class Gene:
    >>>     name: str
    >>>     chromosome: int
    >>>
    >>> backend = fieldz_kb.lpg.backends.neo4j.Neo4jBackend(hostname="localhost")
    >>> with fieldz_kb.lpg.session.Session(backend) as session:
    >>>     gene = Gene(name="TP53", chromosome=17)
    >>>     session.save_from_object(gene)
"""
