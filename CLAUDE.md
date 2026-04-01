# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

fieldz_kb converts Python dataclass-like objects (via the `fieldz` library) into knowledge base representations: Neo4j graphs, clingo/ASP predicates, and BioCypher-compatible formats.

## Commands

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run all tests (requires a running Neo4j instance, see tests/credentials.py)
pytest tests/

# Run a single test
pytest tests/test_typeinfo.py::TestIsFieldzClass::test_returns_true_for_fieldz_class

# Lint and format
ruff check src/ tests/
ruff check src/ tests/ --fix
ruff format src/ tests/

# Multi-version testing
tox                # all versions (3.10-3.13)
tox -e py312       # specific version
```

## Architecture

### Shared layers

- **`typeinfo.py`** — Extracts structured type information from type hints. Returns nested `(type_origin, type_args)` tuples. Handles unions, optionals, generics, and forward references via `typing._eval_type()`.

- **`utils.py`** — Shared helpers for type classification, relationship naming, and field introspection. Used by both neomodel and pylpg backends.

### LPG backends (`lpg/`)

All labeled property graph backends follow the **Backend + Session** pattern:

```python
from fieldz_kb.lpg.neo4j.pylpg import Session, Neo4jBackend
with Session(Neo4jBackend(hostname="localhost")) as session:
    session.save_from_object(person)
    session.execute_query_as_objects("MATCH (n:Person) RETURN n")
```

- **`lpg/pylpg/core.py`** — Plugin system for pylpg: dynamically generates `pylpg.Node` subclasses from Python types. Base types become value nodes, collections become container nodes, dataclasses become node classes with relationship descriptors. Plugin-based extensibility via `PylpgTypePlugin` and `PylpgContext`.

- **`lpg/pylpg/session.py`** — Session wrapping `pylpg.Session`. Provides `save_from_object()`, `save_from_objects()`, `make_object_from_node()`, `execute_query()`, `execute_query_as_objects()`, `delete_all()`.

- **`lpg/neo4j/neomodel/core.py`** — Plugin system for neomodel: dynamically generates `neomodel.StructuredNode` subclasses. Same plugin architecture as pylpg.

- **`lpg/neo4j/neomodel/session.py`** — Session wrapping `neomodel.db`. Same public interface as pylpg Session.

- **`lpg/neo4j/neomodel/backend.py`** — `NeomodelBackend` data holder for connection parameters.

- **`lpg/neo4j/pylpg.py`**, **`lpg/falkordb/pylpg.py`**, **`lpg/falkordblite/pylpg.py`** — Re-export modules for convenience imports.

### Other backends

- **`clingo/core.py`** — Generates `clorm.Predicate` classes from types. Each dataclass produces a base predicate plus per-field predicates. Caches in `_type_to_predicate_class` / `_field_key_to_predicate_class`. Key public API: `get_or_make_predicate_classes_from_type()`, `make_facts_from_object()`, `make_ontology_rules_from_type()`.

- **`biocypher/`** — Adapter layer producing `(id, label, properties)` tuples and YAML schema files for BioCypher ingestion.

### Key design patterns

- **Backend + Session** for all LPG backends. Users create a Backend, pass it to Session, and use session methods.
- **Plugin-based type conversion** via `TypePlugin` ABCs and `Context` dispatchers. Both pylpg and neomodel have their own plugin systems.
- **Global caches** for dynamically generated classes (node classes, predicate classes).
- **Guard sets** prevent infinite recursion when processing cyclic/self-referential type definitions.
- **Integration modes** for `save_from_objects()`: `"hash"` (dedup by hash), `"id"` (dedup by Python `id()`).
- **Relationship naming**: field names are singularized via `inflect` and uppercased (e.g., `employees` → `HAS_EMPLOYEE`).
- **Custom function registration**: `register_make_nodes_function()` and `register_make_object_function()` allow overriding conversion for specific types.

## Forward References

Dataclasses with forward references (e.g., `List["Employee"]`) **must be defined at module level**, not inside functions or test methods. `get_types_from_type_hint()` resolves forward refs using the module's namespace, so locally-defined classes won't resolve. In test files, define such classes at the top of the file and reference them from test methods.

## Code Style

- Always use **absolute imports** (never relative)
- Import order: stdlib, third-party, local (separated by blank lines)
- Type hints on all function signatures; prefer `str | None` over `Optional[str]`
- Docstrings (triple double quotes) on all public functions with Args/Returns/Raises sections
- No inline comments — use docstrings
- Max line length: 88 characters

## Testing

- Neo4j tests require a **real database** — no mocks. Credentials in `tests/credentials.py` (not in git): `URI`, `USERNAME`, `PASSWORD`.
- Database is cleaned before/after each test via fixtures.
- Tests grouped in classes; fixtures in `conftest.py`.
