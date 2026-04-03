"""Shared utility functions for the clingo backend."""

import clorm
import inflect


BASE_TYPES: tuple[type, ...] = (int, str, bool)
ARRAY_TYPES: tuple[type, ...] = (list, tuple, set, frozenset)
ORDERED_ARRAY_TYPES: tuple[type, ...] = (list, tuple)


class FloatField(clorm.StringField):
    """Custom clorm field for float values, stored as strings."""

    def pytocl(value: float) -> str:
        """Convert a Python float to a clingo string."""
        return str(value)

    def cltopy(value: str) -> float:
        """Convert a clingo string to a Python float."""
        return float(value)


def make_predicate_class_name_from_type(type_: type) -> str:
    """Return a predicate class name for a given Python type.

    The first character is lowercased to follow ASP naming conventions.

    Args:
        type_: The Python type.

    Returns:
        The predicate class name string.
    """
    predicate_class_name = type_.__name__
    predicate_class_name = predicate_class_name[0].lower() + predicate_class_name[1:]
    return predicate_class_name


def make_predicate_name_from_field(field_name: str, many: bool) -> str:
    """Generate a predicate name from a field name.

    For plural field names (many=True), singularizes the name segments.

    Args:
        field_name: The field name to convert.
        many: Whether the field represents a to-many relationship.

    Returns:
        A predicate name string like 'hasFieldName'.
    """
    words = field_name.split("_")
    if not words[-1]:
        del words[-1]
        words[-1] = f"{words[-1]}_"
    if many:
        inflect_engine = inflect.engine()
        singulars = []
        for i, word in enumerate(words):
            singular = inflect_engine.singular_noun(word)
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


def make_predicate_class(
    predicate_class_name: str, predicate_name: str, fields: dict
) -> type:
    """Dynamically create a clorm Predicate subclass.

    Args:
        predicate_class_name: The Python class name.
        predicate_name: The ASP predicate name.
        fields: A dict mapping field names to their types.

    Returns:
        A new Predicate subclass.
    """
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
