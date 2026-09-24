import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from evoagent.store import TaskStore


class TaskStoreResourceTests(unittest.TestCase):
    def test_connections_are_closed_after_each_operation(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        connections = []
        real_connect = sqlite3.connect

        def tracked_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connections.append(connection)
            return connection

        try:
            with mock.patch("evoagent.store.sqlite3.connect", side_effect=tracked_connect):
                store = TaskStore(path)
                store.get("missing-task")

            self.assertEqual(len(connections), 2)
            for connection in connections:
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute("SELECT 1")
        finally:
            for connection in connections:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
