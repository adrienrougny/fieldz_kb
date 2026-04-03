"""Tests for fieldz_kb clingo backend.

These tests verify predicate class generation and fact creation
from fieldz objects. No external services are required.
"""

from dataclasses import dataclass, field
from typing import List, Optional

import pytest
import clorm
import fieldz

import fieldz_kb.clingo.session


@pytest.fixture
def clingo_session():
    """Provide a fresh clingo session for each test."""
    return fieldz_kb.clingo.session.Session()


class TestPredicateClassGeneration:
    """Tests for predicate class generation from types."""

    def test_simple_class_generates_predicate(self, clingo_session):
        @dataclass
        class Gene:
            name: str
            chromosome: int

        predicate_classes = (
            clingo_session.get_or_make_predicate_classes_from_type(Gene)
        )
        assert len(predicate_classes) >= 1
        assert issubclass(predicate_classes[0], clorm.Predicate)

    def test_predicate_class_has_id_field(self, clingo_session):
        @dataclass
        class Metabolite:
            concentration: int

        predicate_classes = (
            clingo_session.get_or_make_predicate_classes_from_type(Metabolite)
        )
        main_predicate_class = predicate_classes[0]
        fact = main_predicate_class("test_id")
        assert fact.id_ == "test_id"

    def test_predicate_class_caching(self, clingo_session):
        @dataclass
        class Protein:
            sequence: str

        predicate_classes_1 = (
            clingo_session.get_or_make_predicate_classes_from_type(Protein)
        )
        predicate_classes_2 = (
            clingo_session.get_or_make_predicate_classes_from_type(Protein)
        )
        assert predicate_classes_1[0] is predicate_classes_2[0]

    def test_cache_returns_consistent_shape(self, clingo_session):
        @dataclass
        class Species:
            name: str
            taxonomy_id: int

        predicate_classes_1 = (
            clingo_session.get_or_make_predicate_classes_from_type(Species)
        )
        predicate_classes_2 = (
            clingo_session.get_or_make_predicate_classes_from_type(Species)
        )
        assert len(predicate_classes_1) == len(predicate_classes_2)

    def test_field_predicate_classes_generated(self, clingo_session):
        @dataclass
        class Enzyme:
            name: str
            ec_number: str

        predicate_classes = (
            clingo_session.get_or_make_predicate_classes_from_type(Enzyme)
        )
        assert len(predicate_classes) >= 3

    def test_nested_fieldz_class_field(self, clingo_session):
        @dataclass
        class Organism:
            name: str

        @dataclass
        class GeneWithOrganism:
            organism: Organism

        predicate_classes = (
            clingo_session.get_or_make_predicate_classes_from_type(
                GeneWithOrganism
            )
        )
        assert len(predicate_classes) >= 2

    def test_optional_field_type(self, clingo_session):
        @dataclass
        class ProteinOptional:
            name: Optional[str] = None

        predicate_classes = (
            clingo_session.get_or_make_predicate_classes_from_type(
                ProteinOptional
            )
        )
        assert len(predicate_classes) >= 1

    def test_list_field_type(self, clingo_session):
        @dataclass
        class PathwayWithReactions:
            reactions: List[str]

        predicate_classes = (
            clingo_session.get_or_make_predicate_classes_from_type(
                PathwayWithReactions
            )
        )
        assert len(predicate_classes) >= 2

    def test_unsupported_type_raises_error(self, clingo_session):
        with pytest.raises(ValueError, match="not supported"):
            clingo_session.get_or_make_predicate_classes_from_type(int)


class TestPredicateNaming:
    """Tests for predicate naming conventions."""

    def test_type_predicate_name_lowercase_first(self, clingo_session):
        @dataclass
        class BiologicalProcess:
            name: str

        predicate_classes = (
            clingo_session.get_or_make_predicate_classes_from_type(
                BiologicalProcess
            )
        )
        assert predicate_classes[0].__name__ == "biologicalProcess"

    def test_field_predicate_has_prefix(self, clingo_session):
        @dataclass
        class GeneAnnotation:
            gene_symbol: int

        predicate_classes = (
            clingo_session.get_or_make_predicate_classes_from_type(
                GeneAnnotation
            )
        )
        field_predicate_names = [
            predicate_class.__name__
            for predicate_class in predicate_classes[1:]
        ]
        assert any("hasGeneSymbol" in name for name in field_predicate_names)


class TestFactGeneration:
    """Tests for converting objects to facts."""

    def test_simple_object_facts(self, clingo_session):
        @dataclass
        class Gene:
            name: str
            chromosome: int

        obj = Gene(name="TP53", chromosome=17)
        facts = clingo_session.make_facts_from_object(obj)
        assert len(facts) > 0

    def test_entity_fact_present(self, clingo_session):
        @dataclass
        class Metabolite:
            concentration: int

        obj = Metabolite(concentration=42)
        facts = clingo_session.make_facts_from_object(obj)
        entity_facts = [
            f for f in facts if type(f).__name__ == "metabolite"
        ]
        assert len(entity_facts) == 1
        assert entity_facts[0].id_.startswith("id_")

    def test_fact_values_are_correct(self, clingo_session):
        @dataclass
        class Measurement:
            value: int

        obj = Measurement(value=42)
        facts = clingo_session.make_facts_from_object(obj)
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert any(f.value == 42 for f in value_facts)

    def test_string_field_value(self, clingo_session):
        @dataclass
        class Species:
            name: str

        obj = Species(name="Homo sapiens")
        facts = clingo_session.make_facts_from_object(obj)
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert any(f.value == "Homo sapiens" for f in value_facts)

    def test_none_value_skipped(self, clingo_session):
        @dataclass
        class ProteinOptional:
            name: str
            alias: Optional[str] = None

        obj = ProteinOptional(name="p53", alias=None)
        facts = clingo_session.make_facts_from_object(obj)
        assert len(facts) > 0
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert len(value_facts) == 1
        assert value_facts[0].value == "p53"

    def test_nested_object_facts(self, clingo_session):
        @dataclass
        class CellLocation:
            compartment: str

        @dataclass
        class ProteinLocated:
            name: str
            location: CellLocation

        location = CellLocation(compartment="cytoplasm")
        protein = ProteinLocated(name="insulin", location=location)
        facts = clingo_session.make_facts_from_object(protein)

        entity_type_names = {
            type(f).__name__ for f in facts if not hasattr(f, "value")
        }
        assert "proteinLocated" in entity_type_names
        assert "cellLocation" in entity_type_names

    def test_nested_object_linked_by_id(self, clingo_session):
        @dataclass
        class Substrate:
            name: str

        @dataclass
        class ReactionWithSubstrate:
            substrate: Substrate

        obj = ReactionWithSubstrate(substrate=Substrate(name="glucose"))
        facts = clingo_session.make_facts_from_object(obj)

        substrate_entity = [
            f for f in facts if type(f).__name__ == "substrate"
        ]
        assert len(substrate_entity) == 1
        substrate_id = substrate_entity[0].id_

        link_facts = [
            f
            for f in facts
            if hasattr(f, "value")
            and isinstance(f.value, str)
            and f.value == substrate_id
        ]
        assert len(link_facts) == 1

    def test_list_of_base_types(self, clingo_session):
        @dataclass
        class GeneWithSynonyms:
            synonyms: List[str]

        obj = GeneWithSynonyms(synonyms=["BRCA1", "FANCS", "RNF53"])
        facts = clingo_session.make_facts_from_object(obj)
        assert len(facts) > 0
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert len(value_facts) == 3
        values = {f.value for f in value_facts}
        assert values == {"BRCA1", "FANCS", "RNF53"}

    def test_list_of_fieldz_objects(self, clingo_session):
        @dataclass
        class Metabolite:
            name: str

        @dataclass
        class PathwayWithMetabolites:
            metabolites: List[Metabolite]

        obj = PathwayWithMetabolites(
            metabolites=[
                Metabolite(name="glucose"),
                Metabolite(name="pyruvate"),
            ]
        )
        facts = clingo_session.make_facts_from_object(obj)
        assert len(facts) > 0

        metabolite_entities = [
            f for f in facts if type(f).__name__ == "metabolite"
        ]
        assert len(metabolite_entities) == 2

    def test_deterministic_ids(self, clingo_session):
        @dataclass
        class Enzyme:
            name: str

        obj = Enzyme(name="hexokinase")
        facts = clingo_session.make_facts_from_object(obj)
        entity_fact = [f for f in facts if type(f).__name__ == "enzyme"][0]
        assert entity_fact.id_ == "id_0"

    def test_deterministic_ids_sequential(self, clingo_session):
        @dataclass
        class Reaction:
            name: str

        obj1 = Reaction(name="glycolysis_step_1")
        obj2 = Reaction(name="glycolysis_step_2")
        facts1 = clingo_session.make_facts_from_object(obj1)
        facts2 = clingo_session.make_facts_from_object(obj2)

        entity1 = [f for f in facts1 if type(f).__name__ == "reaction"][0]
        entity2 = [f for f in facts2 if type(f).__name__ == "reaction"][0]
        assert entity1.id_ == "id_0"
        assert entity2.id_ == "id_1"

    def test_empty_list_field(self, clingo_session):
        @dataclass
        class EmptyPathway:
            reactions: List[str] = field(default_factory=list)

        obj = EmptyPathway(reactions=[])
        facts = clingo_session.make_facts_from_object(obj)
        entity_facts = [
            f for f in facts if type(f).__name__ == "emptyPathway"
        ]
        assert len(entity_facts) == 1
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert len(value_facts) == 0

    def test_unsupported_value_type_raises_error(self, clingo_session):
        @dataclass
        class BadType:
            data: dict

        obj = BadType(data={"a": 1})
        with pytest.raises(ValueError, match="not supported"):
            clingo_session.make_facts_from_object(obj)


class TestResetContext:
    """Tests for the session reset functionality."""

    def test_reset_clears_type_cache(self):
        @dataclass
        class ResetTest:
            name: str

        session = fieldz_kb.clingo.session.Session()
        session.get_or_make_predicate_classes_from_type(ResetTest)
        assert ResetTest in session._context.type_to_predicate_class

        session.reset_context()
        assert ResetTest not in session._context.type_to_predicate_class

    def test_reset_resets_id_counter(self):
        @dataclass
        class CounterTest:
            name: str

        session = fieldz_kb.clingo.session.Session()
        obj = CounterTest(name="test")
        facts = session.make_facts_from_object(obj)
        entity = [f for f in facts if type(f).__name__ == "counterTest"][0]
        first_id = entity.id_

        session.reset_context()

        facts2 = session.make_facts_from_object(obj)
        entity2 = [f for f in facts2 if type(f).__name__ == "counterTest"][0]
        assert entity2.id_ == first_id
