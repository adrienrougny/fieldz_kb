import typing
import types

import fieldz


def is_fieldz_class(type_):
    for adapter in fieldz._functions.ADAPTERS:
        if adapter.is_instance(type_):
            return True
    return False


def is_missing_type(type_):
    return type_ is fieldz._types._MISSING_TYPE.MISSING


def get_types_from_type_hint(type_hint, module=None):
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
            type_hint_origin, (list, tuple, set, frozenset, dict)
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
        return get_types_from_type_hint(
            typing._eval_type(type_hint, globals(), globals()), module=module
        )
    elif isinstance(type_hint, str):  # forwardref
        type_hint = typing.ForwardRef(type_hint, module=module)
        return get_types_from_type_hint(type_hint, module=module)
    elif type_hint == Ellipsis:
        return tuple()
    else:
        raise ValueError(
            f'type hint "{type_hint}" of type {type(type_hint)} not supported'
        )
