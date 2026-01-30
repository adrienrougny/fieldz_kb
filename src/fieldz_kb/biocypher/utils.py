"""BioCypher schema utilities for fieldz_kb.

This module provides utilities for generating BioCypher schema files
from fieldz classes.
"""

import yaml
import neomodel
import fieldz_kb.neo4j.core


def make_biocypher_schema_string_from_classes(classes):
    """Generate a BioCypher schema YAML string from a set of classes.

    Args:
        classes: A set of classes to generate the schema for

    Returns:
        A YAML string containing the BioCypher schema
    """
    classes = set(classes)
    schema = {}
    for class_ in classes:
        node_class = fieldz_kb.neo4j.core.get_or_make_node_class_from_type(
            class_, make_node_classes_recursively=True
        )
        label = node_class.__name__
        input_label = label
        base_node_class = node_class.__bases__[0]
        base_node_class_name = base_node_class.__name__
        if base_node_class not in classes and base_node_class_name not in schema:
            schema[base_node_class_name] = {
                "is_a": "entity",
                "input_label": base_node_class.__name__,
                "represented_as": "node",
            }
        is_a = base_node_class_name
        schema[label] = {
            "input_label": input_label,
            "is_a": is_a,
            "represented_as": "node",
        }
        relationships = [
            property_
            for property_ in node_class.defined_properties().values()
            if isinstance(property_, neomodel.RelationshipTo)
        ]
        for relationship in relationships:
            relationship_label = relationship.definition["relation_type"]
            if relationship_label not in schema:
                schema[relationship_label] = {
                    "is_a": "related to",
                    "represented_as": "edge",
                    "input_label": relationship_label,
                }
    return yaml.safe_dump(schema)


def make_biocypher_schema_file_from_classes(classes, output_file_path):
    """Generate a BioCypher schema YAML file from a set of classes.

    Args:
        classes: A set of classes to generate the schema for
        output_file_path: The path to write the YAML file to
    """
    biocypher_schema_string = make_biocypher_schema_string_from_classes(classes)
    with open(output_file_path, "w") as f:
        f.write(biocypher_schema_string)
