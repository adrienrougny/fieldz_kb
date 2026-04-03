"""Concrete type conversion plugins for the clingo backend."""

import abc
import enum
import types
import typing

import clorm
import fieldz

import fieldz_kb.typeinfo
import fieldz_kb.clingo.core
import fieldz_kb.clingo.utils


def make_predicate_classes_and_keys_from_field(
    fieldz_class: type,
    field: fieldz.Field,
    ctx: fieldz_kb.clingo.core.ClingoContext,
    module: str | None = None,
    make_predicate_classes_recursively: bool = True,
    guard: set | None = None,
) -> list[tuple[type, tuple]]:
    """Create predicate classes for a dataclass field, keyed for caching.

    Args:
        fieldz_class: The owning dataclass type.
        field: The fieldz field descriptor.
        ctx: The plugin registry and cache.
        module: Module name for resolving forward references.
        make_predicate_classes_recursively: Whether to create predicates for nested types.
        guard: Guard set for recursion prevention.

    Returns:
        A list of (predicate_class, cache_key) tuples.
    """
    predicate_classes = []
    if guard is None:
        guard = set()
    type_hint = field.type
    types_ = fieldz_kb.typeinfo.get_types_from_type_hint(type_hint)
    many = any([type_[0] in fieldz_kb.clingo.utils.ARRAY_TYPES for type_ in types_])
    predicate_name = fieldz_kb.clingo.utils.make_predicate_name_from_field(
        field.name, many
    )
    for type_ in types_:
        type_origin, type_args = type_
        if type_origin is types.NoneType:
            continue
        fields = {"id_": clorm.ConstantStr}
        if type_origin in fieldz_kb.clingo.utils.BASE_TYPES:
            fields["value"] = type_origin
        elif type_origin is float:
            fields["value"] = fieldz_kb.clingo.utils.FloatField
        elif fieldz_kb.typeinfo.is_fieldz_class(type_origin):
            fields["value"] = clorm.ConstantStr
            if type_origin not in guard:
                fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
                    ctx, type_origin
                )
        elif issubclass(type_origin, enum.Enum):
            fields["value"] = clorm.ConstantStr
            if type_origin not in guard:
                fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
                    ctx, type_origin
                )
        elif type_origin in fieldz_kb.clingo.utils.ARRAY_TYPES:
            for type_arg in type_args:
                if type_arg[0] in fieldz_kb.clingo.utils.BASE_TYPES:
                    fields["value"] = type_arg[0]
                else:
                    fields["value"] = clorm.ConstantStr
        else:
            raise ValueError(f"type {type_} not supported")
        predicate_class_name = (
            f"{fieldz_class.__name__}_{predicate_name}_{type_origin.__name__}"
        )
        predicate_class = fieldz_kb.clingo.utils.make_predicate_class(
            predicate_class_name=predicate_class_name,
            predicate_name=predicate_name,
            fields=fields,
        )
        predicate_classes.append(
            (predicate_class, (fieldz_class, field.name, type_origin))
        )
    return predicate_classes


class FieldzClassPlugin(fieldz_kb.clingo.core.ClingoTypePlugin):
    """Handles fieldz dataclass-like types."""

    @classmethod
    def can_handle_type(cls, type_: type) -> bool:
        """Return True if the type is a fieldz class."""
        return fieldz_kb.typeinfo.is_fieldz_class(type_)

    @classmethod
    def make_predicate_classes(
        cls,
        type_: type,
        ctx: fieldz_kb.clingo.core.ClingoContext,
        module: str | None = None,
        make_predicate_classes_recursively: bool = True,
        guard: set | None = None,
    ) -> list:
        """Create predicate classes for a fieldz dataclass type."""
        predicate_classes = []
        if guard is None:
            guard = set()
        predicate_class_name = (
            fieldz_kb.clingo.utils.make_predicate_class_name_from_type(type_)
        )
        fieldz_class_bases = type_.__bases__
        for base_class in fieldz_class_bases:
            if (
                base_class not in (object, abc.ABC)
                and not base_class.__name__.startswith("_")
                and base_class.__name__ != type_.__name__
            ):
                fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
                    ctx,
                    base_class,
                    make_predicate_classes_recursively=make_predicate_classes_recursively,
                    guard=guard,
                )
        predicate_fields = {"id_": clorm.ConstantStr}
        predicate_class = fieldz_kb.clingo.utils.make_predicate_class(
            predicate_class_name=predicate_class_name,
            predicate_name=predicate_class_name,
            fields=predicate_fields,
        )
        predicate_classes.append(predicate_class)
        for field in fieldz.fields(type_):
            field_predicate_classes = (
                fieldz_kb.clingo.core.get_or_make_predicate_classes_from_field(
                    ctx,
                    type_,
                    field,
                    type_=None,
                    module=type_.__module__,
                    make_predicate_classes_recursively=make_predicate_classes_recursively,
                    guard=guard,
                )
            )
            predicate_classes += field_predicate_classes
        return predicate_classes

    @classmethod
    def make_facts(
        cls,
        obj: object,
        ctx: fieldz_kb.clingo.core.ClingoContext,
        id_to_object: dict | None = None,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration: tuple[type, ...] | None = None,
    ) -> list:
        """Convert a fieldz object to clingo facts."""
        if id_to_object is None:
            id_to_object = {}
        facts = []
        fieldz_class = type(obj)
        fieldz_object_predicate_classes = (
            fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
                ctx, fieldz_class
            )
        )
        fieldz_object_id = fieldz_kb.clingo.core.make_fact_id(
            ctx,
            obj,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
        )
        id_to_object[fieldz_object_id] = obj
        fieldz_object_predicate_class = fieldz_object_predicate_classes[0]
        fieldz_object_fact = fieldz_object_predicate_class(fieldz_object_id)
        facts.append(fieldz_object_fact)
        for field in fieldz.fields(fieldz_class):
            attribute_value = getattr(obj, field.name)
            attribute_value_type = type(attribute_value)
            if attribute_value is None:
                continue
            if (
                attribute_value_type in fieldz_kb.clingo.utils.BASE_TYPES
                or attribute_value_type is float
            ):
                field_predicate_classes = (
                    fieldz_kb.clingo.core.get_or_make_predicate_classes_from_field(
                        ctx, fieldz_class, field, type(attribute_value)
                    )
                )
                field_predicate_class = field_predicate_classes[0]
                values = [attribute_value]
            elif fieldz_kb.typeinfo.is_fieldz_class(attribute_value_type):
                field_predicate_classes = (
                    fieldz_kb.clingo.core.get_or_make_predicate_classes_from_field(
                        ctx, fieldz_class, field, type(attribute_value)
                    )
                )
                field_predicate_class = field_predicate_classes[0]
                attribute_facts = fieldz_kb.clingo.core.make_facts_from_object(
                    ctx,
                    attribute_value,
                    id_to_object=id_to_object,
                    integration_mode=integration_mode,
                    exclude_from_integration=exclude_from_integration,
                )
                facts += attribute_facts
                attribute_fact = attribute_facts[0]
                values = [attribute_fact.id_]
            elif issubclass(attribute_value_type, enum.Enum):
                field_predicate_classes = (
                    fieldz_kb.clingo.core.get_or_make_predicate_classes_from_field(
                        ctx, fieldz_class, field, type(attribute_value)
                    )
                )
                field_predicate_class = field_predicate_classes[0]
                enum_facts = fieldz_kb.clingo.core.make_facts_from_object(
                    ctx,
                    attribute_value,
                    id_to_object=id_to_object,
                    integration_mode=integration_mode,
                    exclude_from_integration=exclude_from_integration,
                )
                facts += enum_facts
                enum_fact = enum_facts[0]
                values = [enum_fact.id_]
            elif attribute_value_type in fieldz_kb.clingo.utils.ARRAY_TYPES:
                values = []
                for attribute_value_element in attribute_value:
                    attribute_value_element_type = type(attribute_value_element)
                    if (
                        attribute_value_element_type
                        in fieldz_kb.clingo.utils.BASE_TYPES
                        or attribute_value_element is float
                    ):
                        field_predicate_classes = (
                            fieldz_kb.clingo.core.get_or_make_predicate_classes_from_field(
                                ctx,
                                fieldz_class,
                                field,
                                type(attribute_value_element),
                            )
                        )
                        field_predicate_class = field_predicate_classes[0]
                        values.append(attribute_value_element)
                    elif fieldz_kb.typeinfo.is_fieldz_class(
                        attribute_value_element_type
                    ):
                        field_predicate_classes = (
                            fieldz_kb.clingo.core.get_or_make_predicate_classes_from_field(
                                ctx,
                                fieldz_class,
                                field,
                                type(attribute_value_element),
                            )
                        )
                        field_predicate_class = field_predicate_classes[0]
                        attribute_element_facts = (
                            fieldz_kb.clingo.core.make_facts_from_object(
                                ctx,
                                attribute_value_element,
                                id_to_object=id_to_object,
                                integration_mode=integration_mode,
                                exclude_from_integration=exclude_from_integration,
                            )
                        )
                        facts += attribute_element_facts
                        attribute_element_fact = attribute_element_facts[0]
                        values.append(attribute_element_fact.id_)
                    elif issubclass(attribute_value_element_type, enum.Enum):
                        field_predicate_classes = (
                            fieldz_kb.clingo.core.get_or_make_predicate_classes_from_field(
                                ctx,
                                fieldz_class,
                                field,
                                type(attribute_value_element),
                            )
                        )
                        field_predicate_class = field_predicate_classes[0]
                        enum_element_facts = (
                            fieldz_kb.clingo.core.make_facts_from_object(
                                ctx,
                                attribute_value_element,
                                id_to_object=id_to_object,
                                integration_mode=integration_mode,
                                exclude_from_integration=exclude_from_integration,
                            )
                        )
                        facts += enum_element_facts
                        enum_element_fact = enum_element_facts[0]
                        values.append(enum_element_fact.id_)
            else:
                raise ValueError(f"type {attribute_value_type} not supported")
            for value in values:
                field_fact = field_predicate_class(
                    id_=fieldz_object_id, value=value
                )
                facts = [field_fact] + facts
        return facts


class EnumPlugin(fieldz_kb.clingo.core.ClingoTypePlugin):
    """Handles enum types."""

    @classmethod
    def can_handle_type(cls, type_: type) -> bool:
        """Return True if the type is an enum subclass."""
        return issubclass(type_, enum.Enum)

    @classmethod
    def make_predicate_classes(
        cls,
        type_: type,
        ctx: fieldz_kb.clingo.core.ClingoContext,
        module: str | None = None,
        make_predicate_classes_recursively: bool = True,
        guard: set | None = None,
    ) -> list:
        """Create predicate classes for an enum type."""
        predicate_classes = []
        predicate_class_name = (
            fieldz_kb.clingo.utils.make_predicate_class_name_from_type(type_)
        )
        predicate_fields = {"id_": clorm.ConstantStr}
        predicate_class = fieldz_kb.clingo.utils.make_predicate_class(
            predicate_class_name=predicate_class_name,
            predicate_name=predicate_class_name,
            fields=predicate_fields,
        )
        predicate_classes.append(predicate_class)
        has_name_class_name = f"{predicate_class_name}_hasName"
        has_name_dict = {
            "__annotations__": {
                "id_": clorm.ConstantStr,
                "value": clorm.ConstantStr,
            }
        }
        has_name_class = type(clorm.Predicate)(
            has_name_class_name,
            (clorm.Predicate,),
            has_name_dict,
            name="hasName",
        )
        predicate_classes.append(has_name_class)
        item_value_types = set([type(item.value) for item in type_])
        if len(item_value_types) != 1:
            raise ValueError(
                f"enum of type {type_} not supported: "
                "types of values must all be the same"
            )
        item_value_type = next(iter(item_value_types))
        has_value_class_name = f"{predicate_class_name}_hasValue"
        if item_value_type in fieldz_kb.clingo.utils.BASE_TYPES:
            value_annotation = item_value_type
        else:
            value_annotation = clorm.ConstantStr
        has_value_dict = {
            "__annotations__": {
                "id_": clorm.ConstantStr,
                "value": value_annotation,
            }
        }
        has_value_class = type(clorm.Predicate)(
            has_value_class_name,
            (clorm.Predicate,),
            has_value_dict,
            name="hasValue",
        )
        predicate_classes.append(has_value_class)
        return predicate_classes

    @classmethod
    def make_facts(
        cls,
        obj: object,
        ctx: fieldz_kb.clingo.core.ClingoContext,
        id_to_object: dict | None = None,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration: tuple[type, ...] | None = None,
    ) -> list:
        """Convert an enum member to clingo facts."""
        if id_to_object is None:
            id_to_object = {}
        enum_class = type(obj)
        predicate_classes = (
            fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
                ctx, enum_class
            )
        )
        predicate_class = predicate_classes[0]
        field_predicate_classes = predicate_classes[1:]
        enum_id = fieldz_kb.clingo.core.make_fact_id(
            ctx,
            obj,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
        )
        id_to_object[enum_id] = obj
        facts = []
        fact = predicate_class(id_=enum_id)
        facts.append(fact)
        for field_predicate_class, field_name in zip(
            field_predicate_classes, ["name", "value"]
        ):
            if field_name == "name":
                field_value = obj.name
            else:
                field_value = obj.value
            field_fact = field_predicate_class(id_=enum_id, value=field_value)
            facts.append(field_fact)
        return facts
