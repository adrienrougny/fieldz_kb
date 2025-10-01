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


_base_types = (int, str, float, bool)
_array_types = (list, tuple, set, frozenset)
_ordered_array_types = (list, tuple)


class OrderedRelationshipTo(neomodel.StructuredRel):
    order = neomodel.IntegerProperty()


class UnorderedRelationshipTo(neomodel.StructuredRel):
    pass


class BaseNode(neomodel.StructuredNode):
    pass


class Integer(BaseNode):
    value = neomodel.IntegerProperty(required=True)


class String(BaseNode):
    value = neomodel.StringProperty(required=True)


class Float(BaseNode):
    value = neomodel.FloatProperty(required=True)


class Boolean(BaseNode):
    value = neomodel.BooleanProperty(required=True)


class Item(BaseNode):
    key = neomodel.RelationshipTo(BaseNode, "HAS_KEY", neomodel.One)
    value = neomodel.RelationshipTo(BaseNode, "HAS_VALUE", neomodel.One)


class Mapping(BaseNode):
    items = neomodel.RelationshipTo(
        Item, "HAS_ITEM", neomodel.ZeroOrMore, model=OrderedRelationshipTo
    )


class Dict(Mapping):
    pass


class FrozenDict(Mapping):
    pass


class Bag(BaseNode):
    items = neomodel.RelationshipTo(
        BaseNode, "HAS_ITEM", neomodel.ZeroOrMore, model=OrderedRelationshipTo
    )


class Set(Bag):
    pass


class FrozenSet(Bag):
    pass


class Sequence(BaseNode):
    items = neomodel.RelationshipTo(
        BaseNode,
        "HAS_ITEM",
        neomodel.ZeroOrMore,
        model=OrderedRelationshipTo,
    )


class List(Sequence):
    pass


class Tuple(Sequence):
    pass


_type_to_node_class = {
    int: Integer,
    str: String,
    float: Float,
    list: List,
    tuple: Tuple,
    set: Set,
    frozenset: FrozenSet,
    bool: Boolean,
}
_node_class_to_type = {
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
_type_to_node_base_property_class = {
    str: neomodel.StringProperty,
    int: neomodel.IntegerProperty,
    float: neomodel.FloatProperty,
    bool: neomodel.BooleanProperty,
}


def connect(
    hostname,
    username,
    password,
    protocol="neo4j",
    port="7687",
    notifications_min_severity: typing.Literal["off", "warning", "information"]
    | None = None,
):
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
    cypher_query("RETURN 1")  # return an error if not connected


def delete_all():
    neomodel.db.cypher_query("MATCH (n) DETACH DELETE n")


def cypher_query(query, params=None, resolve_objects=True):
    return neomodel.db.cypher_query(
        query=query, params=params, resolve_objects=resolve_objects
    )


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


def _make_node_property_from_field(
    field, module=None, make_node_classes_recursively=True, guard=None
):
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
            node_property_class = _type_to_node_base_property_class[target_type]
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
        base_node_property_class = _type_to_node_base_property_class[target_type]
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
        if make_node_classes_recursively:
            for node_property_attributes in node_property_attributes_candidates:
                for target_type in node_property_attributes[1]:
                    target_type_origin = target_type[0]
                    if target_type_origin not in guard:
                        get_or_make_node_class_from_type(
                            target_type_origin,
                            make_node_classes_recursively=make_node_classes_recursively,
                            guard=guard,
                        )
    return node_property


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


def get_or_make_node_class_from_type(
    type_, make_node_classes_recursively=True, guard=None
):
    if guard is None:
        guard = set([])
    node_class = _type_to_node_class.get(type_)
    if node_class is None:
        guard.add(type_)
        node_class = _make_node_class_from_type(
            type_,
            make_node_classes_recursively=make_node_classes_recursively,
            guard=guard,
        )
        _type_to_node_class[type_] = node_class
        _node_class_to_type[node_class] = type_
    return node_class


def _make_node_class_from_type(type_, make_node_classes_recursively=True, guard=None):
    if guard is None:
        guard = []
    if fieldz_kb.typeinfo.is_fieldz_class(type_):
        node_class = _make_node_class_from_fieldz_class(
            type_,
            make_node_classes_recursively=make_node_classes_recursively,
            guard=guard,
        )
    elif issubclass(type_, enum.Enum):
        node_class = _make_node_class_from_enum_class(type_)
    else:
        raise ValueError(f"type {type_} not supported")
    return node_class


def _make_node_class_from_fieldz_class(
    fieldz_class, make_node_classes_recursively=True, guard=None
):
    if guard is None:
        guard = []
    node_class_name = _make_node_class_name_from_type(fieldz_class)
    fieldz_class_bases = fieldz_class.__bases__
    node_class_bases = tuple(
        [
            get_or_make_node_class_from_type(
                base_class,
                make_node_classes_recursively=make_node_classes_recursively,
                guard=guard,
            )
            for base_class in fieldz_class_bases
            if base_class not in (object, abc.ABC)
            and not base_class.__name__.startswith("_")
            and base_class.__name__ != fieldz_class.__name__
        ]
    )
    if not node_class_bases:
        node_class_bases = (BaseNode,)
    node_class_dict = {}
    for field in fieldz.fields(fieldz_class):
        node_property = _make_node_property_from_field(
            field,
            module=fieldz_class.__module__,
            make_node_classes_recursively=make_node_classes_recursively,
            guard=guard,
        )
        node_class_dict[field.name] = node_property
    node_class = type(node_class_name, node_class_bases, node_class_dict)
    return node_class


def _make_node_class_from_enum_class(enum_class):
    node_class_name = _make_node_class_name_from_type(enum_class)
    node_class_bases = (BaseNode,)
    node_class_dict = {"name": neomodel.StringProperty()}
    item_value_types = set([type(item.value) for item in enum_class])
    if len(item_value_types) != 1:
        raise ValueError(
            f"enum of type {enum_class} not supported: types of values must all be the same"
        )
    item_value_type = next(iter(item_value_types))
    node_property_class = _type_to_node_base_property_class.get(item_value_type)
    if node_property_class is not None:
        node_class_dict["value"] = node_property_class()
    node_class = type(node_class_name, node_class_bases, node_class_dict)
    return node_class


def _make_nodes_from_fieldz_object(
    fieldz_object, integration_mode, exclude_from_integration, object_to_node
):
    nodes = []
    to_connect = []
    fieldz_class = type(fieldz_object)
    node_class = get_or_make_node_class_from_type(
        fieldz_class, make_node_classes_recursively=False
    )
    node = node_class()
    nodes.append(node)
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
                if not isinstance(field_value, _array_types):
                    field_value = [field_value]
                for index, field_value_element in enumerate(field_value):
                    sub_nodes, sub_to_connect = make_nodes_from_object(
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


def _make_nodes_from_enum_object(
    enum_object, integration_mode, exclude_from_integration, object_to_node
):
    enum_class = type(enum_object)
    node_class = get_or_make_node_class_from_type(enum_class)
    node = node_class()
    node.name = enum_object.name
    node.value = enum_object.value
    return [node], []


def _make_nodes_from_int_object(
    int_object, integration_mode, exclude_from_integration, object_to_node
):
    node = Integer(value=int_object)
    return [node], []


def _make_nodes_from_string_object(
    string_object, integration_mode, exclude_from_integration, object_to_node
):
    node = String(value=string_object)
    return [node], []


def _make_nodes_from_float_object(
    float_object, integration_mode, exclude_from_integration, object_to_node
):
    node = Float(value=float_object)
    return [node], []


def _make_nodes_from_bool_object(
    bool_object, integration_mode, exclude_from_integration, object_to_node
):
    node = Boolean(value=bool_object)
    return [node], []


def _make_nodes_from_dict_item(
    key, value, integration_mode, exclude_from_integration, object_to_node
):
    node = Item()
    nodes = [node]
    to_connect = []
    nodes_key, to_connect_key = make_nodes_from_object(
        key,
        integration_mode=integration_mode,
        exclude_from_integration=exclude_from_integration,
        object_to_node=object_to_node,
    )
    nodes += nodes_key
    to_connect += to_connect_key
    node_key = nodes_key[0]
    to_connect.append((node, "key", node_key, {}))
    nodes_value, to_connect_value = make_nodes_from_object(
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


def _make_nodes_from_dict_object(
    dict_object, integration_mode, exclude_from_integration, object_to_node
):
    node = Dict()
    nodes = [node]
    to_connect = []
    for key, value in dict_object.items():
        nodes_item, to_connect_item = _make_nodes_from_dict_item(
            key,
            value,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        nodes += nodes_item
        to_connect += to_connect_item
        node_item = nodes_item[0]
        to_connect.append((node, "items", node_item, {}))
    return nodes, to_connect


def _make_nodes_from_frozendict_object(
    dict_object, integration_mode, exclude_from_integration, object_to_node
):
    node = FrozenDict()
    nodes = [node]
    to_connect = []
    for key, value in dict_object.items():
        nodes_item, to_connect_item = _make_nodes_from_dict_item(
            key,
            value,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        nodes += nodes_item
        to_connect += to_connect_item
        node_item = nodes_item[0]
        to_connect.append((node, "items", node_item, {}))
    return nodes, to_connect


def _make_nodes_from_set_object(
    set_object, integration_mode, exclude_from_integration, object_to_node
):
    to_connect = []
    node = Set()
    nodes = [node]
    for element in set_object:
        nodes_element, to_connect_element = make_nodes_from_object(
            element,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        node_element = nodes_element[0]
        nodes.append(node_element)
        to_connect.append((node, "items", node_element, {}))
    return nodes, to_connect


def _make_nodes_from_frozenset_object(
    set_object, integration_mode, exclude_from_integration, object_to_node
):
    to_connect = []
    node = FrozenSet()
    nodes = [node]
    for element in set_object:
        nodes_element, to_connect_element = make_nodes_from_object(
            element,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        node_element = nodes_element[0]
        nodes.append(node_element)
        to_connect.append((node, "items", node_element, {}))
    return nodes, to_connect


def _make_nodes_from_list_object(
    list_object, integration_mode, exclude_from_integration, object_to_node
):
    to_connect = []
    node = List()
    nodes = [node]
    for index, element in enumerate(list_object):
        nodes_element, to_connect_element = make_nodes_from_object(
            element,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        node_element = nodes_element[0]
        nodes.append(node_element)
        to_connect.append((node, "items", node_element, {"order": index}))
    return nodes, to_connect


def _make_nodes_from_tuple_object(
    list_object, integration_mode, exclude_from_integration, object_to_node
):
    to_connect = []
    node = Tuple()
    nodes = [node]
    for index, element in enumerate(list_object):
        nodes_element, to_connect_element = make_nodes_from_object(
            element,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
            object_to_node=object_to_node,
        )
        node_element = nodes_element[0]
        nodes.append(node_element)
        to_connect.append((node, "items", node_element, {"order": index}))
    return nodes, to_connect


_type_to_make_nodes_function = {
    int: _make_nodes_from_int_object,
    str: _make_nodes_from_string_object,
    float: _make_nodes_from_float_object,
    bool: _make_nodes_from_bool_object,
    dict: _make_nodes_from_dict_object,
    frozendict.frozendict: _make_nodes_from_frozendict_object,
    set: _make_nodes_from_set_object,
    frozenset: _make_nodes_from_frozenset_object,
    list: _make_nodes_from_list_object,
    tuple: _make_nodes_from_tuple_object,
}


def register_make_nodes_function(type_, function):
    _type_to_make_nodes_function[type_] = function


def make_nodes_from_object(
    object_,
    integration_mode: typing.Literal["hash", "id"] | None = None,
    exclude_from_integration=None,
    object_to_node=None,
):
    if exclude_from_integration is None:
        exclude_from_integration = tuple()
    if object_to_node is None:
        object_to_node = {}
    if integration_mode is not None and not isinstance(
        object_, exclude_from_integration
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
            return [node], []
    class_ = type(object_)
    make_nodes_function = _type_to_make_nodes_function.get(class_)
    if make_nodes_function is None:  # we use the pre-built save functions
        if fieldz_kb.typeinfo.is_fieldz_class(class_):
            make_nodes_function = _make_nodes_from_fieldz_object
        elif issubclass(class_, enum.Enum):
            make_nodes_function = _make_nodes_from_enum_object
        else:
            raise ValueError(f"object of type {class_} not supported")
    nodes, to_connect = make_nodes_function(
        object_,
        integration_mode=integration_mode,
        exclude_from_integration=exclude_from_integration,
        object_to_node=object_to_node,
    )
    node_class = type(nodes[0])
    if type(object_) not in _type_to_node_class:
        _type_to_node_class[class_] = node_class
    if node_class not in _node_class_to_type:
        _node_class_to_type[node_class] = class_
    if integration_mode == "hash":
        object_to_node[object_] = nodes[0]
    elif integration_mode == "id":
        object_to_node[id(object_)] = nodes[0]
    return nodes, to_connect


@neomodel.db.transaction
def save_from_object(
    object_,
    integration_mode: typing.Literal["hash", "id"] | None = None,
    exclude_from_integration=None,
):
    if exclude_from_integration is None:
        exclude_from_integration = tuple()
    object_to_node = {}
    nodes, to_connect = make_nodes_from_object(
        object_, integration_mode, exclude_from_integration, object_to_node
    )
    saved_node_ids = set()
    for node in nodes:
        if id(node) not in saved_node_ids:
            if not isinstance(node, BaseNode):
                raise ValueError(
                    f"node type {type(node)} must be a subclass of BaseNode"
                )
            node.save()
            saved_node_ids.add(id(node))
    for source_node, source_node_class_attr_name, target_node, properties in to_connect:
        getattr(source_node, source_node_class_attr_name).connect(
            target_node, properties=properties
        )


def _make_base_object_from_node(node, node_element_id_to_object):
    return node.value


def _make_dict_item_from_node(node, node_element_id_to_object):
    key = make_object_from_node(node.key.single(), node_element_id_to_object)
    value = make_object_from_node(node.value.single(), node_element_id_to_object)
    return key, value


def _make_dict_object_from_node(node, node_element_id_to_object):
    dict_object = {}
    for node_item in node.items.all():
        key, value = _make_dict_item_from_node(node_item, node_element_id_to_object)
        dict_object[key] = value
    return dict_object


def _make_sequence_or_bag_object_from_node(node, node_element_id_to_object):
    objects = [
        make_object_from_node(node_item, node_element_id_to_object)
        for node_item in node.items.all()
    ]
    sequence_type = _node_class_to_type[type(node)]
    return sequence_type(objects)


_node_class_to_make_object_function = {
    Integer: _make_base_object_from_node,
    String: _make_base_object_from_node,
    Float: _make_base_object_from_node,
    Boolean: _make_base_object_from_node,
    Dict: _make_dict_object_from_node,
    FrozenDict: _make_sequence_or_bag_object_from_node,
    List: _make_sequence_or_bag_object_from_node,
    Tuple: _make_sequence_or_bag_object_from_node,
    Set: _make_sequence_or_bag_object_from_node,
    FrozenSet: _make_sequence_or_bag_object_from_node,
}


def register_make_object_function(node_class, function):
    _node_class_to_make_object_function[node_class] = function


def _get_array_type_from_field(field):
    array_type = None
    default_factory = field.default_factory
    if not fieldz_kb.typeinfo.is_missing_type(default_factory):
        array_type = default_factory
    else:
        types = fieldz_kb.typeinfo.get_types_from_type_hint(field.type)
        for type_, _ in types:
            if issubclass(type_, _array_types):
                array_type = type_
    if array_type is None:
        raise ValueError(f"could not find appropriate type for field {field.name}")
    return array_type


def _make_fieldz_object_from_node(node, node_element_id_to_object):
    node_class = type(node)
    fieldz_class = _node_class_to_type.get(node_class)
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
                array_type = _get_array_type_from_field(field)
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
                                element_id_to_node[field_value_element.element_id] = (
                                    field_value_element
                                )
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
                        array_type = _get_array_type_from_field(field)
                        field_value = array_type(
                            [
                                make_object_from_node(
                                    element,
                                    node_element_id_to_object=node_element_id_to_object,
                                )
                                for element in field_value
                            ]
                        )
                else:
                    field_value = node_attr_value.single()
                    if field_value is not None:
                        field_value = make_object_from_node(
                            field_value,
                            node_element_id_to_object=node_element_id_to_object,
                        )
        fieldz_object_attr_values[field.name] = field_value
    fieldz_object = fieldz_class(**fieldz_object_attr_values)
    return fieldz_object


def _make_enum_object_from_node(node, node_element_id_to_object):
    node_class = type(node)
    enum_class = _node_class_to_type.get(node_class)
    if enum_class is None:
        raise ValueError(
            f"could not find an appropriate class for node class {node_class}"
        )
    return getattr(enum_class, node.name)


def make_object_from_node(node, node_element_id_to_object=None):
    if node_element_id_to_object is None:
        node_element_id_to_object = {}
    object_ = node_element_id_to_object.get(node.element_id)
    if object_ is not None:
        return object_
    node_class = type(node)
    make_object_function = _node_class_to_make_object_function.get(node_class)
    if make_object_function is None:
        type_ = _node_class_to_type.get(node_class)
        if type_ is None:
            raise ValueError(
                f"could not find an appropriate class for node class {node_class}"
            )
        if fieldz_kb.typeinfo.is_fieldz_class(type_):
            make_object_function = _make_fieldz_object_from_node
        elif issubclass(type_, enum.Enum):
            make_object_function = _make_enum_object_from_node
        else:
            raise ValueError(f"object of type {type_} not supported")
    object_ = make_object_function(
        node, node_element_id_to_object=node_element_id_to_object
    )
    node_element_id_to_object[node.element_id] = object_
    return object_


def cypher_query_as_objects(query, params=None, node_element_id_to_object=None):
    if node_element_id_to_object is None:
        node_element_id_to_object = {}
    object_results = []
    results, meta = cypher_query(query, params=params, resolve_objects=True)
    for row in results:
        row = [
            make_object_from_node(
                _, node_element_id_to_object=node_element_id_to_object
            )
            for _ in row
            if isinstance(_, neomodel.StructuredNode)
        ]
        object_results.append(row)
    return object_results, meta
