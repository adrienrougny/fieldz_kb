"""Pylpg session for fieldz_kb.

Provides a Session class that wraps a pylpg.Session and adds
higher-level methods for saving and retrieving fieldz objects.
"""

import typing

import pylpg.backend.base
import pylpg.node
import pylpg.session

import fieldz_kb.lpg.core
import fieldz_kb.lpg.graph


class Session:
    """Session for saving and retrieving fieldz objects via pylpg.

    Wraps a pylpg.Session internally. Use as a context manager.

    Example:
        >>> import fieldz_kb.lpg
        >>> import fieldz_kb.lpg.backends.neo4j
        >>> backend = fieldz_kb.lpg.backends.neo4j.Neo4jBackend(hostname="localhost")
        >>> with fieldz_kb.lpg.session.Session(backend) as session:
        ...     session.save_from_object(person)
    """

    def __init__(self, backend: pylpg.backend.base.Backend) -> None:
        """Initialize the session with a pylpg backend.

        Args:
            backend: A pylpg backend instance (Neo4jBackend, FalkorDBBackend, etc.)
        """
        self._pylpg_session = pylpg.session.Session(backend)
        self._context = fieldz_kb.lpg.core.get_default_context()

    def reset_context(self) -> None:
        """Replace the conversion context with a fresh one.

        Clears all cached node classes and type mappings while keeping the
        same database connection.
        """
        self._context = fieldz_kb.lpg.core.make_context()

    def __enter__(self) -> "Session":
        """Enter the session context manager."""
        self._pylpg_session.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool | None:
        """Exit the session context manager."""
        return self._pylpg_session.__exit__(exc_type, exc_val, exc_tb)

    def execute_query(
        self,
        query: str,
        params: dict | None = None,
    ) -> list[dict]:
        """Execute a Cypher query against the database.

        Args:
            query: The Cypher query string.
            params: Optional query parameters.

        Returns:
            Query results as a list of dicts.
        """
        return self._pylpg_session.execute_query(
            query, parameters=params
        )

    def save_from_object(
        self,
        object_: object,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration: tuple[type, ...] | None = None,
    ) -> None:
        """Save a single object to the database.

        Args:
            object_: The object to save.
            integration_mode: How to handle duplicate objects ("hash" or "id").
            exclude_from_integration: Types to exclude from integration logic.
        """
        self.save_from_objects(
            objects=[object_],
            integration_mode=integration_mode,
            exclude_from_integration=exclude_from_integration,
        )

    def save_from_objects(
        self,
        objects: list[object],
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration: tuple[type, ...] | None = None,
    ) -> None:
        """Save multiple objects to the database.

        Args:
            objects: The objects to save.
            integration_mode: How to handle duplicate objects ("hash" or "id").
            exclude_from_integration: Types to exclude from integration logic.

        Raises:
            ValueError: If a node is not a subclass of BaseNode.
        """
        if exclude_from_integration is None:
            exclude_from_integration = tuple()
        object_to_node = {}
        saved_node_ids = set()
        all_nodes = []
        all_relationships = []
        for object_ in objects:
            nodes, relationships = fieldz_kb.lpg.core.make_nodes_from_object(
                self._context,
                object_,
                integration_mode,
                exclude_from_integration,
                object_to_node,
            )
            for node in nodes:
                if id(node) not in saved_node_ids:
                    if not isinstance(node, fieldz_kb.lpg.graph.BaseNode):
                        raise ValueError(
                            f"node type {type(node)} must be a subclass of BaseNode"
                        )
                    all_nodes.append(node)
                    saved_node_ids.add(id(node))
            all_relationships += relationships
        self._pylpg_session.save(all_nodes)
        self._pylpg_session.save(all_relationships)

    def execute_query_as_objects(
        self,
        query: str,
        params: dict | None = None,
        node_id_to_object: dict | None = None,
    ) -> list[list[object]]:
        """Execute a Cypher query and convert results to Python objects.

        Args:
            query: The Cypher query string.
            params: Optional query parameters.
            node_id_to_object: Optional cache mapping node database IDs to objects.

        Returns:
            A list of rows, where each row is a list of Python objects
            converted from Node instances in the query results.
        """
        if node_id_to_object is None:
            node_id_to_object = {}
        object_results = []
        results = self._pylpg_session.execute_query(
            query, parameters=params, resolve_nodes=True
        )
        for row_dict in results:
            row = [
                fieldz_kb.lpg.core.make_object_from_node(
                    self._context, value, node_id_to_object
                )
                for value in row_dict.values()
                if isinstance(value, pylpg.node.Node)
            ]
            object_results.append(row)
        return object_results

    def delete_all(self) -> None:
        """Delete all nodes and relationships from the database."""
        self._pylpg_session.delete_all()
