from __future__ import annotations

import importlib
import os
import socket
import sys
import threading
import time
import types
import unittest


class _FakeAlembicConfig:
    def __init__(self, filename):
        self.filename = filename
        self.options = {}

    def set_main_option(self, name, value):
        self.options[name] = value


class CloudRuntimeTests(unittest.TestCase):
    def test_migrates_and_starts_private_api_once(self):
        migrations = []

        command_module = types.SimpleNamespace(
            upgrade=lambda config, revision: migrations.append((config, revision))
        )
        alembic_module = types.ModuleType("alembic")
        alembic_module.command = command_module
        alembic_config_module = types.ModuleType("alembic.config")
        alembic_config_module.Config = _FakeAlembicConfig

        fake_app_module = types.ModuleType("investment_engine.api.app")
        fake_app_module.app = object()

        class FakeConfig:
            def __init__(self, app, host, port, **kwargs):
                self.app = app
                self.host = host
                self.port = port

        class FakeServer:
            def __init__(self, config):
                self.config = config

            def run(self):
                with socket.socket() as listener:
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    listener.bind((self.config.host, self.config.port))
                    listener.listen()
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        listener.settimeout(0.1)
                        try:
                            connection, _ = listener.accept()
                            connection.close()
                        except TimeoutError:
                            pass

        uvicorn_module = types.ModuleType("uvicorn")
        uvicorn_module.Config = FakeConfig
        uvicorn_module.Server = FakeServer

        with socket.socket() as temporary:
            temporary.bind(("127.0.0.1", 0))
            port = temporary.getsockname()[1]

        original_modules = {
            name: sys.modules.get(name)
            for name in ("alembic", "alembic.config", "uvicorn", "investment_engine.api.app")
        }
        try:
            sys.modules["alembic"] = alembic_module
            sys.modules["alembic.config"] = alembic_config_module
            sys.modules["uvicorn"] = uvicorn_module
            sys.modules["investment_engine.api.app"] = fake_app_module

            os.environ["DATABASE_URL"] = "postgresql+psycopg://test"
            os.environ["DATABASE_ADMIN_URL"] = "postgresql+psycopg://admin-test"
            os.environ["EMBEDDED_API_ENABLED"] = "true"
            os.environ["EMBEDDED_API_HOST"] = "127.0.0.1"
            os.environ["EMBEDDED_API_PORT"] = str(port)

            import investment_engine.cloud_runtime as cloud_runtime

            cloud_runtime = importlib.reload(cloud_runtime)
            cloud_runtime.ensure_cloud_runtime()
            first_thread = cloud_runtime._API_THREAD
            cloud_runtime.ensure_cloud_runtime()

            self.assertEqual(len(migrations), 1)
            self.assertEqual(migrations[0][1], "head")
            self.assertEqual(
                os.environ["DATABASE_URL"], "postgresql+psycopg://test"
            )
            self.assertEqual(
                os.environ["DATABASE_ADMIN_URL"],
                "postgresql+psycopg://admin-test",
            )
            self.assertIs(cloud_runtime._API_THREAD, first_thread)
            self.assertTrue(cloud_runtime._port_is_open("127.0.0.1", port))
        finally:
            os.environ.pop("DATABASE_ADMIN_URL", None)
            for name, previous in original_modules.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous


if __name__ == "__main__":
    unittest.main()
