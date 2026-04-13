"""Node and relationship types for the pylpg backend."""

import pylpg.node
import pylpg.relationship


class BaseNode(pylpg.node.Node):
    """Base class for all pylpg node types."""


class Integer(BaseNode):
    """Node class for storing integer values."""

    value: int


class String(BaseNode):
    """Node class for storing string values."""

    value: str


class Float(BaseNode):
    """Node class for storing float values."""

    value: float


class Boolean(BaseNode):
    """Node class for storing boolean values."""

    value: bool


class Null(BaseNode):
    """Node class for storing None values."""


class HasItem(pylpg.relationship.Relationship):
    """Relationship for HAS_ITEM connections."""

    __type__ = "HAS_ITEM"
    order: int | None = None


class HasKey(pylpg.relationship.Relationship):
    """Relationship for HAS_KEY connections in mappings."""

    __type__ = "HAS_KEY"


class HasValue(pylpg.relationship.Relationship):
    """Relationship for HAS_VALUE connections in mappings."""

    __type__ = "HAS_VALUE"


class Item(BaseNode):
    """Node class for storing key-value pairs (used in mappings)."""

    key = pylpg.relationship.RelationshipTo(HasKey)
    value = pylpg.relationship.RelationshipTo(HasValue)


class Mapping(BaseNode):
    """Base node class for mapping types."""

    items = pylpg.relationship.RelationshipTo(HasItem)


class Dict(Mapping):
    """Node class for storing dictionary values."""


class Bag(BaseNode):
    """Base node class for unordered collection types (set, frozenset)."""

    items = pylpg.relationship.RelationshipTo(HasItem)


class Set(Bag):
    """Node class for storing set values."""


class FrozenSet(Bag):
    """Node class for storing frozenset values."""


class Sequence(BaseNode):
    """Base node class for ordered sequence types (list, tuple)."""

    items = pylpg.relationship.RelationshipTo(HasItem)


class List(Sequence):
    """Node class for storing list values."""


class Tuple(Sequence):
    """Node class for storing tuple values."""
