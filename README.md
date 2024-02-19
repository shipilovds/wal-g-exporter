# wal-g-exporter

wal-g-exporter is a Prometheus exporter for gathering WAL-G backup metrics for the PostgreSQL database.

## Features and limitations

#### Primary/Secondary Node Discovery

wal-g-exporter is aware of whether it is running on a primary instance or not. It will not collect and export metrics
for standby/follower instances and will become aware of a role change while running. This ensures that you
can always collect metrics from all exporters in the PostgreSQL cluster with no unwanted accumulation of
metrics between the exporters.

#### http/oneshot Modes

wal-g-exporter has two operating modes (`EXPORTER_OPS_MODE` environment variable):

- `http` - run an HTTP server on `EXPORTER_HTTP_PORT` to make metrics accessible, like most exporters. *Default*
- `oneshot` - write metrics to `EXPORTER_METRICS_FILE`. The service creates a metrics file and then shuts down.
In Docker, you can use a volume to save the file on disk. It can then be taken by [node-exporter](https://github.com/prometheus/node_exporter)
to serve your exporter metrics.

> Open [this link](https://github.com/prometheus/node_exporter#textfile-collector) to read more about the textfile collector.

## Configuration

The following environment variables can be used to configure wal-g-exporter.

| Variable Name         | Default Value          | Description                                                        |
|-----------------------|------------------------|--------------------------------------------------------------------|
| PGHOST                | localhost              | PostgreSQL host (set to '/var/run/postgresql/' to use unix socket) |
| PGPORT                | 5432                   | PostgreSQL port                                                    |
| PGUSER                | postgres               | PostgreSQL user                                                    |
| POSTGRES_DB           | postgres               | PostgreSQL database name                                           |
| POSTGRES_PASSWORD     |                        | PostgreSQL password (no default, must be set in env)               |
| PGSSLMODE             | allow                  | PostgreSQL SSL mode                                                |
| WAL_G_SCRAPE_INTERVAL | 60                     | Interval for scraping WAL-G metrics (for 'http' mode).             |
| EXPORTER_OPS_MODE     | http                   | Operation mode for the exporter ('http' or 'oneshot').             |
| EXPORTER_HTTP_PORT    | 9351                   | Port for HTTP service.                                             |
| EXPORTER_UNIT_NAME    | wal-g                  | Unit name for the exporter. Becomes a label on every metric.       |
| EXPORTER_METRICS_FILE | /prometheus/wal-g.prom | Path to the metrics file for Node exporter textfile collector.     |

## Metrics

| Metric name                           | Labels                     | Description                                                                                    |
| ------------------------------------- | ---------------------------| ---------------------------------------------------------------------------------------------- |
| walg_basebackup_count                 |                            | Number of basebackups stored on S3                                                             |
| walg_oldest_basebackup                |                            | Timestamp of the oldest basebackup                                                             |
| walg_newest_basebackup                |                            | Timestamp of the newest basebackup                                                             |
| walg_last_basebackup_duration         |                            | Duration in seconds of the last basebackup                                                     |
| walg_last_basebackup_throughput_bytes |                            | Throughput in bytes of the last basebackup                                                     |
| walg_wal_archive_count                |                            | Number of WAL archives stored on S3                                                            |
| walg_wal_archive_missing_count        |                            | Amount of missing WAL archives, will only be > 0 when `walg_wal_integrity_status` is `FAILURE` |
| walg_wal_integrity_status             | `OK`, `WARNING`, `FAILURE` | Can be `1` or `0`, while `1` means that the integrity_status is true                           |
| walg_last_upload                      | `basebackup`, `wal`        | Timestamp of the last upload to S3 of the respective label / file type                         |
| walg_s3_diskusage                     |                            | Disk usage on S3 in byte for all backup / archive objects related to this Postgres instance    |

> Every metric receives a label `unit` that can help you identify your instance if you use multiple on the host at the same time.
>> The `unit` label takes it's data from the `EXPORTER_UNIT_NAME` environment variable!

# Credits

- [thedatabaseme](https://github.com/thedatabaseme) - Fork source author
- [camptocamp](https://github.com/camptocamp) - Original project authors
