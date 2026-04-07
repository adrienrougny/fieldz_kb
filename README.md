# fieldz_kb

A library to store dataclass-like objects into knowledge bases.

## Features

- **Multiple backends** — Neo4j, FalkorDB, FalkorDBLite (embedded), clingo/ASP
- **Automatic type conversion** — primitives, collections, enums, nested dataclasses
- **Plugin-based extensibility** — add support for custom types
- **BioCypher integration** — generate BioCypher-compatible nodes, relationships, and YAML schemas

## Installation

```bash
pip install fieldz-kb[neo4j]        # Neo4j support
pip install fieldz-kb[falkordb]     # FalkorDB support
pip install fieldz-kb[falkordblite] # FalkorDBLite (embedded) support
pip install fieldz-kb[clingo]       # Clingo/ASP support
pip install fieldz-kb[biocypher]    # BioCypher adapter
pip install fieldz-kb[all]          # Everything
```

## Quick example

```python
import dataclasses
import fieldz_kb.lpg.session
import fieldz_kb.lpg.backends.neo4j

@dataclasses.dataclass
class Gene:
    name: str
    chromosome: int

backend = fieldz_kb.lpg.backends.neo4j.Neo4jBackend(
    hostname="localhost",
    username="neo4j",
    password="password",
)

with fieldz_kb.lpg.session.Session(backend) as session:
    session.save_from_object(Gene(name="TP53", chromosome=17))

    results = session.execute_query_as_objects(
        "MATCH (n:Gene) RETURN n"
    )
```

## Documentation

Full documentation is available at [https://adrienrougny.github.io/fieldz_kb/](https://adrienrougny.github.io/fieldz_kb/).

## License

GPLv3. See [LICENSE](LICENSE) for details.
