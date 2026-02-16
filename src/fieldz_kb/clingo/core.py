"""Core clingo integration for fieldz_kb.

This module provides the core functionality for converting dataclass-like objects
to clingo predicates. It includes:

- Predicate class generation from Python types (via clorm)
- Object-to-fact conversion
- Support for primitives, enums, collections, and nested dataclasses
- Caching of generated predicate classes
"""

import abc
import enum
import itertools
import types
import re

import clorm
import fieldz
import inflect

import fieldz_kb.typeinfo


_base_types = (int, str, bool)
_array_types = (list, tuple, set, frozenset)
_ordered_array_types = (list, tuple)

_type_to_predicate_class = {}
_field_key_to_predicate_class = {}
_id_counter = itertools.count()


class FloatField(clorm.StringField):
    pytocl = lambda f: str(f)
    cltopy = lambda s: float(s)


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


def _make_predicate_name_from_field(field, many):
    field_name = field.name
    words = field_name.split("_")
    if not words[-1]:
        del words[-1]
        words[-1] = f"{words[-1]}_"
    if many:
        inflect_engine = inflect.engine()
        singulars = []
        for i, word in enumerate(words):
            singular = inflect_engine.singular_noun(
                word
            )  # returns False if already singular
            if singular and singular != word:
                singulars.append(singular)
                break
            else:
                singulars.append(word)
        singulars += words[i + 1 :]
        words = singulars
    words = [word[0].upper() + word[1:] for word in words]
    predicate_class_name = f"has{''.join(words)}"
    return predicate_class_name


def _make_predicate_class(
    predicate_class_name, predicate_name: str, fields: dict
) -> type:
    annotations = {}
    attributes = {}
    for name, type_ in fields.items():
        if isinstance(type_, type) and issubclass(type_, clorm.StringField):
            attributes[name] = clorm.field(type_)
            annotations[name] = str
        else:
            annotations[name] = type_
    attributes["__annotations__"] = annotations
    return type(clorm.Predicate)(
        predicate_class_name, (clorm.Predicate,), attributes, name=predicate_name
    )


def get_or_make_predicate_classes_from_type(
    type_, module=None, make_predicate_classes_recursively=True, guard=None
):
    if guard is None:
        guard = set([])
    cached = _type_to_predicate_class.get(type_)
    if cached is not None:
        return cached
    guard.add(type_)
    predicate_classes = _make_predicate_classes_from_type(
        type_,
        module=module,
        make_predicate_classes_recursively=make_predicate_classes_recursively,
        guard=guard,
    )
    _type_to_predicate_class[type_] = predicate_classes
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
    elif issubclass(type_, enum.Enum):
        predicate_classes = _make_predicate_classes_from_enum_class(type_)
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
            get_or_make_predicate_classes_from_type(
                base_class,
                make_predicate_classes_recursively=make_predicate_classes_recursively,
                guard=guard,
            )
    predicate_fields = {"id_": clorm.ConstantStr}
    predicate_class = _make_predicate_class(
        predicate_class_name=predicate_class_name,
        predicate_name=predicate_class_name,
        fields=predicate_fields,
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


def _make_predicate_classes_from_enum_class(enum_class):
    predicate_classes = []
    predicate_class_name = _make_predicate_class_name_from_type(enum_class)
    predicate_fields = {"id_": clorm.ConstantStr}
    predicate_class = _make_predicate_class(
        predicate_class_name=predicate_class_name,
        predicate_name=predicate_class_name,
        fields=predicate_fields,
    )
    predicate_classes.append(predicate_class)
    has_name_class_name = f"{predicate_class_name}_hasName"
    has_name_dict = {
        "__annotations__": {"id_": clorm.ConstantStr, "value": clorm.ConstantStr}
    }
    has_name_class = type(clorm.Predicate)(
        has_name_class_name, (clorm.Predicate,), has_name_dict, name="hasName"
    )
    predicate_classes.append(has_name_class)

    # hasValue predicate - depends on enum value type
    item_value_types = set([type(item.value) for item in enum_class])
    if len(item_value_types) != 1:
        raise ValueError(
            f"enum of type {enum_class} not supported: types of values must all be the same"
        )
    item_value_type = next(iter(item_value_types))

    has_value_class_name = f"{predicate_class_name}_hasValue"
    if item_value_type in _base_types:
        value_annotation = item_value_type
    else:
        value_annotation = clorm.ConstantStr
    has_value_dict = {
        "__annotations__": {"id_": clorm.ConstantStr, "value": value_annotation}
    }
    has_value_class = type(clorm.Predicate)(
        has_value_class_name, (clorm.Predicate,), has_value_dict, name="hasValue"
    )
    predicate_classes.append(has_value_class)

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
    type_hint = field.type
    types_ = fieldz_kb.typeinfo.get_types_from_type_hint(type_hint)
    many = any([type_[0] in _array_types for type_ in types_])
    predicate_name = _make_predicate_name_from_field(field, many)
    for type_ in types_:
        type_origin, type_args = type_
        if type_origin is types.NoneType:
            continue
        fields = {"id_": clorm.ConstantStr}
        if type_origin in _base_types:
            fields["value"] = type_origin
        elif type_origin is float:
            fields["value"] = FloatField
        elif fieldz_kb.typeinfo.is_fieldz_class(type_origin):
            fields["value"] = clorm.ConstantStr
            if type_origin not in guard:
                get_or_make_predicate_classes_from_type(type_origin)
        elif issubclass(type_origin, enum.Enum):
            fields["value"] = clorm.ConstantStr
            if type_origin not in guard:
                get_or_make_predicate_classes_from_type(type_origin)
        elif type_origin in _array_types:
            for type_arg in type_args:
                if type_arg[0] in _base_types:
                    fields["value"] = type_arg[0]
                else:
                    fields["value"] = clorm.ConstantStr
        else:
            raise ValueError(f"type {type_} not supported")
        predicate_class_name = (
            f"{fieldz_class.__name__}_{predicate_name}_{type_origin.__name__}"
        )
        predicate_class = _make_predicate_class(
            predicate_class_name=predicate_class_name,
            predicate_name=predicate_name,
            fields=fields,
        )
        predicate_classes.append(
            (predicate_class, (fieldz_class, field.name, type_origin))
        )
    return predicate_classes


def _make_facts_from_fieldz_object(fieldz_object):
    facts = []
    fieldz_class = type(fieldz_object)
    fieldz_object_predicate_classes = get_or_make_predicate_classes_from_type(
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
        if attribute_value_type in _base_types or attribute_value_type is float:
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
            attribute_facts = make_facts_from_object(attribute_value)
            facts += attribute_facts
            attribute_fact = attribute_facts[0]
            values = [attribute_fact.id_]
        elif issubclass(attribute_value_type, enum.Enum):
            field_predicate_classes = _get_or_make_predicate_classes_from_field(
                fieldz_class, field, type(attribute_value)
            )
            field_predicate_class = field_predicate_classes[0]
            enum_facts = make_facts_from_object(attribute_value)
            facts += enum_facts
            enum_fact = enum_facts[0]
            values = [enum_fact.id_]
        elif attribute_value_type in _array_types:
            values = []
            for attribute_value_element in attribute_value:
                attribute_value_element_type = type(attribute_value_element)
                if (
                    attribute_value_element_type in _base_types
                    or attribute_value_element is float
                ):
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
                    attribute_element_facts = make_facts_from_object(
                        attribute_value_element
                    )
                    facts += attribute_element_facts
                    attribute_element_fact = attribute_element_facts[0]
                    values.append(attribute_element_fact.id_)
                elif issubclass(attribute_value_element_type, enum.Enum):
                    field_predicate_classes = _get_or_make_predicate_classes_from_field(
                        fieldz_class, field, type(attribute_value_element)
                    )
                    field_predicate_class = field_predicate_classes[0]
                    enum_element_facts = make_facts_from_object(attribute_value_element)
                    facts += enum_element_facts
                    enum_element_fact = enum_element_facts[0]
                    values.append(enum_element_fact.id_)
        else:
            raise ValueError(f"type {attribute_value_type} not supported")
        for value in values:
            field_fact = field_predicate_class(id_=fieldz_object_id, value=value)
            facts = [
                field_fact
            ] + facts  # TODO: put at the end to have a more efficient append
    return facts


def _make_facts_from_enum_object(enum_object):
    enum_class = type(enum_object)
    predicate_classes = get_or_make_predicate_classes_from_type(enum_class)
    predicate_class = predicate_classes[0]
    field_predicate_classes = predicate_classes[1:]
    enum_id = _make_fact_id()
    facts = []
    fact = predicate_class(id_=enum_id)
    facts.append(fact)
    for field_predicate_class, field_name in zip(
        field_predicate_classes, ["name", "value"]
    ):
        if field_name == "name":
            field_value = enum_object.name
        else:
            field_value = enum_object.value
        field_fact = field_predicate_class(id_=enum_id, value=field_value)
        facts.append(field_fact)
    return facts


def make_ontology_rules_from_type(type_):
    rules = set([])
    guard = set([])
    predicate_classes = get_or_make_predicate_classes_from_type(
        type_, make_predicate_classes_recursively=False, guard=guard
    )
    predicate_class = predicate_classes[0]
    predicate_class_name = predicate_class.__name__
    base_classes = type_.__bases__
    for base_class in base_classes:
        if (
            base_class not in (object, abc.ABC)
            and not base_class.__name__.startswith("_")
            and base_class.__name__ != type_.__name__
        ):
            base_predicate_classes = get_or_make_predicate_classes_from_type(
                base_class,
                make_predicate_classes_recursively=False,
                guard=guard,
            )
            base_predicate_class = base_predicate_classes[0]
            base_predicate_class_name = base_predicate_class.__name__
            rule = f"{base_predicate_class_name}(X):-{predicate_class_name}(X)."
            rules.add(rule)
            rules.update(make_ontology_rules_from_type(base_class))
    return sorted(list(rules))


def make_facts_from_object(obj):
    type_ = type(obj)
    if fieldz_kb.typeinfo.is_fieldz_class(type_):
        return _make_facts_from_fieldz_object(obj)
    elif issubclass(type_, enum.Enum):
        return _make_facts_from_enum_object(obj)
    else:
        raise ValueError(f"type {type_} not supported")
