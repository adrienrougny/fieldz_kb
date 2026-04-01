"""Tests for fieldz_kb pylpg backend using real Neo4j database.

These tests require a running Neo4j instance and credentials in tests/credentials.py.
Run with: pytest tests/test_neo4j_pylpg_core.py -v
"""

import enum
from dataclasses import dataclass
from typing import List

import pytest
import frozendict

from fieldz_kb.lpg.neo4j.pylpg import Session, Neo4jBackend
from fieldz_kb.lpg.pylpg import core


# Module-level dataclasses for forward reference testing
@dataclass
class PylpgCompany:
    name: str
    employees: List["PylpgEmployee"]


@dataclass
class PylpgEmployee:
    name: str
    department: str
    skills: List[str]


@pytest.fixture(scope="session")
def neo4j_pylpg_session():
    """Create a pylpg session connected to Neo4j."""
    from tests import credentials

    if (
        not hasattr(credentials, "URI")
        or not hasattr(credentials, "USERNAME")
        or not hasattr(credentials, "PASSWORD")
    ):
        pytest.skip("credentials.py must define URI, USERNAME, and PASSWORD")

    try:
        backend = Neo4jBackend(
            hostname=credentials.URI,
            username=credentials.USERNAME,
            password=credentials.PASSWORD,
        )
        session = Session(backend)
        with session:
            session.execute_query("RETURN 1")
    except Exception:
        pytest.skip("Neo4j server not available")

    return session


@pytest.fixture
def clear_database(neo4j_pylpg_session):
    """Clear database before and after each test."""
    with neo4j_pylpg_session:
        neo4j_pylpg_session.delete_all()
    yield
    with neo4j_pylpg_session:
        neo4j_pylpg_session.delete_all()


class TestNodeClassGeneration:
    """Tests for node class generation functions."""

    def test_get_or_make_node_class_from_builtin_int(self):
        node_class = core.get_or_make_node_class_from_type(int)
        assert node_class is core.Integer

    def test_get_or_make_node_class_from_builtin_str(self):
        node_class = core.get_or_make_node_class_from_type(str)
        assert node_class is core.String

    def test_get_or_make_node_class_from_builtin_float(self):
        node_class = core.get_or_make_node_class_from_type(float)
        assert node_class is core.Float

    def test_get_or_make_node_class_from_builtin_bool(self):
        node_class = core.get_or_make_node_class_from_type(bool)
        assert node_class is core.Boolean

    def test_get_or_make_node_class_caching(self):
        @dataclass
        class PylpgCachingPerson:
            name: str

        class1 = core.get_or_make_node_class_from_type(PylpgCachingPerson)
        class2 = core.get_or_make_node_class_from_type(PylpgCachingPerson)
        assert class1 is class2

    def test_make_node_class_from_fieldz_class(self):
        @dataclass
        class PylpgSimplePerson:
            name: str
            age: int

        node_class = core.get_or_make_node_class_from_type(PylpgSimplePerson)

        assert node_class.__name__ == "PylpgSimplePerson"
        assert issubclass(node_class, core.BaseNode)

    def test_make_node_class_from_enum(self):
        class PylpgColor(enum.Enum):
            RED = "red"
            GREEN = "green"
            BLUE = "blue"

        node_class = core.get_or_make_node_class_from_type(PylpgColor)

        assert node_class.__name__ == "PylpgColor"

    def test_make_node_class_from_enum_with_int_values(self):
        class PylpgPriority(enum.Enum):
            LOW = 1
            MEDIUM = 2
            HIGH = 3

        node_class = core.get_or_make_node_class_from_type(PylpgPriority)

        assert node_class.__name__ == "PylpgPriority"

    def test_enum_with_mixed_value_types_raises_error(self):
        class PylpgMixedEnum(enum.Enum):
            STRING = "string"
            NUMBER = 42

        with pytest.raises(ValueError, match="types of values must all be the same"):
            core.get_or_make_node_class_from_type(PylpgMixedEnum)


class TestMakeNodesFromObject:
    """Tests for converting objects to nodes."""

    def test_make_nodes_from_int(self):
        nodes, to_connect = core.make_nodes_from_object(42)

        assert len(nodes) == 1
        assert isinstance(nodes[0], core.Integer)
        assert nodes[0].value == 42
        assert len(to_connect) == 0

    def test_make_nodes_from_str(self):
        nodes, to_connect = core.make_nodes_from_object("hello")

        assert len(nodes) == 1
        assert isinstance(nodes[0], core.String)
        assert nodes[0].value == "hello"

    def test_make_nodes_from_float(self):
        nodes, to_connect = core.make_nodes_from_object(3.14)

        assert len(nodes) == 1
        assert isinstance(nodes[0], core.Float)
        assert nodes[0].value == 3.14

    def test_make_nodes_from_bool(self):
        nodes, to_connect = core.make_nodes_from_object(True)

        assert len(nodes) == 1
        assert isinstance(nodes[0], core.Boolean)
        assert nodes[0].value is True

    def test_make_nodes_from_simple_fieldz_object(self):
        @dataclass
        class PylpgSimpleNodePerson:
            name: str
            age: int

        person = PylpgSimpleNodePerson(name="Alice", age=30)
        nodes, to_connect = core.make_nodes_from_object(person)

        assert len(nodes) == 1
        node = nodes[0]
        assert isinstance(node, core.BaseNode)
        assert node.__class__.__name__ == "PylpgSimpleNodePerson"

    def test_make_nodes_from_list(self):
        data = [1, 2, 3]
        nodes, to_connect = core.make_nodes_from_object(data)

        assert len(nodes) == 4
        list_node = nodes[0]
        assert isinstance(list_node, core.List)

    def test_make_nodes_from_tuple(self):
        data = (1, 2, 3)
        nodes, to_connect = core.make_nodes_from_object(data)

        assert len(nodes) == 4
        tuple_node = nodes[0]
        assert isinstance(tuple_node, core.Tuple)

    def test_make_nodes_from_set(self):
        data = {1, 2, 3}
        nodes, to_connect = core.make_nodes_from_object(data)

        assert len(nodes) == 4
        set_node = nodes[0]
        assert isinstance(set_node, core.Set)

    def test_make_nodes_from_dict(self):
        data = {"a": 1, "b": 2}
        nodes, to_connect = core.make_nodes_from_object(data)
        dict_node = nodes[0]
        assert isinstance(dict_node, core.Dict)
        assert len(to_connect) > 0

    def test_make_nodes_from_frozendict(self):
        data = frozendict.frozendict({"x": 1, "y": 2})
        nodes, to_connect = core.make_nodes_from_object(data)

        frozen_node = nodes[0]
        assert isinstance(frozen_node, core.FrozenDict)

    def test_make_nodes_from_enum(self):
        class PylpgStatus(enum.Enum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        status = PylpgStatus.ACTIVE
        nodes, to_connect = core.make_nodes_from_object(status)

        assert len(nodes) == 1
        node = nodes[0]
        assert node.__class__.__name__ == "PylpgStatus"

    def test_make_nodes_with_integration_mode_hash(self):
        obj = frozenset([1, 2, 3])
        object_to_node = {}
        nodes1, _ = core.make_nodes_from_object(
            obj, integration_mode="hash", object_to_node=object_to_node
        )
        nodes2, _ = core.make_nodes_from_object(
            obj, integration_mode="hash", object_to_node=object_to_node
        )

        assert nodes1[0] is nodes2[0]

    def test_make_nodes_with_integration_mode_id(self):
        obj1 = [1, 2, 3]
        obj2 = [1, 2, 3]

        nodes1, _ = core.make_nodes_from_object(obj1, integration_mode="id")
        nodes2, _ = core.make_nodes_from_object(obj2, integration_mode="id")
        assert nodes1[0] is not nodes2[0]

    def test_unsupported_type_raises_error(self):
        class UnsupportedClass:
            pass

        with pytest.raises(ValueError, match="not supported"):
            core.make_nodes_from_object(UnsupportedClass())


class TestTypeMappings:
    """Tests for type to node class mappings."""

    def test_type_to_node_class_mappings(self):
        expected_mappings = {
            int: core.Integer,
            str: core.String,
            float: core.Float,
            bool: core.Boolean,
            list: core.List,
            tuple: core.Tuple,
            set: core.Set,
            frozenset: core.FrozenSet,
        }

        for type_, expected_class in expected_mappings.items():
            assert core._default_context.type_to_node_class[type_] == expected_class


@pytest.mark.usefixtures("clear_database")
class TestSaveAndRetrieve:
    """Tests for saving objects to Neo4j via pylpg and retrieving them."""

    def test_save_and_retrieve_simple_object(self, neo4j_pylpg_session):
        @dataclass
        class PylpgSavePerson:
            name: str
            age: int

        person = PylpgSavePerson(name="Alice", age=30)

        with neo4j_pylpg_session:
            neo4j_pylpg_session.save_from_object(person)

            results = neo4j_pylpg_session.execute_query(
                "MATCH (n:PylpgSavePerson) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_pylpg_session.make_object_from_node(results[0]["n"])
            assert isinstance(retrieved, PylpgSavePerson)
            assert retrieved.name == "Alice"
            assert retrieved.age == 30

    def test_save_and_retrieve_with_base_types(self, neo4j_pylpg_session):
        @dataclass
        class PylpgBaseTypesPerson:
            name: str
            age: int
            height: float
            is_active: bool

        person = PylpgBaseTypesPerson(
            name="Bob", age=25, height=1.75, is_active=True
        )

        with neo4j_pylpg_session:
            neo4j_pylpg_session.save_from_object(person)

            results = neo4j_pylpg_session.execute_query(
                "MATCH (n:PylpgBaseTypesPerson) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_pylpg_session.make_object_from_node(results[0]["n"])
            assert retrieved.name == "Bob"
            assert retrieved.age == 25
            assert retrieved.height == 1.75
            assert retrieved.is_active is True

    def test_save_and_retrieve_list(self, neo4j_pylpg_session):
        data = [1, 2, 3]

        with neo4j_pylpg_session:
            neo4j_pylpg_session.save_from_object(data)

            results = neo4j_pylpg_session.execute_query(
                "MATCH (n:List) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_pylpg_session.make_object_from_node(results[0]["n"])
            assert sorted(retrieved) == [1, 2, 3]

    def test_save_and_retrieve_enum(self, neo4j_pylpg_session):
        class PylpgSaveStatus(enum.Enum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        status = PylpgSaveStatus.ACTIVE

        with neo4j_pylpg_session:
            neo4j_pylpg_session.save_from_object(status)

            results = neo4j_pylpg_session.execute_query(
                "MATCH (n:PylpgSaveStatus) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_pylpg_session.make_object_from_node(results[0]["n"])
            assert retrieved is PylpgSaveStatus.ACTIVE

    def test_save_multiple_objects(self, neo4j_pylpg_session):
        @dataclass
        class PylpgMultiPerson:
            name: str

        persons = [PylpgMultiPerson(name="Alice"), PylpgMultiPerson(name="Bob")]

        with neo4j_pylpg_session:
            neo4j_pylpg_session.save_from_objects(persons)

            results = neo4j_pylpg_session.execute_query(
                "MATCH (n:PylpgMultiPerson) RETURN n", resolve_objects=True
            )
            assert len(results) == 2

    def test_save_with_relationships(self, neo4j_pylpg_session):
        @dataclass
        class PylpgRelAddress:
            street: str

        @dataclass
        class PylpgRelPerson:
            name: str
            address: PylpgRelAddress

        address = PylpgRelAddress(street="123 Main St")
        person = PylpgRelPerson(name="Alice", address=address)

        with neo4j_pylpg_session:
            neo4j_pylpg_session.save_from_object(person)

            results = neo4j_pylpg_session.execute_query(
                "MATCH (n:PylpgRelPerson) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            results = neo4j_pylpg_session.execute_query(
                "MATCH (n:PylpgRelAddress) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            results = neo4j_pylpg_session.execute_query(
                "MATCH (p:PylpgRelPerson)-[:HAS_ADDRESS]->(a:PylpgRelAddress) RETURN p, a",
                resolve_objects=True,
            )
            assert len(results) == 1


@pytest.mark.usefixtures("clear_database")
class TestComplexScenarios:
    """Complex integration scenarios."""

    def test_nested_fieldz_objects(self, neo4j_pylpg_session):
        @dataclass
        class PylpgScenarioAddress:
            street: str
            city: str

        @dataclass
        class PylpgScenarioPerson:
            name: str
            address: PylpgScenarioAddress

        person = PylpgScenarioPerson(
            name="Alice",
            address=PylpgScenarioAddress(street="123 Main St", city="NYC"),
        )

        with neo4j_pylpg_session:
            neo4j_pylpg_session.save_from_object(person)

            results = neo4j_pylpg_session.execute_query(
                "MATCH (n:PylpgScenarioPerson) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_pylpg_session.make_object_from_node(results[0]["n"])
            assert retrieved.name == "Alice"
            assert retrieved.address.street == "123 Main St"
            assert retrieved.address.city == "NYC"

    def test_list_of_fieldz_objects(self, neo4j_pylpg_session):
        @dataclass
        class PylpgScenarioItem:
            value: int

        items = [
            PylpgScenarioItem(value=1),
            PylpgScenarioItem(value=2),
            PylpgScenarioItem(value=3),
        ]

        with neo4j_pylpg_session:
            neo4j_pylpg_session.save_from_object(items)

            results = neo4j_pylpg_session.execute_query(
                "MATCH (n:List) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_pylpg_session.make_object_from_node(results[0]["n"])
            assert len(retrieved) == 3
            assert all(
                isinstance(item, PylpgScenarioItem) for item in retrieved
            )
            assert sorted([item.value for item in retrieved]) == [1, 2, 3]

    def test_dict_with_complex_values(self, neo4j_pylpg_session):
        @dataclass
        class PylpgDictPerson:
            name: str

        data = {
            "alice": PylpgDictPerson(name="Alice"),
            "bob": PylpgDictPerson(name="Bob"),
        }

        with neo4j_pylpg_session:
            neo4j_pylpg_session.save_from_object(data)

            results = neo4j_pylpg_session.execute_query(
                "MATCH (n:Dict) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_pylpg_session.make_object_from_node(results[0]["n"])
            assert "alice" in retrieved
            assert "bob" in retrieved

    def test_round_trip_complex_object(self, neo4j_pylpg_session):
        company = PylpgCompany(
            name="TechCorp",
            employees=[
                PylpgEmployee(
                    name="Alice",
                    department="Engineering",
                    skills=["Python", "Neo4j"],
                ),
                PylpgEmployee(
                    name="Bob",
                    department="Design",
                    skills=["Figma", "UI"],
                ),
            ],
        )

        with neo4j_pylpg_session:
            neo4j_pylpg_session.save_from_object(company)

            results = neo4j_pylpg_session.execute_query(
                "MATCH (n:PylpgCompany) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_pylpg_session.make_object_from_node(results[0]["n"])
            assert retrieved.name == "TechCorp"
            assert len(retrieved.employees) == 2
            employee_names = sorted([e.name for e in retrieved.employees])
            assert employee_names == ["Alice", "Bob"]


@pytest.mark.usefixtures("clear_database")
class TestExecuteQueryAsObjects:
    """Tests for execute_query_as_objects method."""

    def test_execute_query_as_objects(self, neo4j_pylpg_session):
        @dataclass
        class PylpgQueryPerson:
            name: str
            age: int

        persons = [
            PylpgQueryPerson(name="Alice", age=30),
            PylpgQueryPerson(name="Bob", age=25),
        ]

        with neo4j_pylpg_session:
            neo4j_pylpg_session.save_from_objects(persons)

            results = neo4j_pylpg_session.execute_query_as_objects(
                "MATCH (n:PylpgQueryPerson) RETURN n ORDER BY n.age"
            )

            assert len(results) == 2
            assert results[0][0].name == "Bob"
            assert results[1][0].name == "Alice"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
