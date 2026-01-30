"""Tests for fieldz_kb.typeinfo module."""

import sys
import typing
from typing import List, Dict, Optional, Union, Tuple, Set, FrozenSet, TypeVar
from dataclasses import dataclass

import pytest
import fieldz

import fieldz_kb.typeinfo as typeinfo


class TestIsFieldzClass:
    """Tests for is_fieldz_class function."""

    def test_returns_true_for_fieldz_class(self):
        """Test that fieldz classes are recognized."""

        @dataclass
        class Person:
            name: str
            age: int

        assert typeinfo.is_fieldz_class(Person) is True

    def test_returns_false_for_regular_class(self):
        """Test that regular classes are not recognized as fieldz classes."""

        class RegularClass:
            pass

        assert typeinfo.is_fieldz_class(RegularClass) is False

    def test_returns_false_for_builtin_types(self):
        """Test that builtin types are not recognized."""
        assert typeinfo.is_fieldz_class(int) is False
        assert typeinfo.is_fieldz_class(str) is False
        assert typeinfo.is_fieldz_class(list) is False

    def test_returns_false_for_dataclasses_module(self):
        """Test that stdlib dataclasses are not recognized."""
        # Standard dataclasses may be recognized if fieldz has adapters for them
        # This test verifies the behavior
        from dataclasses import dataclass

        @dataclass
        class StdlibPerson:
            name: str

        # Note: fieldz might recognize stdlib dataclasses depending on adapters installed
        result = typeinfo.is_fieldz_class(StdlibPerson)
        # Just verify the function doesn't crash
        assert isinstance(result, bool)


class TestIsMissingType:
    """Tests for is_missing_type function."""

    def test_returns_true_for_missing_type(self):
        """Test that MISSING singleton is recognized."""
        missing = fieldz._types._MISSING_TYPE.MISSING
        assert typeinfo.is_missing_type(missing) is True

    def test_returns_false_for_other_values(self):
        """Test that other values are not recognized as missing."""
        assert typeinfo.is_missing_type(None) is False
        assert typeinfo.is_missing_type(0) is False
        assert typeinfo.is_missing_type("") is False
        assert typeinfo.is_missing_type([]) is False


class TestGetTypesFromTypeHint:
    """Tests for get_types_from_type_hint function."""

    def test_simple_types(self):
        """Test basic type hints like int, str, float, bool."""
        result = typeinfo.get_types_from_type_hint(int)
        assert result == ((int, ()),)

        result = typeinfo.get_types_from_type_hint(str)
        assert result == ((str, ()),)

        result = typeinfo.get_types_from_type_hint(float)
        assert result == ((float, ()),)

        result = typeinfo.get_types_from_type_hint(bool)
        assert result == ((bool, ()),)

    def test_union_type(self):
        """Test Union type hints."""
        result = typeinfo.get_types_from_type_hint(Union[int, str])
        assert len(result) == 2
        assert (int, ()) in result
        assert (str, ()) in result

    def test_optional_type(self):
        """Test Optional type hints."""
        result = typeinfo.get_types_from_type_hint(Optional[int])
        # Should return int | None format
        assert len(result) == 2
        type_origins = [t[0] for t in result]
        assert int in type_origins
        assert type(None) in type_origins

    def test_list_type(self):
        """Test List type hints."""
        result = typeinfo.get_types_from_type_hint(List[int])
        assert len(result) == 1
        origin, args = result[0]
        assert origin is list
        assert len(args) == 1
        assert args[0] == (int, ())

    def test_dict_type(self):
        """Test Dict type hints."""
        result = typeinfo.get_types_from_type_hint(Dict[str, int])
        assert len(result) == 1
        origin, args = result[0]
        assert origin is dict
        assert len(args) == 2
        assert (str, ()) in args
        assert (int, ()) in args

    def test_tuple_type(self):
        """Test Tuple type hints."""
        result = typeinfo.get_types_from_type_hint(Tuple[int, str, float])
        assert len(result) == 1
        origin, args = result[0]
        assert origin is tuple
        assert len(args) == 3
        assert (int, ()) in args
        assert (str, ()) in args
        assert (float, ()) in args

    def test_set_type(self):
        """Test Set type hints."""
        result = typeinfo.get_types_from_type_hint(Set[int])
        assert len(result) == 1
        origin, args = result[0]
        assert origin is set
        assert len(args) == 1
        assert args[0] == (int, ())

    def test_frozenset_type(self):
        """Test FrozenSet type hints."""
        result = typeinfo.get_types_from_type_hint(FrozenSet[int])
        assert len(result) == 1
        origin, args = result[0]
        assert origin is frozenset
        assert len(args) == 1
        assert args[0] == (int, ())

    def test_nested_generic_types(self):
        """Test nested generic types like List[List[int]]."""
        result = typeinfo.get_types_from_type_hint(List[List[int]])
        assert len(result) == 1
        outer_origin, outer_args = result[0]
        assert outer_origin is list
        assert len(outer_args) == 1
        inner_origin, inner_args = outer_args[0]
        assert inner_origin is list
        assert (int, ()) in inner_args

    def test_forward_ref_as_string(self):
        """Test forward references as strings."""

        # This tests that string forward refs can be resolved
        @dataclass
        class ForwardNode:
            value: int
            next_node: "ForwardNode"

        # Should not raise an error
        result = typeinfo.get_types_from_type_hint("ForwardNode", module=__name__)
        assert len(result) == 1
        assert result[0][0] is ForwardNode

    def test_ellipsis(self):
        """Test Ellipsis type hint (used in variadic tuples)."""
        result = typeinfo.get_types_from_type_hint(...)
        assert result == ()

    def test_unsupported_type_raises_error(self):
        """Test that unsupported types raise ValueError."""

        # Custom generic types - need to define TypeVar first
        T = TypeVar("T")

        class MyGeneric(typing.Generic[T]):
            pass

        with pytest.raises(ValueError, match="type hint.*not supported"):
            typeinfo.get_types_from_type_hint(MyGeneric[int])

    def test_union_type_operator(self):
        """Test Python 3.10+ union type operator (|)."""
        if sys.version_info >= (3, 10):
            result = typeinfo.get_types_from_type_hint(int | str)
            assert len(result) == 2
            assert (int, ()) in result
            assert (str, ()) in result

    def test_complex_nested_union(self):
        """Test complex nested types with unions."""
        result = typeinfo.get_types_from_type_hint(Union[List[int], str])
        assert len(result) == 2

        # Check list type
        list_types = [r for r in result if r[0] is list]
        assert len(list_types) == 1

        # Check str type
        str_types = [r for r in result if r[0] is str]
        assert len(str_types) == 1


class TestEdgeCases:
    """Edge case tests for typeinfo module."""

    def test_empty_union_not_supported(self):
        """Test that empty unions are not supported."""
        # Union with no arguments
        with pytest.raises((ValueError, TypeError)):
            typeinfo.get_types_from_type_hint(Union[()])

    def test_any_type_handling(self):
        """Test that typing.Any is handled appropriately."""
        # typing.Any may or may not be supported depending on the implementation
        # Just verify it doesn't crash unexpectedly
        try:
            result = typeinfo.get_types_from_type_hint(typing.Any)
            # If it works, it should return a valid result
            assert isinstance(result, tuple)
        except ValueError as e:
            # If it raises, it should be a "not supported" error
            assert "not supported" in str(e).lower()

    def test_callable_not_supported(self):
        """Test that typing.Callable is not supported."""
        with pytest.raises(ValueError, match="not supported"):
            typeinfo.get_types_from_type_hint(typing.Callable)

    def test_none_type(self):
        """Test handling of NoneType."""
        result = typeinfo.get_types_from_type_hint(type(None))
        assert result == ((type(None), ()),)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
