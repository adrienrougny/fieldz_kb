"""Configuration and fixtures for pytest."""

import pytest

from fieldz_kb.lpg.neo4j.neomodel import Session, NeomodelBackend


@pytest.fixture
def sample_person_class():
    """Fixture providing a sample Person dataclass."""
    from dataclasses import dataclass

    @dataclass
    class Person:
        name: str
        age: int

    return Person


@pytest.fixture
def sample_address_class():
    """Fixture providing a sample Address dataclass."""
    from dataclasses import dataclass

    @dataclass
    class Address:
        street: str
        city: str
        zip_code: str

    return Address


@pytest.fixture
def sample_color_enum():
    """Fixture providing a sample Color enum."""
    import enum

    class Color(enum.Enum):
        RED = "red"
        GREEN = "green"
        BLUE = "blue"

    return Color


@pytest.fixture
def sample_priority_enum():
    """Fixture providing a sample Priority enum with integer values."""
    import enum

    class Priority(enum.Enum):
        LOW = 1
        MEDIUM = 2
        HIGH = 3

    return Priority


@pytest.fixture(scope="session")
def neo4j_neomodel_session():
    """Fixture providing a neomodel Session connected to Neo4j.

    Requires credentials in tests/credentials.py:
    - URI: hostname of the Neo4j server
    - USERNAME: Neo4j username
    - PASSWORD: Neo4j password
    """
    from tests import credentials

    if (
        not hasattr(credentials, "URI")
        or not hasattr(credentials, "USERNAME")
        or not hasattr(credentials, "PASSWORD")
    ):
        raise ValueError("credentials.py must define URI, USERNAME, and PASSWORD")

    backend = NeomodelBackend(
        hostname=credentials.URI,
        username=credentials.USERNAME,
        password=credentials.PASSWORD,
    )
    return Session(backend)
