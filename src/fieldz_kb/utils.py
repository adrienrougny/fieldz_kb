"""Shared utility functions for fieldz_kb backends.

This module provides backend-agnostic helper functions used by both
the neomodel and pylpg backends for type classification, relationship
naming, and field introspection.
"""

import re

import inflect

import fieldz_kb.typeinfo


# Type classification constants
_base_types = (int, str, float, bool)
_array_types = (list, tuple, set, frozenset)
_ordered_array_types = (list, tuple)


def _make_node_class_name_from_type(type_):
    """Return a node class name for a given Python type.

    Args:
        type_: The Python type.

    Returns:
        The class name string.
    """
    return type_.__name__


def _make_relationship_type_from_field_name(field_name, many=False):
    """Generate a Neo4j relationship type string from a field name.

    For plural field names (many=True), singularizes the name segments.
    For example: 'employees' -> 'HAS_EMPLOYEE', 'userProfiles' -> 'HAS_USER_PROFILE'.

    Args:
        field_name: The field name to convert.
        many: Whether the field represents a to-many relationship.

    Returns:
        A relationship type string like 'HAS_FIELD_NAME'.
    """
    if many:
        inflect_engine = inflect.engine()
        field_name = re.sub(
            "(.)([A-Z][a-z]+)",
            r"\1_\2",
            field_name,
        )
        field_name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", field_name).lower()
        plurals = field_name.split("_")
        singulars = []
        for i, plural in enumerate(plurals):
            singular = inflect_engine.singular_noun(
                plural
            )  # returns False if already singular
            if singular and singular != plural:
                singulars.append(singular)
                break
            else:
                singulars.append(plural)
        singulars += plurals[i + 1 :]
        singulars = [singular.upper() for singular in singulars]
        relationship_type = f"HAS_{'_'.join(singulars)}"
    else:
        relationship_type = f"HAS_{field_name.upper()}"
    return relationship_type


def _get_node_property_attributes_from_type(type_):
    """Classify a type as base, array, or relationship and extract attributes.

    Args:
        type_: A tuple of (type_origin, type_args) from get_types_from_type_hint.

    Returns:
        A tuple of (property_type, target_types, many, ordered) where:
        - property_type: "base", "array", or "relationship"
        - target_types: frozenset of target types
        - many: whether it's a to-many relationship
        - ordered: whether ordering matters
    """
    type_origin, type_args = type_
    type_args = frozenset(type_args)
    if issubclass(type_origin, _base_types):  # base type, we ignore subtypes
        property_type = "base"
        ordered = False
        many = False
        target_types = frozenset([type_])
    elif issubclass(type_origin, _array_types):  # array type
        many = True
        if issubclass(type_origin, _ordered_array_types):
            ordered = True
        else:
            ordered = False
        if len(type_args) == 1:  # one subtype
            type_arg = next(iter(type_args))
            type_arg_origin = type_arg[0]
            if issubclass(type_arg_origin, _base_types):  # subtype is base type
                property_type = "array"
            else:  # subtype is not base type, must be a relationship
                property_type = "relationship"
        else:  # no subtype (Any) or more than one subtype, must be a relationship
            property_type = "relationship"
        target_types = frozenset(type_args)
    else:
        many = False
        ordered = False
        property_type = "relationship"
        target_types = frozenset([type_])
    return (
        property_type,
        target_types,
        many,
        ordered,
    )


def _get_array_type_from_field(field, module=None):
    """Determine the collection type for a field.

    Args:
        field: The fieldz field descriptor.
        module: Module name for resolving forward references.

    Returns:
        The collection type (list, tuple, set, frozenset).

    Raises:
        ValueError: If no appropriate collection type can be determined.
    """
    array_type = None
    default_factory = field.default_factory
    if not fieldz_kb.typeinfo.is_missing_type(default_factory):
        array_type = default_factory
    else:
        types = fieldz_kb.typeinfo.get_types_from_type_hint(field.type, module=module)
        for type_, _ in types:
            if issubclass(type_, _array_types):
                array_type = type_
    if array_type is None:
        raise ValueError(f"could not find appropriate type for field {field.name}")
    return array_type
