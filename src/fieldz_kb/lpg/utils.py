"""Shared utility functions for fieldz_kb LPG backends.

This module provides helper functions for type classification, relationship
naming, and field introspection.
"""

import dataclasses
import re

import fieldz
import inflect

import fieldz_kb.typeinfo


BASE_TYPES: tuple[type, ...] = (int, str, float, bool)
ARRAY_TYPES: tuple[type, ...] = (list, tuple, set, frozenset)
ORDERED_ARRAY_TYPES: tuple[type, ...] = (list, tuple)


@dataclasses.dataclass(frozen=True)
class TypeAttributes:
    """Describes how a type maps to a node property or relationship.

    Args:
        kind: One of "primitive", "array", or "relationship".
        target_types: Frozenset of target type tuples.
        many: Whether the field represents a to-many relationship.
        ordered: Whether ordering matters for this field.
    """

    kind: str
    target_types: frozenset
    many: bool
    ordered: bool


def make_node_class_name_from_type(type_: type) -> str:
    """Return a node class name for a given Python type.

    Args:
        type_: The Python type.

    Returns:
        The class name string.
    """
    return type_.__name__


def make_relationship_type_from_field_name(
    field_name: str, many: bool = False
) -> str:
    """Generate a relationship type string from a field name.

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
            singular = inflect_engine.singular_noun(plural)
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


def get_type_attributes(type_: tuple) -> TypeAttributes:
    """Classify a type as primitive, array, or relationship and extract attributes.

    Args:
        type_: A tuple of (type_origin, type_args) from get_types_from_type_hint.

    Returns:
        A TypeAttributes describing how the type maps to a node property.
    """
    type_origin, type_args = type_
    type_args = frozenset(type_args)
    if issubclass(type_origin, BASE_TYPES):
        return TypeAttributes(
            kind="primitive",
            target_types=frozenset([type_]),
            many=False,
            ordered=False,
        )
    elif issubclass(type_origin, ARRAY_TYPES):
        many = True
        ordered = issubclass(type_origin, ORDERED_ARRAY_TYPES)
        if len(type_args) == 1:
            type_arg = next(iter(type_args))
            type_arg_origin = type_arg[0]
            kind = "array" if issubclass(type_arg_origin, BASE_TYPES) else "relationship"
        else:
            kind = "relationship"
        return TypeAttributes(
            kind=kind,
            target_types=frozenset(type_args),
            many=many,
            ordered=ordered,
        )
    else:
        return TypeAttributes(
            kind="relationship",
            target_types=frozenset([type_]),
            many=False,
            ordered=False,
        )


def get_array_type_from_field(
    field: fieldz.Field, module: str | None = None
) -> type:
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
            if issubclass(type_, ARRAY_TYPES):
                array_type = type_
    if array_type is None:
        raise ValueError(f"could not find appropriate type for field {field.name}")
    return array_type
