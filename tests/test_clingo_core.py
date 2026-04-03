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
def clingo_context():
    """Provide a fresh clingo context for each test."""
    context = fieldz_kb.clingo.core.make_context()
    yield context


class TestPredicateClassGeneration:
    """Tests for predicate class generation from types."""

    def test_simple_class_generates_predicate(self, clingo_context):
        @dataclass
        class Gene:
            name: str
            chromosome: int

        predicate_classes = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            clingo_context, Gene
        )
        assert len(predicate_classes) >= 1
        assert issubclass(predicate_classes[0], clorm.Predicate)

    def test_predicate_class_has_id_field(self, clingo_context):
        @dataclass
        class Metabolite:
            concentration: int

        predicate_classes = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            clingo_context, Metabolite
        )
        main_predicate_class = predicate_classes[0]
        fact = main_predicate_class("test_id")
        assert fact.id_ == "test_id"

    def test_predicate_class_caching(self, clingo_context):
        @dataclass
        class Protein:
            sequence: str

        predicate_classes_1 = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            clingo_context, Protein
        )
        predicate_classes_2 = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            clingo_context, Protein
        )
        assert predicate_classes_1[0] is predicate_classes_2[0]

    def test_cache_returns_consistent_shape(self, clingo_context):
        @dataclass
        class Species:
            name: str
            taxonomy_id: int

        predicate_classes_1 = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            clingo_context, Species
        )
        predicate_classes_2 = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            clingo_context, Species
        )
        assert len(predicate_classes_1) == len(predicate_classes_2)

    def test_field_predicate_classes_generated(self, clingo_context):
        @dataclass
        class Enzyme:
            name: str
            ec_number: str

        predicate_classes = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            clingo_context, Enzyme
        )
        assert len(predicate_classes) >= 3

    def test_nested_fieldz_class_field(self, clingo_context):
        @dataclass
        class Organism:
            name: str

        @dataclass
        class GeneWithOrganism:
            organism: Organism

        predicate_classes = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            clingo_context, GeneWithOrganism
        )
        assert len(predicate_classes) >= 2

    def test_optional_field_type(self, clingo_context):
        @dataclass
        class ProteinOptional:
            name: Optional[str] = None

        predicate_classes = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            clingo_context, ProteinOptional
        )
        assert len(predicate_classes) >= 1

    def test_list_field_type(self, clingo_context):
        @dataclass
        class PathwayWithReactions:
            reactions: List[str]

        predicate_classes = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            clingo_context, PathwayWithReactions
        )
        assert len(predicate_classes) >= 2

    def test_unsupported_type_raises_error(self, clingo_context):
        with pytest.raises(ValueError, match="not supported"):
            fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
                clingo_context, int
            )


class TestPredicateNaming:
    """Tests for predicate naming conventions."""

    def test_type_predicate_name_lowercase_first(self, clingo_context):
        @dataclass
        class BiologicalProcess:
            name: str

        predicate_classes = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            clingo_context, BiologicalProcess
        )
        assert predicate_classes[0].__name__ == "biologicalProcess"

    def test_field_predicate_has_prefix(self, clingo_context):
        @dataclass
        class GeneAnnotation:
            gene_symbol: int

        fields_ = fieldz.fields(GeneAnnotation)
        predicate_classes = fieldz_kb.clingo.core.get_or_make_predicate_classes_from_field(
            clingo_context, GeneAnnotation, fields_[0]
        )
        assert len(predicate_classes) >= 1


class TestFactGeneration:
    """Tests for converting objects to facts."""

    def test_simple_object_facts(self, clingo_context):
        @dataclass
        class Gene:
            name: str
            chromosome: int

        obj = Gene(name="TP53", chromosome=17)
        facts = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj)
        assert len(facts) > 0

    def test_entity_fact_present(self, clingo_context):
        @dataclass
        class Metabolite:
            concentration: int

        obj = Metabolite(concentration=42)
        facts = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj)
        entity_facts = [f for f in facts if type(f).__name__ == "metabolite"]
        assert len(entity_facts) == 1
        assert entity_facts[0].id_.startswith("id_")

    def test_fact_values_are_correct(self, clingo_context):
        @dataclass
        class Measurement:
            value: int

        obj = Measurement(value=42)
        facts = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj)
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert any(f.value == 42 for f in value_facts)

    def test_string_field_value(self, clingo_context):
        @dataclass
        class Species:
            name: str

        obj = Species(name="Homo sapiens")
        facts = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj)
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert any(f.value == "Homo sapiens" for f in value_facts)

    def test_none_value_skipped(self, clingo_context):
        @dataclass
        class ProteinOptional:
            name: str
            alias: Optional[str] = None

        obj = ProteinOptional(name="p53", alias=None)
        facts = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj)
        assert len(facts) > 0
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert len(value_facts) == 1
        assert value_facts[0].value == "p53"

    def test_nested_object_facts(self, clingo_context):
        @dataclass
        class CellLocation:
            compartment: str

        @dataclass
        class ProteinLocated:
            name: str
            location: CellLocation

        location = CellLocation(compartment="cytoplasm")
        protein = ProteinLocated(name="insulin", location=location)
        facts = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, protein)

        entity_type_names = {
            type(f).__name__ for f in facts if not hasattr(f, "value")
        }
        assert "proteinLocated" in entity_type_names
        assert "cellLocation" in entity_type_names

    def test_nested_object_linked_by_id(self, clingo_context):
        @dataclass
        class Substrate:
            name: str

        @dataclass
        class ReactionWithSubstrate:
            substrate: Substrate

        obj = ReactionWithSubstrate(substrate=Substrate(name="glucose"))
        facts = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj)

        substrate_entity = [f for f in facts if type(f).__name__ == "substrate"]
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

    def test_list_of_base_types(self, clingo_context):
        @dataclass
        class GeneWithSynonyms:
            synonyms: List[str]

        obj = GeneWithSynonyms(synonyms=["BRCA1", "FANCS", "RNF53"])
        facts = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj)
        assert len(facts) > 0
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert len(value_facts) == 3
        values = {f.value for f in value_facts}
        assert values == {"BRCA1", "FANCS", "RNF53"}

    def test_list_of_fieldz_objects(self, clingo_context):
        @dataclass
        class Metabolite:
            name: str

        @dataclass
        class PathwayWithMetabolites:
            metabolites: List[Metabolite]

        obj = PathwayWithMetabolites(
            metabolites=[Metabolite(name="glucose"), Metabolite(name="pyruvate")]
        )
        facts = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj)
        assert len(facts) > 0

        metabolite_entities = [
            f for f in facts if type(f).__name__ == "metabolite"
        ]
        assert len(metabolite_entities) == 2

    def test_deterministic_ids(self, clingo_context):
        @dataclass
        class Enzyme:
            name: str

        obj = Enzyme(name="hexokinase")
        facts = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj)
        entity_fact = [f for f in facts if type(f).__name__ == "enzyme"][0]
        assert entity_fact.id_ == "id_0"

    def test_deterministic_ids_sequential(self, clingo_context):
        @dataclass
        class Reaction:
            name: str

        obj1 = Reaction(name="glycolysis_step_1")
        obj2 = Reaction(name="glycolysis_step_2")
        facts1 = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj1)
        facts2 = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj2)

        entity1 = [f for f in facts1 if type(f).__name__ == "reaction"][0]
        entity2 = [f for f in facts2 if type(f).__name__ == "reaction"][0]
        assert entity1.id_ == "id_0"
        assert entity2.id_ == "id_1"

    def test_empty_list_field(self, clingo_context):
        @dataclass
        class EmptyPathway:
            reactions: List[str] = field(default_factory=list)

        obj = EmptyPathway(reactions=[])
        facts = fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj)
        entity_facts = [f for f in facts if type(f).__name__ == "emptyPathway"]
        assert len(entity_facts) == 1
        value_facts = [f for f in facts if hasattr(f, "value")]
        assert len(value_facts) == 0

    def test_unsupported_value_type_raises_error(self, clingo_context):
        @dataclass
        class BadType:
            data: dict

        obj = BadType(data={"a": 1})
        with pytest.raises(ValueError, match="not supported"):
            fieldz_kb.clingo.core.make_facts_from_object(clingo_context, obj)


class TestResetCaches:
    """Tests for the context reset functionality."""

    def test_reset_clears_type_cache(self):
        @dataclass
        class ResetTest:
            name: str

        context = fieldz_kb.clingo.core.make_context()
        fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            context, ResetTest
        )
        assert ResetTest in context.type_to_predicate_class

        context.reset()
        assert ResetTest not in context.type_to_predicate_class

    def test_reset_resets_id_counter(self):
        @dataclass
        class CounterTest:
            name: str

        context = fieldz_kb.clingo.core.make_context()
        obj = CounterTest(name="test")
        facts = fieldz_kb.clingo.core.make_facts_from_object(context, obj)
        entity = [f for f in facts if type(f).__name__ == "counterTest"][0]
        first_id = entity.id_

        context.reset()

        facts2 = fieldz_kb.clingo.core.make_facts_from_object(context, obj)
        entity2 = [f for f in facts2 if type(f).__name__ == "counterTest"][0]
        assert entity2.id_ == first_id
