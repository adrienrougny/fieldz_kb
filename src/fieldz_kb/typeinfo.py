"""Type introspection utilities for fieldz_kb.

This module provides utilities for introspecting type hints, including
support for forward references, unions, optionals, and generic types.
"""

import sys
import typing
import types
import collections.abc

import fieldz


def is_fieldz_class(type_):
    """Check if a type is a fieldz-supported class (e.g., dataclass).

    Args:
        type_: The type to check

    Returns:
        True if the type is a fieldz class, False otherwise
    """
    for adapter in fieldz._functions.ADAPTERS:
        if adapter.is_instance(type_):
            return True
    return False


def is_missing_type(type_):
    """Check if a type is the fieldz missing type sentinel.

    Args:
        type_: The type to check

    Returns:
        True if the type is the missing sentinel, False otherwise
    """
    return type_ is fieldz._types._MISSING_TYPE.MISSING


def _evaluate_forward_ref(forward_ref: typing.ForwardRef) -> type:
    """Evaluate a ForwardRef to its resolved type.

    Uses ForwardRef.evaluate() on Python 3.14+, falls back to
    typing._eval_type() on earlier versions.

    Args:
        forward_ref: The ForwardRef to evaluate.

    Returns:
        The resolved type.
    """
    if sys.version_info >= (3, 14):
        return forward_ref.evaluate()
    if sys.version_info >= (3, 13):
        return typing._eval_type(
            forward_ref, globals(), globals(), type_params=()
        )
    return typing._eval_type(forward_ref, globals(), globals())


def get_types_from_type_hint(type_hint, module=None):
    """Extract type information from a type hint.

        This function recursively processes type hints to extract the underlying
    types, handling:
        - Union types (including Optional)
        - Generic types (List, Dict, Set, etc.)
        - Forward references (including string annotations)
        - Base types

        Args:
            type_hint: The type hint to process
            module: Optional module name for resolving forward references

        Returns:
            A tuple of (type_origin, type_args) pairs describing the type structure

        Raises:
            ValueError: If the type hint format is not supported
    """
    if (
        type_hint_origin := typing.get_origin(type_hint)
    ) is not None:  # subscribed type
        if (
            isinstance(type_hint_origin, type)
            and issubclass(type_hint_origin, types.UnionType)
            or type_hint_origin is typing.Union
        ):  # union
            type_hint_args = list(typing.get_args(type_hint))
            return tuple(
                [
                    get_types_from_type_hint(type_hint_arg, module=module)[0]
                    for type_hint_arg in type_hint_args
                ]
            )
        elif type_hint_origin is typing.Optional:  # optional: we make type_hint | None
            type_hint_args = list(typing.get_args(type_hint))
            type_hint = type_hint_args[0] | None
            return get_types_from_type_hint(type_hint, module=module)
        elif isinstance(type_hint_origin, type) and issubclass(  # a generic
            type_hint_origin, collections.abc.Collection
        ):
            return tuple(
                [
                    (
                        type_hint_origin,
                        tuple(
                            sum(
                                [
                                    get_types_from_type_hint(
                                        type_hint_arg, module=module
                                    )
                                    for type_hint_arg in typing.get_args(type_hint)
                                ],
                                tuple(),
                            )
                        ),
                    )
                ]
            )
        else:
            raise ValueError(f"type hint {type_hint} not supported")
    elif isinstance(type_hint, type):  # an unsubscribed type
        return tuple(
            [
                (
                    type_hint,
                    tuple(),
                )
            ]
        )
    elif isinstance(type_hint, typing.ForwardRef):  # forwardref
        if module is not None:
            type_hint = typing.ForwardRef(type_hint.__forward_arg__, module=module)
        resolved = _evaluate_forward_ref(type_hint)
        return get_types_from_type_hint(resolved, module=module)
    elif isinstance(type_hint, str):  # forwardref
        type_hint = typing.ForwardRef(type_hint, module=module)
        return get_types_from_type_hint(type_hint, module=module)
    elif type_hint == Ellipsis:
        return tuple()
    else:
        raise ValueError(
            f'type hint "{type_hint}" of type {type(type_hint)} not supported'
        )
