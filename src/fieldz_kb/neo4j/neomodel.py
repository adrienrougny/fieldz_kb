import types
import typing
import re
import collections.abc
import enum

import fieldz
import inflect
import neomodel

import fieldz_kb.typeinfo


base_types = (int, str, float, bool)
array_types = (list, tuple, set, frozenset)
ordered_array_types = (list, tuple)


class OrderedRelationshipTo(neomodel.StructuredRel):
    order = neomodel.IntegerProperty()


class UnorderedRelationshipTo(neomodel.StructuredRel):
    pass


class BaseNode(neomodel.StructuredNode):
    pass


class Integer(BaseNode):
    value: neomodel.IntegerProperty(required=True)


_type_to_node_class = {}
type_to_node_base_property_class = {
    str: neomodel.StringProperty,
    int: neomodel.IntegerProperty,
    float: neomodel.FloatProperty,
    bool: neomodel.BooleanProperty,
}


def connect(uri, user, password):
    neomodel.config.DATABASE_URL = f"bolt://{user}:{password}@{uri}"


def delete_all():
    neomodel.db.cypher_query("MATCH (n) DETACH DELETE n")


def _make_node_class_name_from_class(fieldz_class):
    return fieldz_class.__name__


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


def _make_node_property_from_field(field, module=None):
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
            node_property_class = type_to_node_base_property_class[target_type]
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
        base_node_property_class = type_to_node_base_property_class[target_type]
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
        relationship_type = _make_relationship_type_from_field_name(field.name, many)
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
    return node_property


def _get_node_property_attributes_from_type(type_):
    type_origin, type_args = type_
    type_args = frozenset(type_args)
    if issubclass(type_origin, base_types):  # base type, we ignore subtypes
        property_type = "base"
        ordered = False
        many = False
        target_types = frozenset([type_])
    elif issubclass(type_origin, array_types):  # array type
        many = True
        if issubclass(type_origin, ordered_array_types):
            ordered = True
        else:
            ordered = False
        if len(type_args) == 1:  # one subtype
            type_arg = next(iter(type_args))
            type_arg_origin = type_arg[0]
            if issubclass(type_arg_origin, base_types):  # subtype is base type
                property_type = "array"
            else:  # subtype is not base type, must be a relationship
                property_type = "relationship"
        else:  # no subtype (Any) or more than one subtype, must be a relationship
            property_type = "relationship"
        target_types = frozenset(type_args)
    elif fieldz_kb.typeinfo.is_fieldz_class(type_origin) or issubclass(
        type_origin, enum.Enum
    ):
        many = False
        ordered = False
        property_type = "relationship"
        target_types = frozenset([type_])
    elif type_origin.__name__ == "NoneValueType":  # TO DELETE
        many = False
        ordered = False
        property_type = "relationship"
        target_types = frozenset([(str, ())])
    else:
        raise ValueError(f"type {type_} not supported")
    return (
        property_type,
        target_types,
        many,
        ordered,
    )


def _get_or_make_node_class_from_class(type_):
    node_class = _type_to_node_class.get(type_)
    if node_class is None:
        node_class = _make_node_class_from_class(type_)
    return node_class


def _make_node_class_from_class(class_):
    node_class = None
    if fieldz_kb.typeinfo.is_fieldz_class(class_):
        node_class = _make_node_class_from_fieldz_class(class_)
    elif issubclass(class_, enum.Enum):
        node_class = _make_node_class_from_enum_class(class_)
    return node_class


def _make_node_class_from_fieldz_class(fieldz_class):
    node_class_name = _make_node_class_name_from_class(fieldz_class)
    node_class_bases = (BaseNode,)
    node_class_dict = {}
    for field in fieldz.fields(fieldz_class):
        node_property = _make_node_property_from_field(
            field, module=fieldz_class.__module__
        )
        node_class_dict[field.name] = node_property
    node_class = type(node_class_name, node_class_bases, node_class_dict)
    _type_to_node_class[fieldz_class] = node_class
    return node_class


def _make_node_class_from_enum_class(enum_class):
    node_class_name = _make_node_class_name_from_class(enum_class)
    node_class_bases = (BaseNode,)
    node_class_dict = {"name": neomodel.StringProperty()}
    item_value_types = set([type(item.value) for item in enum_class])
    if len(item_value_types) != 1:
        raise ValueError(
            f"enum of type {enum_class} not supported: types of values must all be the same"
        )
    item_value_type = next(iter(item_value_types))
    node_property_class = type_to_node_base_property_class.get(item_value_type)
    if node_property_class is not None:
        node_class_dict["value"] = node_property_class()
    node_class = type(node_class_name, node_class_bases, node_class_dict)
    _type_to_node_class[enum_class] = node_class
    return node_class


def _save_node_from_fieldz_object(
    fieldz_object, integration_mode, object_to_node, exclude_from_integration
) -> neomodel.StructuredNode:
    fieldz_class = type(fieldz_object)
    node_class = _get_or_make_node_class_from_class(fieldz_class)
    node = node_class()
    nodes_to_connect = []
    for field in fieldz.fields(fieldz_class):
        field_value = getattr(fieldz_object, field.name)
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
                if not isinstance(field_value, array_types):
                    field_value = [field_value]
                for index, field_value_element in enumerate(field_value):
                    if add_order:
                        order = index
                    else:
                        order = None
                    node_element = save_node_from_object(
                        field_value_element,
                        integration_mode=integration_mode,
                        object_to_node=object_to_node,
                        exclude_from_integration=exclude_from_integration,
                    )
                    nodes_to_connect.append((node_element, field.name, order))
    node.save()
    for node_to_connect, node_class_attr_name, order in nodes_to_connect:
        if order is not None:
            properties = {"order": order}
        else:
            properties = None
        getattr(node, node_class_attr_name).connect(
            node_to_connect, properties=properties
        )
    return node


def _save_node_from_enum_object(
    enum_object, integration_mode, object_to_node, exclude_from_integration
):
    enum_class = type(enum_object)
    node_class = _get_or_make_node_class_from_class(enum_class)
    node = node_class()
    node.name = enum_object.name
    node.value = enum_object.value
    node.save()
    return node


def _save_node_from_int_object(
    int_object, integration_mode, object_to_node, exclude_from_integration
):
    node = Integer(value=int_object)
    node.save()
    return node


_type_to_save_node_function = {
    int: _save_node_from_int_object,
}


def register_save_node_function(type_, function):
    _type_to_save_node_function[type_] = function


def save_node_from_object(
    object_,
    integration_mode: typing.Literal["hash", "id"] | None = None,
    object_to_node=None,
    exclude_from_integration=None,
):
    if object_to_node is None:
        object_to_node = {}
    if exclude_from_integration is None:
        exclude_from_integration = tuple([])
    if integration_mode is not None and not isinstance(
        object_, tuple(exclude_from_integration)
    ):
        if integration_mode == "hash":
            if not isinstance(object_, collections.abc.Hashable):
                raise ValueError(
                    f"object of type {type(object_)} not hashable, cannot use hash integration mode"
                )
            node = object_to_node.get(object_)
        elif integration_mode == "id":
            node = object_to_node.get(id(object_))
        if node is not None:
            return node
    class_ = type(object_)
    save_node_function = _type_to_save_node_function.get(class_)
    if save_node_function is None:  # we use the pre-built save functions
        if fieldz_kb.typeinfo.is_fieldz_class(class_):
            save_node_function = _save_node_from_fieldz_object
        elif issubclass(class_, enum.Enum):
            save_node_function = _save_node_from_enum_object
        else:
            raise ValueError(f"object of type {class_} not supported")
    node = save_node_function(
        object_, integration_mode, object_to_node, exclude_from_integration
    )
    if not isinstance(node, BaseNode):
        raise ValueError(
            f"custom node type {type(node)} must be a subclass of BaseNode"
        )
    if class_ not in _type_to_node_class:
        _type_to_node_class[class_] = type(node)
    if integration_mode == "hash":
        object_to_node[object_] = node
    elif integration_mode == "id":
        object_to_node[id(object_)] = node
    return node
