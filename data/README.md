# Nautilus data import

這個目錄放 alpha experiments 讀取 homestack `nautilus-data` catalog 的流程與 helper。
來源文件在 `/opt/docker/docs/homestack/nautilus-catalog-builder.md`。

## Catalog 來源

| 項目 | 值 |
| --- | --- |
| S3 bucket | `nautilus-data` |
| Catalog prefix | bucket root |
| 已建置 symbols | `BNBUSDT.BINANCE`, `BTCUSDT.BINANCE`, `ETHUSDT.BINANCE` |
| 已建置 data types | `trade_tick`, `order_book_depths` |

這裡只讀取已經轉好的 Nautilus Trader Parquet catalog，不會觸發轉檔、不會寫入 S3，
也不需要連到 homestack Docker network。

## 環境變數

不要把實際 secret 寫進 repo。需要連線時在 shell 設定：

```bash
export CATALOG_S3_ENDPOINT="http://<minio-host>:9000"
export CATALOG_S3_ACCESS_KEY="<access-key>"
export CATALOG_S3_SECRET_KEY="<secret-key>"
export CATALOG_OUTPUT_S3_BUCKET="nautilus-data"
```

請使用只允許讀取 `nautilus-data` 的專用 credential。部署主機上的 reader
credential 由 homestack 的運維設定管理；請以
[`nautilus-catalog-builder` 運維文件](/opt/docker/docs/homestack/nautilus-catalog-builder.md)
為準，不要猜測或複製 credential，也不要使用 builder 或 archiver 的寫入 credential。

## 安裝相依套件

```bash
uv sync
```

## 在其他程式 import

```python
from data.nautilus_catalog import make_catalog
from nautilus_trader.model.data import OrderBookDepth10
from nautilus_trader.model.identifiers import InstrumentId


catalog = make_catalog()
instrument = InstrumentId.from_str("BTCUSDT.BINANCE")

trades = catalog.trade_ticks(
    instrument_ids=[instrument],
    start="2026-06-17T00:00:00Z",
    end="2026-06-17T00:01:00Z",
)

depths = catalog.query(
    OrderBookDepth10,
    identifiers=[str(instrument)],
    start="2026-06-17T00:00:00Z",
    end="2026-06-17T00:01:00Z",
)
```

`trades` 和 `depths` 都已經是 Nautilus Trader data objects，可以直接餵給
`BacktestEngine.add_data(...)`：

```python
engine.add_data(trades)
engine.add_data(depths)
```

## 注意事項

- MinIO/S3 需要 path-style request；helper 會保留 `addressing_style=path` 和
  `virtual_hosted_style_request=false`。
- 目前不要用 `ParquetDataCatalog.from_uri("s3://nautilus-data")`，這個環境的
  `s3fs` 組合會帶入不相容的 `host` option。
- `fs_rust_storage_options` 的 endpoint key 必須是 `endpoint_url`。
