"""Concrete type conversion plugins for the pylpg backend."""

import types
import typing
import enum
import abc

import fieldz
import frozendict
import pylpg.relationship

import fieldz_kb.typeinfo
import fieldz_kb.lpg.utils
import fieldz_kb.lpg.graph
import fieldz_kb.lpg.core


class BaseTypePlugin(fieldz_kb.lpg.core.PylpgTypePlugin):
    """Handles base types: int, str, float, bool."""

    _handled_types: set[type] = {int, str, float, bool}
    _handled_node_classes: set[type] = {
        fieldz_kb.lpg.graph.Integer,
        fieldz_kb.lpg.graph.String,
        fieldz_kb.lpg.graph.Float,
        fieldz_kb.lpg.graph.Boolean,
    }
    _type_to_node_class: dict[type, type[fieldz_kb.lpg.graph.BaseNode]] = {
        int: fieldz_kb.lpg.graph.Integer,
        str: fieldz_kb.lpg.graph.String,
        float: fieldz_kb.lpg.graph.Float,
        bool: fieldz_kb.lpg.graph.Boolean,
    }

    @classmethod
    def can_handle_type(cls, type_: type) -> bool:
        """Return True if the type is a base type (int, str, float, bool)."""
        return type_ in cls._handled_types

    @classmethod
    def can_handle_node_class(
        cls, node_class: type, ctx: fieldz_kb.lpg.core.PylpgContext
    ) -> bool:
        """Return True if the node class is a base type node class."""
        return node_class in cls._handled_node_classes

    @classmethod
    def make_node_class_from_type(
        cls,
        type_: type,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        make_node_classes_recursively: bool = True,
        guard: set[type] | None = None,
    ) -> type[fieldz_kb.lpg.graph.BaseNode] | None:
        """Return None; base types use pre-built node classes."""
        return None

    @classmethod
    def make_nodes_from_object(
        cls,
        obj: object,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        integration_mode: typing.Literal["hash", "id"],
        exclude_from_integration: tuple[type, ...],
        object_to_node: dict,
    ) -> tuple[
        list[fieldz_kb.lpg.graph.BaseNode], list[pylpg.relationship.Relationship]
    ]:
        """Convert a base type value to a single value node."""
        node_class = cls._type_to_node_class[type(obj)]
        return [node_class(value=obj)], []

    @classmethod
    def make_object_from_node(
        cls,
        node: fieldz_kb.lpg.graph.BaseNode,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        node_id_to_object: dict,
    ) -> object:
        """Extract the value from a base type node."""
        return node.value


class SequencePlugin(fieldz_kb.lpg.core.PylpgTypePlugin):
    """Handles ordered sequences: list, tuple."""

    _handled_types: set[type] = {list, tuple}
    _handled_node_classes: set[type] = {
        fieldz_kb.lpg.graph.List,
        fieldz_kb.lpg.graph.Tuple,
    }
    _type_to_node_class: dict[type, type[fieldz_kb.lpg.graph.BaseNode]] = {
        list: fieldz_kb.lpg.graph.List,
        tuple: fieldz_kb.lpg.graph.Tuple,
    }

    @classmethod
    def can_handle_type(cls, type_: type) -> bool:
        """Return True if the type is a sequence type (list, tuple)."""
        return type_ in cls._handled_types

    @classmethod
    def can_handle_node_class(
        cls, node_class: type, ctx: fieldz_kb.lpg.core.PylpgContext
    ) -> bool:
        """Return True if the node class is a sequence node class."""
        return node_class in cls._handled_node_classes

    @classmethod
    def make_node_class_from_type(
        cls,
        type_: type,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        make_node_classes_recursively: bool = True,
        guard: set[type] | None = None,
    ) -> type[fieldz_kb.lpg.graph.BaseNode] | None:
        """Return None; sequence types use pre-built node classes."""
        return None

    @classmethod
    def make_nodes_from_object(
        cls,
        obj: object,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        integration_mode: typing.Literal["hash", "id"],
        exclude_from_integration: tuple[type, ...],
        object_to_node: dict,
    ) -> tuple[
        list[fieldz_kb.lpg.graph.BaseNode], list[pylpg.relationship.Relationship]
    ]:
        """Convert a sequence to a container node with ordered HAS_ITEM relationships."""
        node_class = cls._type_to_node_class[type(obj)]
        node = node_class()
        nodes = [node]
        relationships = []
        for index, element in enumerate(obj):
            element_nodes, element_relationships = (
                fieldz_kb.lpg.core.make_nodes_from_object(
                    ctx,
                    element,
                    integration_mode=integration_mode,
                    exclude_from_integration=exclude_from_integration,
                    object_to_node=object_to_node,
                )
            )
            element_node = element_nodes[0]
            nodes.append(element_node)
            relationships += element_relationships
            relationships.append(
                fieldz_kb.lpg.graph.HasItem(
                    source=node, target=element_node, order=index
                )
            )
        return nodes, relationships

    @classmethod
    def make_object_from_node(
        cls,
        node: fieldz_kb.lpg.graph.BaseNode,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        node_id_to_object: dict,
    ) -> object:
        """Reconstruct a sequence from a container node."""
        items = node.items.all()
        objects = [
            fieldz_kb.lpg.core.make_object_from_node(ctx, node_item, node_id_to_object)
            for node_item in items
        ]
        sequence_type = ctx.node_class_to_type[type(node)]
        return sequence_type(objects)


class BagPlugin(fieldz_kb.lpg.core.PylpgTypePlugin):
    """Handles unordered collections: set, frozenset."""

    _handled_types: set[type] = {set, frozenset}
    _handled_node_classes: set[type] = {
        fieldz_kb.lpg.graph.Set,
        fieldz_kb.lpg.graph.FrozenSet,
    }
    _type_to_node_class: dict[type, type[fieldz_kb.lpg.graph.BaseNode]] = {
        set: fieldz_kb.lpg.graph.Set,
        frozenset: fieldz_kb.lpg.graph.FrozenSet,
    }

    @classmethod
    def can_handle_type(cls, type_: type) -> bool:
        """Return True if the type is an unordered collection type (set, frozenset)."""
        return type_ in cls._handled_types

    @classmethod
    def can_handle_node_class(
        cls, node_class: type, ctx: fieldz_kb.lpg.core.PylpgContext
    ) -> bool:
        """Return True if the node class is a bag node class."""
        return node_class in cls._handled_node_classes

    @classmethod
    def make_node_class_from_type(
        cls,
        type_: type,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        make_node_classes_recursively: bool = True,
        guard: set[type] | None = None,
    ) -> type[fieldz_kb.lpg.graph.BaseNode] | None:
        """Return None; bag types use pre-built node classes."""
        return None

    @classmethod
    def make_nodes_from_object(
        cls,
        obj: object,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        integration_mode: typing.Literal["hash", "id"],
        exclude_from_integration: tuple[type, ...],
        object_to_node: dict,
    ) -> tuple[
        list[fieldz_kb.lpg.graph.BaseNode], list[pylpg.relationship.Relationship]
    ]:
        """Convert a set/frozenset to a container node with unordered HAS_ITEM relationships."""
        node_class = cls._type_to_node_class[type(obj)]
        node = node_class()
        nodes = [node]
        relationships = []
        for element in obj:
            element_nodes, element_relationships = (
                fieldz_kb.lpg.core.make_nodes_from_object(
                    ctx,
                    element,
                    integration_mode=integration_mode,
                    exclude_from_integration=exclude_from_integration,
                    object_to_node=object_to_node,
                )
            )
            element_node = element_nodes[0]
            nodes.append(element_node)
            relationships += element_relationships
            relationships.append(
                fieldz_kb.lpg.graph.HasItem(source=node, target=element_node)
            )
        return nodes, relationships

    @classmethod
    def make_object_from_node(
        cls,
        node: fieldz_kb.lpg.graph.BaseNode,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        node_id_to_object: dict,
    ) -> object:
        """Reconstruct a set/frozenset from a container node."""
        items = node.items.all()
        objects = [
            fieldz_kb.lpg.core.make_object_from_node(ctx, node_item, node_id_to_object)
            for node_item in items
        ]
        bag_type = ctx.node_class_to_type[type(node)]
        return bag_type(objects)


class DictPlugin(fieldz_kb.lpg.core.PylpgTypePlugin):
    """Handles mapping types: dict, frozendict."""

    _handled_types: set[type] = {dict, frozendict.frozendict}
    _handled_node_classes: set[type] = {
        fieldz_kb.lpg.graph.Dict,
        fieldz_kb.lpg.graph.FrozenDict,
    }
    _type_to_node_class: dict[type, type[fieldz_kb.lpg.graph.BaseNode]] = {
        dict: fieldz_kb.lpg.graph.Dict,
        frozendict.frozendict: fieldz_kb.lpg.graph.FrozenDict,
    }

    @classmethod
    def can_handle_type(cls, type_: type) -> bool:
        """Return True if the type is a mapping type (dict, frozendict)."""
        return type_ in cls._handled_types

    @classmethod
    def can_handle_node_class(
        cls, node_class: type, ctx: fieldz_kb.lpg.core.PylpgContext
    ) -> bool:
        """Return True if the node class is a mapping node class."""
        return node_class in cls._handled_node_classes

    @classmethod
    def make_node_class_from_type(
        cls,
        type_: type,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        make_node_classes_recursively: bool = True,
        guard: set[type] | None = None,
    ) -> type[fieldz_kb.lpg.graph.BaseNode] | None:
        """Return None; mapping types use pre-built node classes."""
        return None

    @classmethod
    def _make_nodes_from_dict_item(
        cls,
        key: object,
        value: object,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        integration_mode: typing.Literal["hash", "id"],
        exclude_from_integration: tuple[type, ...],
        object_to_node: dict,
    ) -> tuple[
        list[fieldz_kb.lpg.graph.BaseNode], list[pylpg.relationship.Relationship]
    ]:
        """Convert a single key-value pair to an Item node with HAS_KEY/HAS_VALUE relationships."""
        node = fieldz_kb.lpg.graph.Item()
        nodes = [node]
        relationships = []
        key_nodes, key_relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            ctx,
            key,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        nodes += key_nodes
        relationships += key_relationships
        key_node = key_nodes[0]
        relationships.append(
            fieldz_kb.lpg.graph.HasKey(source=node, target=key_node)
        )
        value_nodes, value_relationships = fieldz_kb.lpg.core.make_nodes_from_object(
            ctx,
            value,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        nodes += value_nodes
        relationships += value_relationships
        value_node = value_nodes[0]
        relationships.append(
            fieldz_kb.lpg.graph.HasValue(source=node, target=value_node)
        )
        return nodes, relationships

    @classmethod
    def make_nodes_from_object(
        cls,
        obj: object,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        integration_mode: typing.Literal["hash", "id"],
        exclude_from_integration: tuple[type, ...],
        object_to_node: dict,
    ) -> tuple[
        list[fieldz_kb.lpg.graph.BaseNode], list[pylpg.relationship.Relationship]
    ]:
        """Convert a dict/frozendict to a Mapping node with Item sub-nodes."""
        node_class = cls._type_to_node_class[type(obj)]
        node = node_class()
        nodes = [node]
        relationships = []
        for key, value in obj.items():
            item_nodes, item_relationships = cls._make_nodes_from_dict_item(
                key,
                value,
                ctx,
                integration_mode=integration_mode,
                exclude_from_integration=exclude_from_integration,
                object_to_node=object_to_node,
            )
            nodes += item_nodes
            relationships += item_relationships
            item_node = item_nodes[0]
            relationships.append(
                fieldz_kb.lpg.graph.HasItem(source=node, target=item_node)
            )
        return nodes, relationships

    @classmethod
    def make_object_from_node(
        cls,
        node: fieldz_kb.lpg.graph.BaseNode,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        node_id_to_object: dict,
    ) -> object:
        """Reconstruct a dict/frozendict from a Mapping node."""
        node_class = type(node)
        if node_class is fieldz_kb.lpg.graph.Dict:
            dict_object = {}
            for item_node in node.items.all():
                key_nodes = item_node.key.all()
                value_nodes = item_node.value.all()
                key = fieldz_kb.lpg.core.make_object_from_node(
                    ctx, key_nodes[0], node_id_to_object
                )
                value = fieldz_kb.lpg.core.make_object_from_node(
                    ctx, value_nodes[0], node_id_to_object
                )
                dict_object[key] = value
            return dict_object
        else:
            objects = [
                fieldz_kb.lpg.core.make_object_from_node(
                    ctx, item_node, node_id_to_object
                )
                for item_node in node.items.all()
            ]
            return ctx.node_class_to_type[node_class](objects)


class FieldzClassPlugin(fieldz_kb.lpg.core.PylpgTypePlugin):
    """Handles fieldz dataclass-like types."""

    @classmethod
    def can_handle_type(cls, type_: type) -> bool:
        """Return True if the type is a fieldz class."""
        return fieldz_kb.typeinfo.is_fieldz_class(type_)

    @classmethod
    def can_handle_node_class(
        cls, node_class: type, ctx: fieldz_kb.lpg.core.PylpgContext
    ) -> bool:
        """Return True if the node class maps to a fieldz class."""
        type_ = ctx.node_class_to_type.get(node_class)
        if type_ is None:
            return False
        return fieldz_kb.typeinfo.is_fieldz_class(type_)

    @classmethod
    def _make_node_property_from_field(
        cls,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        field: fieldz.Field,
        module: str | None = None,
        make_node_classes_recursively: bool = True,
        guard: set[type] | None = None,
    ) -> dict:
        """Determine the property type for a dataclass field.

        Returns a dict describing how the field should be represented:
        - {"kind": "primitive", "type": <type>} for primitive type annotations
        - {"kind": "array", "type": <type>, "item_type": <type>} for array properties
        - {"kind": "relationship", "relationship_class": <class>,
           "descriptor": <RelationshipTo>, "many": bool, "ordered": bool}
           for relationships

        Args:
            ctx: The plugin registry and cache.
            field: The fieldz field descriptor.
            module: Module name for resolving forward references.
            make_node_classes_recursively: Whether to create node classes for nested types.
            guard: Guard set for recursion prevention.

        Returns:
            A dict describing the field representation.
        """
        if guard is None:
            guard = set()
        all_types = fieldz_kb.typeinfo.get_types_from_type_hint(
            field.type, module=module
        )
        non_none_types = tuple(
            type_ for type_ in all_types if type_[0] is not types.NoneType
        )
        optional = len(non_none_types) < len(all_types)
        candidates = {
            fieldz_kb.lpg.utils.get_type_attributes(type_)
            for type_ in non_none_types
        }
        kinds = {candidate.kind for candidate in candidates}
        target_type_sets = {candidate.target_types for candidate in candidates}
        if kinds == {"primitive"} and len(target_type_sets) == 1:
            target_types = next(iter(target_type_sets))
            target_type_origin = next(iter(target_types))[0]
            return {
                "kind": "primitive",
                "type": target_type_origin,
                "optional": optional,
            }
        if kinds == {"array"} and len(target_type_sets) == 1:
            target_types = next(iter(target_type_sets))
            target_type_origin = next(iter(target_types))[0]
            return {
                "kind": "array",
                "type": list,
                "item_type": target_type_origin,
                "optional": optional,
            }
        many = any(candidate.many for candidate in candidates)
        ordered = any(candidate.ordered for candidate in candidates)
        relationship_type = (
            fieldz_kb.lpg.utils.make_relationship_type_from_field_name(
                field.name, many
            )
        )
        if ordered:
            relationship_class = type(
                f"Ordered{relationship_type}",
                (pylpg.relationship.Relationship,),
                {
                    "__type__": relationship_type,
                    "__annotations__": {"order": int | None},
                    "order": None,
                },
            )
        else:
            relationship_class = type(
                f"Unordered{relationship_type}",
                (pylpg.relationship.Relationship,),
                {"__type__": relationship_type},
            )
        descriptor = pylpg.relationship.RelationshipTo(relationship_class)
        if make_node_classes_recursively:
            for candidate in candidates:
                for target_type in candidate.target_types:
                    target_type_origin = target_type[0]
                    if target_type_origin not in guard:
                        fieldz_kb.lpg.core.get_or_make_node_class_from_type(
                            ctx,
                            target_type_origin,
                            make_node_classes_recursively=make_node_classes_recursively,
                            guard=guard,
                        )
        return {
            "kind": "relationship",
            "relationship_class": relationship_class,
            "descriptor": descriptor,
            "many": many,
            "ordered": ordered,
            "optional": optional,
        }

    @classmethod
    def make_node_class_from_type(
        cls,
        type_: type,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        make_node_classes_recursively: bool = True,
        guard: set[type] | None = None,
    ) -> type[fieldz_kb.lpg.graph.BaseNode] | None:
        """Dynamically create a node class mirroring the fieldz class structure."""
        if guard is None:
            guard = set()
        node_class_name = fieldz_kb.lpg.utils.make_node_class_name_from_type(type_)
        fieldz_class_bases = type_.__bases__
        node_class_bases = tuple(
            [
                fieldz_kb.lpg.core.get_or_make_node_class_from_type(
                    ctx,
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
            node_class_bases = (fieldz_kb.lpg.graph.BaseNode,)
        node_class_dict = {}
        node_class_annotations = {}
        for field in fieldz.fields(type_):
            field_info = cls._make_node_property_from_field(
                ctx,
                field,
                module=type_.__module__,
                make_node_classes_recursively=make_node_classes_recursively,
                guard=guard,
            )
            if field_info["kind"] == "primitive":
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

    @classmethod
    def make_nodes_from_object(
        cls,
        obj: object,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        integration_mode: typing.Literal["hash", "id"],
        exclude_from_integration: tuple[type, ...],
        object_to_node: dict,
    ) -> tuple[
        list[fieldz_kb.lpg.graph.BaseNode], list[pylpg.relationship.Relationship]
    ]:
        """Convert a fieldz object to nodes and relationships."""
        nodes = []
        relationships = []
        fieldz_class = type(obj)
        node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            ctx, fieldz_class, make_node_classes_recursively=False
        )
        node = node_class()
        nodes.append(node)
        for field in fieldz.fields(fieldz_class):
            field_value = getattr(obj, field.name)
            if field_value is not None:
                field_info = getattr(node_class, f"_field_info_{field.name}", None)
                if field_info is None:
                    if isinstance(field_value, fieldz_kb.lpg.utils.ARRAY_TYPES):
                        setattr(node, field.name, list(field_value))
                    else:
                        setattr(node, field.name, field_value)
                else:
                    relationship_class = field_info["relationship_class"]
                    add_order = field_info["ordered"]
                    if not isinstance(field_value, fieldz_kb.lpg.utils.ARRAY_TYPES):
                        field_value = [field_value]
                    for index, field_value_element in enumerate(field_value):
                        sub_nodes, sub_relationships = (
                            fieldz_kb.lpg.core.make_nodes_from_object(
                                ctx,
                                field_value_element,
                                integration_mode,
                                exclude_from_integration,
                                object_to_node,
                            )
                        )
                        nodes += sub_nodes
                        relationships += sub_relationships
                        properties = {"order": index} if add_order else {}
                        relationships.append(
                            relationship_class(
                                source=node, target=sub_nodes[0], **properties
                            )
                        )
        return nodes, relationships

    @classmethod
    def make_object_from_node(
        cls,
        node: fieldz_kb.lpg.graph.BaseNode,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        node_id_to_object: dict,
    ) -> object:
        """Reconstruct a fieldz object from a node and its relationships."""
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
                    array_type = fieldz_kb.lpg.utils.get_array_type_from_field(
                        field, module=fieldz_class.__module__
                    )
                    field_value = array_type(node_attr_value)
                else:
                    field_value = node_attr_value
            else:
                bound_relationship = getattr(node, field.name)
                many = field_info["many"]
                if many:
                    related_nodes = bound_relationship.all()
                    if not related_nodes and field.default is None:
                        field_value = None
                    else:
                        array_type = fieldz_kb.lpg.utils.get_array_type_from_field(
                            field, module=fieldz_class.__module__
                        )
                        field_value = array_type(
                            [
                                fieldz_kb.lpg.core.make_object_from_node(
                                    ctx,
                                    element,
                                    node_id_to_object=node_id_to_object,
                                )
                                for element in related_nodes
                            ]
                        )
                else:
                    related_nodes = bound_relationship.all()
                    if related_nodes:
                        field_value = fieldz_kb.lpg.core.make_object_from_node(
                            ctx,
                            related_nodes[0],
                            node_id_to_object=node_id_to_object,
                        )
                    else:
                        field_value = None
            fieldz_object_attr_values[field.name] = field_value
        fieldz_object = fieldz_class(**fieldz_object_attr_values)
        return fieldz_object


class EnumPlugin(fieldz_kb.lpg.core.PylpgTypePlugin):
    """Handles enum types."""

    @classmethod
    def can_handle_type(cls, type_: type) -> bool:
        """Return True if the type is an enum subclass."""
        return issubclass(type_, enum.Enum)

    @classmethod
    def can_handle_node_class(
        cls, node_class: type, ctx: fieldz_kb.lpg.core.PylpgContext
    ) -> bool:
        """Return True if the node class maps to an enum type."""
        type_ = ctx.node_class_to_type.get(node_class)
        if type_ is None:
            return False
        return issubclass(type_, enum.Enum)

    @classmethod
    def make_node_class_from_type(
        cls,
        type_: type,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        make_node_classes_recursively: bool = True,
        guard: set[type] | None = None,
    ) -> type[fieldz_kb.lpg.graph.BaseNode] | None:
        """Dynamically create a node class with name and value properties for an enum."""
        node_class_name = fieldz_kb.lpg.utils.make_node_class_name_from_type(type_)
        node_class_bases = (fieldz_kb.lpg.graph.BaseNode,)
        node_class_annotations = {"name": str | None}
        item_value_types = set([type(item.value) for item in type_])
        if len(item_value_types) != 1:
            raise ValueError(
                f"enum of type {type_} not supported: types of values must all be the same"
            )
        item_value_type = next(iter(item_value_types))
        if item_value_type in fieldz_kb.lpg.utils.BASE_TYPES:
            node_class_annotations["value"] = item_value_type | None
        node_class_dict = {
            "__annotations__": node_class_annotations,
            "name": None,
            "value": None,
        }
        node_class = type(node_class_name, node_class_bases, node_class_dict)
        return node_class

    @classmethod
    def make_nodes_from_object(
        cls,
        obj: object,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        integration_mode: typing.Literal["hash", "id"],
        exclude_from_integration: tuple[type, ...],
        object_to_node: dict,
    ) -> tuple[
        list[fieldz_kb.lpg.graph.BaseNode], list[pylpg.relationship.Relationship]
    ]:
        """Convert an enum member to a node with name and value properties."""
        enum_class = type(obj)
        node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(ctx, enum_class)
        node = node_class()
        node.name = obj.name
        node.value = obj.value
        return [node], []

    @classmethod
    def make_object_from_node(
        cls,
        node: fieldz_kb.lpg.graph.BaseNode,
        ctx: fieldz_kb.lpg.core.PylpgContext,
        node_id_to_object: dict,
    ) -> object:
        """Reconstruct an enum member from a node."""
        node_class = type(node)
        enum_class = ctx.node_class_to_type.get(node_class)
        if enum_class is None:
            raise ValueError(
                f"could not find an appropriate class for node class {node_class}"
            )
        return getattr(enum_class, node.name)
