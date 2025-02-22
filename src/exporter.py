import logging
import os
import sys
import psycopg2
import time
import signal
import subprocess
import json
import datetime
import argparse
from decouple import Config, RepositoryEnv
from prometheus_client import start_http_server, CollectorRegistry, Gauge, write_to_textfile
from psycopg2.extras import DictCursor


class MyLogger:
    def __init__(self, name, level=logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.INFO)
        stdout_handler.setFormatter(formatter)
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.ERROR)
        stderr_handler.setFormatter(formatter)
        self.logger.addHandler(stdout_handler)
        self.logger.addHandler(stderr_handler)


class Decouwrapper():
    def __init__(self):
        self.__config = {}
        self.__read_config()

    def __read_envfile(self):
        parser = argparse.ArgumentParser(description='WAL-G exporter options')
        parser.add_argument('--envfile', type=str, help='Path to config.env file', default='./config.env')
        return parser.parse_args().envfile

    def __read_config(self):
        self.__config = Config(RepositoryEnv(self.__read_envfile()))

    def __call__(self, *args, **kwargs):
        return self.__config.get(*args, **kwargs)


terminate = False


def sigterm_handler(sig, frame):
    global terminate
    log.info('SIGTERM received, preparing to shut down...')
    terminate = True


class Database:
    """
    Represents a database connection context manager.

    Usage:
        with Database(db_config, cursor_factory=psycopg2.extras.DictCursor) as cursor:
            # Perform database operations using the cursor

    Args:
        db_config (dict): Database connection configuration (e.g., host, port, database, user, password).
        cursor_factory (type, optional): Cursor factory class (default: None).

    Returns:
        psycopg2.extensions.cursor: A cursor for executing SQL queries.
    """

    def __init__(self, db_config, cursor_factory=None):
        """
        Initialize a Database instance.

        Args:
            db_config (dict): Database connection configuration.
            cursor_factory (type, optional): Cursor factory class (default: None).
        """
        self.db_config = db_config
        self.cursor_factory = cursor_factory

    def __enter__(self):
        """
        Establish a database connection and return a cursor.

        Returns:
            psycopg2.extensions.cursor: A cursor for executing SQL queries.
        """
        self.conn = psycopg2.connect(**self.db_config)
        return self.conn.cursor(cursor_factory=self.cursor_factory)

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Clean up resources by committing any pending transactions and closing the connection.

        Args:
            exc_type: Exception type (if an exception occurred during execution).
            exc_value: Exception value (if an exception occurred during execution).
            traceback: Traceback information (if an exception occurred during execution).
        """
        self.conn.commit()
        self.conn.close()


class Exporter():
    """
    TODO: add docstrings
    """
    def __init__(self, db_connection_config, unit):
        self.log = MyLogger(self.__class__.__name__).logger
        self.unit = unit
        self.first_start = True
        self.db_connection_config = db_connection_config
        self.registry = CollectorRegistry()
        self.basebackup_count = Gauge('walg_basebackup_count',
                                      'Remote Basebackups count', ['unit'], registry=self.registry)
        self.oldest_basebackup = Gauge('walg_oldest_basebackup',
                                       'oldest full backup', ['unit'], registry=self.registry)
        self.newest_basebackup = Gauge('walg_newest_basebackup',
                                       'newest full backup', ['unit'], registry=self.registry)
        self.last_basebackup_duration = Gauge('walg_last_basebackup_duration',
                                              'Duration of the last basebackup in seconds',
                                              ['unit'], registry=self.registry)
        self.last_basebackup_throughput = Gauge('walg_last_basebackup_throughput_bytes',
                                                'Show the throuhput in bytes per second for the last backup',
                                                ['unit'],
                                                registry=self.registry)
        self.wal_archive_count = Gauge('walg_wal_archive_count',
                                       'Archived WAL count', ['unit'], registry=self.registry)
        self.wal_archive_missing_count = Gauge('walg_wal_archive_missing_count',
                                               'Missing WAL count', ['unit'], registry=self.registry)
        self.wal_integrity_status = Gauge('walg_wal_integrity_status',
                                          'Overall WAL archive integrity status',  ['unit', 'status'], registry=self.registry)
        self.last_upload = Gauge('walg_last_upload',
                                 'Last upload of incremental or full backup',  ['unit', 'type'], registry=self.registry)
        self.s3_diskusage = Gauge('walg_s3_diskusage',
                                  'Usage of S3 storage in bytes', ['unit'], registry=self.registry)

    def start_http(self, http_port):
        return start_http_server(http_port, registry=self.registry)

    # Fetch current basebackups located on S3
    def update_basebackup(self):

        self.log.info('Updating basebackup metrics...')
        try:
            # Fetch remote backup list
            res = subprocess.run(["wal-g", "backup-list",
                                  "--detail", "--json"],
                                 capture_output=True, check=True)

        except subprocess.CalledProcessError as e:
            self.log.error(str(e))

        if res.stdout.decode("utf-8") == "":
            basebackup_list = []
        else:
            basebackup_list = list(json.loads(res.stdout))
            basebackup_list.sort(key=lambda basebackup: basebackup['start_time'])

        # Update backup list and export metrics
        if (len(basebackup_list) > 0):
            self.log.info("%s basebackups found (first: %s, last: %s)",
                          len(basebackup_list),
                          basebackup_list[0]['start_time'],
                          basebackup_list[len(basebackup_list) - 1]['start_time'])
            # We need to convert the start_time to a timestamp
            oldest_basebackup_timestamp = datetime.datetime.strptime(basebackup_list[0]['start_time'],
                                                                     "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
            newest_basebackup_timestamp = datetime.datetime.strptime(basebackup_list[len(basebackup_list) - 1]['start_time'],
                                                                     "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
            last_backup = basebackup_list[len(basebackup_list) - 1]
            finish_time = datetime.datetime.strptime(last_backup['finish_time'], "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
            start_time = datetime.datetime.strptime(last_backup['start_time'], "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
            last_basebackup_duration = finish_time - start_time
            last_basebackup_throughput = basebackup_list[len(basebackup_list) - 1]['compressed_size'] / last_basebackup_duration

            self.log.info(f"Last basebackup duration: {last_basebackup_duration}")

            # Set basebackup count, oldest and newest timestamp
            self.basebackup_count.labels(self.unit).set(len(basebackup_list))
            self.oldest_basebackup.labels(self.unit).set(oldest_basebackup_timestamp)
            self.newest_basebackup.labels(self.unit).set(newest_basebackup_timestamp)
            self.last_upload.labels(self.unit, 'basebackup').set(newest_basebackup_timestamp)
            self.last_basebackup_duration.labels(self.unit).set(last_basebackup_duration)
            self.last_basebackup_throughput.labels(self.unit).set(last_basebackup_throughput)

            self.log.info('Finished updating basebackup metrics...')
        else:
            self.log.info("No basebackups found")
            self.basebackup_count.labels(self.unit).set(0)
            self.oldest_basebackup.labels(self.unit).set(0)
            self.newest_basebackup.labels(self.unit).set(0)

    # Fetch WAL archives located on S3
    def update_wal_archive(self):

        self.log.info('Updating WAL archive metrics...')
        try:
            # Fetch remote archive list
            res = subprocess.run(["wal-g", "wal-verify", "integrity", "--json"],
                                 capture_output=True, check=True)

        except subprocess.CalledProcessError as e:
            self.log.error(str(e))

        # Check json output of wal-g for the integrity status
        if res.stdout.decode("utf-8") == "":
            wal_archive_list = []
            wal_archive_integrity_status = []
        else:
            wal_archive_list = list(json.loads(res.stdout)["integrity"]["details"])
            wal_archive_list.sort(key=lambda walarchive: walarchive['timeline_id'])
            wal_archive_integrity_status = json.loads(res.stdout)["integrity"]["status"]

        wal_archive_count = 0
        wal_archive_missing_count = 0

        if (len(wal_archive_list) > 0):
            # Update WAL archive list and export metrics
            # Count found and missing WAL archives
            for timelines in wal_archive_list:
                if timelines['status'] == 'FOUND':
                    wal_archive_count = wal_archive_count + timelines['segments_count']
                else:
                    wal_archive_missing_count = wal_archive_missing_count + timelines['segments_count']

            # Get archive status from database
            archive_status = self.get_archive_status()

            # Log WAL informations
            self.log.info(f"WAL integrity status is: {wal_archive_integrity_status}")
            self.log.info("Found %s WAL archives in %s timelines, %s WAL archives missing",
                          wal_archive_count, len(wal_archive_list), wal_archive_missing_count)

            # Update all WAL related metrics
            # Check for the integrity status and set the metrics accordingly
            # first set default statuses:
            self.wal_integrity_status.labels(self.unit, 'OK').set(0)
            self.wal_integrity_status.labels(self.unit, 'WARNING').set(0)
            self.wal_integrity_status.labels(self.unit, 'FAILURE').set(0)
            # then set the real one:
            self.wal_integrity_status.labels(self.unit, wal_archive_integrity_status).set(1)

            self.wal_archive_count.labels(self.unit).set(wal_archive_count)
            self.wal_archive_missing_count.labels(self.unit).set(wal_archive_missing_count)
            # There is a case when database just started and there is no archives, so we got None here
            # Let's skip it then
            if archive_status is not None:
                self.last_upload.labels(self.unit, 'wal').set(archive_status['last_archived_time'].timestamp())

            self.log.info('Finished updating WAL archive metrics...')
        else:
            self.log.info("No WAL archives found")
            self.wal_archive_count.labels(self.unit).set(0)

    # Fetch S3 object list for disk usage calculation
    def update_s3_disk_usage(self):

        self.log.info('Updating S3 disk usage...')
        try:
            # Fetch remote object list
            res = subprocess.run(["wal-g", "st", "ls", "-r"], capture_output=True, check=True)

        except subprocess.CalledProcessError as e:
            self.log.error(str(e))

        # Check output of S3 ls command
        if res.stdout.decode("utf-8") == "":
            s3_object_list = []
        else:
            s3_object_list = res.stdout.decode().split('\n')[1:]

        s3_diskusage = 0

        # Loop through the list of all objects and count the size
        if (len(s3_object_list) > 0):
            for s3_object in s3_object_list:
                if s3_object.strip():
                    s3_object = s3_object.split(' ')
                    s3_diskusage = s3_diskusage + int(s3_object[2])

            self.log.info(f"S3 diskusage in bytes: {s3_diskusage}")

            self.s3_diskusage.labels(self.unit).set(s3_diskusage)

            self.log.info('Finished updating S3 metrics...')
        else:
            self.log.info("No S3 objects found")
            self.s3_diskusage.labels(self.unit).set(0)

    def get_archive_status(self):
        with Database(self.db_connection_config, cursor_factory=DictCursor) as pg_cursor:
            try:
                pg_cursor.execute('SELECT archived_count, failed_count, '
                                  'last_archived_wal, '
                                  'last_archived_time, '
                                  'last_failed_wal, '
                                  'last_failed_time '
                                  'FROM pg_stat_archiver')
                pg_archive_status = pg_cursor.fetchone()
                if not bool(pg_archive_status) or not pg_archive_status[0]:
                    self.log.warning("Cannot fetch archive status")
                else:
                    return pg_archive_status
            except Exception as e:
                self.log.error("Unable to fetch archive status from pg_stat_archiver")
                raise Exception(f"Unable to fetch archive status from pg_stat_archiver {str(e)}")

    def update_metrics(self):
        with Database(self.db_connection_config) as pg_cursor:
            try:
                pg_cursor.execute("SELECT NOT pg_is_in_recovery()")
                pg_is_primary = pg_cursor.fetchone()
                self.log.info(f"Is NOT in recovery mode? {pg_is_primary[0]}")
                if bool(pg_is_primary) and pg_is_primary[0]:
                    self.log.info("Connected to primary database")
                    self.log.info("Evaluating wal-g backups...")
                    self.update_basebackup()
                    self.update_wal_archive()
                    self.update_s3_disk_usage()
                    self.log.info("All metrics collected. Waiting for next update cycle...")
                else:
                    # If the exporter had run before and run on a replica suddenly, there was
                    # potentially a failover. So we kill our own process and start from scratch
                    if not self.first_start:
                        self.log.info("Potential failover detected. Clearing old metrics. Stopping exporter.")
                        os.kill(os.getpid(), signal.SIGTERM)
                    self.log.info("Running on replica, waiting for promotion...")
            except Exception as e:
                self.log.error("Unable to execute SELECT NOT pg_is_in_recovery()")
                raise Exception(f"Unable to execute SELECT NOT pg_is_in_recovery() {str(e)}")

    def write_metrics_to_file(self, metrics_file):
        write_to_textfile(metrics_file, self.registry)
        self.log.info(f"Metrics file {metrics_file} successfully updated")


if __name__ == '__main__':
    log = MyLogger("Main").logger
    log.info("Startup...")
    log.info(f"My PID is: {os.getpid()}")

    # Register the signal handler for SIGTERM
    signal.signal(signal.SIGTERM, sigterm_handler)

    log.info("Reading environment configuration")
    config = Decouwrapper()

    # Read configuration from ENV
    wal_g_scrape_interval = int(config('WAL_G_SCRAPE_INTERVAL', default=60))
    http_port = int(config('EXPORTER_HTTP_PORT', default=9351))
    exporter_ops_mode = config('EXPORTER_OPS_MODE', default='http')
    unit = config('EXPORTER_UNIT_NAME', default='wal-g')
    metrics_file = config('EXPORTER_METRICS_FILE', default=f"/prometheus/walg-{unit}.prom")

    # Postgres config dict
    db_connection_config = {
        'host': config('PGHOST', default='localhost'),
        'port': config('PGPORT', default=5432),
        'user': config('PGUSER', default='postgres'),
        'password': config('POSTGRES_PASSWORD'),
        'dbname': config('POSTGRES_DB', default='postgres'),
        'sslmode': config('PGSSLMODE', default='allow')}

    log.info("Starting exporter...")
    exporter = Exporter(db_connection_config, unit)
    if exporter_ops_mode == 'http':
        # Start up the server to expose the metrics.
        http_server = exporter.start_http(http_port)
        log.info(f"Webserver started on port {http_port}")

    # Check if this is a primary instance
    # with while True and try catch this is how reconnect already should work.
    while True:

        if terminate:
            log.info("Received SIGTERM, shutting down...")
            break

        try:
            exporter.update_metrics()
            # To recognize a later failover, we set first_start = False now
            exporter.first_start = False
            if exporter_ops_mode == 'oneshot':
                log.info("\"Oneshot\" type of run")
                # write metrics to file and exit
                exporter.write_metrics_to_file(metrics_file)
                log.info("Exiting after successful metrics fetch...")
                break
            time.sleep(wal_g_scrape_interval)
        except Exception as e:
            if terminate:
                log.info("Received SIGTERM during exception, shutting down...")
                break
            log.error(f"Error occured, retrying in 60sec... {str(e)}")
            time.sleep(wal_g_scrape_interval)
