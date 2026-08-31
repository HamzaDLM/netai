# ClickHouse binary artifacts

Place the official ClickHouse Debian packages used by the deployment in this
directory. The default role configuration expects:

```text
clickhouse-common-static_26.3.17.110_amd64.deb
clickhouse-client_26.3.17.110_amd64.deb
clickhouse-server_26.3.17.110_amd64.deb
```

For ARM64 hosts, use the same filenames with `arm64` in place of `amd64`. Only
the three packages matching the managed host's architecture are copied and
installed. They are intentionally ordered common-static, client, then server so
their local package dependencies are satisfied without an external repository.

When changing packages, update `netai_clickhouse_version`. For an additional
integrity check, populate `netai_clickhouse_deb_sha256` with package filenames
and their expected lowercase SHA-256 digests in inventory or Tower/AWX.
