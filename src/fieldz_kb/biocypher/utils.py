"""BioCypher schema utilities for fieldz_kb.

Generates BioCypher schema YAML files from fieldz classes.
"""

import yaml
import pylpg.relationship

import fieldz_kb.lpg.core


def make_biocypher_schema_string_from_classes(
    classes: set[type],
) -> str:
    """Generate a BioCypher schema YAML string from a set of classes.

    Args:
        classes: A set of classes to generate the schema for.

    Returns:
        A YAML string containing the BioCypher schema.
    """
    context = fieldz_kb.lpg.core.get_default_context()
    classes = set(classes)
    schema = {}
    for class_ in classes:
        node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            context,
            class_,
            make_node_classes_recursively=True,
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
        for attribute_name, attribute_value in vars(node_class).items():
            if isinstance(attribute_value, pylpg.relationship.RelationshipTo):
                relationship_label = attribute_value._relationship_class.__type__
                if relationship_label not in schema:
                    schema[relationship_label] = {
                        "is_a": "related to",
                        "represented_as": "edge",
                        "input_label": relationship_label,
                    }
    return yaml.safe_dump(schema)


def make_biocypher_schema_file_from_classes(
    classes: set[type],
    output_file_path: str,
) -> None:
    """Generate a BioCypher schema YAML file from a set of classes.

    Args:
        classes: A set of classes to generate the schema for.
        output_file_path: The path to write the YAML file to.
    """
    biocypher_schema_string = make_biocypher_schema_string_from_classes(classes)
    with open(output_file_path, "w") as output_file:
        output_file.write(biocypher_schema_string)
