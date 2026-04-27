"""Unit tests for fieldz_kb.lpg.session.Session that don't require a live database."""

import unittest.mock

import fieldz_kb.lpg.session


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
