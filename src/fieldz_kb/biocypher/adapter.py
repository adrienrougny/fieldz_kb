"""BioCypher adapter for fieldz_kb.

Converts fieldz objects to BioCypher-compatible node and relationship tuples.
"""

import fieldz_kb.lpg.core


class Adapter:
    """Adapter for converting fieldz objects to BioCypher format.

    Takes a fieldz object and converts it to BioCypher-compatible
    nodes and relationships using the LPG conversion layer.

    Args:
        obj: The object to convert to BioCypher format.

    Example:
        >>> import dataclasses
        >>> import fieldz_kb.biocypher.adapter
        >>>
        >>> @dataclasses.dataclass
        ... class Gene:
        ...     name: str
        ...     chromosome: int
        >>>
        >>> adapter = fieldz_kb.biocypher.adapter.Adapter(Gene(name="TP53", chromosome=17))
        >>> nodes, relationships = adapter.make_nodes_and_relationships()
    """

    def __init__(self, obj: object) -> None:
        """Initialize the adapter with an object.

        Args:
            obj: The object to convert to BioCypher format.
        """
        self.obj = obj
        self._context = fieldz_kb.lpg.core.get_default_context()

    def make_nodes_and_relationships(
        self,
    ) -> tuple[list[tuple], list[tuple]]:
        """Convert the object to BioCypher nodes and relationships.

        Returns:
            A tuple of (biocypher_nodes, biocypher_relationships) where:
            - biocypher_nodes: List of (id, label, properties) tuples.
            - biocypher_relationships: List of (source_id, target_id, label, properties) tuples.
        """
        nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            self._context, self.obj
        )
        biocypher_nodes = []
        for node in nodes:
            label = node.__class__.__name__
            properties = node.to_dict()
            biocypher_nodes.append((id(node), label, properties))
        biocypher_relationships = []
        for relationship in relationships:
            label = type(relationship).__type__
            relationship_properties = {}
            for property_name in type(relationship).__primitive_properties__:
                property_value = getattr(relationship, property_name)
                if property_value is not None:
                    relationship_properties[property_name] = property_value
            biocypher_relationships.append((
                id(relationship.source),
                id(relationship.target),
                label,
                relationship_properties,
            ))
        return biocypher_nodes, biocypher_relationships
