"""Tests for fieldz_kb LPG core: node class generation, object conversion, and database round-trips."""

import enum
import dataclasses
import typing

import pytest
import frozendict

import fieldz_kb.lpg.core
import fieldz_kb.lpg.graph


@dataclasses.dataclass
class Pathway:
    """Module-level dataclass for forward reference testing."""

    name: str
    reactions: typing.List["Reaction"]


@dataclasses.dataclass
class Reaction:
    """Module-level dataclass for forward reference testing."""

    name: str
    enzyme: str
    substrates: typing.List[str]


class TestNodeClassGeneration:
    """Tests for node class generation functions."""

    def test_get_or_make_node_class_from_builtin_int(self):
        node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            fieldz_kb.lpg.core.get_default_context(), int
        )
        assert node_class is fieldz_kb.lpg.graph.Integer

    def test_get_or_make_node_class_from_builtin_str(self):
        node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            fieldz_kb.lpg.core.get_default_context(), str
        )
        assert node_class is fieldz_kb.lpg.graph.String

    def test_get_or_make_node_class_from_builtin_float(self):
        node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            fieldz_kb.lpg.core.get_default_context(), float
        )
        assert node_class is fieldz_kb.lpg.graph.Float

    def test_get_or_make_node_class_from_builtin_bool(self):
        node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            fieldz_kb.lpg.core.get_default_context(), bool
        )
        assert node_class is fieldz_kb.lpg.graph.Boolean

    def test_get_or_make_node_class_caching(self):
        @dataclasses.dataclass
        class Gene:
            name: str

        context = fieldz_kb.lpg.core.get_default_context()
        class1 = fieldz_kb.lpg.core.get_or_make_node_class_from_type(context, Gene)
        class2 = fieldz_kb.lpg.core.get_or_make_node_class_from_type(context, Gene)
        assert class1 is class2

    def test_make_node_class_from_fieldz_class(self):
        @dataclasses.dataclass
        class Protein:
            name: str
            molecular_weight: float

        node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            fieldz_kb.lpg.core.get_default_context(), Protein
        )

        assert node_class.__name__ == "Protein"
        assert issubclass(node_class, fieldz_kb.lpg.graph.BaseNode)

    def test_make_node_class_from_enum(self):
        class Compartment(enum.Enum):
            CYTOPLASM = "cytoplasm"
            NUCLEUS = "nucleus"
            MEMBRANE = "membrane"

        node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            fieldz_kb.lpg.core.get_default_context(), Compartment
        )

        assert node_class.__name__ == "Compartment"

    def test_make_node_class_from_enum_with_int_values(self):
        class EvidenceLevel(enum.Enum):
            LOW = 1
            MEDIUM = 2
            HIGH = 3

        node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            fieldz_kb.lpg.core.get_default_context(), EvidenceLevel
        )

        assert node_class.__name__ == "EvidenceLevel"

    def test_enum_with_mixed_value_types_raises_error(self):
        class MixedEnum(enum.Enum):
            STRING = "active"
            NUMBER = 42

        with pytest.raises(ValueError, match="types of values must all be the same"):
            fieldz_kb.lpg.core.get_or_make_node_class_from_type(
                fieldz_kb.lpg.core.get_default_context(), MixedEnum
            )


class TestMakeNodesFromObject:
    """Tests for converting objects to nodes."""

    def test_make_nodes_from_int(self):
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            fieldz_kb.lpg.core.get_default_context(), 42
        )

        assert len(nodes) == 1
        assert isinstance(nodes[0], fieldz_kb.lpg.graph.Integer)
        assert nodes[0].value == 42
        assert len(relationships) == 0

    def test_make_nodes_from_str(self):
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            fieldz_kb.lpg.core.get_default_context(), "ATP"
        )

        assert len(nodes) == 1
        assert isinstance(nodes[0], fieldz_kb.lpg.graph.String)
        assert nodes[0].value == "ATP"

    def test_make_nodes_from_float(self):
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            fieldz_kb.lpg.core.get_default_context(), 6.022e23
        )

        assert len(nodes) == 1
        assert isinstance(nodes[0], fieldz_kb.lpg.graph.Float)
        assert nodes[0].value == 6.022e23

    def test_make_nodes_from_bool(self):
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            fieldz_kb.lpg.core.get_default_context(), True
        )

        assert len(nodes) == 1
        assert isinstance(nodes[0], fieldz_kb.lpg.graph.Boolean)
        assert nodes[0].value is True

    def test_make_nodes_from_simple_fieldz_object(self):
        @dataclasses.dataclass
        class Metabolite:
            name: str
            molecular_weight: float

        metabolite = Metabolite(name="glucose", molecular_weight=180.16)
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            fieldz_kb.lpg.core.get_default_context(), metabolite
        )

        assert len(nodes) == 1
        node = nodes[0]
        assert isinstance(node, fieldz_kb.lpg.graph.BaseNode)
        assert node.__class__.__name__ == "Metabolite"

    def test_make_nodes_from_list(self):
        data = [1, 2, 3]
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            fieldz_kb.lpg.core.get_default_context(), data
        )

        assert len(nodes) == 4
        list_node = nodes[0]
        assert isinstance(list_node, fieldz_kb.lpg.graph.List)

    def test_make_nodes_from_tuple(self):
        data = (1, 2, 3)
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            fieldz_kb.lpg.core.get_default_context(), data
        )

        assert len(nodes) == 4
        tuple_node = nodes[0]
        assert isinstance(tuple_node, fieldz_kb.lpg.graph.Tuple)

    def test_make_nodes_from_set(self):
        data = {1, 2, 3}
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            fieldz_kb.lpg.core.get_default_context(), data
        )

        assert len(nodes) == 4
        set_node = nodes[0]
        assert isinstance(set_node, fieldz_kb.lpg.graph.Set)

    def test_make_nodes_from_dict(self):
        data = {"ATP": 1, "ADP": 2}
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            fieldz_kb.lpg.core.get_default_context(), data
        )
        dict_node = nodes[0]
        assert isinstance(dict_node, fieldz_kb.lpg.graph.Dict)
        assert len(relationships) > 0

    def test_make_nodes_from_frozendict(self):
        data = frozendict.frozendict({"glucose": 1, "fructose": 2})
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            fieldz_kb.lpg.core.get_default_context(), data
        )

        frozen_node = nodes[0]
        assert isinstance(frozen_node, fieldz_kb.lpg.graph.FrozenDict)

    def test_make_nodes_from_enum(self):
        class Compartment(enum.Enum):
            CYTOPLASM = "cytoplasm"
            NUCLEUS = "nucleus"

        compartment = Compartment.CYTOPLASM
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            fieldz_kb.lpg.core.get_default_context(), compartment
        )

        assert len(nodes) == 1
        node = nodes[0]
        assert node.__class__.__name__ == "Compartment"

    def test_make_nodes_with_integration_mode_hash(self):
        obj = frozenset([1, 2, 3])
        object_to_node = {}
        context = fieldz_kb.lpg.core.get_default_context()
        nodes1, _ = fieldz_kb.lpg.core.make_nodes_from_object(
            context, obj, integration_mode="hash", object_to_node=object_to_node
        )
        nodes2, _ = fieldz_kb.lpg.core.make_nodes_from_object(
            context, obj, integration_mode="hash", object_to_node=object_to_node
        )

        assert nodes1[0] is nodes2[0]

    def test_make_nodes_with_integration_mode_id(self):
        obj1 = [1, 2, 3]
        obj2 = [1, 2, 3]

        context = fieldz_kb.lpg.core.get_default_context()
        nodes1, _ = fieldz_kb.lpg.core.make_nodes_from_object(
            context, obj1, integration_mode="id"
        )
        nodes2, _ = fieldz_kb.lpg.core.make_nodes_from_object(
            context, obj2, integration_mode="id"
        )
        assert nodes1[0] is not nodes2[0]

    def test_unsupported_type_raises_error(self):
        class UnsupportedClass:
            pass

        with pytest.raises(ValueError, match="not supported"):
            fieldz_kb.lpg.core.make_nodes_from_object(
                fieldz_kb.lpg.core.get_default_context(), UnsupportedClass()
            )


class TestTypeMappings:
    """Tests for type to node class mappings."""

    def test_type_to_node_class_mappings(self):
        expected_mappings = {
            int: fieldz_kb.lpg.graph.Integer,
            str: fieldz_kb.lpg.graph.String,
            float: fieldz_kb.lpg.graph.Float,
            bool: fieldz_kb.lpg.graph.Boolean,
            list: fieldz_kb.lpg.graph.List,
            tuple: fieldz_kb.lpg.graph.Tuple,
            set: fieldz_kb.lpg.graph.Set,
            frozenset: fieldz_kb.lpg.graph.FrozenSet,
        }

        context = fieldz_kb.lpg.core.get_default_context()
        for type_, expected_class in expected_mappings.items():
            assert context.type_to_node_class[type_] == expected_class


@pytest.mark.usefixtures("clear_database")
class TestSaveAndRetrieve:
    """Tests for saving objects to a database and retrieving them."""

    def test_save_and_retrieve_simple_object(self, session, clear_database):
        @dataclasses.dataclass
        class Gene:
            name: str
            chromosome: int

        gene = Gene(name="TP53", chromosome=17)

        session.save_from_object(gene)

        results = session.execute_query_as_objects(
            "MATCH (n:Gene) RETURN n"
        )
        assert len(results) == 1

        retrieved = results[0][0]
        assert isinstance(retrieved, Gene)
        assert retrieved.name == "TP53"
        assert retrieved.chromosome == 17

    def test_save_and_retrieve_with_base_types(self, session, clear_database):
        @dataclasses.dataclass
        class Protein:
            name: str
            length: int
            molecular_weight: float
            is_enzyme: bool

        protein = Protein(
            name="p53", length=393, molecular_weight=43.7, is_enzyme=False
        )

        session.save_from_object(protein)

        results = session.execute_query_as_objects(
            "MATCH (n:Protein) RETURN n"
        )
        assert len(results) == 1

        retrieved = results[0][0]
        assert retrieved.name == "p53"
        assert retrieved.length == 393
        assert retrieved.molecular_weight == 43.7
        assert retrieved.is_enzyme is False

    def test_save_and_retrieve_list(self, session, clear_database):
        data = [1, 2, 3]

        session.save_from_object(data)

        results = session.execute_query_as_objects(
            "MATCH (n:List) RETURN n"
        )
        assert len(results) == 1

        retrieved = results[0][0]
        assert sorted(retrieved) == [1, 2, 3]

    def test_save_and_retrieve_enum(self, session, clear_database):
        class Compartment(enum.Enum):
            CYTOPLASM = "cytoplasm"
            NUCLEUS = "nucleus"

        compartment = Compartment.CYTOPLASM

        session.save_from_object(compartment)

        results = session.execute_query_as_objects(
            "MATCH (n:Compartment) RETURN n"
        )
        assert len(results) == 1

        retrieved = results[0][0]
        assert retrieved is Compartment.CYTOPLASM

    def test_save_multiple_objects(self, session, clear_database):
        @dataclasses.dataclass
        class Species:
            name: str

        species = [Species(name="Homo sapiens"), Species(name="Mus musculus")]

        session.save_from_objects(species)

        results = session.execute_query(
            "MATCH (n:Species) RETURN n"
        )
        assert len(results) == 2

    def test_save_with_relationships(self, session, clear_database):
        @dataclasses.dataclass
        class Organism:
            name: str

        @dataclasses.dataclass
        class GeneWithOrganism:
            name: str
            organism: Organism

        organism = Organism(name="Homo sapiens")
        gene = GeneWithOrganism(name="BRCA1", organism=organism)

        session.save_from_object(gene)

        results = session.execute_query(
            "MATCH (n:GeneWithOrganism) RETURN n"
        )
        assert len(results) == 1

        results = session.execute_query(
            "MATCH (n:Organism) RETURN n"
        )
        assert len(results) == 1

        results = session.execute_query(
            "MATCH (g:GeneWithOrganism)-[:HAS_ORGANISM]->(o:Organism) RETURN g, o"
        )
        assert len(results) == 1


@pytest.mark.usefixtures("clear_database")
class TestComplexScenarios:
    """Complex integration scenarios."""

    def test_nested_fieldz_objects(self, session, clear_database):
        @dataclasses.dataclass
        class CellLocation:
            compartment: str
            membrane: str

        @dataclasses.dataclass
        class ProteinWithLocation:
            name: str
            location: CellLocation

        protein = ProteinWithLocation(
            name="insulin receptor",
            location=CellLocation(compartment="cytoplasm", membrane="plasma"),
        )

        session.save_from_object(protein)

        results = session.execute_query_as_objects(
            "MATCH (n:ProteinWithLocation) RETURN n"
        )
        assert len(results) == 1

        retrieved = results[0][0]
        assert retrieved.name == "insulin receptor"
        assert retrieved.location.compartment == "cytoplasm"
        assert retrieved.location.membrane == "plasma"

    def test_list_of_fieldz_objects(self, session, clear_database):
        @dataclasses.dataclass
        class Metabolite:
            name: str

        metabolites = [
            Metabolite(name="glucose"),
            Metabolite(name="pyruvate"),
            Metabolite(name="lactate"),
        ]

        session.save_from_object(metabolites)

        results = session.execute_query_as_objects(
            "MATCH (n:List) RETURN n"
        )
        assert len(results) == 1

        retrieved = results[0][0]
        assert len(retrieved) == 3
        assert all(
            isinstance(item, Metabolite) for item in retrieved
        )
        assert sorted([item.name for item in retrieved]) == [
            "glucose",
            "lactate",
            "pyruvate",
        ]

    def test_dict_with_complex_values(self, session, clear_database):
        @dataclasses.dataclass
        class GeneAnnotation:
            symbol: str

        data = {
            "TP53": GeneAnnotation(symbol="TP53"),
            "BRCA1": GeneAnnotation(symbol="BRCA1"),
        }

        session.save_from_object(data)

        results = session.execute_query_as_objects(
            "MATCH (n:Dict) RETURN n"
        )
        assert len(results) == 1

        retrieved = results[0][0]
        assert "TP53" in retrieved
        assert "BRCA1" in retrieved

    def test_round_trip_complex_object(self, session, clear_database):
        pathway = Pathway(
            name="Glycolysis",
            reactions=[
                Reaction(
                    name="Hexokinase",
                    enzyme="HK1",
                    substrates=["glucose", "ATP"],
                ),
                Reaction(
                    name="Phosphofructokinase",
                    enzyme="PFK1",
                    substrates=["fructose-6-phosphate", "ATP"],
                ),
            ],
        )

        session.save_from_object(pathway)

        results = session.execute_query_as_objects(
            "MATCH (n:Pathway) RETURN n"
        )
        assert len(results) == 1

        retrieved = results[0][0]
        assert retrieved.name == "Glycolysis"
        assert len(retrieved.reactions) == 2
        reaction_names = sorted([r.name for r in retrieved.reactions])
        assert reaction_names == ["Hexokinase", "Phosphofructokinase"]


@pytest.mark.usefixtures("clear_database")
class TestExecuteQueryAsObjects:
    """Tests for execute_query_as_objects method."""

    def test_execute_query_as_objects(self, session, clear_database):
        @dataclasses.dataclass
        class Enzyme:
            name: str
            ec_number: str

        enzymes = [
            Enzyme(name="Hexokinase", ec_number="2.7.1.1"),
            Enzyme(name="Phosphofructokinase", ec_number="2.7.1.11"),
        ]

        session.save_from_objects(enzymes)

        results = session.execute_query_as_objects(
            "MATCH (n:Enzyme) RETURN n ORDER BY n.ec_number"
        )

        assert len(results) == 2
        assert results[0][0].name == "Hexokinase"
        assert results[1][0].name == "Phosphofructokinase"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
