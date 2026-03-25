"""Core Neo4j integration for fieldz_kb.

This module provides the core functionality for converting dataclass-like objects
to Neo4j nodes and relationships. It includes:

- Node class generation from Python types
- Object-to-node conversion (saving)
- Node-to-object conversion (retrieval)
- Support for primitives, collections, enums, and nested dataclasses
- Relationship handling with ordering support
- Plugin-based extensibility via Neo4jTypePlugin and Neo4jContext
"""

import types
import typing
import re
import collections.abc
import enum
import abc

import fieldz
import inflect
import neomodel
import neo4j
import frozendict

import fieldz_kb.typeinfo


# Type classification constants
_base_types = (int, str, float, bool)
_array_types = (list, tuple, set, frozenset)
_ordered_array_types = (list, tuple)


class OrderedRelationshipTo(neomodel.StructuredRel):
    """Relationship model for ordered relationships with sequence information."""

    order = neomodel.IntegerProperty()


class UnorderedRelationshipTo(neomodel.StructuredRel):
    """Relationship model for unordered relationships."""

    pass


class BaseNode(neomodel.StructuredNode):
    """Base class for all Neo4j node types."""

    pass


class Integer(BaseNode):
    """Node class for storing integer values."""

    value = neomodel.IntegerProperty(required=True)


class String(BaseNode):
    """Node class for storing string values."""

    value = neomodel.StringProperty(required=True)


class Float(BaseNode):
    """Node class for storing float values."""

    value = neomodel.FloatProperty(required=True)


class Boolean(BaseNode):
    """Node class for storing boolean values."""

    value = neomodel.BooleanProperty(required=True)


class Item(BaseNode):
    """Node class for storing key-value pairs (used in mappings)."""

    key = neomodel.RelationshipTo(BaseNode, "HAS_KEY", neomodel.One)
    value = neomodel.RelationshipTo(BaseNode, "HAS_VALUE", neomodel.One)


class Mapping(BaseNode):
    """Base node class for mapping types (dict, frozendict)."""

    items = neomodel.RelationshipTo(
        Item, "HAS_ITEM", neomodel.ZeroOrMore, model=OrderedRelationshipTo
    )


class Dict(Mapping):
    """Node class for storing dictionary values."""

    pass


class FrozenDict(Mapping):
    """Node class for storing frozendict values."""

    pass


class Bag(BaseNode):
    """Base node class for unordered collection types (set, frozenset)."""

    items = neomodel.RelationshipTo(
        BaseNode, "HAS_ITEM", neomodel.ZeroOrMore, model=OrderedRelationshipTo
    )


class Set(Bag):
    """Node class for storing set values."""

    pass


class FrozenSet(Bag):
    """Node class for storing frozenset values."""

    pass


class Sequence(BaseNode):
    """Base node class for ordered sequence types (list, tuple)."""

    items = neomodel.RelationshipTo(
        BaseNode,
        "HAS_ITEM",
        neomodel.ZeroOrMore,
        model=OrderedRelationshipTo,
    )


class List(Sequence):
    """Node class for storing list values."""

    pass


class Tuple(Sequence):
    """Node class for storing tuple values."""

    pass


def _make_node_class_name_from_type(type_):
    return type_.__name__


def _make_relationship_type_from_field_name(field_name, many=False):
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
            singular = inflect_engine.singular_noun(
                plural
            )  # returns False if already singular
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


def _get_node_property_attributes_from_type(type_):
    type_origin, type_args = type_
    type_args = frozenset(type_args)
    if issubclass(type_origin, _base_types):  # base type, we ignore subtypes
        property_type = "base"
        ordered = False
        many = False
        target_types = frozenset([type_])
    elif issubclass(type_origin, _array_types):  # array type
        many = True
        if issubclass(type_origin, _ordered_array_types):
            ordered = True
        else:
            ordered = False
        if len(type_args) == 1:  # one subtype
            type_arg = next(iter(type_args))
            type_arg_origin = type_arg[0]
            if issubclass(type_arg_origin, _base_types):  # subtype is base type
                property_type = "array"
            else:  # subtype is not base type, must be a relationship
                property_type = "relationship"
        else:  # no subtype (Any) or more than one subtype, must be a relationship
            property_type = "relationship"
        target_types = frozenset(type_args)
    else:
        many = False
        ordered = False
        property_type = "relationship"
        target_types = frozenset([type_])
    return (
        property_type,
        target_types,
        many,
        ordered,
    )


def _get_array_type_from_field(field, module=None):
    array_type = None
    default_factory = field.default_factory
    if not fieldz_kb.typeinfo.is_missing_type(default_factory):
        array_type = default_factory
    else:
        types = fieldz_kb.typeinfo.get_types_from_type_hint(field.type, module=module)
        for type_, _ in types:
            if issubclass(type_, _array_types):
                array_type = type_
    if array_type is None:
        raise ValueError(f"could not find appropriate type for field {field.name}")
    return array_type


class Neo4jTypePlugin(abc.ABC):
    """Abstract base class for Neo4j type conversion plugins.

    Each plugin handles one or more Python types, providing:
    - Node class creation (for dynamically generated types)
    - Object-to-node conversion
    - Node-to-object conversion

    Args (for subclass methods):
        ctx: The Neo4jContext instance providing access to caches and other plugins.
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
        """Create a Neo4j node class for the given Python type.

        Returns:
            A StructuredNode subclass, or None if the type uses a pre-built node class.
        """
        return None

    @abc.abstractmethod
    def make_nodes(
        self, obj, ctx, integration_mode, exclude_from_integration, object_to_node
    ):
        """Convert a Python object to Neo4j nodes and connection instructions.

        Returns:
            A tuple of (nodes, to_connect) where nodes is a list of node instances
            and to_connect is a list of (source, attr_name, target, properties) tuples.
        """
        ...

    @abc.abstractmethod
    def make_object(self, node, ctx, node_element_id_to_object):
        """Convert a Neo4j node back to a Python object.

        Returns:
            The reconstructed Python object.
        """
        ...


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


class Neo4jContext:
    """Owns all caches and plugin registrations for Neo4j type conversion.

    Provides the main dispatch methods that delegate to registered plugins.
    A default module-level instance is created with all built-in plugins.
    """

    def __init__(self):
        self.type_to_node_class = {}
        self.node_class_to_type = {}
        self.type_to_node_base_property_class = {}
        self._type_to_plugin = {}
        self._node_class_to_plugin = {}
        self._fallback_plugins = []

    def register(self, plugin):
        """Register a type plugin with this context.

        Args:
            plugin: A Neo4jTypePlugin instance.
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
            The matching Neo4jTypePlugin.

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
        """Look up the plugin for a Neo4j node class.

        Args:
            node_class: The node class to look up.

        Returns:
            The matching Neo4jTypePlugin.

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
        """Get or create a Neo4j node class for a given Python type.

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
        """Create a neomodel property or relationship for a dataclass field.

        Args:
            field: The fieldz field descriptor.
            module: Module name for resolving forward references.
            make_node_classes_recursively: Whether to create node classes for nested types.
            guard: Guard set for recursion prevention.

        Returns:
            A neomodel Property or RelationshipTo instance.
        """
        if guard is None:
            guard = []
        type_hint = field.type
        types_ = fieldz_kb.typeinfo.get_types_from_type_hint(type_hint, module=module)
        node_property_attributes_candidates = set()
        node_property = None
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
                    node_property_attributes[0] == "base"
                    for node_property_attributes in node_property_attributes_candidates
                ]
            )
            and len(
                set(
                    [
                        node_property_attributes[1]
                        for node_property_attributes in node_property_attributes_candidates
                    ]
                )
            )
            == 1
        ):  # only base with same type
            property_type, target_types, many, ordered = next(
                iter(node_property_attributes_candidates)
            )
            if property_type == "base":
                target_type, _ = next(iter(target_types))
                node_property_class = self.type_to_node_base_property_class[target_type]
                node_property = node_property_class(required=not optional)
        elif (
            all(
                [
                    node_property_attributes[0] == "array"
                    for node_property_attributes in node_property_attributes_candidates
                ]
            )
            and len(
                set(
                    [
                        node_property_attributes[1]
                        for node_property_attributes in node_property_attributes_candidates
                    ]
                )
            )
            == 1
        ):  # only array with same type
            property_type, target_types, many, ordered = next(
                iter(node_property_attributes_candidates)
            )
            target_type, _ = next(iter(target_types))
            base_node_property_class = self.type_to_node_base_property_class[
                target_type
            ]
            node_property = neomodel.ArrayProperty(
                base_node_property_class(), required=not optional
            )
        else:
            many = any(
                [
                    node_property_attributes[2] is True
                    for node_property_attributes in node_property_attributes_candidates
                ]
            )
            ordered = any(
                [
                    node_property_attributes[3] is True
                    for node_property_attributes in node_property_attributes_candidates
                ]
            )
            relationship_type = _make_relationship_type_from_field_name(
                field.name, many
            )
            if many:
                cardinality = neomodel.ZeroOrMore
            else:
                if optional:
                    cardinality = neomodel.ZeroOrOne
                else:
                    cardinality = neomodel.One
            if ordered:
                model = OrderedRelationshipTo
            else:
                model = UnorderedRelationshipTo
            node_property = neomodel.RelationshipTo(
                BaseNode, relationship_type, cardinality, model=model
            )
            if make_node_classes_recursively:
                for node_property_attributes in node_property_attributes_candidates:
                    for target_type in node_property_attributes[1]:
                        target_type_origin = target_type[0]
                        if target_type_origin not in guard:
                            self.get_or_make_node_class(
                                target_type_origin,
                                make_node_classes_recursively=make_node_classes_recursively,
                                guard=guard,
                            )
        return node_property

    def make_nodes_from_object(
        self,
        object_,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration=None,
        object_to_node=None,
    ):
        """Convert a Python object to Neo4j nodes.

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

    def make_object_from_node(self, node, node_element_id_to_object=None):
        """Convert a Neo4j node back to a Python object.

        Args:
            node: The Neo4j node to convert.
            node_element_id_to_object: Optional cache mapping node element IDs to objects.

        Returns:
            The reconstructed Python object.

        Raises:
            ValueError: If the node type cannot be mapped to a Python class.
        """
        if node_element_id_to_object is None:
            node_element_id_to_object = {}
        object_ = node_element_id_to_object.get(node.element_id)
        if object_ is not None:
            return object_
        node_class = type(node)
        plugin = self.get_plugin_for_node_class(node_class)
        object_ = plugin.make_object(
            node, self, node_element_id_to_object=node_element_id_to_object
        )
        node_element_id_to_object[node.element_id] = object_
        return object_


# ---------------------------------------------------------------------------
# Built-in Plugins
# ---------------------------------------------------------------------------


class BaseTypePlugin(Neo4jTypePlugin):
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

    def make_object(self, node, ctx, node_element_id_to_object):
        return node.value


class SequencePlugin(Neo4jTypePlugin):
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
            to_connect.append((node, "items", node_element, {"order": index}))
        return nodes, to_connect

    def make_object(self, node, ctx, node_element_id_to_object):
        objects = [
            ctx.make_object_from_node(node_item, node_element_id_to_object)
            for node_item in node.items.all()
        ]
        sequence_type = ctx.node_class_to_type[type(node)]
        return sequence_type(objects)


class BagPlugin(Neo4jTypePlugin):
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
            to_connect.append((node, "items", node_element, {}))
        return nodes, to_connect

    def make_object(self, node, ctx, node_element_id_to_object):
        objects = [
            ctx.make_object_from_node(node_item, node_element_id_to_object)
            for node_item in node.items.all()
        ]
        bag_type = ctx.node_class_to_type[type(node)]
        return bag_type(objects)


class DictPlugin(Neo4jTypePlugin):
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
        to_connect.append((node, "key", node_key, {}))
        nodes_value, to_connect_value = ctx.make_nodes_from_object(
            value,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        nodes += nodes_value
        to_connect += to_connect_value
        node_value = nodes_value[0]
        to_connect.append((node, "value", node_value, {}))
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
            to_connect.append((node, "items", node_item, {}))
        return nodes, to_connect

    def make_object(self, node, ctx, node_element_id_to_object):
        node_class = type(node)
        if node_class is Dict:
            dict_object = {}
            for node_item in node.items.all():
                key = ctx.make_object_from_node(
                    node_item.key.single(), node_element_id_to_object
                )
                value = ctx.make_object_from_node(
                    node_item.value.single(), node_element_id_to_object
                )
                dict_object[key] = value
            return dict_object
        else:
            # FrozenDict uses the sequence/bag pattern
            objects = [
                ctx.make_object_from_node(node_item, node_element_id_to_object)
                for node_item in node.items.all()
            ]
            return ctx.node_class_to_type[node_class](objects)


class FieldzClassPlugin(Neo4jTypePlugin):
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
        node_class_dict = {}
        for field in fieldz.fields(type_):
            node_property = ctx.make_node_property_from_field(
                field,
                module=type_.__module__,
                make_node_classes_recursively=make_node_classes_recursively,
                guard=guard,
            )
            node_class_dict[field.name] = node_property
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
                node_class_property = getattr(node_class, field.name)
                if isinstance(
                    node_class_property, neomodel.properties.ArrayProperty
                ):  # many, one base type
                    setattr(node, field.name, list(field_value))
                elif isinstance(
                    node_class_property, neomodel.properties.Property
                ):  # not many, one base type
                    setattr(node, field.name, field_value)
                else:  # not one base type
                    if node_class_property.definition["model"] is OrderedRelationshipTo:
                        add_order = True
                    else:
                        add_order = False
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
                            properties = None
                        to_connect.append((node, field.name, sub_nodes[0], properties))
        return nodes, to_connect

    def make_object(self, node, ctx, node_element_id_to_object):
        node_class = type(node)
        fieldz_class = ctx.node_class_to_type.get(node_class)
        if fieldz_class is None:
            raise ValueError(
                f"could not find an appropriate class for node class {node_class}"
            )
        fieldz_object_attr_values = {}
        for field in fieldz.fields(fieldz_class):
            node_attr_value = getattr(node, field.name)
            if node_attr_value is None:
                field_value = None
            else:
                node_class_property = getattr(node_class, field.name)
                if isinstance(node_class_property, neomodel.properties.ArrayProperty):
                    array_type = _get_array_type_from_field(
                        field, module=fieldz_class.__module__
                    )
                    field_value = array_type(node_attr_value)
                elif isinstance(
                    node_class_property, neomodel.properties.Property
                ):  # not many, one base type
                    field_value = node_attr_value
                else:  # a relationship
                    if node_class_property.manager in [
                        neomodel.ZeroOrMore,
                        neomodel.OneOrMore,
                    ]:
                        field_value = node_attr_value.all()
                        if not field_value and field.default is None:
                            field_value = None
                        else:
                            if issubclass(
                                node_class_property.definition["model"],
                                OrderedRelationshipTo,
                            ):
                                # we remove duplicates, we will get them back with relationships
                                element_id_to_node = {}
                                for field_value_element in field_value:
                                    element_id_to_node[
                                        field_value_element.element_id
                                    ] = field_value_element
                                field_value = list(element_id_to_node.values())
                                # we get the relationships, might be more than one by node
                                relationships = sum(
                                    [
                                        node_attr_value.all_relationships(node)
                                        for node in field_value
                                    ],
                                    [],
                                )
                                # we sort the relationships following their order attribute
                                relationships = sorted(
                                    relationships,
                                    key=lambda relationship: relationship.order,
                                )
                                # we get the nodes, ordered
                                field_value = [
                                    relationship.end_node()
                                    for relationship in relationships
                                ]
                            array_type = _get_array_type_from_field(
                                field, module=fieldz_class.__module__
                            )
                            field_value = array_type(
                                [
                                    ctx.make_object_from_node(
                                        element,
                                        node_element_id_to_object=node_element_id_to_object,
                                    )
                                    for element in field_value
                                ]
                            )
                    else:
                        field_value = node_attr_value.single()
                        if field_value is not None:
                            field_value = ctx.make_object_from_node(
                                field_value,
                                node_element_id_to_object=node_element_id_to_object,
                            )
            fieldz_object_attr_values[field.name] = field_value
        fieldz_object = fieldz_class(**fieldz_object_attr_values)
        return fieldz_object


class EnumPlugin(Neo4jTypePlugin):
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
        node_class_dict = {"name": neomodel.StringProperty()}
        item_value_types = set([type(item.value) for item in type_])
        if len(item_value_types) != 1:
            raise ValueError(
                f"enum of type {type_} not supported: types of values must all be the same"
            )
        item_value_type = next(iter(item_value_types))
        node_property_class = ctx.type_to_node_base_property_class.get(item_value_type)
        if node_property_class is not None:
            node_class_dict["value"] = node_property_class()
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

    def make_object(self, node, ctx, node_element_id_to_object):
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
    """Create and configure the default Neo4jContext with all built-in plugins."""
    ctx = Neo4jContext()

    # Seed caches with pre-built types
    ctx.type_to_node_class = {
        int: Integer,
        str: String,
        float: Float,
        list: List,
        tuple: Tuple,
        set: Set,
        frozenset: FrozenSet,
        bool: Boolean,
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
    ctx.type_to_node_base_property_class = {
        str: neomodel.StringProperty,
        int: neomodel.IntegerProperty,
        float: neomodel.FloatProperty,
        bool: neomodel.BooleanProperty,
    }

    # Register built-in plugins
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


def connect(
    hostname,
    username,
    password,
    protocol="neo4j",
    port="7687",
    notifications_min_severity: typing.Literal["off", "warning", "information"]
    | None = None,
):
    """Connect to a Neo4j database.

    Args:
        hostname: The Neo4j server hostname
        username: The Neo4j username
        password: The Neo4j password
        protocol: The protocol to use (default: "neo4j")
        port: The port to connect to (default: "7687")
        notifications_min_severity: Minimum severity level for notifications

    Returns:
        The Neo4j driver instance
    """
    uri = f"{protocol}://{hostname}:{port}"
    if notifications_min_severity is not None:
        notifications_min_severity = neo4j.NotificationMinimumSeverity[
            notifications_min_severity.upper()
        ]
    driver = neo4j.GraphDatabase().driver(
        uri,
        auth=(username, password),
        notifications_min_severity=notifications_min_severity,
    )
    neomodel.db.set_connection(driver=driver)
    return driver


def delete_all():
    """Delete all nodes and relationships from the database.

    Warning: This permanently deletes all data in the database.
    """
    neomodel.db.cypher_query("MATCH (n) DETACH DELETE n")


def cypher_query(query, params=None, resolve_objects=False, db=neomodel.db):
    """Execute a Cypher query against the Neo4j database.

    Args:
        query: The Cypher query string
        params: Optional query parameters
        resolve_objects: Whether to resolve results as neomodel objects
        db: The database connection to use

    Returns:
        A tuple of (results, meta) where results is a list of rows
    """
    return db.cypher_query(query=query, params=params, resolve_objects=resolve_objects)


def get_or_make_node_class_from_type(
    type_, make_node_classes_recursively=True, guard=None
):
    """Get or create a Neo4j node class for a given Python type.

    This function returns an existing node class if one has already been created
    for the given type, otherwise it creates a new one.

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
    """Convert a Python object to Neo4j nodes.

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

    This wraps the function in a plugin and registers it with the default context.
    The function signature must be:
        function(obj, integration_mode, exclude_from_integration, object_to_node)
            -> (nodes, to_connect)

    Args:
        type_: The Python type to register the function for.
        function: The conversion function.
    """

    class _FunctionPlugin(Neo4jTypePlugin):
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

        def make_object(self, node, ctx, node_element_id_to_object):
            raise NotImplementedError(f"make_object not registered for type {type_}")

    _default_context.register(_FunctionPlugin())


def register_make_object_function(node_class, function):
    """Register a custom node-to-object conversion function for a node class.

    This wraps the function in a plugin and registers it with the default context.
    The function signature must be:
        function(node, node_element_id_to_object) -> object

    Args:
        node_class: The Neo4j node class to register the function for.
        function: The conversion function.
    """

    class _FunctionPlugin(Neo4jTypePlugin):
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

        def make_object(self, node, ctx, node_element_id_to_object):
            return function(node, node_element_id_to_object=node_element_id_to_object)

    _default_context.register(_FunctionPlugin())


def save_from_object(
    object_,
    integration_mode: typing.Literal["hash", "id"] = "id",
    exclude_from_integration=None,
):
    """Save a single object to Neo4j.

    Args:
        object_: The object to save
        integration_mode: How to handle duplicate objects ("hash" or "id")
        exclude_from_integration: Types to exclude from integration logic
    """
    save_from_objects(
        objects=[object_],
        integration_mode=integration_mode,
        exclude_from_integration=exclude_from_integration,
    )


@neomodel.db.transaction
def save_from_objects(
    objects,
    integration_mode: typing.Literal["hash", "id"] = "id",
    exclude_from_integration=None,
):
    """Save multiple objects to Neo4j in a single transaction.

    Args:
        objects: The objects to save
        integration_mode: How to handle duplicate objects ("hash" or "id")
        exclude_from_integration: Types to exclude from integration logic

    Raises:
        ValueError: If a node is not a subclass of BaseNode
    """
    if exclude_from_integration is None:
        exclude_from_integration = tuple()
    object_to_node = {}
    saved_node_ids = set()
    for object_ in objects:
        nodes, to_connect = _default_context.make_nodes_from_object(
            object_, integration_mode, exclude_from_integration, object_to_node
        )
        for node in nodes:
            if id(node) not in saved_node_ids:
                if not isinstance(node, BaseNode):
                    raise ValueError(
                        f"node type {type(node)} must be a subclass of BaseNode"
                    )
                node.save()
                saved_node_ids.add(id(node))
        for (
            source_node,
            source_node_class_attr_name,
            target_node,
            properties,
        ) in to_connect:
            getattr(source_node, source_node_class_attr_name).connect(
                target_node, properties=properties
            )


def make_object_from_node(node, node_element_id_to_object=None):
    """Convert a Neo4j node back to a Python object.

    Args:
        node: The Neo4j node to convert
        node_element_id_to_object: Optional cache mapping node element IDs to objects

    Returns:
        The reconstructed Python object

    Raises:
        ValueError: If the node type cannot be mapped to a Python class
    """
    return _default_context.make_object_from_node(node, node_element_id_to_object)


def cypher_query_as_objects(query, params=None, node_element_id_to_object=None):
    """Execute a Cypher query and convert results to Python objects.

    Args:
        query: The Cypher query string
        params: Optional query parameters
        node_element_id_to_object: Optional cache mapping node element IDs to objects

    Returns:
        A tuple of (object_results, meta) where object_results contains Python objects
    """
    if node_element_id_to_object is None:
        node_element_id_to_object = {}
    object_results = []
    results, meta = cypher_query(query, params=params, resolve_objects=True)
    for row in results:
        row = [
            _default_context.make_object_from_node(
                _, node_element_id_to_object=node_element_id_to_object
            )
            for _ in row
            if isinstance(_, neomodel.StructuredNode)
        ]
        object_results.append(row)
    return object_results, meta
