"""Base dataclass whose string annotations only resolve in this module.

Used by the inheritance tests to check that inherited fields are resolved in
the module of the class that declares them, not in the subclass's module.
"""

import dataclasses

Tags = tuple[str, ...]


@dataclasses.dataclass
class ForwardReferenceBase:
    """Base with self-referencing and module-local string annotations."""

    name: str = ""
    parent: "ForwardReferenceBase | None" = None
    children: "list[ForwardReferenceBase] | None" = None
    tags: "Tags | None" = None
