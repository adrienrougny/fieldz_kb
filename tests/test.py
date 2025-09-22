import types
import typing
import dataclasses
import fieldz
import fieldz_kb.neo4j.neomodel


@dataclasses.dataclass(frozen=True)
class B:
    a: float
    b: int


@dataclasses.dataclass
class A:
    x: str | int
    y: int
    z: list[int]
    w: list[int | str]
    a: list[list[int]]
    b: tuple
    c: set[float]
    d: list | tuple
    e: list | set
    f: list[int] | list[str]
    g: set[int] | list[str]
    h: set[int] | frozenset[str]
    i: B
    j: list[int] | set[typing.ForwardRef("B")]
    k: list[int] | set["B"] | None
    l: "B"
    m: B | B
    n: list[int] | tuple[int]
    o: list[int] | set[int]
    p: list[int] | B


@dataclasses.dataclass(frozen=True)
class C:
    x: int
    y: str
    z: tuple[B]
    a: frozenset[B]


if __name__ == "__main__":
    fieldz_kb.neo4j.neomodel.connect("localhost", "neo4j", "neofourj")
    fieldz_kb.neo4j.neomodel.delete_all()
    b1 = B(1, 1)
    b2 = B(2, 2)
    c = C(3, "3", (b1, b2), frozenset([b1]))
    fieldz_kb.neo4j.neomodel.save_node_from_object(c, integration_mode="hash")
