"""Core pylpg integration for fieldz_kb.

This module provides:
- PylpgTypePlugin: abstract base class for type conversion plugins
- PylpgContext: plugin registry and cache
- Module-level dispatch functions for converting objects to/from nodes
- make_context(): factory for creating fresh contexts with built-in plugins

This module is backend-agnostic — it works with any pylpg backend (Neo4j,
FalkorDB, FalkorDBLite). Use with fieldz_kb.lpg.session.Session
and a pylpg backend (e.g., pylpg.backend.neo4j.Neo4jBackend).
"""

import typing
import collections.abc
import abc

import pylpg.relationship

import fieldz_kb.lpg.graph


class PylpgTypePlugin(abc.ABC):
    """Abstract base class for pylpg type conversion plugins.

    Plugins are used as classes, not instances — all methods are classmethods.
    Each plugin handles one or more Python types, providing:
    - Type/node class matching
    - Node class creation (for dynamically generated types)
    - Object-to-node conversion
    - Node-to-object conversion

    Args (for subclass methods):
        ctx: The PylpgContext providing access to caches and other plugins.
    """

    @classmethod
    @abc.abstractmethod
    def can_handle_type(cls, type_: type) -> bool:
        """Return True if this plugin can handle the given Python type.

        Used for both direct lookup caching (via _handled_types) and
        predicate-based fallback dispatch (e.g., for fieldz classes, enums).
        """
        ...

    @classmethod
    @abc.abstractmethod
    def can_handle_node_class(cls, node_class: type, ctx: "PylpgContext") -> bool:
        """Return True if this plugin can handle the given node class.

        Used for both direct lookup caching (via _handled_node_classes) and
        predicate-based fallback dispatch.
        """
        ...

    @classmethod
    @abc.abstractmethod
    def make_node_class_from_type(
        cls,
        type_: type,
        ctx: "PylpgContext",
        make_node_classes_recursively: bool = True,
        guard: set[type] | None = None,
    ) -> type[fieldz_kb.lpg.graph.BaseNode] | None:
        """Create a pylpg node class for the given Python type.

        Returns:
            A Node subclass, or None if the type uses a pre-built node class.
        """
        ...

    @classmethod
    @abc.abstractmethod
    def make_nodes_from_object(
        cls,
        obj: object,
        ctx: "PylpgContext",
        integration_mode: typing.Literal["hash", "id"],
        exclude_from_integration: tuple[type, ...],
        object_to_node: dict,
    ) -> tuple[
        list[fieldz_kb.lpg.graph.BaseNode], list[pylpg.relationship.Relationship]
    ]:
        """Convert a Python object to pylpg nodes and relationships.

        Returns:
            A tuple of (nodes, relationships) where nodes is a list of node instances
            and relationships is a list of Relationship instances.
        """
        ...

    @classmethod
    @abc.abstractmethod
    def make_object_from_node(
        cls,
        node: fieldz_kb.lpg.graph.BaseNode,
        ctx: "PylpgContext",
        node_id_to_object: dict,
    ) -> object:
        """Convert a pylpg node back to a Python object.

        Returns:
            The reconstructed Python object.
        """
        ...


class PylpgContext:
    """Plugin registry and cache for pylpg type conversion.

    Stores registered plugin classes and caches for type-to-node-class mappings.
    """

    def __init__(self) -> None:
        """Initialize an empty context with no plugins registered."""
        self.type_to_node_class: dict[type, type[fieldz_kb.lpg.graph.BaseNode]] = {}
        self.node_class_to_type: dict[type[fieldz_kb.lpg.graph.BaseNode], type] = {}
        self._type_to_plugin: dict[type, type[PylpgTypePlugin]] = {}
        self._node_class_to_plugin: dict[
            type[fieldz_kb.lpg.graph.BaseNode], type[PylpgTypePlugin]
        ] = {}
        self._plugins: list[type[PylpgTypePlugin]] = []

    def register(self, plugin: type[PylpgTypePlugin]) -> None:
        """Register a type plugin class with this context.

        Args:
            plugin: A PylpgTypePlugin subclass (not an instance).
        """
        self._plugins.append(plugin)

    def get_plugin_for_type(self, type_: type) -> type[PylpgTypePlugin]:
        """Look up the plugin class for a Python type.

        Args:
            type_: The Python type to look up.

        Returns:
            The matching PylpgTypePlugin subclass.

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

    def get_plugin_for_node_class(
        self, node_class: type[fieldz_kb.lpg.graph.BaseNode]
    ) -> type[PylpgTypePlugin]:
        """Look up the plugin class for a pylpg node class.

        Args:
            node_class: The node class to look up.

        Returns:
            The matching PylpgTypePlugin subclass.

        Raises:
            ValueError: If no plugin can handle the node class.
        """
        plugin = self._node_class_to_plugin.get(node_class)
        if plugin is not None:
            return plugin
        for candidate in self._plugins:
            if candidate.can_handle_node_class(node_class, self):
                self._node_class_to_plugin[node_class] = candidate
                return candidate
        raise ValueError(f"node class {node_class} not supported")


def get_or_make_node_class_from_type(
    ctx: PylpgContext,
    type_: type,
    make_node_classes_recursively: bool = True,
    guard: set[type] | None = None,
) -> type[fieldz_kb.lpg.graph.BaseNode] | None:
    """Get or create a pylpg node class for a given Python type.

    Args:
        ctx: The plugin registry and cache.
        type_: The Python type to get or create a node class for.
        make_node_classes_recursively: Whether to create node classes for nested types.
        guard: Set of types currently being processed (prevents infinite recursion).

    Returns:
        The node class (a subclass of BaseNode), or None.
    """
    if guard is None:
        guard = set()
    node_class = ctx.type_to_node_class.get(type_)
    if node_class is None:
        guard.add(type_)
        plugin = ctx.get_plugin_for_type(type_)
        node_class = plugin.make_node_class_from_type(
            type_, ctx, make_node_classes_recursively, guard
        )
        if node_class is not None:
            ctx.type_to_node_class[type_] = node_class
            ctx.node_class_to_type[node_class] = type_
            ctx._node_class_to_plugin[node_class] = plugin
    return node_class


def make_nodes_from_object(
    ctx: PylpgContext,
    object_: object,
    integration_mode: typing.Literal["hash", "id"] = "id",
    exclude_from_integration: tuple[type, ...] | None = None,
    object_to_node: dict | None = None,
) -> tuple[list[fieldz_kb.lpg.graph.BaseNode], list[pylpg.relationship.Relationship]]:
    """Convert a Python object to pylpg nodes and relationships.

    Args:
        ctx: The plugin registry and cache.
        object_: The object to convert.
        integration_mode: How to handle duplicate objects ("hash" or "id").
        exclude_from_integration: Types to exclude from integration logic.
        object_to_node: Cache mapping objects to their nodes for deduplication.

    Returns:
        A tuple of (nodes, relationships).
    """
    if exclude_from_integration is None:
        exclude_from_integration = tuple()
    if object_to_node is None:
        object_to_node = {}
    if not isinstance(object_, exclude_from_integration):
        if integration_mode == "hash":
            if not isinstance(object_, collections.abc.Hashable):
                raise ValueError(
                    f"object of type {type(object_)} not hashable, cannot use hash integration mode"
                )
            node = object_to_node.get(object_)
        else:
            node = object_to_node.get(id(object_))
        if node is not None:
            return [node], []
    class_ = type(object_)
    plugin = ctx.get_plugin_for_type(class_)
    nodes, relationships = plugin.make_nodes_from_object(
        object_,
        ctx,
        integration_mode=integration_mode,
        exclude_from_integration=exclude_from_integration,
        object_to_node=object_to_node,
    )
    node_class = type(nodes[0])
    if class_ not in ctx.type_to_node_class:
        ctx.type_to_node_class[class_] = node_class
    if node_class not in ctx.node_class_to_type:
        ctx.node_class_to_type[node_class] = class_
    if integration_mode == "hash":
        object_to_node[object_] = nodes[0]
    else:
        object_to_node[id(object_)] = nodes[0]
    return nodes, relationships


def make_object_from_node(
    ctx: PylpgContext,
    node: fieldz_kb.lpg.graph.BaseNode,
    node_id_to_object: dict | None = None,
) -> object:
    """Convert a pylpg node back to a Python object.

    Args:
        ctx: The plugin registry and cache.
        node: The pylpg node to convert.
        node_id_to_object: Optional cache mapping node database IDs to objects.

    Returns:
        The reconstructed Python object.

    Raises:
        ValueError: If the node type cannot be mapped to a Python class.
    """
    if node_id_to_object is None:
        node_id_to_object = {}
    object_ = node_id_to_object.get(node._database_id)
    if object_ is not None:
        return object_
    node_class = type(node)
    plugin = ctx.get_plugin_for_node_class(node_class)
    object_ = plugin.make_object_from_node(
        node, ctx, node_id_to_object=node_id_to_object
    )
    node_id_to_object[node._database_id] = object_
    return object_


def make_context() -> PylpgContext:
    """Create a fresh PylpgContext with all built-in plugins registered."""
    import frozendict

    import fieldz_kb.lpg.plugins

    context = PylpgContext()

    context.type_to_node_class = {
        int: fieldz_kb.lpg.graph.Integer,
        str: fieldz_kb.lpg.graph.String,
        float: fieldz_kb.lpg.graph.Float,
        bool: fieldz_kb.lpg.graph.Boolean,
        list: fieldz_kb.lpg.graph.List,
        tuple: fieldz_kb.lpg.graph.Tuple,
        set: fieldz_kb.lpg.graph.Set,
        frozenset: fieldz_kb.lpg.graph.FrozenSet,
    }
    context.node_class_to_type = {
        fieldz_kb.lpg.graph.Integer: int,
        fieldz_kb.lpg.graph.String: str,
        fieldz_kb.lpg.graph.Float: float,
        fieldz_kb.lpg.graph.Boolean: bool,
        fieldz_kb.lpg.graph.List: list,
        fieldz_kb.lpg.graph.Tuple: tuple,
        fieldz_kb.lpg.graph.Set: set,
        fieldz_kb.lpg.graph.FrozenSet: frozenset,
        fieldz_kb.lpg.graph.Dict: dict,
        fieldz_kb.lpg.graph.FrozenDict: frozendict.frozendict,
    }

    context.register(fieldz_kb.lpg.plugins.BaseTypePlugin)
    context.register(fieldz_kb.lpg.plugins.SequencePlugin)
    context.register(fieldz_kb.lpg.plugins.BagPlugin)
    context.register(fieldz_kb.lpg.plugins.DictPlugin)
    context.register(fieldz_kb.lpg.plugins.FieldzClassPlugin)
    context.register(fieldz_kb.lpg.plugins.EnumPlugin)

    return context


_default_context: PylpgContext | None = None


def get_default_context() -> PylpgContext:
    """Return the shared default context, creating it on first access."""
    global _default_context
    if _default_context is None:
        _default_context = make_context()
    return _default_context
