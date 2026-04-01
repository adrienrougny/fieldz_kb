"""Neomodel session for fieldz_kb.

Provides a Session class that wraps neomodel's global database state
and adds higher-level methods for saving and retrieving fieldz objects.
"""

import typing

import neomodel
import neo4j

from fieldz_kb.lpg.neo4j.neomodel.core import (
    BaseNode,
    _default_context,
)


class Session:
    """Session for saving and retrieving fieldz objects via neomodel.

    Wraps neomodel's global database connection. Use as a context manager.

    Example:
        >>> from fieldz_kb.lpg.neo4j.neomodel import Session, NeomodelBackend
        >>> backend = NeomodelBackend(hostname="localhost", username="neo4j", password="neo4j")
        >>> with Session(backend) as session:
        ...     session.save_from_object(person)
    """

    def __init__(self, backend):
        """Initialize the session with a NeomodelBackend.

        Args:
            backend: A NeomodelBackend instance with connection parameters.
        """
        self._backend = backend
        self._driver = None
        self._context = _default_context

    def __enter__(self):
        uri = f"{self._backend.protocol}://{self._backend.hostname}:{self._backend.port}"
        notifications_min_severity = self._backend.notifications_min_severity
        if notifications_min_severity is not None:
            notifications_min_severity = neo4j.NotificationMinimumSeverity[
                notifications_min_severity.upper()
            ]
        self._driver = neo4j.GraphDatabase().driver(
            uri,
            auth=(self._backend.username, self._backend.password),
            notifications_min_severity=notifications_min_severity,
        )
        neomodel.db.set_connection(driver=self._driver)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._driver is not None:
            self._driver.close()
            self._driver = None
        return False

    def execute_query(self, query, params=None, resolve_objects=False):
        """Execute a Cypher query against the Neo4j database.

        Args:
            query: The Cypher query string.
            params: Optional query parameters.
            resolve_objects: Whether to resolve results as neomodel objects.

        Returns:
            A tuple of (results, meta) where results is a list of rows.
        """
        return neomodel.db.cypher_query(
            query=query, params=params, resolve_objects=resolve_objects
        )

    def save_from_object(
        self,
        object_,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration=None,
    ):
        """Save a single object to Neo4j.

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

    @neomodel.db.transaction
    def save_from_objects(
        self,
        objects,
        integration_mode: typing.Literal["hash", "id"] = "id",
        exclude_from_integration=None,
    ):
        """Save multiple objects to Neo4j in a single transaction.

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
                    node.save()
                    saved_node_ids.add(id(node))
            for (
                source_node,
                source_node_class_attr_name,
                target_node,
                properties,
            ) in to_connect:
                getattr(source_node, source_node_class_attr_name).connect(
                    target_node, properties=properties
                )

    def make_object_from_node(self, node, node_element_id_to_object=None):
        """Convert a Neo4j node back to a Python object.

        Args:
            node: The Neo4j node to convert.
            node_element_id_to_object: Optional cache mapping node element IDs to objects.

        Returns:
            The reconstructed Python object.

        Raises:
            ValueError: If the node type cannot be mapped to a Python class.
        """
        return self._context.make_object_from_node(node, node_element_id_to_object)

    def execute_query_as_objects(
        self, query, params=None, node_element_id_to_object=None
    ):
        """Execute a Cypher query and convert results to Python objects.

        Args:
            query: The Cypher query string.
            params: Optional query parameters.
            node_element_id_to_object: Optional cache mapping node element IDs to objects.

        Returns:
            A list of rows, where each row is a list of Python objects
            converted from neomodel node instances in the query results.
        """
        if node_element_id_to_object is None:
            node_element_id_to_object = {}
        object_results = []
        results, meta = self.execute_query(
            query, params=params, resolve_objects=True
        )
        for row in results:
            row = [
                self._context.make_object_from_node(
                    _, node_element_id_to_object=node_element_id_to_object
                )
                for _ in row
                if isinstance(_, neomodel.StructuredNode)
            ]
            object_results.append(row)
        return object_results

    def delete_all(self):
        """Delete all nodes and relationships from the database."""
        neomodel.db.cypher_query("MATCH (n) DETACH DELETE n")
