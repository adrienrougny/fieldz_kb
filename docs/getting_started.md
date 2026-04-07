# Getting started

## Defining models

fieldz_kb works with any class supported by [fieldz](https://github.com/pyapp-kit/fieldz), including standard `dataclasses`:

```python
import dataclasses

@dataclasses.dataclass
class Gene:
    name: str
    chromosome: int

@dataclasses.dataclass
class Protein:
    name: str
    molecular_weight: float
    is_enzyme: bool = False
```

## Supported types

fieldz_kb handles:

- **Primitives**: `int`, `str`, `float`, `bool`
- **None**: stored as `Null` nodes
- **Collections**: `list`, `tuple`, `set`, `frozenset`, `dict`, `frozendict`
- **Enums**: stored with name and value
- **Nested dataclasses**: stored as separate nodes with relationships
- **Optional fields**: `str | None`, `Optional[int]`, etc.

## LPG backends (Neo4j, FalkorDB, FalkorDBLite)

### Connecting to a database

#### Neo4j

```python
import fieldz_kb.lpg.backends.neo4j

backend = fieldz_kb.lpg.backends.neo4j.Neo4jBackend(
    hostname="localhost",
    port=7687,
    username="neo4j",
    password="password",
)
```

#### FalkorDB

```python
import fieldz_kb.lpg.backends.falkordb

backend = fieldz_kb.lpg.backends.falkordb.FalkorDBBackend(
    hostname="localhost",
    port=6379,
    database="default",
)
```

#### FalkorDBLite (embedded)

No server required:

```python
import fieldz_kb.lpg.backends.falkordblite

backend = fieldz_kb.lpg.backends.falkordblite.FalkorDBLiteBackend(
    path="/tmp/my_graph.db",
    database="default",
)
```

### Sessions

A session manages the connection between your Python objects and the database:

```python
import fieldz_kb.lpg.session

with fieldz_kb.lpg.session.Session(backend) as session:
    session.save_from_object(gene)
```

### Saving objects

```python
gene = Gene(name="TP53", chromosome=17)

with fieldz_kb.lpg.session.Session(backend) as session:
    # Save a single object
    session.save_from_object(gene)

    # Save multiple objects
    genes = [Gene(name="BRCA1", chromosome=17), Gene(name="HK1", chromosome=10)]
    session.save_from_objects(genes)
```

### Querying and retrieving objects

```python
with fieldz_kb.lpg.session.Session(backend) as session:
    session.save_from_object(gene)

    # Raw Cypher query
    results = session.execute_query(
        "MATCH (n:Gene) WHERE n.chromosome = $chr RETURN n",
        params={"chr": 17},
    )

    # Query with automatic conversion to Python objects
    results = session.execute_query_as_objects(
        "MATCH (n:Gene) RETURN n ORDER BY n.name"
    )
    for row in results:
        gene = row[0]
        print(gene.name, gene.chromosome)
```

### Nested objects and relationships

Nested dataclasses are stored as separate nodes connected by relationships:

```python
@dataclasses.dataclass
class Organism:
    name: str

@dataclasses.dataclass
class GeneWithOrganism:
    name: str
    organism: Organism

gene = GeneWithOrganism(
    name="TP53",
    organism=Organism(name="Homo sapiens"),
)

with fieldz_kb.lpg.session.Session(backend) as session:
    session.save_from_object(gene)
    # Creates: (GeneWithOrganism)-[:HAS_ORGANISM]->(Organism)
```

Collections of dataclasses work the same way:

```python
@dataclasses.dataclass
class Pathway:
    name: str
    genes: list[Gene]

pathway = Pathway(
    name="Glycolysis",
    genes=[Gene(name="HK1", chromosome=10), Gene(name="PFK1", chromosome=21)],
)
```

### Resetting the context

If you need a fresh type conversion cache (e.g., to avoid class name clashes between modules):

```python
with fieldz_kb.lpg.session.Session(backend) as session:
    session.save_from_object(object_from_module_a)
    session.reset_context()
    session.save_from_object(object_from_module_b)
```

## Clingo/ASP backend

Convert objects to clingo facts for answer set programming:

```python
import fieldz_kb.clingo.session

session = fieldz_kb.clingo.session.Session()

# Convert to facts
facts = session.make_facts_from_object(gene)

# Generate predicate classes for a type
predicate_classes = session.get_or_make_predicate_classes_from_type(Gene)

# Generate ontology rules (type inheritance as ASP rules)
rules = session.make_ontology_rules_from_type(Gene)
```

## BioCypher adapter

Convert objects to BioCypher-compatible format:

```python
import fieldz_kb.biocypher.adapter

adapter = fieldz_kb.biocypher.adapter.Adapter(pathway)
nodes, relationships = adapter.make_nodes_and_relationships()
# nodes: list of (id, label, properties) tuples
# relationships: list of (source_id, target_id, label, properties) tuples
```

Generate BioCypher schema YAML:

```python
import fieldz_kb.biocypher.utils

schema_yaml = fieldz_kb.biocypher.utils.make_biocypher_schema_string_from_classes(
    {Gene, Pathway}
)
```
