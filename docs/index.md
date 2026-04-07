# fieldz_kb

**fieldz_kb** converts Python dataclass-like objects (via the [fieldz](https://github.com/pyapp-kit/fieldz) library) into knowledge base representations: Neo4j/FalkorDB graphs, clingo/ASP predicates, and BioCypher-compatible formats.

## Features

- **Multiple backends** — Neo4j, FalkorDB, FalkorDBLite (embedded), clingo/ASP
- **Automatic type conversion** — primitives, collections, enums, nested dataclasses
- **Plugin-based extensibility** — add support for custom types
- **BioCypher integration** — generate BioCypher-compatible nodes, relationships, and YAML schemas
- **Forward reference support** — handles `List["MyClass"]` and similar patterns

## Installation

```bash
pip install fieldz_kb
```

### Backend-specific extras

```bash
pip install fieldz_kb[neo4j]        # Neo4j support
pip install fieldz_kb[falkordb]     # FalkorDB support
pip install fieldz_kb[falkordblite] # FalkorDBLite (embedded) support
pip install fieldz_kb[clingo]       # Clingo/ASP support
pip install fieldz_kb[biocypher]    # BioCypher adapter
pip install fieldz_kb[all]          # Everything
```

## Quick example

### Storing objects in Neo4j

```python
import dataclasses
import fieldz_kb.lpg.session
import fieldz_kb.lpg.backends.neo4j

@dataclasses.dataclass
class Gene:
    name: str
    chromosome: int

@dataclasses.dataclass
class Pathway:
    name: str
    genes: list[Gene]

backend = fieldz_kb.lpg.backends.neo4j.Neo4jBackend(
    hostname="localhost",
    username="neo4j",
    password="password",
)

pathway = Pathway(
    name="Glycolysis",
    genes=[
        Gene(name="HK1", chromosome=10),
        Gene(name="PFK1", chromosome=21),
    ],
)

with fieldz_kb.lpg.session.Session(backend) as session:
    session.save_from_object(pathway)

    results = session.execute_query_as_objects(
        "MATCH (n:Pathway) RETURN n"
    )
```

### Converting objects to clingo facts

```python
import fieldz_kb.clingo.session

session = fieldz_kb.clingo.session.Session()
facts = session.make_facts_from_object(pathway)
```

## Documentation

- [Getting started](getting_started.md) — detailed guide with examples
- [API reference](api_reference/typeinfo.md) — full API documentation
