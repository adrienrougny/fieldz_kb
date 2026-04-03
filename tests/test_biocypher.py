"""Tests for fieldz_kb biocypher adapter and schema utilities."""

import dataclasses
import typing

import pytest

import fieldz_kb.biocypher.adapter
import fieldz_kb.biocypher.utils


class TestAdapter:
    """Tests for the BioCypher Adapter."""

    def test_simple_object_produces_nodes(self):
        @dataclasses.dataclass
        class Gene:
            name: str
            chromosome: int

        adapter = fieldz_kb.biocypher.adapter.Adapter(
            Gene(name="TP53", chromosome=17)
        )
        nodes, relationships = adapter.make_nodes_and_relationships()

        assert len(nodes) == 1
        node_id, label, properties = nodes[0]
        assert label == "Gene"
        assert properties["name"] == "TP53"
        assert properties["chromosome"] == 17

    def test_simple_object_has_no_relationships(self):
        @dataclasses.dataclass
        class Metabolite:
            name: str

        adapter = fieldz_kb.biocypher.adapter.Adapter(
            Metabolite(name="glucose")
        )
        nodes, relationships = adapter.make_nodes_and_relationships()

        assert len(nodes) == 1
        assert len(relationships) == 0

    def test_nested_object_produces_relationship(self):
        @dataclasses.dataclass
        class Organism:
            name: str

        @dataclasses.dataclass
        class ProteinWithOrganism:
            name: str
            organism: Organism

        protein = ProteinWithOrganism(
            name="p53", organism=Organism(name="Homo sapiens")
        )
        adapter = fieldz_kb.biocypher.adapter.Adapter(protein)
        nodes, relationships = adapter.make_nodes_and_relationships()

        assert len(nodes) == 2
        assert len(relationships) == 1

        labels = {node[1] for node in nodes}
        assert "ProteinWithOrganism" in labels
        assert "Organism" in labels

        relationship_source_id, relationship_target_id, label, properties = (
            relationships[0]
        )
        assert label == "HAS_ORGANISM"

    def test_relationship_source_and_target_match_node_ids(self):
        @dataclasses.dataclass
        class CellLocation:
            compartment: str

        @dataclasses.dataclass
        class GeneLocated:
            name: str
            location: CellLocation

        gene = GeneLocated(
            name="BRCA1", location=CellLocation(compartment="nucleus")
        )
        adapter = fieldz_kb.biocypher.adapter.Adapter(gene)
        nodes, relationships = adapter.make_nodes_and_relationships()

        node_ids = {node[0] for node in nodes}
        for source_id, target_id, label, properties in relationships:
            assert source_id in node_ids
            assert target_id in node_ids

    def test_list_produces_multiple_nodes(self):
        data = [1, 2, 3]
        adapter = fieldz_kb.biocypher.adapter.Adapter(data)
        nodes, relationships = adapter.make_nodes_and_relationships()

        assert len(nodes) == 4
        assert len(relationships) == 3

    def test_relationship_properties_included(self):
        @dataclasses.dataclass
        class Substrate:
            name: str

        @dataclasses.dataclass
        class ReactionWithSubstrates:
            name: str
            substrates: typing.List[Substrate]

        reaction = ReactionWithSubstrates(
            name="Hexokinase",
            substrates=[
                Substrate(name="glucose"),
                Substrate(name="ATP"),
            ],
        )
        adapter = fieldz_kb.biocypher.adapter.Adapter(reaction)
        nodes, relationships = adapter.make_nodes_and_relationships()

        ordered_relationships = [
            relationship
            for relationship in relationships
            if relationship[3]
        ]
        assert len(ordered_relationships) > 0
        for _, _, _, properties in ordered_relationships:
            assert "order" in properties


class TestSchemaGeneration:
    """Tests for BioCypher schema YAML generation."""

    def test_schema_contains_class(self):
        @dataclasses.dataclass
        class Enzyme:
            name: str

        schema_string = fieldz_kb.biocypher.utils.make_biocypher_schema_string_from_classes(
            {Enzyme}
        )
        assert "Enzyme" in schema_string
        assert "represented_as: node" in schema_string

    def test_schema_contains_base_class(self):
        @dataclasses.dataclass
        class Protein:
            name: str

        schema_string = fieldz_kb.biocypher.utils.make_biocypher_schema_string_from_classes(
            {Protein}
        )
        assert "BaseNode" in schema_string

    def test_schema_contains_relationship(self):
        @dataclasses.dataclass
        class Compartment:
            name: str

        @dataclasses.dataclass
        class ProteinLocated:
            name: str
            compartment: Compartment

        schema_string = fieldz_kb.biocypher.utils.make_biocypher_schema_string_from_classes(
            {ProteinLocated}
        )
        assert "HAS_COMPARTMENT" in schema_string
        assert "represented_as: edge" in schema_string
