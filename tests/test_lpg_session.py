"""Unit tests for fieldz_kb.lpg.session.Session that don't require a live database."""

import unittest.mock

import fieldz_kb.lpg.session


class TestExecuteQuery:
    """Tests for Session.execute_query argument forwarding."""

    def test_resolve_nodes_defaults_to_false(self):
        """The default must preserve the previous raw-result behaviour."""
        backend = unittest.mock.MagicMock()
        session = fieldz_kb.lpg.session.Session(backend)
        mock_pylpg_session = unittest.mock.MagicMock()
        session._pylpg_session = mock_pylpg_session

        session.execute_query("MATCH (n) RETURN n")

        mock_pylpg_session.execute_query.assert_called_once_with(
            "MATCH (n) RETURN n", parameters=None, resolve_nodes=False
        )

    def test_resolve_nodes_is_forwarded_to_pylpg(self):
        """resolve_nodes is a pass-through to the pylpg session."""
        backend = unittest.mock.MagicMock()
        session = fieldz_kb.lpg.session.Session(backend)
        mock_pylpg_session = unittest.mock.MagicMock()
        session._pylpg_session = mock_pylpg_session

        session.execute_query(
            "MATCH (n:Person) RETURN n", params={"x": 1}, resolve_nodes=True
        )

        mock_pylpg_session.execute_query.assert_called_once_with(
            "MATCH (n:Person) RETURN n", parameters={"x": 1}, resolve_nodes=True
        )


class TestDeleteAll:
    """Tests for Session.delete_all routing."""

    def test_delegates_to_pylpg_session_and_does_not_execute_query(self):
        """delete_all must call the underlying pylpg session, not raw Cypher.

        Raw "MATCH (n) DETACH DELETE n" leaves stale label-index entries on
        FalkorDB, producing phantom rows on subsequent label-projected queries.
        The pylpg backend's delete_all clears the label index correctly, so
        fieldz_kb must delegate to it.
        """
        backend = unittest.mock.MagicMock()
        session = fieldz_kb.lpg.session.Session(backend)
        mock_pylpg_session = unittest.mock.MagicMock()
        session._pylpg_session = mock_pylpg_session

        session.delete_all()

        mock_pylpg_session.delete_all.assert_called_once_with()
        assert mock_pylpg_session.execute_query.call_count == 0
