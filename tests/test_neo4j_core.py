"""Tests for fieldz_kb.neo4j.core module using real Neo4j database.

These tests require a running Neo4j instance and credentials in tests/credentials.py.
Run with: pytest tests/test_neo4j_core.py -v
"""

import enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Set, Tuple

import pytest
import fieldz
import frozendict

import fieldz_kb.neo4j.core as neo4j_core


@pytest.fixture(autouse=True)
def clear_database_before_tests(neo4j_connection):
    """Clear database before each test to ensure isolation."""
    neo4j_core.delete_all()
    yield
    neo4j_core.delete_all()


class TestNodeClassGeneration:
    """Tests for node class generation functions."""

    def test_get_or_make_node_class_from_builtin_int(self):
        """Test getting node class for int type."""
        node_class = neo4j_core.get_or_make_node_class_from_type(int)
        assert node_class is neo4j_core.Integer

    def test_get_or_make_node_class_from_builtin_str(self):
        """Test getting node class for str type."""
        node_class = neo4j_core.get_or_make_node_class_from_type(str)
        assert node_class is neo4j_core.String

    def test_get_or_make_node_class_from_builtin_float(self):
        """Test getting node class for float type."""
        node_class = neo4j_core.get_or_make_node_class_from_type(float)
        assert node_class is neo4j_core.Float

    def test_get_or_make_node_class_from_builtin_bool(self):
        """Test getting node class for bool type."""
        node_class = neo4j_core.get_or_make_node_class_from_type(bool)
        assert node_class is neo4j_core.Boolean

    def test_get_or_make_node_class_caching(self):
        """Test that node classes are cached."""

        @dataclass
        class CachingPerson:
            name: str

        class1 = neo4j_core.get_or_make_node_class_from_type(CachingPerson)
        class2 = neo4j_core.get_or_make_node_class_from_type(CachingPerson)
        assert class1 is class2

    def test_make_node_class_from_fieldz_class(self):
        """Test creating node class from fieldz class."""

        @dataclass
        class SimplePerson:
            name: str
            age: int

        node_class = neo4j_core._make_node_class_from_type(SimplePerson)

        # Check class name
        assert node_class.__name__ == "SimplePerson"

        # Check base class
        assert issubclass(node_class, neo4j_core.BaseNode)

        # Check properties
        assert hasattr(node_class, "name")
        assert hasattr(node_class, "age")

    def test_make_node_class_from_enum(self):
        """Test creating node class from enum."""

        class Color(enum.Enum):
            RED = "red"
            GREEN = "green"
            BLUE = "blue"

        node_class = neo4j_core._make_node_class_from_type(Color)

        assert node_class.__name__ == "Color"
        assert hasattr(node_class, "name")
        assert hasattr(node_class, "value")

    def test_make_node_class_from_enum_with_int_values(self):
        """Test creating node class from enum with integer values."""

        class Priority(enum.Enum):
            LOW = 1
            MEDIUM = 2
            HIGH = 3

        node_class = neo4j_core._make_node_class_from_type(Priority)

        assert node_class.__name__ == "Priority"
        assert hasattr(node_class, "name")
        assert hasattr(node_class, "value")

    def test_enum_with_mixed_value_types_raises_error(self):
        """Test that enums with mixed value types raise an error."""

        class MixedEnum(enum.Enum):
            STRING = "string"
            NUMBER = 42

        with pytest.raises(ValueError, match="types of values must all be the same"):
            neo4j_core._make_node_class_from_type(MixedEnum)

    def test_make_node_class_with_list_field(self):
        """Test creating node class with list field."""

        @dataclass
        class ListPerson:
            name: str
            tags: List[str]

        node_class = neo4j_core._make_node_class_from_type(ListPerson)

        assert hasattr(node_class, "name")
        assert hasattr(node_class, "tags")

    def test_make_node_class_with_optional_field(self):
        """Test creating node class with optional field."""

        @dataclass
        class OptionalPerson:
            name: str
            nickname: Optional[str] = None

        node_class = neo4j_core._make_node_class_from_type(OptionalPerson)

        assert hasattr(node_class, "name")
        assert hasattr(node_class, "nickname")


class TestMakeNodesFromObject:
    """Tests for converting objects to nodes."""

    def test_make_nodes_from_int(self):
        """Test converting int to node."""
        nodes, to_connect = neo4j_core.make_nodes_from_object(42)

        assert len(nodes) == 1
        assert isinstance(nodes[0], neo4j_core.Integer)
        assert nodes[0].value == 42
        assert len(to_connect) == 0

    def test_make_nodes_from_str(self):
        """Test converting str to node."""
        nodes, to_connect = neo4j_core.make_nodes_from_object("hello")

        assert len(nodes) == 1
        assert isinstance(nodes[0], neo4j_core.String)
        assert nodes[0].value == "hello"

    def test_make_nodes_from_float(self):
        """Test converting float to node."""
        nodes, to_connect = neo4j_core.make_nodes_from_object(3.14)

        assert len(nodes) == 1
        assert isinstance(nodes[0], neo4j_core.Float)
        assert nodes[0].value == 3.14

    def test_make_nodes_from_bool(self):
        """Test converting bool to node."""
        nodes, to_connect = neo4j_core.make_nodes_from_object(True)

        assert len(nodes) == 1
        assert isinstance(nodes[0], neo4j_core.Boolean)
        assert nodes[0].value is True

    def test_make_nodes_from_simple_fieldz_object(self):
        """Test converting simple fieldz object to nodes."""

        @dataclass
        class SimpleNodePerson:
            name: str
            age: int

        person = SimpleNodePerson(name="Alice", age=30)
        nodes, to_connect = neo4j_core.make_nodes_from_object(person)

        assert len(nodes) == 1
        node = nodes[0]
        assert isinstance(node, neo4j_core.BaseNode)
        assert node.__class__.__name__ == "SimpleNodePerson"

    def test_make_nodes_from_list(self):
        """Test converting list to nodes."""
        data = [1, 2, 3]
        nodes, to_connect = neo4j_core.make_nodes_from_object(data)

        assert len(nodes) == 4  # 1 List node + 3 Integer nodes
        list_node = nodes[0]
        assert isinstance(list_node, neo4j_core.List)

    def test_make_nodes_from_tuple(self):
        """Test converting tuple to nodes."""
        data = (1, 2, 3)
        nodes, to_connect = neo4j_core.make_nodes_from_object(data)

        assert len(nodes) == 4  # 1 Tuple node + 3 Integer nodes
        tuple_node = nodes[0]
        assert isinstance(tuple_node, neo4j_core.Tuple)

    def test_make_nodes_from_set(self):
        """Test converting set to nodes."""
        data = {1, 2, 3}
        nodes, to_connect = neo4j_core.make_nodes_from_object(data)

        assert len(nodes) == 4  # 1 Set node + 3 Integer nodes
        set_node = nodes[0]
        assert isinstance(set_node, neo4j_core.Set)

    def test_make_nodes_from_dict(self):
        """Test converting dict to nodes."""
        data = {"a": 1, "b": 2}
        nodes, to_connect = neo4j_core.make_nodes_from_object(data)
        dict_node = nodes[0]
        assert isinstance(dict_node, neo4j_core.Dict)
        assert len(to_connect) > 0

    def test_make_nodes_from_frozendict(self):
        """Test converting frozendict to nodes."""
        data = frozendict.frozendict({"x": 1, "y": 2})
        nodes, to_connect = neo4j_core.make_nodes_from_object(data)

        frozen_node = nodes[0]
        assert isinstance(frozen_node, neo4j_core.FrozenDict)

    def test_make_nodes_from_enum(self):
        """Test converting enum to nodes."""

        class Status(enum.Enum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        status = Status.ACTIVE
        nodes, to_connect = neo4j_core.make_nodes_from_object(status)

        assert len(nodes) == 1
        node = nodes[0]
        assert node.__class__.__name__ == "Status"

    def test_make_nodes_with_integration_mode_hash(self):
        """Test hash-based integration mode."""
        obj = frozenset([1, 2, 3])
        object_to_node = {}
        nodes1, _ = neo4j_core.make_nodes_from_object(
            obj, integration_mode="hash", object_to_node=object_to_node
        )
        nodes2, _ = neo4j_core.make_nodes_from_object(
            obj, integration_mode="hash", object_to_node=object_to_node
        )

        assert nodes1[0] is nodes2[0]

    def test_make_nodes_with_integration_mode_id(self):
        """Test id-based integration mode."""
        obj1 = [1, 2, 3]
        obj2 = [1, 2, 3]  # Different object with same values

        nodes1, _ = neo4j_core.make_nodes_from_object(obj1, integration_mode="id")
        nodes2, _ = neo4j_core.make_nodes_from_object(obj2, integration_mode="id")
        assert nodes1[0] is not nodes2[0]

    def test_unsupported_type_raises_error(self):
        """Test that unsupported types raise ValueError."""

        class UnsupportedClass:
            pass

        with pytest.raises(ValueError, match="not supported"):
            neo4j_core.make_nodes_from_object(UnsupportedClass())


class TestSaveAndRetrieve:
    """Tests for saving objects to Neo4j and retrieving them."""

    def test_save_and_retrieve_simple_object(self, neo4j_connection):
        """Test saving a simple fieldz object and retrieving it."""

        @dataclass
        class SavePerson:
            name: str
            age: int

        person = SavePerson(name="Alice", age=30)

        # Save the object
        neo4j_core.save_from_object(person)

        # Query and verify it was saved
        results, _ = neo4j_core.cypher_query("MATCH (n:SavePerson) RETURN n")
        assert len(results) == 1

        # Retrieve the object
        retrieved = neo4j_core.make_object_from_node(results[0][0])
        assert isinstance(retrieved, SavePerson)
        assert retrieved.name == "Alice"
        assert retrieved.age == 30

    def test_save_and_retrieve_with_base_types(self, neo4j_connection):
        """Test saving object with base type fields."""

        @dataclass
        class BaseTypesPerson:
            name: str
            age: int
            height: float
            is_active: bool

        person = BaseTypesPerson(name="Bob", age=25, height=1.75, is_active=True)
        neo4j_core.save_from_object(person)

        results, _ = neo4j_core.cypher_query("MATCH (n:BaseTypesPerson) RETURN n")
        assert len(results) == 1

        retrieved = neo4j_core.make_object_from_node(results[0][0])
        assert retrieved.name == "Bob"
        assert retrieved.age == 25
        assert retrieved.height == 1.75
        assert retrieved.is_active is True

    def test_save_and_retrieve_list(self, neo4j_connection):
        """Test saving and retrieving a list."""
        data = [1, 2, 3]
        neo4j_core.save_from_object(data)

        results, _ = neo4j_core.cypher_query("MATCH (n:List) RETURN n")
        assert len(results) == 1

        retrieved = neo4j_core.make_object_from_node(results[0][0])
        assert retrieved == [1, 2, 3]

    def test_save_and_retrieve_enum(self, neo4j_connection):
        """Test saving and retrieving an enum."""

        class SaveStatus(enum.Enum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        status = SaveStatus.ACTIVE
        neo4j_core.save_from_object(status)

        results, _ = neo4j_core.cypher_query("MATCH (n:SaveStatus) RETURN n")
        assert len(results) == 1

        retrieved = neo4j_core.make_object_from_node(results[0][0])
        assert retrieved is SaveStatus.ACTIVE

    def test_save_multiple_objects(self, neo4j_connection):
        """Test saving multiple objects."""

        @dataclass
        class MultiPerson:
            name: str

        persons = [MultiPerson(name="Alice"), MultiPerson(name="Bob")]
        neo4j_core.save_from_objects(persons)

        results, _ = neo4j_core.cypher_query("MATCH (n:MultiPerson) RETURN n")
        assert len(results) == 2

    def test_save_with_relationships(self, neo4j_connection):
        """Test saving objects with relationships."""

        @dataclass
        class RelAddress:
            street: str

        @dataclass
        class RelPerson:
            name: str
            address: RelAddress

        address = RelAddress(street="123 Main St")
        person = RelPerson(name="Alice", address=address)

        neo4j_core.save_from_object(person)

        # Check both nodes were saved
        results, _ = neo4j_core.cypher_query("MATCH (n:RelPerson) RETURN n")
        assert len(results) == 1

        results, _ = neo4j_core.cypher_query("MATCH (n:RelAddress) RETURN n")
        assert len(results) == 1

        # Check relationship exists
        results, _ = neo4j_core.cypher_query(
            "MATCH (p:RelPerson)-[:HAS_ADDRESS]->(a:RelAddress) RETURN p, a"
        )
        assert len(results) == 1


class TestRelationshipTypeGeneration:
    """Tests for relationship type name generation."""

    def test_simple_field_name(self):
        """Test relationship type from simple field name."""
        result = neo4j_core._make_relationship_type_from_field_name("name")
        assert result == "HAS_NAME"

    def test_camel_case_field_name(self):
        """Test relationship type from camelCase field name."""
        result = neo4j_core._make_relationship_type_from_field_name("firstName")
        # inflect singularizes "Name" to "Name", producing "HAS_FIRSTNAME"
        # This is the actual behavior of the implementation
        assert result == "HAS_FIRSTNAME"

    def test_snake_case_field_name(self):
        """Test relationship type from snake_case field name."""
        result = neo4j_core._make_relationship_type_from_field_name("first_name")
        assert result == "HAS_FIRST_NAME"

    def test_plural_field_name(self):
        """Test relationship type from plural field name (many=True)."""
        result = neo4j_core._make_relationship_type_from_field_name(
            "children", many=True
        )
        assert result == "HAS_CHILD"

    def test_camel_case_plural(self):
        """Test relationship type from camelCase plural."""
        result = neo4j_core._make_relationship_type_from_field_name(
            "userProfiles", many=True
        )
        assert "USER_PROFILE" in result


class TestNodePropertyGeneration:
    """Tests for node property generation."""

    def test_base_type_property(self):
        """Test property generation for base types."""

        @dataclass
        class PropertyPerson:
            name: str

        field = fieldz.fields(PropertyPerson)[0]
        prop = neo4j_core._make_node_property_from_field(field)

        assert prop is not None

    def test_array_type_property(self):
        """Test property generation for array types."""

        @dataclass
        class ArrayPerson:
            tags: List[str]

        field = fieldz.fields(ArrayPerson)[0]
        prop = neo4j_core._make_node_property_from_field(field)

        assert prop is not None

    def test_optional_property(self):
        """Test property generation for optional fields."""

        @dataclass
        class OptionalNicknamePerson:
            nickname: Optional[str] = None

        field = fieldz.fields(OptionalNicknamePerson)[0]
        prop = neo4j_core._make_node_property_from_field(field)

        assert prop is not None


class TestTypeMappings:
    """Tests for type to node class mappings."""

    def test_type_to_node_class_mappings(self):
        """Test that all base types have mappings."""
        expected_mappings = {
            int: neo4j_core.Integer,
            str: neo4j_core.String,
            float: neo4j_core.Float,
            bool: neo4j_core.Boolean,
            list: neo4j_core.List,
            tuple: neo4j_core.Tuple,
            set: neo4j_core.Set,
            frozenset: neo4j_core.FrozenSet,
        }

        for type_, expected_class in expected_mappings.items():
            assert neo4j_core._type_to_node_class[type_] == expected_class

    def test_property_class_mappings(self):
        """Test base type to property class mappings."""
        import neomodel

        expected_mappings = {
            str: neomodel.StringProperty,
            int: neomodel.IntegerProperty,
            float: neomodel.FloatProperty,
            bool: neomodel.BooleanProperty,
        }

        for type_, expected_class in expected_mappings.items():
            assert neo4j_core._type_to_node_base_property_class[type_] == expected_class


class TestComplexScenarios:
    """Complex integration scenarios."""

    def test_nested_fieldz_objects(self, neo4j_connection):
        """Test nested fieldz dataclasses."""

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
        neo4j_core.save_from_object(person)

        # Retrieve and verify
        results, _ = neo4j_core.cypher_query("MATCH (n:ScenarioPerson) RETURN n")
        assert len(results) == 1

        retrieved = neo4j_core.make_object_from_node(results[0][0])
        assert retrieved.name == "Alice"
        assert retrieved.address.street == "123 Main St"
        assert retrieved.address.city == "NYC"

    def test_list_of_fieldz_objects(self, neo4j_connection):
        """Test list containing fieldz objects."""

        @dataclass
        class ScenarioItem:
            value: int

        items = [ScenarioItem(value=1), ScenarioItem(value=2), ScenarioItem(value=3)]
        neo4j_core.save_from_object(items)

        results, _ = neo4j_core.cypher_query("MATCH (n:List) RETURN n")
        assert len(results) == 1

        retrieved = neo4j_core.make_object_from_node(results[0][0])
        # List items should be preserved
        assert len(retrieved) == 3

    def test_dict_with_complex_values(self, neo4j_connection):
        """Test dict with complex values."""

        @dataclass
        class DictPerson:
            name: str

        data = {"alice": DictPerson(name="Alice"), "bob": DictPerson(name="Bob")}
        neo4j_core.save_from_object(data)

        results, _ = neo4j_core.cypher_query("MATCH (n:Dict) RETURN n")
        assert len(results) == 1

        retrieved = neo4j_core.make_object_from_node(results[0][0])
        assert "alice" in retrieved
        assert "bob" in retrieved

    def test_round_trip_complex_object(self, neo4j_connection):
        """Test complete round-trip of a complex object."""

        @dataclass
        class Company:
            name: str
            employees: List["Employee"]

        @dataclass
        class Employee:
            name: str
            department: str
            skills: List[str]

        company = Company(
            name="TechCorp",
            employees=[
                Employee(
                    name="Alice", department="Engineering", skills=["Python", "Neo4j"]
                ),
                Employee(name="Bob", department="Design", skills=["Figma", "UI"]),
            ],
        )

        # Save
        neo4j_core.save_from_object(company)

        # Retrieve
        results, _ = neo4j_core.cypher_query("MATCH (n:Company) RETURN n")
        assert len(results) == 1

        retrieved = neo4j_core.make_object_from_node(results[0][0])
        assert retrieved.name == "TechCorp"
        assert len(retrieved.employees) == 2
        assert retrieved.employees[0].name == "Alice"
        assert retrieved.employees[0].skills == ["Python", "Neo4j"]


class TestCypherQueryAsObjects:
    """Tests for cypher_query_as_objects function."""

    def test_cypher_query_as_objects(self, neo4j_connection):
        """Test querying and converting results to objects."""

        @dataclass
        class QueryPerson:
            name: str
            age: int

        persons = [
            QueryPerson(name="Alice", age=30),
            QueryPerson(name="Bob", age=25),
        ]
        neo4j_core.save_from_objects(persons)

        # Query using cypher_query_as_objects
        results, _ = neo4j_core.cypher_query_as_objects(
            "MATCH (n:QueryPerson) RETURN n ORDER BY n.age"
        )

        assert len(results) == 2
        assert results[0][0].name == "Bob"  # Younger first
        assert results[1][0].name == "Alice"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
