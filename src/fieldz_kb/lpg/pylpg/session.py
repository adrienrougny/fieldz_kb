"""Pylpg session for fieldz_kb.

Provides a Session class that wraps a pylpg.Session and adds
higher-level methods for saving and retrieving fieldz objects.
"""

import typing

import pylpg.session
from pylpg.node import Node

from fieldz_kb.lpg.pylpg.core import (
    BaseNode,
    _default_context,
)


class Session:
    """Session for saving and retrieving fieldz objects via pylpg.

    Wraps a pylpg.Session internally. Use as a context manager.

    Example:
        >>> from fieldz_kb.lpg.neo4j.pylpg import Session, Neo4jBackend
        >>> backend = Neo4jBackend(hostname="localhost")
        >>> with Session(backend) as session:
        ...     session.save_from_object(person)
    """

    def __init__(self, backend):
        """Initialize the session with a pylpg backend.

        Args:
            backend: A pylpg backend instance (Neo4jBackend, FalkorDBBackend, etc.)
        """
        self._pylpg_session = pylpg.session.Session(backend)
        self._context = _default_context

    def __enter__(self):
        self._pylpg_session.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._pylpg_session.__exit__(exc_type, exc_val, exc_tb)

    def execute_query(self, query, params=None, resolve_objects=False):
        """Execute a Cypher query against the database.

        Args:
            query: The Cypher query string.
            params: Optional query parameters.
            resolve_objects: Whether to resolve results as node objects.

        Returns:
            Query results as a list of dicts.
        """
        return self._pylpg_session.execute_query(
            query, parameters=params, resolve_nodes=resolve_objects
        )

    def save_from_object(
        self,
        object_,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration=None,
    ):
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
        objects,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration=None,
    ):
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
        all_to_connect = []
        for object_ in objects:
            nodes, to_connect = self._context.make_nodes_from_object(
                object_, integration_mode, exclude_from_integration, object_to_node
            )
            for node in nodes:
                if id(node) not in saved_node_ids:
                    if not isinstance(node, BaseNode):
                        raise ValueError(
                            f"node type {type(node)} must be a subclass of BaseNode"
                        )
                    self._pylpg_session.save(node)
                    saved_node_ids.add(id(node))
            all_to_connect += to_connect
        for source_node, rel_class, target_node, properties in all_to_connect:
            rel = rel_class(source=source_node, target=target_node, **properties)
            self._pylpg_session.save(rel)

    def make_object_from_node(self, node, node_id_to_object=None):
        """Convert a pylpg node back to a Python object.

        Args:
            node: The pylpg node to convert.
            node_id_to_object: Optional cache mapping node database IDs to objects.

        Returns:
            The reconstructed Python object.

        Raises:
            ValueError: If the node type cannot be mapped to a Python class.
        """
        return self._context.make_object_from_node(node, node_id_to_object)

    def execute_query_as_objects(self, query, params=None, node_id_to_object=None):
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
        results = self.execute_query(query, params=params, resolve_objects=True)
        for row_dict in results:
            row = [
                self._context.make_object_from_node(
                    value, node_id_to_object=node_id_to_object
                )
                for value in row_dict.values()
                if isinstance(value, Node)
            ]
            object_results.append(row)
        return object_results

    def delete_all(self):
        """Delete all nodes and relationships from the database."""
        self.execute_query("MATCH (n) DETACH DELETE n")
