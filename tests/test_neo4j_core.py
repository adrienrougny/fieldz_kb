"""Tests for fieldz_kb neomodel backend using real Neo4j database.

These tests require a running Neo4j instance and credentials in tests/credentials.py.
Run with: pytest tests/test_neo4j_core.py -v
"""

import enum
from dataclasses import dataclass
from typing import List, Optional

import pytest
import fieldz
import frozendict

from fieldz_kb.lpg.neo4j.neomodel import core
from fieldz_kb.utils import _make_relationship_type_from_field_name


# Module-level dataclasses for forward reference testing
@dataclass
class Company:
    name: str
    employees: List["Employee"]


@dataclass
class Employee:
    name: str
    department: str
    skills: List[str]


@pytest.fixture
def clear_database(neo4j_neomodel_session):
    """Clear database before and after each test."""
    with neo4j_neomodel_session:
        neo4j_neomodel_session.delete_all()
    yield
    with neo4j_neomodel_session:
        neo4j_neomodel_session.delete_all()


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
        class CachingPerson:
            name: str

        class1 = core.get_or_make_node_class_from_type(CachingPerson)
        class2 = core.get_or_make_node_class_from_type(CachingPerson)
        assert class1 is class2

    def test_make_node_class_from_fieldz_class(self):
        @dataclass
        class SimplePerson:
            name: str
            age: int

        node_class = core.get_or_make_node_class_from_type(SimplePerson)

        assert node_class.__name__ == "SimplePerson"
        assert issubclass(node_class, core.BaseNode)
        assert hasattr(node_class, "name")
        assert hasattr(node_class, "age")

    def test_make_node_class_from_enum(self):
        class Color(enum.Enum):
            RED = "red"
            GREEN = "green"
            BLUE = "blue"

        node_class = core.get_or_make_node_class_from_type(Color)

        assert node_class.__name__ == "Color"
        assert hasattr(node_class, "name")
        assert hasattr(node_class, "value")

    def test_make_node_class_from_enum_with_int_values(self):
        class Priority(enum.Enum):
            LOW = 1
            MEDIUM = 2
            HIGH = 3

        node_class = core.get_or_make_node_class_from_type(Priority)

        assert node_class.__name__ == "Priority"
        assert hasattr(node_class, "name")
        assert hasattr(node_class, "value")

    def test_enum_with_mixed_value_types_raises_error(self):
        class MixedEnum(enum.Enum):
            STRING = "string"
            NUMBER = 42

        with pytest.raises(ValueError, match="types of values must all be the same"):
            core.get_or_make_node_class_from_type(MixedEnum)

    def test_make_node_class_with_list_field(self):
        @dataclass
        class ListPerson:
            name: str
            tags: List[str]

        node_class = core.get_or_make_node_class_from_type(ListPerson)

        assert hasattr(node_class, "name")
        assert hasattr(node_class, "tags")

    def test_make_node_class_with_optional_field(self):
        @dataclass
        class OptionalPerson:
            name: str
            nickname: Optional[str] = None

        node_class = core.get_or_make_node_class_from_type(OptionalPerson)

        assert hasattr(node_class, "name")
        assert hasattr(node_class, "nickname")


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
        class SimpleNodePerson:
            name: str
            age: int

        person = SimpleNodePerson(name="Alice", age=30)
        nodes, to_connect = core.make_nodes_from_object(person)

        assert len(nodes) == 1
        node = nodes[0]
        assert isinstance(node, core.BaseNode)
        assert node.__class__.__name__ == "SimpleNodePerson"

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
        class Status(enum.Enum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        status = Status.ACTIVE
        nodes, to_connect = core.make_nodes_from_object(status)

        assert len(nodes) == 1
        node = nodes[0]
        assert node.__class__.__name__ == "Status"

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


@pytest.mark.usefixtures("clear_database")
class TestSaveAndRetrieve:
    """Tests for saving objects to Neo4j and retrieving them."""

    def test_save_and_retrieve_simple_object(self, neo4j_neomodel_session):
        @dataclass
        class SavePerson:
            name: str
            age: int

        person = SavePerson(name="Alice", age=30)

        with neo4j_neomodel_session:
            neo4j_neomodel_session.save_from_object(person)

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (n:SavePerson) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_neomodel_session.make_object_from_node(results[0][0])
            assert isinstance(retrieved, SavePerson)
            assert retrieved.name == "Alice"
            assert retrieved.age == 30

    def test_save_and_retrieve_with_base_types(self, neo4j_neomodel_session):
        @dataclass
        class BaseTypesPerson:
            name: str
            age: int
            height: float
            is_active: bool

        person = BaseTypesPerson(name="Bob", age=25, height=1.75, is_active=True)

        with neo4j_neomodel_session:
            neo4j_neomodel_session.save_from_object(person)

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (n:BaseTypesPerson) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_neomodel_session.make_object_from_node(results[0][0])
            assert retrieved.name == "Bob"
            assert retrieved.age == 25
            assert retrieved.height == 1.75
            assert retrieved.is_active is True

    def test_save_and_retrieve_list(self, neo4j_neomodel_session):
        data = [1, 2, 3]

        with neo4j_neomodel_session:
            neo4j_neomodel_session.save_from_object(data)

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (n:List) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_neomodel_session.make_object_from_node(results[0][0])
            assert sorted(retrieved) == [1, 2, 3]

    def test_save_and_retrieve_enum(self, neo4j_neomodel_session):
        class SaveStatus(enum.Enum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        status = SaveStatus.ACTIVE

        with neo4j_neomodel_session:
            neo4j_neomodel_session.save_from_object(status)

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (n:SaveStatus) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_neomodel_session.make_object_from_node(results[0][0])
            assert retrieved is SaveStatus.ACTIVE

    def test_save_multiple_objects(self, neo4j_neomodel_session):
        @dataclass
        class MultiPerson:
            name: str

        persons = [MultiPerson(name="Alice"), MultiPerson(name="Bob")]

        with neo4j_neomodel_session:
            neo4j_neomodel_session.save_from_objects(persons)

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (n:MultiPerson) RETURN n", resolve_objects=True
            )
            assert len(results) == 2

    def test_save_with_relationships(self, neo4j_neomodel_session):
        @dataclass
        class RelAddress:
            street: str

        @dataclass
        class RelPerson:
            name: str
            address: RelAddress

        address = RelAddress(street="123 Main St")
        person = RelPerson(name="Alice", address=address)

        with neo4j_neomodel_session:
            neo4j_neomodel_session.save_from_object(person)

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (n:RelPerson) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (n:RelAddress) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (p:RelPerson)-[:HAS_ADDRESS]->(a:RelAddress) RETURN p, a",
                resolve_objects=True,
            )
            assert len(results) == 1


class TestRelationshipTypeGeneration:
    """Tests for relationship type name generation."""

    def test_simple_field_name(self):
        result = _make_relationship_type_from_field_name("name")
        assert result == "HAS_NAME"

    def test_camel_case_field_name(self):
        result = _make_relationship_type_from_field_name("firstName")
        assert result == "HAS_FIRSTNAME"

    def test_snake_case_field_name(self):
        result = _make_relationship_type_from_field_name("first_name")
        assert result == "HAS_FIRST_NAME"

    def test_plural_field_name(self):
        result = _make_relationship_type_from_field_name("children", many=True)
        assert result == "HAS_CHILD"

    def test_camel_case_plural(self):
        result = _make_relationship_type_from_field_name("userProfiles", many=True)
        assert "USER_PROFILE" in result


class TestNodePropertyGeneration:
    """Tests for node property generation."""

    def test_base_type_property(self):
        @dataclass
        class PropertyPerson:
            name: str

        field = fieldz.fields(PropertyPerson)[0]
        prop = core._default_context.make_node_property_from_field(field)

        assert prop is not None

    def test_array_type_property(self):
        @dataclass
        class ArrayPerson:
            tags: List[str]

        field = fieldz.fields(ArrayPerson)[0]
        prop = core._default_context.make_node_property_from_field(field)

        assert prop is not None

    def test_optional_property(self):
        @dataclass
        class OptionalNicknamePerson:
            nickname: Optional[str] = None

        field = fieldz.fields(OptionalNicknamePerson)[0]
        prop = core._default_context.make_node_property_from_field(field)

        assert prop is not None


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

    def test_property_class_mappings(self):
        import neomodel

        expected_mappings = {
            str: neomodel.StringProperty,
            int: neomodel.IntegerProperty,
            float: neomodel.FloatProperty,
            bool: neomodel.BooleanProperty,
        }

        for type_, expected_class in expected_mappings.items():
            assert (
                core._default_context.type_to_node_base_property_class[type_]
                == expected_class
            )


@pytest.mark.usefixtures("clear_database")
class TestComplexScenarios:
    """Complex integration scenarios."""

    def test_nested_fieldz_objects(self, neo4j_neomodel_session):
        @dataclass
        class ScenarioAddress:
            street: str
            city: str

        @dataclass
        class ScenarioPerson:
            name: str
            address: ScenarioAddress

        person = ScenarioPerson(
            name="Alice", address=ScenarioAddress(street="123 Main St", city="NYC")
        )

        with neo4j_neomodel_session:
            neo4j_neomodel_session.save_from_object(person)

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (n:ScenarioPerson) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_neomodel_session.make_object_from_node(results[0][0])
            assert retrieved.name == "Alice"
            assert retrieved.address.street == "123 Main St"
            assert retrieved.address.city == "NYC"

    def test_list_of_fieldz_objects(self, neo4j_neomodel_session):
        @dataclass
        class ScenarioItem:
            value: int

        items = [ScenarioItem(value=1), ScenarioItem(value=2), ScenarioItem(value=3)]

        with neo4j_neomodel_session:
            neo4j_neomodel_session.save_from_object(items)

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (n:List) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_neomodel_session.make_object_from_node(results[0][0])
            assert len(retrieved) == 3
            assert all(isinstance(item, ScenarioItem) for item in retrieved)
            assert sorted([item.value for item in retrieved]) == [1, 2, 3]

    def test_dict_with_complex_values(self, neo4j_neomodel_session):
        @dataclass
        class DictPerson:
            name: str

        data = {"alice": DictPerson(name="Alice"), "bob": DictPerson(name="Bob")}

        with neo4j_neomodel_session:
            neo4j_neomodel_session.save_from_object(data)

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (n:Dict) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_neomodel_session.make_object_from_node(results[0][0])
            assert "alice" in retrieved
            assert "bob" in retrieved

    def test_round_trip_complex_object(self, neo4j_neomodel_session):
        company = Company(
            name="TechCorp",
            employees=[
                Employee(
                    name="Alice", department="Engineering", skills=["Python", "Neo4j"]
                ),
                Employee(name="Bob", department="Design", skills=["Figma", "UI"]),
            ],
        )

        with neo4j_neomodel_session:
            neo4j_neomodel_session.save_from_object(company)

            results, _ = neo4j_neomodel_session.execute_query(
                "MATCH (n:Company) RETURN n", resolve_objects=True
            )
            assert len(results) == 1

            retrieved = neo4j_neomodel_session.make_object_from_node(results[0][0])
            assert retrieved.name == "TechCorp"
            assert len(retrieved.employees) == 2
            assert retrieved.employees[0].name == "Alice"
            assert retrieved.employees[0].skills == ["Python", "Neo4j"]


@pytest.mark.usefixtures("clear_database")
class TestExecuteQueryAsObjects:
    """Tests for execute_query_as_objects method."""

    def test_execute_query_as_objects(self, neo4j_neomodel_session):
        @dataclass
        class QueryPerson:
            name: str
            age: int

        persons = [
            QueryPerson(name="Alice", age=30),
            QueryPerson(name="Bob", age=25),
        ]

        with neo4j_neomodel_session:
            neo4j_neomodel_session.save_from_objects(persons)

            results = neo4j_neomodel_session.execute_query_as_objects(
                "MATCH (n:QueryPerson) RETURN n ORDER BY n.age"
            )

            assert len(results) == 2
            assert results[0][0].name == "Bob"
            assert results[1][0].name == "Alice"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
