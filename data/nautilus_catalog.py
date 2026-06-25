from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NautilusCatalogConfig:
    bucket: str
    fs_protocol: str
    fs_storage_options: dict[str, Any]
    fs_rust_storage_options: dict[str, str]


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _load_dotenv() -> None:
    env_path = Path(os.getcwd()) / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def catalog_config_from_env() -> NautilusCatalogConfig:
    _load_dotenv()

    endpoint = _required_env("CATALOG_S3_ENDPOINT")
    access_key = _required_env("CATALOG_S3_ACCESS_KEY")
    secret_key = _required_env("CATALOG_S3_SECRET_KEY")
    bucket = os.environ.get("CATALOG_OUTPUT_S3_BUCKET", "nautilus-data")

    return NautilusCatalogConfig(
        bucket=bucket,
        fs_protocol="s3",
        fs_storage_options={
            "key": access_key,
            "secret": secret_key,
            "client_kwargs": {"endpoint_url": endpoint},
            "config_kwargs": {"s3": {"addressing_style": "path"}},
        },
        fs_rust_storage_options={
            "endpoint_url": endpoint,
            "access_key_id": access_key,
            "secret_access_key": secret_key,
            "region": "us-east-1",
            "allow_http": "true",
            "virtual_hosted_style_request": "false",
        },
    )


def make_catalog():
    from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

    config = catalog_config_from_env()
    return ParquetDataCatalog(
        config.bucket,
        fs_protocol=config.fs_protocol,
        fs_storage_options=config.fs_storage_options,
        fs_rust_storage_options=config.fs_rust_storage_options,
    )
