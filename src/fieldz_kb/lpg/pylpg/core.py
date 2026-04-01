"""Core pylpg integration for fieldz_kb.

This module provides the core functionality for converting dataclass-like objects
to labeled property graph nodes and relationships via pylpg. It includes:

- Node class generation from Python types
- Object-to-node conversion (saving)
- Node-to-object conversion (retrieval)
- Support for primitives, collections, enums, and nested dataclasses
- Relationship handling with ordering support
- Plugin-based extensibility via PylpgTypePlugin and PylpgContext

This module is backend-agnostic — it works with any pylpg backend (Neo4j,
FalkorDB, FalkorDBLite). Database-specific connect() functions are provided
by the thin wrapper modules (e.g., fieldz_kb.neo4j.pylpg.core).
"""

import types
import typing
import collections.abc
import enum
import abc

import fieldz
import frozendict
from pylpg.node import Node
from pylpg.relationship import Relationship, RelationshipTo

import fieldz_kb.typeinfo
from fieldz_kb.utils import (
    _base_types,
    _array_types,
    _make_node_class_name_from_type,
    _make_relationship_type_from_field_name,
    _get_node_property_attributes_from_type,
    _get_array_type_from_field,
)


# ---------------------------------------------------------------------------
# Pre-built node classes
# ---------------------------------------------------------------------------


class BaseNode(Node):
    """Base class for all pylpg node types."""

    __labels__ = frozenset({"BaseNode"})


class Integer(BaseNode):
    """Node class for storing integer values."""

    __labels__ = frozenset({"Integer"})
    value: int


class String(BaseNode):
    """Node class for storing string values."""

    __labels__ = frozenset({"String"})
    value: str


class Float(BaseNode):
    """Node class for storing float values."""

    __labels__ = frozenset({"Float"})
    value: float


class Boolean(BaseNode):
    """Node class for storing boolean values."""

    __labels__ = frozenset({"Boolean"})
    value: bool


# ---------------------------------------------------------------------------
# Pre-built relationship classes
# ---------------------------------------------------------------------------


class OrderedHasItem(Relationship):
    """Relationship for ordered HAS_ITEM connections."""

    __type__ = "HAS_ITEM"
    order: int | None = None


class UnorderedHasItem(Relationship):
    """Relationship for unordered HAS_ITEM connections."""

    __type__ = "HAS_ITEM"


class HasKey(Relationship):
    """Relationship for HAS_KEY connections in mappings."""

    __type__ = "HAS_KEY"


class HasValue(Relationship):
    """Relationship for HAS_VALUE connections in mappings."""

    __type__ = "HAS_VALUE"


# ---------------------------------------------------------------------------
# Pre-built collection node classes
# ---------------------------------------------------------------------------


class Item(BaseNode):
    """Node class for storing key-value pairs (used in mappings)."""

    __labels__ = frozenset({"Item"})
    key = RelationshipTo(HasKey)
    value = RelationshipTo(HasValue)


class Mapping(BaseNode):
    """Base node class for mapping types (dict, frozendict)."""

    __labels__ = frozenset({"Mapping"})
    items = RelationshipTo(OrderedHasItem)


class Dict(Mapping):
    """Node class for storing dictionary values."""

    __labels__ = frozenset({"Dict"})


class FrozenDict(Mapping):
    """Node class for storing frozendict values."""

    __labels__ = frozenset({"FrozenDict"})


class Bag(BaseNode):
    """Base node class for unordered collection types (set, frozenset)."""

    __labels__ = frozenset({"Bag"})
    items = RelationshipTo(UnorderedHasItem)


class Set(Bag):
    """Node class for storing set values."""

    __labels__ = frozenset({"Set"})


class FrozenSet(Bag):
    """Node class for storing frozenset values."""

    __labels__ = frozenset({"FrozenSet"})


class Sequence(BaseNode):
    """Base node class for ordered sequence types (list, tuple)."""

    __labels__ = frozenset({"Sequence"})
    items = RelationshipTo(OrderedHasItem)


class List(Sequence):
    """Node class for storing list values."""

    __labels__ = frozenset({"List"})


class Tuple(Sequence):
    """Node class for storing tuple values."""

    __labels__ = frozenset({"Tuple"})


# ---------------------------------------------------------------------------
# Plugin ABC
# ---------------------------------------------------------------------------


class PylpgTypePlugin(abc.ABC):
    """Abstract base class for pylpg type conversion plugins.

    Each plugin handles one or more Python types, providing:
    - Node class creation (for dynamically generated types)
    - Object-to-node conversion
    - Node-to-object conversion

    Args (for subclass methods):
        ctx: The PylpgContext instance providing access to caches and other plugins.
    """

    @abc.abstractmethod
    def handled_types(self) -> list[type]:
        """Return the Python types this plugin handles via direct lookup."""
        ...

    def handled_node_classes(self) -> list[type]:
        """Return the node classes this plugin handles for make_object dispatch."""
        return []

    def can_handle_type(self, type_) -> bool:
        """Predicate-based fallback for type dispatch.

        Called when no direct type match is found. Override for types that
        cannot be enumerated upfront (e.g., fieldz classes, enums).
        """
        return False

    def can_handle_node_class(self, node_class, ctx) -> bool:
        """Predicate-based fallback for node class dispatch.

        Called when no direct node class match is found.
        """
        return False

    def make_node_class(
        self, type_, ctx, make_node_classes_recursively=True, guard=None
    ):
        """Create a pylpg node class for the given Python type.

        Returns:
            A Node subclass, or None if the type uses a pre-built node class.
        """
        return None

    @abc.abstractmethod
    def make_nodes(
        self, obj, ctx, integration_mode, exclude_from_integration, object_to_node
    ):
        """Convert a Python object to pylpg nodes and connection instructions.

        Returns:
            A tuple of (nodes, to_connect) where nodes is a list of node instances
            and to_connect is a list of (source, rel_class, target, properties) tuples.
        """
        ...

    @abc.abstractmethod
    def make_object(self, node, ctx, node_id_to_object):
        """Convert a pylpg node back to a Python object.

        Returns:
            The reconstructed Python object.
        """
        ...


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


class PylpgContext:
    """Owns all caches and plugin registrations for pylpg type conversion.

    Provides the main dispatch methods that delegate to registered plugins.
    A default module-level instance is created with all built-in plugins.
    """

    def __init__(self):
        self.type_to_node_class = {}
        self.node_class_to_type = {}
        self._type_to_plugin = {}
        self._node_class_to_plugin = {}
        self._fallback_plugins = []

    def register(self, plugin):
        """Register a type plugin with this context.

        Args:
            plugin: A PylpgTypePlugin instance.
        """
        for t in plugin.handled_types():
            self._type_to_plugin[t] = plugin
        for nc in plugin.handled_node_classes():
            self._node_class_to_plugin[nc] = plugin
        self._fallback_plugins.append(plugin)

    def get_plugin_for_type(self, type_):
        """Look up the plugin for a Python type.

        Args:
            type_: The Python type to look up.

        Returns:
            The matching PylpgTypePlugin.

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

    def get_plugin_for_node_class(self, node_class):
        """Look up the plugin for a pylpg node class.

        Args:
            node_class: The node class to look up.

        Returns:
            The matching PylpgTypePlugin.

        Raises:
            ValueError: If no plugin can handle the node class.
        """
        plugin = self._node_class_to_plugin.get(node_class)
        if plugin is None:
            for p in self._fallback_plugins:
                if p.can_handle_node_class(node_class, self):
                    plugin = p
                    break
        if plugin is None:
            raise ValueError(f"node class {node_class} not supported")
        return plugin

    def get_or_make_node_class(
        self, type_, make_node_classes_recursively=True, guard=None
    ):
        """Get or create a pylpg node class for a given Python type.

        Args:
            type_: The Python type to get or create a node class for.
            make_node_classes_recursively: Whether to create node classes for nested types.
            guard: Set of types currently being processed (prevents infinite recursion).

        Returns:
            The node class (a subclass of BaseNode).
        """
        if guard is None:
            guard = set([])
        node_class = self.type_to_node_class.get(type_)
        if node_class is None:
            guard.add(type_)
            plugin = self.get_plugin_for_type(type_)
            node_class = plugin.make_node_class(
                type_, self, make_node_classes_recursively, guard
            )
            if node_class is not None:
                self.type_to_node_class[type_] = node_class
                self.node_class_to_type[node_class] = type_
                self._node_class_to_plugin[node_class] = plugin
        return node_class

    def make_node_property_from_field(
        self, field, module=None, make_node_classes_recursively=True, guard=None
    ):
        """Determine the property type for a dataclass field.

        Returns a dict describing how the field should be represented:
        - {"kind": "base", "type": <type>} for base type annotations
        - {"kind": "array", "type": <type>, "item_type": <type>} for array properties
        - {"kind": "relationship", "rel_class": <class>, "descriptor": <RelationshipTo>,
           "many": bool, "ordered": bool} for relationships

        Args:
            field: The fieldz field descriptor.
            module: Module name for resolving forward references.
            make_node_classes_recursively: Whether to create node classes for nested types.
            guard: Guard set for recursion prevention.

        Returns:
            A dict describing the field representation.
        """
        if guard is None:
            guard = []
        type_hint = field.type
        types_ = fieldz_kb.typeinfo.get_types_from_type_hint(type_hint, module=module)
        node_property_attributes_candidates = set()
        optional = False
        for type_ in types_:
            type_origin = type_[0]
            if type_origin is types.NoneType:
                optional = True
                break
        if optional:
            types_ = list(types_)
            types_.remove(type_)
            types_ = tuple(types_)
        for type_ in types_:
            node_property_attributes_candidates.add(
                _get_node_property_attributes_from_type(type_)
            )
        if (
            all(
                [
                    npa[0] == "base"
                    for npa in node_property_attributes_candidates
                ]
            )
            and len(
                set(
                    [
                        npa[1]
                        for npa in node_property_attributes_candidates
                    ]
                )
            )
            == 1
        ):
            _, target_types, _, _ = next(iter(node_property_attributes_candidates))
            target_type_origin = next(iter(target_types))[0]
            return {"kind": "base", "type": target_type_origin, "optional": optional}
        elif (
            all(
                [
                    npa[0] == "array"
                    for npa in node_property_attributes_candidates
                ]
            )
            and len(
                set(
                    [
                        npa[1]
                        for npa in node_property_attributes_candidates
                    ]
                )
            )
            == 1
        ):
            _, target_types, _, _ = next(iter(node_property_attributes_candidates))
            target_type_origin = next(iter(target_types))[0]
            return {
                "kind": "array",
                "type": list,
                "item_type": target_type_origin,
                "optional": optional,
            }
        else:
            many = any(
                [npa[2] is True for npa in node_property_attributes_candidates]
            )
            ordered = any(
                [npa[3] is True for npa in node_property_attributes_candidates]
            )
            relationship_type = _make_relationship_type_from_field_name(
                field.name, many
            )
            if ordered:
                rel_class = type(
                    f"Ordered{relationship_type}",
                    (Relationship,),
                    {
                        "__type__": relationship_type,
                        "__annotations__": {"order": int | None},
                        "order": None,
                    },
                )
            else:
                rel_class = type(
                    f"Unordered{relationship_type}",
                    (Relationship,),
                    {"__type__": relationship_type},
                )
            descriptor = RelationshipTo(rel_class)
            if make_node_classes_recursively:
                for npa in node_property_attributes_candidates:
                    for target_type in npa[1]:
                        target_type_origin = target_type[0]
                        if target_type_origin not in guard:
                            self.get_or_make_node_class(
                                target_type_origin,
                                make_node_classes_recursively=make_node_classes_recursively,
                                guard=guard,
                            )
            return {
                "kind": "relationship",
                "rel_class": rel_class,
                "descriptor": descriptor,
                "many": many,
                "ordered": ordered,
                "optional": optional,
            }

    def make_nodes_from_object(
        self,
        object_,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration=None,
        object_to_node=None,
    ):
        """Convert a Python object to pylpg nodes.

        Args:
            object_: The object to convert.
            integration_mode: How to handle duplicate objects ("hash" or "id").
            exclude_from_integration: Types to exclude from integration logic.
            object_to_node: Cache mapping objects to their nodes for deduplication.

        Returns:
            A tuple of (nodes, to_connect).
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
        plugin = self.get_plugin_for_type(class_)
        nodes, to_connect = plugin.make_nodes(
            object_,
            self,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        node_class = type(nodes[0])
        if class_ not in self.type_to_node_class:
            self.type_to_node_class[class_] = node_class
        if node_class not in self.node_class_to_type:
            self.node_class_to_type[node_class] = class_
        if integration_mode == "hash":
            object_to_node[object_] = nodes[0]
        else:
            object_to_node[id(object_)] = nodes[0]
        return nodes, to_connect

    def make_object_from_node(self, node, node_id_to_object=None):
        """Convert a pylpg node back to a Python object.

        Args:
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
        plugin = self.get_plugin_for_node_class(node_class)
        object_ = plugin.make_object(
            node, self, node_id_to_object=node_id_to_object
        )
        node_id_to_object[node._database_id] = object_
        return object_


# ---------------------------------------------------------------------------
# Built-in Plugins
# ---------------------------------------------------------------------------


class BaseTypePlugin(PylpgTypePlugin):
    """Handles base types: int, str, float, bool."""

    _type_to_node_class = {int: Integer, str: String, float: Float, bool: Boolean}

    def handled_types(self):
        return [int, str, float, bool]

    def handled_node_classes(self):
        return [Integer, String, Float, Boolean]

    def make_nodes(
        self, obj, ctx, integration_mode, exclude_from_integration, object_to_node
    ):
        node_class = self._type_to_node_class[type(obj)]
        return [node_class(value=obj)], []

    def make_object(self, node, ctx, node_id_to_object):
        return node.value


class SequencePlugin(PylpgTypePlugin):
    """Handles ordered sequences: list, tuple."""

    _type_to_node_class = {list: List, tuple: Tuple}

    def handled_types(self):
        return [list, tuple]

    def handled_node_classes(self):
        return [List, Tuple]

    def make_nodes(
        self, obj, ctx, integration_mode, exclude_from_integration, object_to_node
    ):
        node_class = self._type_to_node_class[type(obj)]
        node = node_class()
        nodes = [node]
        to_connect = []
        for index, element in enumerate(obj):
            nodes_element, to_connect_element = ctx.make_nodes_from_object(
                element,
                integration_mode=integration_mode,
                exclude_from_integration=exclude_from_integration,
                object_to_node=object_to_node,
            )
            node_element = nodes_element[0]
            nodes.append(node_element)
            to_connect += to_connect_element
            to_connect.append(
                (node, OrderedHasItem, node_element, {"order": index})
            )
        return nodes, to_connect

    def make_object(self, node, ctx, node_id_to_object):
        items = node.items.all()
        objects = [
            ctx.make_object_from_node(node_item, node_id_to_object)
            for node_item in items
        ]
        sequence_type = ctx.node_class_to_type[type(node)]
        return sequence_type(objects)


class BagPlugin(PylpgTypePlugin):
    """Handles unordered collections: set, frozenset."""

    _type_to_node_class = {set: Set, frozenset: FrozenSet}

    def handled_types(self):
        return [set, frozenset]

    def handled_node_classes(self):
        return [Set, FrozenSet]

    def make_nodes(
        self, obj, ctx, integration_mode, exclude_from_integration, object_to_node
    ):
        node_class = self._type_to_node_class[type(obj)]
        node = node_class()
        nodes = [node]
        to_connect = []
        for element in obj:
            nodes_element, to_connect_element = ctx.make_nodes_from_object(
                element,
                integration_mode=integration_mode,
                exclude_from_integration=exclude_from_integration,
                object_to_node=object_to_node,
            )
            node_element = nodes_element[0]
            nodes.append(node_element)
            to_connect += to_connect_element
            to_connect.append((node, UnorderedHasItem, node_element, {}))
        return nodes, to_connect

    def make_object(self, node, ctx, node_id_to_object):
        items = node.items.all()
        objects = [
            ctx.make_object_from_node(node_item, node_id_to_object)
            for node_item in items
        ]
        bag_type = ctx.node_class_to_type[type(node)]
        return bag_type(objects)


class DictPlugin(PylpgTypePlugin):
    """Handles mapping types: dict, frozendict."""

    _type_to_node_class = {dict: Dict, frozendict.frozendict: FrozenDict}

    def handled_types(self):
        return [dict, frozendict.frozendict]

    def handled_node_classes(self):
        return [Dict, FrozenDict]

    def _make_nodes_from_dict_item(
        self,
        key,
        value,
        ctx,
        integration_mode,
        exclude_from_integration,
        object_to_node,
    ):
        node = Item()
        nodes = [node]
        to_connect = []
        nodes_key, to_connect_key = ctx.make_nodes_from_object(
            key,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        nodes += nodes_key
        to_connect += to_connect_key
        node_key = nodes_key[0]
        to_connect.append((node, HasKey, node_key, {}))
        nodes_value, to_connect_value = ctx.make_nodes_from_object(
            value,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        nodes += nodes_value
        to_connect += to_connect_value
        node_value = nodes_value[0]
        to_connect.append((node, HasValue, node_value, {}))
        return nodes, to_connect

    def make_nodes(
        self, obj, ctx, integration_mode, exclude_from_integration, object_to_node
    ):
        node_class = self._type_to_node_class[type(obj)]
        node = node_class()
        nodes = [node]
        to_connect = []
        for key, value in obj.items():
            nodes_item, to_connect_item = self._make_nodes_from_dict_item(
                key,
                value,
                ctx,
                integration_mode=integration_mode,
                exclude_from_integration=exclude_from_integration,
                object_to_node=object_to_node,
            )
            nodes += nodes_item
            to_connect += to_connect_item
            node_item = nodes_item[0]
            to_connect.append((node, OrderedHasItem, node_item, {}))
        return nodes, to_connect

    def make_object(self, node, ctx, node_id_to_object):
        node_class = type(node)
        if node_class is Dict:
            dict_object = {}
            for node_item in node.items.all():
                key_nodes = node_item.key.all()
                value_nodes = node_item.value.all()
                key = ctx.make_object_from_node(key_nodes[0], node_id_to_object)
                value = ctx.make_object_from_node(value_nodes[0], node_id_to_object)
                dict_object[key] = value
            return dict_object
        else:
            objects = [
                ctx.make_object_from_node(node_item, node_id_to_object)
                for node_item in node.items.all()
            ]
            return ctx.node_class_to_type[node_class](objects)


class FieldzClassPlugin(PylpgTypePlugin):
    """Handles fieldz dataclass-like types."""

    def handled_types(self):
        return []

    def can_handle_type(self, type_):
        return fieldz_kb.typeinfo.is_fieldz_class(type_)

    def can_handle_node_class(self, node_class, ctx):
        type_ = ctx.node_class_to_type.get(node_class)
        if type_ is None:
            return False
        return fieldz_kb.typeinfo.is_fieldz_class(type_)

    def make_node_class(
        self, type_, ctx, make_node_classes_recursively=True, guard=None
    ):
        if guard is None:
            guard = []
        node_class_name = _make_node_class_name_from_type(type_)
        fieldz_class_bases = type_.__bases__
        node_class_bases = tuple(
            [
                ctx.get_or_make_node_class(
                    base_class,
                    make_node_classes_recursively=make_node_classes_recursively,
                    guard=guard,
                )
                for base_class in fieldz_class_bases
                if base_class not in (object, abc.ABC)
                and not base_class.__name__.startswith("_")
                and base_class.__name__ != type_.__name__
            ]
        )
        if not node_class_bases:
            node_class_bases = (BaseNode,)
        node_class_dict = {
            "__labels__": frozenset({node_class_name}),
        }
        node_class_annotations = {}
        for field in fieldz.fields(type_):
            field_info = ctx.make_node_property_from_field(
                field,
                module=type_.__module__,
                make_node_classes_recursively=make_node_classes_recursively,
                guard=guard,
            )
            if field_info["kind"] == "base":
                node_class_annotations[field.name] = field_info["type"] | None
                node_class_dict[field.name] = None
            elif field_info["kind"] == "array":
                item_type = field_info["item_type"]
                node_class_annotations[field.name] = list[item_type] | None
                node_class_dict[field.name] = None
            else:
                node_class_dict[field.name] = field_info["descriptor"]
                node_class_dict[f"_field_info_{field.name}"] = field_info
        node_class_dict["__annotations__"] = node_class_annotations
        node_class = type(node_class_name, node_class_bases, node_class_dict)
        return node_class

    def make_nodes(
        self, obj, ctx, integration_mode, exclude_from_integration, object_to_node
    ):
        nodes = []
        to_connect = []
        fieldz_class = type(obj)
        node_class = ctx.get_or_make_node_class(
            fieldz_class, make_node_classes_recursively=False
        )
        node = node_class()
        nodes.append(node)
        for field in fieldz.fields(fieldz_class):
            field_value = getattr(obj, field.name)
            if field_value is not None:
                field_info = getattr(
                    node_class, f"_field_info_{field.name}", None
                )
                if field_info is None:
                    if isinstance(field_value, _array_types):
                        setattr(node, field.name, list(field_value))
                    else:
                        setattr(node, field.name, field_value)
                else:
                    rel_class = field_info["rel_class"]
                    add_order = field_info["ordered"]
                    if not isinstance(field_value, _array_types):
                        field_value = [field_value]
                    for index, field_value_element in enumerate(field_value):
                        sub_nodes, sub_to_connect = ctx.make_nodes_from_object(
                            field_value_element,
                            integration_mode,
                            exclude_from_integration,
                            object_to_node,
                        )
                        nodes += sub_nodes
                        to_connect += sub_to_connect
                        if add_order:
                            properties = {"order": index}
                        else:
                            properties = {}
                        to_connect.append(
                            (node, rel_class, sub_nodes[0], properties)
                        )
        return nodes, to_connect

    def make_object(self, node, ctx, node_id_to_object):
        node_class = type(node)
        fieldz_class = ctx.node_class_to_type.get(node_class)
        if fieldz_class is None:
            raise ValueError(
                f"could not find an appropriate class for node class {node_class}"
            )
        fieldz_object_attr_values = {}
        for field in fieldz.fields(fieldz_class):
            field_info = getattr(node_class, f"_field_info_{field.name}", None)
            if field_info is None:
                node_attr_value = getattr(node, field.name)
                if node_attr_value is None:
                    field_value = None
                elif isinstance(node_attr_value, list):
                    array_type = _get_array_type_from_field(
                        field, module=fieldz_class.__module__
                    )
                    field_value = array_type(node_attr_value)
                else:
                    field_value = node_attr_value
            else:
                bound_rel = getattr(node, field.name)
                many = field_info["many"]
                if many:
                    related_nodes = bound_rel.all()
                    if not related_nodes and field.default is None:
                        field_value = None
                    else:
                        array_type = _get_array_type_from_field(
                            field, module=fieldz_class.__module__
                        )
                        field_value = array_type(
                            [
                                ctx.make_object_from_node(
                                    element,
                                    node_id_to_object=node_id_to_object,
                                )
                                for element in related_nodes
                            ]
                        )
                else:
                    related_nodes = bound_rel.all()
                    if related_nodes:
                        field_value = ctx.make_object_from_node(
                            related_nodes[0],
                            node_id_to_object=node_id_to_object,
                        )
                    else:
                        field_value = None
            fieldz_object_attr_values[field.name] = field_value
        fieldz_object = fieldz_class(**fieldz_object_attr_values)
        return fieldz_object


class EnumPlugin(PylpgTypePlugin):
    """Handles enum types."""

    def handled_types(self):
        return []

    def can_handle_type(self, type_):
        try:
            return issubclass(type_, enum.Enum)
        except TypeError:
            return False

    def can_handle_node_class(self, node_class, ctx):
        type_ = ctx.node_class_to_type.get(node_class)
        if type_ is None:
            return False
        try:
            return issubclass(type_, enum.Enum)
        except TypeError:
            return False

    def make_node_class(
        self, type_, ctx, make_node_classes_recursively=True, guard=None
    ):
        node_class_name = _make_node_class_name_from_type(type_)
        node_class_bases = (BaseNode,)
        node_class_annotations = {"name": str | None}
        item_value_types = set([type(item.value) for item in type_])
        if len(item_value_types) != 1:
            raise ValueError(
                f"enum of type {type_} not supported: types of values must all be the same"
            )
        item_value_type = next(iter(item_value_types))
        if item_value_type in _base_types:
            node_class_annotations["value"] = item_value_type | None
        node_class_dict = {
            "__labels__": frozenset({node_class_name}),
            "__annotations__": node_class_annotations,
            "name": None,
            "value": None,
        }
        node_class = type(node_class_name, node_class_bases, node_class_dict)
        return node_class

    def make_nodes(
        self, obj, ctx, integration_mode, exclude_from_integration, object_to_node
    ):
        enum_class = type(obj)
        node_class = ctx.get_or_make_node_class(enum_class)
        node = node_class()
        node.name = obj.name
        node.value = obj.value
        return [node], []

    def make_object(self, node, ctx, node_id_to_object):
        node_class = type(node)
        enum_class = ctx.node_class_to_type.get(node_class)
        if enum_class is None:
            raise ValueError(
                f"could not find an appropriate class for node class {node_class}"
            )
        return getattr(enum_class, node.name)


# ---------------------------------------------------------------------------
# Default context
# ---------------------------------------------------------------------------


def _make_default_context():
    """Create and configure the default PylpgContext with all built-in plugins."""
    ctx = PylpgContext()

    ctx.type_to_node_class = {
        int: Integer,
        str: String,
        float: Float,
        bool: Boolean,
        list: List,
        tuple: Tuple,
        set: Set,
        frozenset: FrozenSet,
    }
    ctx.node_class_to_type = {
        Integer: int,
        String: str,
        Float: float,
        Boolean: bool,
        List: list,
        Tuple: tuple,
        Set: set,
        FrozenSet: frozenset,
        Dict: dict,
        FrozenDict: frozendict,
    }

    ctx.register(BaseTypePlugin())
    ctx.register(SequencePlugin())
    ctx.register(BagPlugin())
    ctx.register(DictPlugin())
    ctx.register(FieldzClassPlugin())
    ctx.register(EnumPlugin())

    return ctx


_default_context = _make_default_context()


# ---------------------------------------------------------------------------
# Public API (thin wrappers around default context)
# ---------------------------------------------------------------------------


def get_or_make_node_class_from_type(
    type_, make_node_classes_recursively=True, guard=None
):
    """Get or create a pylpg node class for a given Python type.

    Args:
        type_: The Python type to get or create a node class for
        make_node_classes_recursively: Whether to create node classes for nested types
        guard: Set of types currently being processed (prevents infinite recursion)

    Returns:
        The node class (a subclass of BaseNode)
    """
    return _default_context.get_or_make_node_class(
        type_, make_node_classes_recursively, guard
    )


def make_nodes_from_object(
    object_,
    integration_mode: typing.Literal["hash", "id"] = "id",
    exclude_from_integration=None,
    object_to_node=None,
):
    """Convert a Python object to pylpg nodes.

    Args:
        object_: The object to convert
        integration_mode: How to handle duplicate objects ("hash" or "id")
        exclude_from_integration: Types to exclude from integration logic
        object_to_node: Cache mapping objects to their nodes for deduplication

    Returns:
        A tuple of (nodes, to_connect)
    """
    return _default_context.make_nodes_from_object(
        object_, integration_mode, exclude_from_integration, object_to_node
    )


def register_make_nodes_function(type_, function):
    """Register a custom object-to-nodes conversion function for a type.

    Args:
        type_: The Python type to register the function for.
        function: The conversion function.
    """

    class _FunctionPlugin(PylpgTypePlugin):
        def handled_types(self):
            return [type_]

        def make_nodes(
            self, obj, ctx, integration_mode, exclude_from_integration, object_to_node
        ):
            return function(
                obj,
                integration_mode=integration_mode,
                exclude_from_integration=exclude_from_integration,
                object_to_node=object_to_node,
            )

        def make_object(self, node, ctx, node_id_to_object):
            raise NotImplementedError(f"make_object not registered for type {type_}")

    _default_context.register(_FunctionPlugin())


def register_make_object_function(node_class, function):
    """Register a custom node-to-object conversion function for a node class.

    Args:
        node_class: The pylpg node class to register the function for.
        function: The conversion function.
    """

    class _FunctionPlugin(PylpgTypePlugin):
        def handled_types(self):
            return []

        def handled_node_classes(self):
            return [node_class]

        def make_nodes(
            self, obj, ctx, integration_mode, exclude_from_integration, object_to_node
        ):
            raise NotImplementedError(
                f"make_nodes not registered for node class {node_class}"
            )

        def make_object(self, node, ctx, node_id_to_object):
            return function(node, node_id_to_object=node_id_to_object)

    _default_context.register(_FunctionPlugin())
