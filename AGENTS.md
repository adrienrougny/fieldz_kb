# Agent Guidelines for fieldz_kb

A library to store dataclass-like objects into knowledge bases (Neo4j).

## Build/Lint/Test Commands

### Running Tests
```bash
# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_typeinfo.py

# Run a single test class
pytest tests/test_typeinfo.py::TestIsFieldzClass

# Run a single test method
pytest tests/test_typeinfo.py::TestIsFieldzClass::test_returns_true_for_fieldz_class

# Run tests with verbose output
pytest tests/ -v

# Run tests across all Python versions (requires tox)
tox

# Run tests for specific Python version
tox -e py312
```

### Linting
```bash
# Run ruff linter (configured in pyproject.toml dependency groups)
ruff check src/ tests/

# Run ruff with auto-fix
ruff check src/ tests/ --fix

# Run ruff formatter
ruff format src/ tests/
```

### Type Checking
```bash
# This project uses type hints but doesn't enforce strict type checking in CI
# You can run mypy if installed:
mypy src/fieldz_kb/
```

### Build/Install
```bash
# Install with development dependencies
pip install -e ".[dev]"

# Or using uv (preferred in this project)
uv pip install -e ".[dev]"

# Build package
python -m build
```

## Code Style Guidelines

### Imports
- **ALWAYS use absolute imports** - never use relative imports (no `from .module import`)
- Order: stdlib imports → third-party imports → local imports
- Use absolute imports for local modules: `import fieldz_kb.typeinfo` or `from fieldz_kb import typeinfo`
- Group imports with a blank line between groups
- Example:
  ```python
  import typing
  import types
  
  import fieldz
  
  import fieldz_kb.typeinfo
  from fieldz_kb.neo4j import core as neo4j_core
  ```

### Formatting
- Follow PEP 8
- Use 4 spaces for indentation
- Maximum line length: 88 characters (Black/ruff default)
- Two blank lines between module-level functions and classes
- One blank line between methods within a class
- Use trailing commas in multi-line collections

### Naming Conventions
- **Functions/variables**: `snake_case` (e.g., `get_types_from_type_hint`)
- **Classes**: `CamelCase` (e.g., `BaseNode`, `OrderedRelationshipTo`)
- **Private functions**: `_leading_underscore` (e.g., `_make_node_class_from_type`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `_base_types`, `_array_types`)
- **Type variables**: descriptive, not single letters when possible

### Type Hints
- Use type hints for function parameters and return values
- Use `typing` module for complex types (e.g., `typing.Literal`, `typing.Optional`)
- Prefer modern union syntax: `str | None` over `Optional[str]`
- Use type hints from `typing` for generics: `List`, `Dict`, `Tuple`, etc.

### Error Handling
- Raise `ValueError` with descriptive messages for unsupported types/operations
- Use specific exception types when available
- Include context in error messages (e.g., `f"type {type_} not supported"`)

### Documentation
- Add docstrings to all modules, classes, and public functions
- Use triple double quotes for all docstrings
- Module docstrings should describe the module's purpose and contents
- Class docstrings should describe the class purpose and behavior
- Function/method docstrings should include:
  - Brief description of what it does
  - Args section with parameter descriptions
  - Returns section with return value description
  - Raises section if exceptions are raised
- Example style:
  ```python
  def get_types_from_type_hint(type_hint, module=None):
      """Extract type information from a type hint.
      
      This function recursively processes type hints to extract the underlying
      types, handling unions, generic types, forward references, and base types.
      
      Args:
          type_hint: The type hint to process
          module: Optional module name for resolving forward references
      
      Returns:
          A tuple of (type_origin, type_args) pairs describing the type structure
      
      Raises:
          ValueError: If the type hint format is not supported
      """
  ```
- No inline comments in code, only docstrings
- Keep docstrings concise but informative

### Testing
- Use pytest for all tests
- Group related tests in classes
- Use fixtures from `conftest.py` for shared setup
- Tests use a **real Neo4j database** (configured via `tests/credentials.py`)
- Tests will fail if Neo4j is not available or credentials are missing (no skips)
- Database is automatically cleaned before/after each test for isolation

## Project Structure

```
src/fieldz_kb/           # Main package
├── __init__.py
├── typeinfo.py          # Type introspection utilities
├── neo4j/               # Neo4j integration
│   └── core.py
└── biocypher/           # BioCypher integration
    ├── core.py
    └── utils.py
tests/                   # Test suite
├── conftest.py          # Pytest fixtures
├── credentials.py       # Neo4j credentials (not in git)
├── test_typeinfo.py
└── test_neo4j_core.py
```

## Dependencies

- **Core**: `fieldz>=0.1.2`, `neomodel>=5.5.0`, `inflect>=7.5.0`, `frozendict>=2.4.7`
- **Dev**: `ruff>=0.12.8`
- **Test**: `pytest>=9.0.2`

Python version support: 3.10, 3.11, 3.12, 3.13

## Key Patterns

- This library converts dataclass-like objects to Neo4j nodes
- Uses `fieldz` library for introspecting dataclass-like objects
- Supports conversion of Python primitives, enums, and collections
- Node classes are dynamically generated using `type()`
- Uses `neomodel` for Neo4j OGM functionality

## Forward Reference Handling

Forward references (e.g., `List["Employee"]`) are supported but require special handling:

- **Module-level definitions**: Dataclasses with forward references must be defined at the module level, not inside test methods or functions
- **Why**: The `get_types_from_type_hint()` function uses `typing._eval_type()` with the module's namespace to resolve forward references. Local class definitions don't exist in the module's namespace
- **Best practice**: Define all dataclasses with forward references at module level:
  ```python
  # Good - at module level
  @dataclass
  class Company:
      name: str
      employees: List["Employee"]

  @dataclass
  class Employee:
      name: str

  # Bad - inside function (forward refs won't resolve)
  def test_something():
      @dataclass
      class Company:
          employees: List["Employee"]  # Won't work!
  ```

## Testing Forward References

When writing tests for forward references:
- Define the dataclasses at module level in the test file
- Use the module-level classes in your test methods
- See `tests/test_typeinfo.py` and `tests/test_neo4j_core.py` for examples
