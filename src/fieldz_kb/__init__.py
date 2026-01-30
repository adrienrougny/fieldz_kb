"""fieldz_kb - A library to store dataclass-like objects into Neo4j knowledge bases.

This library provides functionality for converting Python dataclass-like objects
to Neo4j nodes and relationships, with support for:

- Basic types (int, str, float, bool)
- Collections (list, tuple, set, frozenset, dict)
- Enums
- Nested dataclasses
- Forward references
- BioCypher integration

Example:
    >>> from dataclasses import dataclass
    >>> import fieldz_kb.neo4j.core
    >>>
    >>> @dataclass
    >>> class Person:
    >>>     name: str
    >>>     age: int
    >>>
    >>> # Connect to Neo4j
    >>> driver = fieldz_kb.neo4j.core.connect("localhost", "neo4j", "password")
    >>>
    >>> # Save an object
    >>> person = Person(name="Alice", age=30)
    >>> fieldz_kb.neo4j.core.save_from_object(person)
"""
