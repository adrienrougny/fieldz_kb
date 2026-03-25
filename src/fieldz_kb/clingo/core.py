"""Core clingo integration for fieldz_kb.

This module provides the core functionality for converting dataclass-like objects
to clingo predicates. It includes:

- Predicate class generation from Python types (via clorm)
- Object-to-fact conversion
- Support for primitives, enums, collections, and nested dataclasses
- Plugin-based extensibility via ClingoTypePlugin and ClingoContext
"""

import abc
import collections.abc
import enum
import itertools
import typing
import types

import clorm
import fieldz
import inflect

import fieldz_kb.typeinfo


_base_types = (int, str, bool)
_array_types = (list, tuple, set, frozenset)
_ordered_array_types = (list, tuple)


class FloatField(clorm.StringField):
    pytocl = lambda f: str(f)
    cltopy = lambda s: float(s)


# ---------------------------------------------------------------------------
# Helper functions (pure, no context state needed)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Plugin ABC
# ---------------------------------------------------------------------------


class ClingoTypePlugin(abc.ABC):
    """Abstract base class for clingo type conversion plugins.

    Each plugin handles one or more Python types, providing:
    - Predicate class generation
    - Object-to-fact conversion
    """

    @abc.abstractmethod
    def handled_types(self) -> list[type]:
        """Return the Python types this plugin handles via direct lookup."""
        ...

    def can_handle_type(self, type_) -> bool:
        """Predicate-based fallback for type dispatch."""
        return False

    @abc.abstractmethod
    def make_predicate_classes(self, type_, ctx, module=None, make_predicate_classes_recursively=True, guard=None):
        """Create clorm predicate classes for the given Python type.

        Returns:
            A list of predicate classes.
        """
        ...

    @abc.abstractmethod
    def make_facts(self, obj, ctx, id_to_object=None, integration_mode="id", exclude_from_integration=None):
        """Convert a Python object to clingo facts.

        Returns:
            A list of clorm facts.
        """
        ...


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


class ClingoContext:
    """Owns all caches and plugin registrations for clingo type conversion.

    Provides the main dispatch methods that delegate to registered plugins.
    """

    def __init__(self):
        self.type_to_predicate_class = {}
        self.field_key_to_predicate_class = {}
        self.object_to_id = {}
        self.id_counter = itertools.count()
        self._type_to_plugin = {}
        self._fallback_plugins = []

    def register(self, plugin):
        """Register a type plugin with this context.

        Args:
            plugin: A ClingoTypePlugin instance.
        """
        for t in plugin.handled_types():
            self._type_to_plugin[t] = plugin
        self._fallback_plugins.append(plugin)

    def get_plugin_for_type(self, type_):
        """Look up the plugin for a Python type.

        Args:
            type_: The Python type to look up.

        Returns:
            The matching ClingoTypePlugin.

        Raises:
            ValueError: If no plugin can handle the type.
        """
        plugin = self._type_to_plugin.get(type_)
        if plugin is None:
            for p in self._fallback_plugins:
                if p.can_handle_type(type_):
                    plugin = p
                    break
        if plugin is None:
            raise ValueError(f"type {type_} not supported")
        return plugin

    def reset(self):
        """Reset all internal caches and ID counter.

        Primarily intended for use in tests to ensure isolation between test cases.
        """
        self.type_to_predicate_class.clear()
        self.field_key_to_predicate_class.clear()
        self.object_to_id.clear()
        self.id_counter = itertools.count()

    def make_fact_id(
        self,
        obj,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration=None,
    ):
        """Get or create a fact ID for an object.

        Args:
            obj: The object to get/create an ID for.
            integration_mode: How to key the dedup cache ("hash" or "id").
            exclude_from_integration: Types to exclude from deduplication.

        Returns:
            A string ID like "id_0", "id_1", etc.
        """
        if exclude_from_integration is None:
            exclude_from_integration = tuple()
        if isinstance(obj, exclude_from_integration):
            id_ = f"id_{next(self.id_counter)}"
            return id_
        if integration_mode == "hash":
            if not isinstance(obj, collections.abc.Hashable):
                raise ValueError(
                    f"object of type {type(obj)} not hashable, cannot use hash integration mode"
                )
            key = obj
        else:
            key = id(obj)
        id_ = self.object_to_id.get(key)
        if id_ is None:
            id_ = f"id_{next(self.id_counter)}"
            self.object_to_id[key] = id_
        return id_

    def get_or_make_predicate_classes_from_type(
        self, type_, module=None, make_predicate_classes_recursively=True, guard=None
    ):
        """Get or create predicate classes for a given Python type.

        Args:
            type_: The Python type.
            module: Module name for resolving forward references.
            make_predicate_classes_recursively: Whether to create predicates for nested types.
            guard: Set of types currently being processed (prevents infinite recursion).

        Returns:
            A list of predicate classes.
        """
        if guard is None:
            guard = set([])
        cached = self.type_to_predicate_class.get(type_)
        if cached is not None:
            return cached
        guard.add(type_)
        plugin = self.get_plugin_for_type(type_)
        predicate_classes = plugin.make_predicate_classes(
            type_,
            self,
            module=module,
            make_predicate_classes_recursively=make_predicate_classes_recursively,
            guard=guard,
        )
        self.type_to_predicate_class[type_] = predicate_classes
        return predicate_classes

    def get_or_make_predicate_classes_from_field(
        self,
        fieldz_class,
        field,
        type_=None,
        module=None,
        make_predicate_classes_recursively=True,
        guard=None,
    ):
        """Get or create predicate classes for a dataclass field.

        Args:
            fieldz_class: The owning dataclass type.
            field: The fieldz field descriptor.
            type_: Optional specific type for cache lookup.
            module: Module name for resolving forward references.
            make_predicate_classes_recursively: Whether to create predicates for nested types.
            guard: Guard set for recursion prevention.

        Returns:
            A list of predicate classes.
        """
        if guard is None:
            guard = set([])
        cached = self.field_key_to_predicate_class.get(
            (fieldz_class, field.name, type_)
        )
        if cached is not None:
            return [cached]
        guard.add((fieldz_class, field.name))
        predicate_classes_and_keys = _make_predicate_classes_and_keys_from_field(
            fieldz_class,
            field,
            self,
            module=module,
            make_predicate_classes_recursively=make_predicate_classes_recursively,
            guard=guard,
        )
        for predicate_class, key in predicate_classes_and_keys:
            self.field_key_to_predicate_class[key] = predicate_class
        return [_[0] for _ in predicate_classes_and_keys]

    def make_facts_from_object(
        self,
        obj,
        id_to_object=None,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration=None,
    ):
        """Convert a Python object to clingo facts.

        Args:
            obj: The object to convert.
            id_to_object: Optional cache mapping fact IDs to objects.
            integration_mode: How to handle duplicate objects ("hash" or "id").
            exclude_from_integration: Types to exclude from integration logic.

        Returns:
            A list of clorm facts.
        """
        if id_to_object is None:
            id_to_object = {}
        type_ = type(obj)
        plugin = self.get_plugin_for_type(type_)
        return plugin.make_facts(
            obj, self,
            id_to_object=id_to_object,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
        )


# ---------------------------------------------------------------------------
# Field-level helper (needs context)
# ---------------------------------------------------------------------------


def _make_predicate_classes_and_keys_from_field(
    fieldz_class,
    field,
    ctx,
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
                ctx.get_or_make_predicate_classes_from_type(type_origin)
        elif issubclass(type_origin, enum.Enum):
            fields["value"] = clorm.ConstantStr
            if type_origin not in guard:
                ctx.get_or_make_predicate_classes_from_type(type_origin)
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


# ---------------------------------------------------------------------------
# Built-in Plugins
# ---------------------------------------------------------------------------


class FieldzClassPlugin(ClingoTypePlugin):
    """Handles fieldz dataclass-like types."""

    def handled_types(self):
        return []

    def can_handle_type(self, type_):
        return fieldz_kb.typeinfo.is_fieldz_class(type_)

    def make_predicate_classes(self, type_, ctx, module=None, make_predicate_classes_recursively=True, guard=None):
        predicate_classes = []
        if guard is None:
            guard = set([])
        predicate_class_name = _make_predicate_class_name_from_type(type_)
        fieldz_class_bases = type_.__bases__
        for base_class in fieldz_class_bases:
            if (
                base_class not in (object, abc.ABC)
                and not base_class.__name__.startswith("_")
                and base_class.__name__ != type_.__name__
            ):
                ctx.get_or_make_predicate_classes_from_type(
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
        for field in fieldz.fields(type_):
            field_predicate_classes = ctx.get_or_make_predicate_classes_from_field(
                type_,
                field,
                type_=None,
                module=type_.__module__,
                make_predicate_classes_recursively=make_predicate_classes_recursively,
                guard=guard,
            )
            predicate_classes += field_predicate_classes
        return predicate_classes

    def make_facts(self, obj, ctx, id_to_object=None, integration_mode="id", exclude_from_integration=None):
        if id_to_object is None:
            id_to_object = {}
        facts = []
        fieldz_class = type(obj)
        fieldz_object_predicate_classes = ctx.get_or_make_predicate_classes_from_type(
            fieldz_class
        )
        fieldz_object_id = ctx.make_fact_id(
            obj, integration_mode=integration_mode,
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
            if attribute_value_type in _base_types or attribute_value_type is float:
                field_predicate_classes = ctx.get_or_make_predicate_classes_from_field(
                    fieldz_class, field, type(attribute_value)
                )
                field_predicate_class = field_predicate_classes[0]
                values = [attribute_value]
            elif fieldz_kb.typeinfo.is_fieldz_class(attribute_value_type):
                field_predicate_classes = ctx.get_or_make_predicate_classes_from_field(
                    fieldz_class, field, type(attribute_value)
                )
                field_predicate_class = field_predicate_classes[0]
                attribute_facts = ctx.make_facts_from_object(
                    attribute_value, id_to_object=id_to_object,
                    integration_mode=integration_mode,
                    exclude_from_integration=exclude_from_integration,
                )
                facts += attribute_facts
                attribute_fact = attribute_facts[0]
                values = [attribute_fact.id_]
            elif issubclass(attribute_value_type, enum.Enum):
                field_predicate_classes = ctx.get_or_make_predicate_classes_from_field(
                    fieldz_class, field, type(attribute_value)
                )
                field_predicate_class = field_predicate_classes[0]
                enum_facts = ctx.make_facts_from_object(
                    attribute_value, id_to_object=id_to_object,
                    integration_mode=integration_mode,
                    exclude_from_integration=exclude_from_integration,
                )
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
                        field_predicate_classes = (
                            ctx.get_or_make_predicate_classes_from_field(
                                fieldz_class, field, type(attribute_value_element)
                            )
                        )
                        field_predicate_class = field_predicate_classes[0]
                        values.append(attribute_value_element)
                    elif fieldz_kb.typeinfo.is_fieldz_class(
                        attribute_value_element_type
                    ):
                        field_predicate_classes = (
                            ctx.get_or_make_predicate_classes_from_field(
                                fieldz_class, field, type(attribute_value_element)
                            )
                        )
                        field_predicate_class = field_predicate_classes[0]
                        attribute_element_facts = ctx.make_facts_from_object(
                            attribute_value_element, id_to_object=id_to_object,
                            integration_mode=integration_mode,
                            exclude_from_integration=exclude_from_integration,
                        )
                        facts += attribute_element_facts
                        attribute_element_fact = attribute_element_facts[0]
                        values.append(attribute_element_fact.id_)
                    elif issubclass(attribute_value_element_type, enum.Enum):
                        field_predicate_classes = (
                            ctx.get_or_make_predicate_classes_from_field(
                                fieldz_class, field, type(attribute_value_element)
                            )
                        )
                        field_predicate_class = field_predicate_classes[0]
                        enum_element_facts = ctx.make_facts_from_object(
                            attribute_value_element, id_to_object=id_to_object,
                            integration_mode=integration_mode,
                            exclude_from_integration=exclude_from_integration,
                        )
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


class EnumPlugin(ClingoTypePlugin):
    """Handles enum types."""

    def handled_types(self):
        return []

    def can_handle_type(self, type_):
        try:
            return issubclass(type_, enum.Enum)
        except TypeError:
            return False

    def make_predicate_classes(self, type_, ctx, module=None, make_predicate_classes_recursively=True, guard=None):
        predicate_classes = []
        predicate_class_name = _make_predicate_class_name_from_type(type_)
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
        item_value_types = set([type(item.value) for item in type_])
        if len(item_value_types) != 1:
            raise ValueError(
                f"enum of type {type_} not supported: types of values must all be the same"
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

    def make_facts(self, obj, ctx, id_to_object=None, integration_mode="id", exclude_from_integration=None):
        if id_to_object is None:
            id_to_object = {}
        enum_class = type(obj)
        predicate_classes = ctx.get_or_make_predicate_classes_from_type(enum_class)
        predicate_class = predicate_classes[0]
        field_predicate_classes = predicate_classes[1:]
        enum_id = ctx.make_fact_id(
            obj, integration_mode=integration_mode,
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


# ---------------------------------------------------------------------------
# Default context
# ---------------------------------------------------------------------------


def _make_default_context():
    """Create and configure the default ClingoContext with all built-in plugins."""
    ctx = ClingoContext()
    ctx.register(FieldzClassPlugin())
    ctx.register(EnumPlugin())
    return ctx


_default_context = _make_default_context()


# ---------------------------------------------------------------------------
# Public API (thin wrappers around default context)
# ---------------------------------------------------------------------------


def reset_caches():
    """Reset all internal predicate class caches and ID counter.

    Primarily intended for use in tests to ensure isolation between test cases.
    """
    _default_context.reset()


def get_or_make_predicate_classes_from_type(
    type_, module=None, make_predicate_classes_recursively=True, guard=None
):
    """Get or create predicate classes for a given Python type.

    Args:
        type_: The Python type.
        module: Module name for resolving forward references.
        make_predicate_classes_recursively: Whether to create predicates for nested types.
        guard: Set of types currently being processed (prevents infinite recursion).

    Returns:
        A list of predicate classes.
    """
    return _default_context.get_or_make_predicate_classes_from_type(
        type_, module, make_predicate_classes_recursively, guard
    )


def make_facts_from_object(
    obj,
    id_to_object=None,
    integration_mode: typing.Literal["hash", "id"] = "id",
    exclude_from_integration=None,
):
    """Convert a Python object to clingo facts.

    Args:
        obj: The object to convert.
        id_to_object: Optional cache mapping fact IDs to objects.
        integration_mode: How to handle duplicate objects ("hash" or "id").
        exclude_from_integration: Types to exclude from integration logic.

    Returns:
        A list of clorm facts.
    """
    return _default_context.make_facts_from_object(
        obj, id_to_object, integration_mode, exclude_from_integration
    )


def make_ontology_rules_from_type(type_):
    """Generate ontology rules expressing type inheritance as ASP rules.

    Args:
        type_: The Python type to generate rules for.

    Returns:
        A sorted list of ASP rule strings.
    """
    rules = set([])
    guard = set([])
    predicate_classes = _default_context.get_or_make_predicate_classes_from_type(
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
            base_predicate_classes = (
                _default_context.get_or_make_predicate_classes_from_type(
                    base_class,
                    make_predicate_classes_recursively=False,
                    guard=guard,
                )
            )
            base_predicate_class = base_predicate_classes[0]
            base_predicate_class_name = base_predicate_class.__name__
            rule = f"{base_predicate_class_name}(X):-{predicate_class_name}(X)."
            rules.add(rule)
            rules.update(make_ontology_rules_from_type(base_class))
    return sorted(list(rules))
