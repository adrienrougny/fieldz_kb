"""Neomodel backend for fieldz_kb.

Provides connection parameters for a neomodel-based Neo4j backend.
"""


class NeomodelBackend:
    """Backend configuration for neomodel-based Neo4j connections.

    This is a data holder for connection parameters. The Session
    uses these to establish the neomodel connection.

    Args:
        hostname: The Neo4j server hostname.
        username: The Neo4j username.
        password: The Neo4j password.
        protocol: The protocol to use (default: "neo4j").
        port: The port to connect to (default: "7687").
        notifications_min_severity: Minimum severity level for notifications.
    """

    def __init__(
        self,
        hostname="localhost",
        username="neo4j",
        password="neo4j",
        protocol="neo4j",
        port="7687",
        notifications_min_severity=None,
    ):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.protocol = protocol
        self.port = port
        self.notifications_min_severity = notifications_min_severity
