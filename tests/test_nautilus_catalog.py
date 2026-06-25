import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class NautilusCatalogConfigTests(unittest.TestCase):
    def test_missing_required_environment_variable_raises_clear_error(self):
        from data.nautilus_catalog import catalog_config_from_env

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {},
            clear=True,
        ), patch("os.getcwd", return_value=directory):
            with self.assertRaisesRegex(RuntimeError, "CATALOG_S3_ENDPOINT"):
                catalog_config_from_env()

    def test_catalog_config_uses_minio_path_style_options(self):
        from data.nautilus_catalog import catalog_config_from_env

        env = {
            "CATALOG_S3_ENDPOINT": "http://minio.local:9000",
            "CATALOG_S3_ACCESS_KEY": "access",
            "CATALOG_S3_SECRET_KEY": "secret",
            "CATALOG_OUTPUT_S3_BUCKET": "custom-bucket",
        }

        with patch.dict(os.environ, env, clear=True):
            config = catalog_config_from_env()

        self.assertEqual(config.bucket, "custom-bucket")
        self.assertEqual(config.fs_protocol, "s3")
        self.assertEqual(config.fs_storage_options["key"], "access")
        self.assertEqual(config.fs_storage_options["secret"], "secret")
        self.assertEqual(
            config.fs_storage_options["client_kwargs"]["endpoint_url"],
            "http://minio.local:9000",
        )
        self.assertEqual(
            config.fs_storage_options["config_kwargs"],
            {"s3": {"addressing_style": "path"}},
        )
        self.assertEqual(
            config.fs_rust_storage_options["endpoint_url"],
            "http://minio.local:9000",
        )
        self.assertEqual(config.fs_rust_storage_options["allow_http"], "true")
        self.assertEqual(
            config.fs_rust_storage_options["virtual_hosted_style_request"],
            "false",
        )

    def test_catalog_config_loads_dotenv_from_current_project(self):
        from data.nautilus_catalog import catalog_config_from_env

        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "CATALOG_S3_ENDPOINT=http://dotenv.local:9000",
                        "CATALOG_S3_ACCESS_KEY=dotenv-access",
                        "CATALOG_S3_SECRET_KEY=dotenv-secret",
                        "CATALOG_OUTPUT_S3_BUCKET=dotenv-bucket",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True), patch("os.getcwd", return_value=directory):
                config = catalog_config_from_env()

        self.assertEqual(config.bucket, "dotenv-bucket")
        self.assertEqual(
            config.fs_storage_options["client_kwargs"]["endpoint_url"],
            "http://dotenv.local:9000",
        )


if __name__ == "__main__":
    unittest.main()
