"""Configuration and fixtures for pytest."""

import pytest


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


@pytest.fixture
def mock_neo4j_connection():
    """Fixture providing a mocked Neo4j connection."""
    from unittest.mock import Mock, patch

    with (
        patch("fieldz_kb.neo4j.core.neo4j.GraphDatabase") as mock_db,
        patch("fieldz_kb.neo4j.core.neomodel.db") as mock_neomodel,
    ):
        mock_driver = Mock()
        mock_db.return_value.driver.return_value = mock_driver

        yield {
            "driver": mock_driver,
            "neomodel_db": mock_neomodel,
        }
