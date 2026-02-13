"""Configuration and fixtures for pytest."""

import pytest

import fieldz_kb.neo4j.core


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
def neo4j_connection():
    """Fixture providing a real Neo4j database connection.

    Requires credentials in tests/credentials.py:
    - URI: hostname of the Neo4j server
    - USERNAME: Neo4j username
    - PASSWORD: Neo4j password
    """
    from tests import credentials

    # Check if credentials exist
    if (
        not hasattr(credentials, "URI")
        or not hasattr(credentials, "USERNAME")
        or not hasattr(credentials, "PASSWORD")
    ):
        raise ValueError("credentials.py must define URI, USERNAME, and PASSWORD")

    # Connect to Neo4j
    driver = fieldz_kb.neo4j.core.connect(
        hostname=credentials.URI,
        username=credentials.USERNAME,
        password=credentials.PASSWORD,
    )

    yield driver

    # Cleanup: close the driver after all tests
    driver.close()


@pytest.fixture
def cleanup_neo4j_database(neo4j_connection):
    """Fixture that cleans up the Neo4j database before each test.

    This ensures test isolation by deleting all nodes and relationships
    before each test runs. Not autouse — neo4j tests use their own
    clear_database_before_tests fixture.
    """
    # Clean up before test
    fieldz_kb.neo4j.core.delete_all()

    yield

    # Clean up after test
    fieldz_kb.neo4j.core.delete_all()


@pytest.fixture
def mock_neo4j_connection():
    """Fixture providing a mocked Neo4j connection (kept for backwards compatibility)."""
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
