"""Subclass of ForwardReferenceBase in a module that does not import its names.

Only the base module is imported, so ``ForwardReferenceBase`` and ``Tags`` are
not defined in this module's namespace.
"""

import dataclasses

import tests.forward_reference_base


@dataclasses.dataclass
class ForwardReferenceSubclass(tests.forward_reference_base.ForwardReferenceBase):
    """Subclass inheriting fields with module-local string annotations."""

    extra: int = 0
