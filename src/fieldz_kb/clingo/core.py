"""Core clingo integration for fieldz_kb.

This module provides:
- ClingoTypePlugin: abstract base class for clingo type conversion plugins
- ClingoContext: plugin registry and cache
- Module-level dispatch functions for predicate class generation and fact conversion
- make_context(): factory for creating fresh contexts with built-in plugins
"""

import abc
import collections.abc
import itertools
import typing


class ClingoTypePlugin(abc.ABC):
    """Abstract base class for clingo type conversion plugins.

    Plugins are used as classes, not instances — all methods are classmethods.
    Each plugin handles one or more Python types, providing:
    - Predicate class generation
    - Object-to-fact conversion
    """

    @classmethod
    @abc.abstractmethod
    def can_handle_type(cls, type_: type) -> bool:
        """Return True if this plugin can handle the given Python type."""
        ...

    @classmethod
    @abc.abstractmethod
    def make_predicate_classes(
        cls,
        type_: type,
        ctx: "ClingoContext",
        module: str | None = None,
        make_predicate_classes_recursively: bool = True,
        guard: set | None = None,
    ) -> list:
        """Create clorm predicate classes for the given Python type.

        Args:
            type_: The Python type.
            ctx: The plugin registry and cache.
            module: Module name for resolving forward references.
            make_predicate_classes_recursively: Whether to create predicates for nested types.
            guard: Set of types currently being processed (prevents infinite recursion).

        Returns:
            A list of predicate classes.
        """
        ...

    @classmethod
    @abc.abstractmethod
    def make_facts(
        cls,
        obj: object,
        ctx: "ClingoContext",
        id_to_object: dict | None = None,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration: tuple[type, ...] | None = None,
    ) -> list:
        """Convert a Python object to clingo facts.

        Args:
            obj: The object to convert.
            ctx: The plugin registry and cache.
            id_to_object: Optional cache mapping fact IDs to objects.
            integration_mode: How to handle duplicate objects ("hash" or "id").
            exclude_from_integration: Types to exclude from integration logic.

        Returns:
            A list of clorm facts.
        """
        ...


class ClingoContext:
    """Plugin registry and cache for clingo type conversion.

    Stores registered plugin classes and caches for type-to-predicate-class mappings.
    """

    def __init__(self) -> None:
        """Initialize an empty context with no plugins registered."""
        self.type_to_predicate_class: dict[type, list] = {}
        self.field_key_to_predicate_class: dict[tuple, type] = {}
        self.object_to_id: dict = {}
        self.id_counter: itertools.count = itertools.count()
        self._type_to_plugin: dict[type, type[ClingoTypePlugin]] = {}
        self._plugins: list[type[ClingoTypePlugin]] = []

    def register(self, plugin: type[ClingoTypePlugin]) -> None:
        """Register a type plugin class with this context.

        Args:
            plugin: A ClingoTypePlugin subclass (not an instance).
        """
        self._plugins.append(plugin)

    def get_plugin_for_type(self, type_: type) -> type[ClingoTypePlugin]:
        """Look up the plugin class for a Python type.

        Args:
            type_: The Python type to look up.

        Returns:
            The matching ClingoTypePlugin subclass.

        Raises:
            ValueError: If no plugin can handle the type.
        """
        plugin = self._type_to_plugin.get(type_)
        if plugin is not None:
            return plugin
        for candidate in self._plugins:
            if candidate.can_handle_type(type_):
                self._type_to_plugin[type_] = candidate
                return candidate
        raise ValueError(f"type {type_} not supported")

    def reset(self) -> None:
        """Reset all internal caches and ID counter.

        Primarily intended for use in tests to ensure isolation between test cases.
        """
        self.type_to_predicate_class.clear()
        self.field_key_to_predicate_class.clear()
        self.object_to_id.clear()
        self.id_counter = itertools.count()


def make_fact_id(
    ctx: ClingoContext,
    obj: object,
    integration_mode: typing.Literal["hash", "id"] = "id",
    exclude_from_integration: tuple[type, ...] | None = None,
) -> str:
    """Get or create a fact ID for an object.

    Args:
        ctx: The plugin registry and cache.
        obj: The object to get/create an ID for.
        integration_mode: How to key the dedup cache ("hash" or "id").
        exclude_from_integration: Types to exclude from deduplication.

    Returns:
        A string ID like "id_0", "id_1", etc.
    """
    if exclude_from_integration is None:
        exclude_from_integration = tuple()
    if isinstance(obj, exclude_from_integration):
        return f"id_{next(ctx.id_counter)}"
    if integration_mode == "hash":
        if not isinstance(obj, collections.abc.Hashable):
            raise ValueError(
                f"object of type {type(obj)} not hashable, "
                "cannot use hash integration mode"
            )
        key = obj
    else:
        key = id(obj)
    fact_id = ctx.object_to_id.get(key)
    if fact_id is None:
        fact_id = f"id_{next(ctx.id_counter)}"
        ctx.object_to_id[key] = fact_id
    return fact_id


def get_or_make_predicate_classes_from_type(
    ctx: ClingoContext,
    type_: type,
    module: str | None = None,
    make_predicate_classes_recursively: bool = True,
    guard: set | None = None,
) -> list:
    """Get or create predicate classes for a given Python type.

    Args:
        ctx: The plugin registry and cache.
        type_: The Python type.
        module: Module name for resolving forward references.
        make_predicate_classes_recursively: Whether to create predicates for nested types.
        guard: Set of types currently being processed (prevents infinite recursion).

    Returns:
        A list of predicate classes.
    """
    if guard is None:
        guard = set()
    cached = ctx.type_to_predicate_class.get(type_)
    if cached is not None:
        return cached
    guard.add(type_)
    plugin = ctx.get_plugin_for_type(type_)
    predicate_classes = plugin.make_predicate_classes(
        type_,
        ctx,
        module=module,
        make_predicate_classes_recursively=make_predicate_classes_recursively,
        guard=guard,
    )
    ctx.type_to_predicate_class[type_] = predicate_classes
    return predicate_classes


def get_or_make_predicate_classes_from_field(
    ctx: ClingoContext,
    fieldz_class: type,
    field: object,
    type_: type | None = None,
    module: str | None = None,
    make_predicate_classes_recursively: bool = True,
    guard: set | None = None,
) -> list:
    """Get or create predicate classes for a dataclass field.

    Args:
        ctx: The plugin registry and cache.
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
        guard = set()
    cached = ctx.field_key_to_predicate_class.get(
        (fieldz_class, field.name, type_)
    )
    if cached is not None:
        return [cached]
    guard.add((fieldz_class, field.name))

    import fieldz_kb.clingo.plugins

    predicate_classes_and_keys = (
        fieldz_kb.clingo.plugins.make_predicate_classes_and_keys_from_field(
            fieldz_class,
            field,
            ctx,
            module=module,
            make_predicate_classes_recursively=make_predicate_classes_recursively,
            guard=guard,
        )
    )
    for predicate_class, key in predicate_classes_and_keys:
        ctx.field_key_to_predicate_class[key] = predicate_class
    return [item[0] for item in predicate_classes_and_keys]


def make_facts_from_object(
    ctx: ClingoContext,
    obj: object,
    id_to_object: dict | None = None,
    integration_mode: typing.Literal["hash", "id"] = "id",
    exclude_from_integration: tuple[type, ...] | None = None,
) -> list:
    """Convert a Python object to clingo facts.

    Args:
        ctx: The plugin registry and cache.
        obj: The object to convert.
        id_to_object: Optional cache mapping fact IDs to objects.
        integration_mode: How to handle duplicate objects ("hash" or "id").
        exclude_from_integration: Types to exclude from integration logic.

    Returns:
        A list of clorm facts.
    """
    if id_to_object is None:
        id_to_object = {}
    plugin = ctx.get_plugin_for_type(type(obj))
    return plugin.make_facts(
        obj,
        ctx,
        id_to_object=id_to_object,
        integration_mode=integration_mode,
        exclude_from_integration=exclude_from_integration,
    )


def make_ontology_rules_from_type(
    ctx: ClingoContext,
    type_: type,
) -> list[str]:
    """Generate ontology rules expressing type inheritance as ASP rules.

    Args:
        ctx: The plugin registry and cache.
        type_: The Python type to generate rules for.

    Returns:
        A sorted list of ASP rule strings.
    """
    import abc as abc_module

    rules = set()
    guard = set()
    predicate_classes = get_or_make_predicate_classes_from_type(
        ctx, type_, make_predicate_classes_recursively=False, guard=guard
    )
    predicate_class = predicate_classes[0]
    predicate_class_name = predicate_class.__name__
    base_classes = type_.__bases__
    for base_class in base_classes:
        if (
            base_class not in (object, abc_module.ABC)
            and not base_class.__name__.startswith("_")
            and base_class.__name__ != type_.__name__
        ):
            base_predicate_classes = get_or_make_predicate_classes_from_type(
                ctx,
                base_class,
                make_predicate_classes_recursively=False,
                guard=guard,
            )
            base_predicate_class = base_predicate_classes[0]
            base_predicate_class_name = base_predicate_class.__name__
            rule = f"{base_predicate_class_name}(X):-{predicate_class_name}(X)."
            rules.add(rule)
            rules.update(make_ontology_rules_from_type(ctx, base_class))
    return sorted(list(rules))


def make_context() -> ClingoContext:
    """Create a fresh ClingoContext with all built-in plugins registered."""
    import fieldz_kb.clingo.plugins

    context = ClingoContext()
    context.register(fieldz_kb.clingo.plugins.FieldzClassPlugin)
    context.register(fieldz_kb.clingo.plugins.EnumPlugin)
    return context


_default_context: ClingoContext | None = None


def get_default_context() -> ClingoContext:
    """Return the shared default context, creating it on first access."""
    global _default_context
    if _default_context is None:
        _default_context = make_context()
    return _default_context
