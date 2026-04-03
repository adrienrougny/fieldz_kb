"""Clingo session for fieldz_kb.

Provides a Session class for converting fieldz objects to clingo facts
and predicate classes.
"""

import typing

import fieldz_kb.clingo.core


class Session:
    """Session for converting fieldz objects to clingo predicates and facts.

    Example:
        >>> import dataclasses
        >>> import fieldz_kb.clingo.session
        >>>
        >>> @dataclasses.dataclass
        ... class Gene:
        ...     name: str
        ...     chromosome: int
        >>>
        >>> session = fieldz_kb.clingo.session.Session()
        >>> facts = session.make_facts_from_object(Gene(name="TP53", chromosome=17))
    """

    def __init__(self) -> None:
        """Initialize the session with a fresh clingo context."""
        self._context = fieldz_kb.clingo.core.make_context()

    def __enter__(self) -> "Session":
        """Enter the session context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit the session context manager."""

    def reset_context(self) -> None:
        """Replace the conversion context with a fresh one.

        Clears all cached predicate classes, type mappings, and ID counter.
        """
        self._context = fieldz_kb.clingo.core.make_context()

    def make_facts_from_object(
        self,
        obj: object,
        id_to_object: dict | None = None,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration: tuple[type, ...] | None = None,
    ) -> list:
        """Convert a Python object to clingo facts.

        Args:
            obj: The object to convert.
            id_to_object: Optional cache mapping fact IDs to objects.
            integration_mode: How to handle duplicate objects ("hash" or "id").
            exclude_from_integration: Types to exclude from integration logic.

        Returns:
            A list of clorm facts.
        """
        return fieldz_kb.clingo.core.make_facts_from_object(
            self._context,
            obj,
            id_to_object=id_to_object,
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
        )

    def get_or_make_predicate_classes_from_type(
        self,
        type_: type,
        module: str | None = None,
        make_predicate_classes_recursively: bool = True,
    ) -> list:
        """Get or create predicate classes for a given Python type.

        Args:
            type_: The Python type.
            module: Module name for resolving forward references.
            make_predicate_classes_recursively: Whether to create predicates for nested types.

        Returns:
            A list of predicate classes.
        """
        return fieldz_kb.clingo.core.get_or_make_predicate_classes_from_type(
            self._context,
            type_,
            module=module,
            make_predicate_classes_recursively=make_predicate_classes_recursively,
        )

    def make_ontology_rules_from_type(self, type_: type) -> list[str]:
        """Generate ontology rules expressing type inheritance as ASP rules.

        Args:
            type_: The Python type to generate rules for.

        Returns:
            A sorted list of ASP rule strings.
        """
        return fieldz_kb.clingo.core.make_ontology_rules_from_type(
            self._context, type_
        )
