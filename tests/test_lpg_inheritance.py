"""Tests for node-class generation across inheritance hierarchies.

Regression tests for a bug where a subclass node class would shadow a base
class's relationship descriptor with ``None`` (because the subclass classified
the same-named field differently — e.g. primitive instead of relationship)
while the base's ``_field_info_<name>`` still resolved via MRO. The
deserializer would then look up ``_field_info_<name>`` (relationship), call
``getattr(node, name).all()`` and crash with
``AttributeError: 'NoneType' object has no attribute 'all'``.
"""

import dataclasses
import typing

import pylpg.relationship
import pytest

import fieldz_kb.lpg.core


@dataclasses.dataclass
class Point:
    """Module-level dataclass for inheritance tests (forward refs need module scope)."""

    x: float = 0.0
    y: float = 0.0


@dataclasses.dataclass
class BaseLayout:
    """Base with a single-valued relationship field."""

    position: typing.Optional[Point] = None


@dataclasses.dataclass
class SubLayoutNoOverride(BaseLayout):
    """Subclass that adds nothing — must inherit position as a relationship."""


@dataclasses.dataclass
class SubLayoutNarrowed(BaseLayout):
    """Subclass that narrows the relationship type but still references Point."""

    position: Point = dataclasses.field(default_factory=Point)


@dataclasses.dataclass
class SubLayoutPrimitiveOverride(BaseLayout):
    """Subclass that overrides position with a primitive — kind changes."""

    position: typing.Optional[str] = None


@dataclasses.dataclass
class CycleA:
    """Half of a mutual-reference cycle."""

    label: str = ""
    other: typing.Optional["CycleB"] = None


@dataclasses.dataclass
class CycleB:
    """Other half of the cycle."""

    label: str = ""
    other: typing.Optional[CycleA] = None


def _node_position_attr(node_class):
    return getattr(node_class, "position", None)


class TestInheritanceNodeClassConsistency:
    """The node class must be self-consistent: if `_field_info_<name>` says
    'relationship', then the descriptor at `<name>` must also be a
    relationship descriptor. If the field info says primitive (or is absent),
    then the attribute on an instance must not pretend to be a relationship.
    """

    def test_subclass_with_no_override_inherits_relationship_descriptor(self):
        """Subclass without overrides must round-trip the relationship descriptor."""
        ctx = fieldz_kb.lpg.core.make_context()
        sub_node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            ctx, SubLayoutNoOverride
        )
        instance = sub_node_class()
        field_info = getattr(sub_node_class, "_field_info_position", None)
        position_attr = getattr(instance, "position")
        if field_info is not None and field_info["kind"] == "relationship":
            assert isinstance(position_attr, pylpg.relationship.BoundRelationship), (
                "subclass _field_info says relationship but instance attribute is "
                f"{type(position_attr).__name__}"
            )

    def test_subclass_built_before_base_is_consistent(self):
        """Order independence: building subclass before base must not break either."""
        ctx = fieldz_kb.lpg.core.make_context()
        sub_node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            ctx, SubLayoutNoOverride
        )
        base_node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            ctx, BaseLayout
        )
        for node_class in (base_node_class, sub_node_class):
            instance = node_class()
            field_info = getattr(node_class, "_field_info_position", None)
            if field_info is not None and field_info["kind"] == "relationship":
                assert isinstance(
                    getattr(instance, "position"),
                    pylpg.relationship.BoundRelationship,
                )

    def test_subclass_narrowed_relationship_still_bound(self):
        """Narrowing `Point | None` to `Point` keeps it a relationship."""
        ctx = fieldz_kb.lpg.core.make_context()
        sub_node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            ctx, SubLayoutNarrowed
        )
        instance = sub_node_class()
        field_info = getattr(sub_node_class, "_field_info_position", None)
        assert field_info is not None
        assert field_info["kind"] == "relationship"
        assert isinstance(
            getattr(instance, "position"), pylpg.relationship.BoundRelationship
        )

    def test_subclass_primitive_override_does_not_leak_base_relationship_info(self):
        """If a subclass overrides a relationship field with a primitive, the
        subclass must not expose the base's relationship `_field_info`. The
        deserializer keys off `_field_info_<name>`; if it picks up the base's
        info via MRO while the descriptor at `<name>` is `None`, deserialization
        crashes with AttributeError on `None.all()`.
        """
        ctx = fieldz_kb.lpg.core.make_context()
        sub_node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(
            ctx, SubLayoutPrimitiveOverride
        )
        instance = sub_node_class()
        field_info = getattr(sub_node_class, "_field_info_position", None)
        position_attr = getattr(instance, "position")
        if field_info is not None and field_info["kind"] == "relationship":
            assert isinstance(position_attr, pylpg.relationship.BoundRelationship), (
                "primitive override leaked base's relationship info: "
                "_field_info_position points at a relationship but the descriptor "
                f"is {position_attr!r}"
            )

    def test_cycle_classes_share_consistent_node_classes(self):
        """A mutual reference cycle must produce stable, fully-populated node classes."""
        ctx = fieldz_kb.lpg.core.make_context()
        a_node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(ctx, CycleA)
        b_node_class = fieldz_kb.lpg.core.get_or_make_node_class_from_type(ctx, CycleB)
        assert ctx.type_to_node_class[CycleA] is a_node_class
        assert ctx.type_to_node_class[CycleB] is b_node_class
        a_instance = a_node_class()
        b_instance = b_node_class()
        for instance, node_class in ((a_instance, a_node_class), (b_instance, b_node_class)):
            field_info = getattr(node_class, "_field_info_other", None)
            assert field_info is not None
            assert field_info["kind"] == "relationship"
            assert isinstance(
                getattr(instance, "other"), pylpg.relationship.BoundRelationship
            )


@pytest.mark.usefixtures("clear_database")
class TestInheritanceRoundTrip:
    """End-to-end save+load through a real backend for inherited relationships."""

    def test_subclass_round_trip_with_inherited_relationship(self, session, clear_database):
        layout = SubLayoutNoOverride(position=Point(x=1.5, y=2.5))
        session.save_from_object(layout)
        results = session.execute_query_as_objects(
            "MATCH (n:SubLayoutNoOverride) RETURN n"
        )
        assert len(results) == 1
        retrieved = results[0][0]
        assert isinstance(retrieved, SubLayoutNoOverride)
        assert isinstance(retrieved.position, Point)
        assert retrieved.position.x == 1.5
        assert retrieved.position.y == 2.5

    def test_subclass_primitive_override_round_trip(self, session, clear_database):
        layout = SubLayoutPrimitiveOverride(position="top-left")
        session.save_from_object(layout)
        results = session.execute_query_as_objects(
            "MATCH (n:SubLayoutPrimitiveOverride) RETURN n"
        )
        assert len(results) == 1
        retrieved = results[0][0]
        assert isinstance(retrieved, SubLayoutPrimitiveOverride)
        assert retrieved.position == "top-left"
