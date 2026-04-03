"""Configuration and fixtures for pytest."""

import os
import dataclasses
import enum
import importlib.util
import urllib.parse

import pytest
import testcontainers.neo4j
import testcontainers.core.container
import testcontainers.core.waiting_utils

import pylpg.backend.neo4j
import pylpg.backend.falkordb
import pylpg.backend.falkordblite

import fieldz_kb.lpg.session

HAS_FALKORDBLITE = importlib.util.find_spec("redislite") is not None


@pytest.fixture(scope="session")
def neo4j_container():
    """Start a Neo4j container for the test session."""
    container = testcontainers.neo4j.Neo4jContainer("neo4j:5")
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="session")
def falkordb_container():
    """Start a FalkorDB container for the test session."""
    container = testcontainers.core.container.DockerContainer(
        "falkordb/falkordb:latest"
    )
    container.with_exposed_ports(6379)
    container.start()
    testcontainers.core.waiting_utils.wait_for_logs(
        container, "Ready to accept connections"
    )
    yield container
    container.stop()


@pytest.fixture(scope="session")
def neo4j_backend(neo4j_container):
    """Create a Neo4j backend connected to the test container."""
    if os.environ.get("CI"):
        return pylpg.backend.neo4j.Neo4jBackend(
            hostname="localhost",
            port=7687,
            username="neo4j",
            password="testpassword",
        )
    parsed = urllib.parse.urlparse(neo4j_container.get_connection_url())
    return pylpg.backend.neo4j.Neo4jBackend(
        hostname=parsed.hostname,
        port=parsed.port,
        protocol=parsed.scheme,
        username=neo4j_container.username,
        password=neo4j_container.password,
    )


@pytest.fixture(scope="session")
def falkordb_backend(falkordb_container):
    """Create a FalkorDB backend connected to the test container."""
    if os.environ.get("CI"):
        return pylpg.backend.falkordb.FalkorDBBackend(
            hostname="localhost",
            port=6379,
            database="test",
        )
    return pylpg.backend.falkordb.FalkorDBBackend(
        hostname=falkordb_container.get_container_host_ip(),
        port=int(falkordb_container.get_exposed_port(6379)),
        database="test",
    )


@pytest.fixture(scope="session")
def falkordblite_backend():
    """Create a FalkorDBLite backend using a temp file."""
    if not HAS_FALKORDBLITE:
        pytest.skip("redislite not installed")
    backend = pylpg.backend.falkordblite.FalkorDBLiteBackend(
        path="/tmp/test_falkordblite.db",
        database="test",
    )
    yield backend
    backend.close()


def _backend_params():
    """Build the list of available backend parameter names."""
    params = ["neo4j", "falkordb"]
    if HAS_FALKORDBLITE:
        params.append("falkordblite")
    return params


@pytest.fixture(params=_backend_params())
def backend(request):
    """Parameterized fixture providing each available backend."""
    return request.getfixturevalue(f"{request.param}_backend")


@pytest.fixture(scope="session")
def neo4j_session(neo4j_backend):
    """Create a fieldz_kb Session connected to Neo4j."""
    session = fieldz_kb.lpg.session.Session(neo4j_backend)
    session.__enter__()
    yield session
    session.__exit__(None, None, None)


@pytest.fixture(scope="session")
def falkordb_session(falkordb_backend):
    """Create a fieldz_kb Session connected to FalkorDB."""
    session = fieldz_kb.lpg.session.Session(falkordb_backend)
    session.__enter__()
    yield session
    session.__exit__(None, None, None)


@pytest.fixture(scope="session")
def falkordblite_session(falkordblite_backend):
    """Create a fieldz_kb Session connected to FalkorDBLite."""
    session = fieldz_kb.lpg.session.Session(falkordblite_backend)
    session.__enter__()
    yield session
    session.__exit__(None, None, None)


@pytest.fixture(params=_backend_params())
def session(request):
    """Parameterized fixture providing a session for each available backend."""
    return request.getfixturevalue(f"{request.param}_session")


@pytest.fixture
def clear_database(session):
    """Clear database before and after each test."""
    session.delete_all()
    yield
    session.delete_all()


@pytest.fixture
def sample_gene_class():
    """Fixture providing a sample Gene dataclass."""

    @dataclasses.dataclass
    class Gene:
        name: str
        chromosome: int

    return Gene


@pytest.fixture
def sample_protein_class():
    """Fixture providing a sample Protein dataclass."""

    @dataclasses.dataclass
    class Protein:
        name: str
        sequence: str
        molecular_weight: float

    return Protein


@pytest.fixture
def sample_compartment_enum():
    """Fixture providing a sample Compartment enum."""

    class Compartment(enum.Enum):
        CYTOPLASM = "cytoplasm"
        NUCLEUS = "nucleus"
        MEMBRANE = "membrane"

    return Compartment


@pytest.fixture
def sample_evidence_level_enum():
    """Fixture providing a sample EvidenceLevel enum with integer values."""

    class EvidenceLevel(enum.Enum):
        LOW = 1
        MEDIUM = 2
        HIGH = 3

    return EvidenceLevel
