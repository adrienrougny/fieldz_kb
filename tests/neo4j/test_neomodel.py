import typing
import types
import dataclasses
import pydantic
import neomodel

import pytest

import fieldz_kb.neo4j.neomodel


def are_node_classes_equal(node_class1, node_class2):
    def _are_properties_equal(property1, property2):
        if type(property1) is not type(property2):
            return False
        if isinstance(property1, neomodel.properties.Property):
            if property1.required != property2.required:
                return False
            if isinstance(property1, neomodel.ArrayProperty):
                if not _are_properties_equal(
                    property1.base_property, property2.base_property
                ):
                    return False
        else:
            if property1.manager != property2.manager:
                return False
            if property1.definition != property2.definition:
                return False
            if not are_node_classes_equal(property1._raw_class, property2._raw_class):
                return False
        return True

    if node_class1.__name__ != node_class2.__name__:
        return False
    for name, property1 in node_class1.defined_properties().items():
        property2 = node_class2.defined_properties().get(name)
        if property2 is None:
            return False
        if not _are_properties_equal(property1, property2):
            return False
    for name, property2 in node_class2.defined_properties().items():
        property1 = node_class1.defined_properties().get(name)
        if property1 is None:
            return False
        if not _are_properties_equal(property1, property2):
            return False
    return True


@pytest.fixture(scope="module")
def dataclass_required_base_property_example():
    return dataclasses.make_dataclass(
        "RequiredBasePropertyExample", [("x", int), ("y", str)]
    )


@pytest.fixture(scope="module")
def dataclass_optional_base_property_example_1():
    return dataclasses.make_dataclass(
        "OptionalBasePropertyExample", [("x", int | None), ("y", str)]
    )


@pytest.fixture(scope="module")
def dataclass_optional_base_property_example_2():
    return dataclasses.make_dataclass(
        "OptionalBasePropertyExample", [("x", typing.Optional[int]), ("y", str)]
    )


@pytest.fixture(scope="module")
def dataclass_optional_base_property_example_3():
    return dataclasses.make_dataclass(
        "OptionalBasePropertyExample",
        [("x", typing.Union[int, types.NoneType]), ("y", str)],
    )


@pytest.fixture(scope="module")
def pydantic_class_required_base_property_example():
    return pydantic.create_model("RequiredBasePropertyExample", x=int, y=str)


@pytest.fixture(scope="module")
def node_class_required_base_property_example():
    node_class = type(
        "RequiredBasePropertyExampleNode",
        (neomodel.StructuredNode,),
        {
            "x": neomodel.IntegerProperty(required=True),
            "y": neomodel.StringProperty(required=True),
        },
    )
    neomodel.db._NODE_CLASS_REGISTRY = {}
    return node_class


@pytest.fixture(scope="module")
def node_class_optional_base_property_example():
    node_class = type(
        "OptionalBasePropertyExampleNode",
        (neomodel.StructuredNode,),
        {
            "x": neomodel.IntegerProperty(required=False),
            "y": neomodel.StringProperty(required=True),
        },
    )
    neomodel.db._NODE_CLASS_REGISTRY = {}
    return node_class


@pytest.fixture(scope="module")
def dataclass_array_property_example():
    return dataclasses.make_dataclass(
        "ArrayPropertyExample", [("x", int), ("y", list[str])]
    )


@pytest.fixture(scope="module")
def node_class_array_property_example():
    node_class = type(
        "ArrayPropertyExampleNode",
        (neomodel.StructuredNode,),
        {
            "x": neomodel.IntegerProperty(required=True),
            "y": neomodel.ArrayProperty(neomodel.StringProperty(), required=True),
        },
    )
    neomodel.db._NODE_CLASS_REGISTRY = {}
    return node_class


@pytest.fixture(scope="module")
def dataclass_relationship_example(dataclass_required_base_property_example):
    return dataclasses.make_dataclass(
        "RelationshipExample",
        [("x", int), ("y", dataclass_required_base_property_example)],
    )


@pytest.fixture(scope="module")
def node_class_relationship_example(node_class_required_base_property_example):
    node_class = type(
        "RelationshipExampleNode",
        (neomodel.StructuredNode,),
        {
            "x": neomodel.IntegerProperty(required=True),
            "y": neomodel.RelationshipTo(
                cls_name=fieldz_kb.neo4j.neomodel.BaseNode,
                relation_type="HAS_Y",
                cardinality=neomodel.One,
                model=fieldz_kb.neo4j.neomodel.UnorderedRelationshipTo,
            ),
        },
    )
    neomodel.db._NODE_CLASS_REGISTRY = {}
    return node_class


@pytest.mark.parametrize(
    "fieldz_class, node_class",
    [
        (
            "dataclass_required_base_property_example",
            "node_class_required_base_property_example",
        ),
        (
            "pydantic_class_required_base_property_example",
            "node_class_required_base_property_example",
        ),
        (
            "dataclass_optional_base_property_example_1",
            "node_class_optional_base_property_example",
        ),
        (
            "dataclass_optional_base_property_example_2",
            "node_class_optional_base_property_example",
        ),
        (
            "dataclass_optional_base_property_example_3",
            "node_class_optional_base_property_example",
        ),
        (
            "dataclass_array_property_example",
            "node_class_array_property_example",
        ),
        ("dataclass_relationship_example", "node_class_relationship_example"),
    ],
)
def test_make_node_class_from_fieldz_class(fieldz_class, node_class, request):
    fieldz_class = request.getfixturevalue(fieldz_class)
    node_class = request.getfixturevalue(node_class)
    node_class_from_fieldz_class = (
        fieldz_kb.neo4j.neomodel._make_node_class_from_fieldz_class(fieldz_class)
    )
    neomodel.db._NODE_CLASS_REGISTRY = {}
    assert are_node_classes_equal(node_class_from_fieldz_class, node_class)
