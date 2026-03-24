"""Tests for fieldz_kb.clingo.core module.

These tests verify predicate class generation and fact creation
from fieldz objects. No external services are required.
"""

from dataclasses import dataclass, field
from typing import List, Optional

import pytest
import clorm
import fieldz

import fieldz_kb.clingo.core


@pytest.fixture(autouse=True)
def clear_clingo_caches():
    """Reset caches before each test for isolation."""
    fieldz_kb.clingo.core.reset_caches()
    yield
    fieldz_kb.clingo.core.reset_caches()


class TestPredicateClassGeneration:
    """Tests for predicate class generation from types."""

    def test_simple_class_generates_predicate(self):
        @dataclass
        class Person:
            name: str
            age: int

        pcs = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(Person)
        assert len(pcs) >= 1
        assert issubclass(pcs[0], clorm.Predicate)

    def test_predicate_class_has_id_field(self):
        @dataclass
        class Item:
            value: int

        pcs = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(Item)
        main_pc = pcs[0]
        # Can instantiate with an id
        fact = main_pc("test_id")
        assert fact.id_ == "test_id"

    def test_predicate_class_caching(self):
        @dataclass
        class CachedClass:
            x: int

        pcs1 = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(CachedClass)
        pcs2 = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(CachedClass)
        assert pcs1[0] is pcs2[0]

    def test_cache_returns_consistent_shape(self):
        @dataclass
        class Consistent:
            name: str
            age: int

        pcs1 = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(Consistent)
        pcs2 = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(Consistent)
        # Cache hit should return the same list shape as cache miss
        assert len(pcs1) == len(pcs2)

    def test_field_predicate_classes_generated(self):
        @dataclass
        class WithFields:
            name: str
            age: int

        pcs = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(WithFields)
        # Main predicate + one per field
        assert len(pcs) >= 3

    def test_nested_fieldz_class_field(self):
        @dataclass
        class Inner:
            value: int

        @dataclass
        class Outer:
            inner: Inner

        pcs = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(Outer)
        assert len(pcs) >= 2

    def test_optional_field_type(self):
        @dataclass
        class OptionalField:
            name: Optional[str] = None

        pcs = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(OptionalField)
        assert len(pcs) >= 1

    def test_list_field_type(self):
        @dataclass
        class WithList:
            items: List[int]

        pcs = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(WithList)
        assert len(pcs) >= 2

    def test_unsupported_type_raises_error(self):
        with pytest.raises(ValueError, match="not supported"):
            fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(int)


class TestPredicateNaming:
    """Tests for predicate naming conventions."""

    def test_type_predicate_name_lowercase_first(self):
        @dataclass
        class MyClass:
            x: int

        pcs = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(MyClass)
        assert pcs[0].__name__ == "myClass"

    def test_field_predicate_has_prefix(self):
        @dataclass
        class Named:
            my_field: int

        fields_ = fieldz.fields(Named)
        pcs = fieldz_kb.clingo.core._default_context.get_or_make_predicate_classes_from_field(
            Named, fields_[0]
        )
        # Field predicates should have "has" prefix in their predicate name
        assert len(pcs) >= 1


class TestFactGeneration:
    """Tests for converting objects to facts."""

    def test_simple_object_facts(self):
        @dataclass
        class Simple:
            name: str
            age: int

        obj = Simple(name="Alice", age=30)
        facts = fieldz_kb.clingo.core.make_facts_from_object(obj)
        assert len(facts) > 0

    def test_entity_fact_present(self):
        @dataclass
        class Entity:
            x: int

        obj = Entity(x=42)
        facts = fieldz_kb.clingo.core.make_facts_from_object(obj)
        # There should be an entity fact with an id_
        entity_facts = [f for f in facts if type(f).__name__ == "entity"]
        assert len(entity_facts) == 1
        assert entity_facts[0].id_.startswith("id_")

    def test_fact_values_are_correct(self):
        @dataclass
        class Valued:
            x: int

        obj = Valued(x=42)
        facts = fieldz_kb.clingo.core.make_facts_from_object(obj)
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert any(f.value == 42 for f in value_facts)

    def test_string_field_value(self):
        @dataclass
        class WithString:
            name: str

        obj = WithString(name="Alice")
        facts = fieldz_kb.clingo.core.make_facts_from_object(obj)
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert any(f.value == "Alice" for f in value_facts)

    def test_none_value_skipped(self):
        @dataclass
        class OptObj:
            name: str
            nickname: Optional[str] = None

        obj = OptObj(name="Alice", nickname=None)
        facts = fieldz_kb.clingo.core.make_facts_from_object(obj)
        # Should succeed without error
        assert len(facts) > 0
        # Should have facts for name but not for nickname
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert len(value_facts) == 1
        assert value_facts[0].value == "Alice"

    def test_nested_object_facts(self):
        @dataclass
        class Address:
            city: str

        @dataclass
        class Person:
            name: str
            address: Address

        addr = Address(city="NYC")
        person = Person(name="Alice", address=addr)
        facts = fieldz_kb.clingo.core.make_facts_from_object(person)

        # Should have entity facts for both Person and Address
        entity_type_names = {type(f).__name__ for f in facts if not hasattr(f, "value")}
        assert "person" in entity_type_names
        assert "address" in entity_type_names

    def test_nested_object_linked_by_id(self):
        @dataclass
        class Inner:
            value: int

        @dataclass
        class Outer:
            inner: Inner

        obj = Outer(inner=Inner(value=42))
        facts = fieldz_kb.clingo.core.make_facts_from_object(obj)

        # The outer entity's hasInner fact should reference the inner entity's id
        inner_entity = [f for f in facts if type(f).__name__ == "inner"]
        assert len(inner_entity) == 1
        inner_id = inner_entity[0].id_

        # Find the hasInner field fact that links outer to inner
        link_facts = [
            f
            for f in facts
            if hasattr(f, "value") and isinstance(f.value, str) and f.value == inner_id
        ]
        assert len(link_facts) == 1

    def test_list_of_base_types(self):
        @dataclass
        class WithTags:
            tags: List[str]

        obj = WithTags(tags=["a", "b", "c"])
        facts = fieldz_kb.clingo.core.make_facts_from_object(obj)
        assert len(facts) > 0
        # Should have 3 value facts for tags
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert len(value_facts) == 3
        tag_values = {f.value for f in value_facts}
        assert tag_values == {"a", "b", "c"}

    def test_list_of_fieldz_objects(self):
        @dataclass
        class Item:
            value: int

        @dataclass
        class Container:
            items: List[Item]

        obj = Container(items=[Item(value=1), Item(value=2)])
        facts = fieldz_kb.clingo.core.make_facts_from_object(obj)
        assert len(facts) > 0

        # Should have entity facts for the container and both items
        item_entities = [f for f in facts if type(f).__name__ == "item"]
        assert len(item_entities) == 2

    def test_deterministic_ids(self):
        @dataclass
        class Det:
            x: int

        obj = Det(x=1)
        facts = fieldz_kb.clingo.core.make_facts_from_object(obj)
        entity_fact = [f for f in facts if type(f).__name__ == "det"][0]
        # ID should follow counter pattern, not memory addresses
        assert entity_fact.id_ == "id_0"

    def test_deterministic_ids_sequential(self):
        @dataclass
        class Seq:
            x: int

        obj1 = Seq(x=1)
        obj2 = Seq(x=2)
        facts1 = fieldz_kb.clingo.core.make_facts_from_object(obj1)
        facts2 = fieldz_kb.clingo.core.make_facts_from_object(obj2)

        entity1 = [f for f in facts1 if type(f).__name__ == "seq"][0]
        entity2 = [f for f in facts2 if type(f).__name__ == "seq"][0]
        assert entity1.id_ == "id_0"
        assert entity2.id_ == "id_1"

    def test_empty_list_field(self):
        @dataclass
        class EmptyList:
            items: List[int] = field(default_factory=list)

        obj = EmptyList(items=[])
        facts = fieldz_kb.clingo.core.make_facts_from_object(obj)
        # Should have just the entity fact, no value facts
        entity_facts = [f for f in facts if type(f).__name__ == "emptyList"]
        assert len(entity_facts) == 1
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert len(value_facts) == 0

    def test_unsupported_value_type_raises_error(self):
        @dataclass
        class BadType:
            data: dict

        obj = BadType(data={"a": 1})
        with pytest.raises(ValueError, match="not supported"):
            fieldz_kb.clingo.core.make_facts_from_object(obj)


class TestResetCaches:
    """Tests for the reset_caches utility."""

    def test_reset_clears_type_cache(self):
        @dataclass
        class ResetTest:
            x: int

        fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(ResetTest)
        assert ResetTest in fieldz_kb.clingo.core._default_context.type_to_predicate_class

        fieldz_kb.clingo.core.reset_caches()
        assert ResetTest not in fieldz_kb.clingo.core._default_context.type_to_predicate_class

    def test_reset_resets_id_counter(self):
        @dataclass
        class CounterTest:
            x: int

        obj = CounterTest(x=1)
        facts = fieldz_kb.clingo.core.make_facts_from_object(obj)
        entity = [f for f in facts if type(f).__name__ == "counterTest"][0]
        first_id = entity.id_

        fieldz_kb.clingo.core.reset_caches()

        facts2 = fieldz_kb.clingo.core.make_facts_from_object(obj)
        entity2 = [f for f in facts2 if type(f).__name__ == "counterTest"][0]
        assert entity2.id_ == first_id  # Same id after reset
