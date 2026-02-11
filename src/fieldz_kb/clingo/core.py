"""Core clingo integration for fieldz_kb.

This module provides the core functionality for converting dataclass-like objects
to clingo predicates. It includes:

- Predicate class generation from Python types (via clorm)
- Object-to-fact conversion
- Support for primitives, collections, and nested dataclasses
- Caching of generated predicate classes
"""

import abc
import itertools
import types

import clorm
import fieldz

import fieldz_kb.typeinfo


_base_types = (int, str, float, bool)
_array_types = (list, tuple, set, frozenset)
_ordered_array_types = (list, tuple)

_type_to_predicate_class = {}
_field_key_to_predicate_class = {}
_id_counter = itertools.count()


def reset_caches():
    """Reset all internal predicate class caches and ID counter.

    Primarily intended for use in tests to ensure isolation between test cases.
    """
    global _id_counter
    _type_to_predicate_class.clear()
    _field_key_to_predicate_class.clear()
    _id_counter = itertools.count()


def _make_fact_id():
    return f"id_{next(_id_counter)}"


def _make_predicate_class_name_from_type(type_):
    predicate_class_name = type_.__name__
    predicate_class_name = predicate_class_name[0].lower() + predicate_class_name[1:]
    return predicate_class_name


def _make_predicate_name_from_field(field):
    field_name = field.name
    field_name = field_name[0].upper() + field_name[1:]
    predicate_class_name = f"has{field_name}"
    return predicate_class_name


def _get_or_make_predicate_classes_from_type(
    type_, module=None, make_predicate_classes_recursively=True, guard=None
):
    if guard is None:
        guard = set([])
    cached = _type_to_predicate_class.get(type_)
    if cached is not None:
        return [cached]
    guard.add(type_)
    predicate_classes = _make_predicate_classes_from_type(
        type_,
        module=module,
        make_predicate_classes_recursively=make_predicate_classes_recursively,
        guard=guard,
    )
    _type_to_predicate_class[type_] = predicate_classes[0]
    return predicate_classes


def _get_or_make_predicate_classes_from_field(
    fieldz_class,
    field,
    type_=None,
    module=None,
    make_predicate_classes_recursively=True,
    guard=None,
):
    if guard is None:
        guard = set([])
    cached = _field_key_to_predicate_class.get((fieldz_class, field.name, type_))
    if cached is not None:
        return [cached]
    guard.add((fieldz_class, field.name))
    predicate_classes_and_keys = _make_predicate_classes_and_keys_from_field(
        fieldz_class,
        field,
        module=module,
        make_predicate_classes_recursively=make_predicate_classes_recursively,
        guard=guard,
    )
    for predicate_class, key in predicate_classes_and_keys:
        _field_key_to_predicate_class[key] = predicate_class
    return [_[0] for _ in predicate_classes_and_keys]


def _make_predicate_classes_from_type(
    type_, module=None, make_predicate_classes_recursively=True, guard=None
):
    if guard is None:
        guard = set([])
    if fieldz_kb.typeinfo.is_fieldz_class(type_):
        predicate_classes = _make_predicate_classes_from_fieldz_class(
            type_,
            module=module,
            make_predicate_classes_recursively=make_predicate_classes_recursively,
            guard=guard,
        )
    else:
        raise ValueError(f"type {type_} not supported")
    return predicate_classes


def _make_predicate_classes_from_fieldz_class(
    fieldz_class, module=None, make_predicate_classes_recursively=True, guard=None
):
    predicate_classes = []
    if guard is None:
        guard = set([])
    predicate_class_name = _make_predicate_class_name_from_type(fieldz_class)
    fieldz_class_bases = fieldz_class.__bases__
    for base_class in fieldz_class_bases:
        if (
            base_class not in (object, abc.ABC)
            and not base_class.__name__.startswith("_")
            and base_class.__name__ != fieldz_class.__name__
        ):
            _get_or_make_predicate_classes_from_type(
                base_class,
                make_predicate_classes_recursively=make_predicate_classes_recursively,
                guard=guard,
            )
    predicate_class_bases = (clorm.Predicate,)
    predicate_class_dict = {"__annotations__": {"id_": clorm.ConstantStr}}
    predicate_class = type(clorm.Predicate)(
        predicate_class_name, predicate_class_bases, predicate_class_dict
    )
    predicate_classes.append(predicate_class)
    for field in fieldz.fields(fieldz_class):
        field_predicate_classes = _get_or_make_predicate_classes_from_field(
            fieldz_class,
            field,
            type_=None,
            module=fieldz_class.__module__,
            make_predicate_classes_recursively=make_predicate_classes_recursively,
            guard=guard,
        )
        predicate_classes += field_predicate_classes
    return predicate_classes


def _make_predicate_classes_and_keys_from_field(
    fieldz_class,
    field,
    module=None,
    make_predicate_classes_recursively=True,
    guard=None,
):
    predicate_classes = []
    if guard is None:
        guard = set([])
    predicate_name = _make_predicate_name_from_field(field)
    predicate_class_bases = (clorm.Predicate,)
    type_hint = field.type
    types_ = fieldz_kb.typeinfo.get_types_from_type_hint(type_hint)
    for type_ in types_:
        type_origin, type_args = type_
        if type_origin is not types.NoneType:
            annotations = {"id_": clorm.ConstantStr}
            if type_origin in _base_types:
                annotations["value"] = type_origin
            elif fieldz_kb.typeinfo.is_fieldz_class(type_origin):
                annotations["value"] = clorm.ConstantStr
                if type_origin not in guard:
                    _get_or_make_predicate_classes_from_type(type_origin)
            elif type_origin in _array_types:
                for type_arg in type_args:
                    if type_arg[0] in _base_types:
                        annotations["value"] = type_arg[0]
                    else:
                        annotations["value"] = clorm.ConstantStr
            else:
                raise ValueError(f"type {type_} not supported")
            predicate_class_dict = {
                "__annotations__": annotations,
            }
            predicate_class_name = (
                f"{fieldz_class.__name__}_{predicate_name}_{type_origin.__name__}"
            )
            predicate_class = type(clorm.Predicate)(
                predicate_class_name,
                predicate_class_bases,
                predicate_class_dict,
                name=predicate_name,
            )
            predicate_classes.append(
                (predicate_class, (fieldz_class, field.name, type_origin))
            )
    return predicate_classes


def _make_facts_from_fieldz_object(fieldz_object):
    facts = []
    fieldz_class = type(fieldz_object)
    fieldz_object_predicate_classes = _get_or_make_predicate_classes_from_type(
        fieldz_class
    )
    fieldz_object_id = _make_fact_id()
    fieldz_object_predicate_class = fieldz_object_predicate_classes[0]
    fieldz_object_fact = fieldz_object_predicate_class(fieldz_object_id)
    facts.append(fieldz_object_fact)
    for field in fieldz.fields(fieldz_class):
        attribute_value = getattr(fieldz_object, field.name)
        attribute_value_type = type(attribute_value)
        if attribute_value is None:
            continue
        if type(attribute_value) in _base_types:
            field_predicate_classes = _get_or_make_predicate_classes_from_field(
                fieldz_class, field, type(attribute_value)
            )
            field_predicate_class = field_predicate_classes[0]
            values = [attribute_value]
        elif fieldz_kb.typeinfo.is_fieldz_class(attribute_value_type):
            field_predicate_classes = _get_or_make_predicate_classes_from_field(
                fieldz_class, field, type(attribute_value)
            )
            field_predicate_class = field_predicate_classes[0]
            attribute_facts = _make_facts_from_fieldz_object(attribute_value)
            facts += attribute_facts
            attribute_fact = attribute_facts[0]
            values = [attribute_fact.id_]
        elif attribute_value_type in _array_types:
            values = []
            for attribute_value_element in attribute_value:
                attribute_value_element_type = type(attribute_value_element)
                if attribute_value_element_type in _base_types:
                    field_predicate_classes = _get_or_make_predicate_classes_from_field(
                        fieldz_class, field, type(attribute_value_element)
                    )
                    field_predicate_class = field_predicate_classes[0]
                    values.append(attribute_value_element)
                elif fieldz_kb.typeinfo.is_fieldz_class(attribute_value_element_type):
                    field_predicate_classes = _get_or_make_predicate_classes_from_field(
                        fieldz_class, field, type(attribute_value_element)
                    )
                    field_predicate_class = field_predicate_classes[0]
                    attribute_element_facts = _make_facts_from_fieldz_object(
                        attribute_value_element
                    )
                    facts += attribute_element_facts
                    attribute_element_fact = attribute_element_facts[0]
                    values.append(attribute_element_fact.id_)
        else:
            raise ValueError(f"type {attribute_value_type} not supported")
        for value in values:
            field_fact = field_predicate_class(id_=fieldz_object_id, value=value)
            facts = [
                field_fact
            ] + facts  # TODO: put at the end to have a more efficient append
    return facts


def make_facts_from_object(obj):
    type_ = type(obj)
    if fieldz_kb.typeinfo.is_fieldz_class(type_):
        return _make_facts_from_fieldz_object(obj)
    else:
        raise ValueError(f"type {type_} not supported")
