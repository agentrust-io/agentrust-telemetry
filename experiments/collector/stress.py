"""Queue pressure, in-flight collector loss and complete event projection checks."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from google.protobuf import json_format
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest, ExportLogsServiceResponse
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from agentrust_telemetry import OTelLogEmitter, SchemaValidator, TelemetryClient

from fidelity import any_value, check_delivery, check_projection
from run import BINARY_SHA, ROOT, port, wait_ready


def wait_until(predicate, description):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise TimeoutError(description)


def run(binary, output):
    if hashlib.sha256(binary.read_bytes()).hexdigest() != BINARY_SHA:
        raise ValueError("collector binary differs from pinned release")
    output.mkdir(parents=True, exist_ok=False)
    database = output / "observations.sqlite"
    with sqlite3.connect(database) as db:
        db.executescript("CREATE TABLE evidence(case_id TEXT,body TEXT);"
                         "CREATE TABLE attempts(case_id TEXT,event_id TEXT,body TEXT);"
                         "CREATE TABLE committed(case_id TEXT,event_id TEXT,PRIMARY KEY(case_id,event_id));")
    state = {}
    lock = threading.Lock()
    entered, release = threading.Event(), threading.Event()

    class Receiver(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            if self.headers.get('Content-Encoding') == 'gzip':
                raw = gzip.decompress(raw)
            request = ExportLogsServiceRequest()
            if 'json' in self.headers.get('Content-Type', ''):
                json_format.Parse(raw.decode('utf-8'), request)
            else:
                request.ParseFromString(raw)
            observations = [{"body": any_value(record.body), "event_name": record.event_name,
                             "timestamp_ns": str(record.time_unix_nano)}
                            for resource in request.resource_logs for scope in resource.scope_logs
                            for record in scope.log_records]
            with lock:
                case, mode = state['case'], state['mode']
                state['requests'] += 1
                first = state['requests'] == 1
            with sqlite3.connect(database) as db:
                db.executemany('INSERT INTO attempts VALUES (?,?,?)',
                               [(case, item['body']['event_id'], json.dumps(item)) for item in observations])
            if first and mode == 'queue_saturation':
                entered.set()
                if not release.wait(30):
                    raise TimeoutError('test never released blocked backend')
            with sqlite3.connect(database) as db:
                db.executemany('INSERT OR IGNORE INTO committed VALUES (?,?)',
                               [(case, item['body']['event_id']) for item in observations])
            if first and mode == 'inflight_restart':
                entered.set()
                if not release.wait(30):
                    raise TimeoutError('test never released lost acknowledgement')
            payload = ExportLogsServiceResponse().SerializeToString()
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-protobuf')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected after the collector is killed before the ACK.

    receiver = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
    receiver.daemon_threads = True
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    clean_env = {key: value for key, value in os.environ.items()
                 if key.lower() not in {'http_proxy', 'https_proxy', 'all_proxy'}}
    summaries = []

    def read_rows(table, column, case):
        with sqlite3.connect(database) as db:
            return [row[0] for row in db.execute(f'SELECT {column} FROM {table} WHERE case_id=? ORDER BY rowid', (case,))]

    try:
        for language in ('python', 'typescript'):
            for mode in ('queue_healthy', 'queue_saturation', 'inflight_restart', 'reorder'):
                case = f'{language}-{mode}'
                directory = output / case
                directory.mkdir()
                entered.clear()
                release.clear()
                with lock:
                    state.update(case=case, mode=mode, requests=0)
                number = port()
                queue = {'enabled': mode != 'reorder', 'num_consumers': 1,
                         'queue_size': 1, 'block_on_overflow': False}
                config = directory / 'collector.json'
                config.write_text(json.dumps({
                    'receivers': {'otlp': {'protocols': {'http': {'endpoint': f'127.0.0.1:{number}'}}}},
                    'exporters': {'otlp_http': {'endpoint': f'http://127.0.0.1:{receiver.server_port}',
                        'timeout': '30s', 'sending_queue': queue, 'retry_on_failure': {'enabled': False}}},
                    'service': {'telemetry': {'metrics': {'level': 'none'}}, 'pipelines': {
                        'logs': {'receivers': ['otlp'], 'exporters': ['otlp_http']}}}}, indent=2))
                count = 8 if mode.startswith('queue_') else (2 if mode == 'inflight_restart' else 3)
                events = []
                for index in range(count):
                    event = json.loads((ROOT / 'conformance/fixtures/valid/usage.json').read_text())
                    event['event_id'] = str(uuid4())
                    event['time_unix_nano'] = str(int(event['time_unix_nano']) + index)
                    events.append(event)
                if mode == 'reorder':
                    events.reverse()
                (directory / 'input.json').write_text(json.dumps(events))
                endpoint = f'http://127.0.0.1:{number}/v1/logs'

                def emit(items, phase):
                    if language == 'python':
                        class Evidence:
                            def append(self, item):
                                with sqlite3.connect(database) as db:
                                    db.execute('INSERT INTO evidence VALUES (?,?)', (case, json.dumps(item)))
                        provider = LoggerProvider()
                        provider.add_log_record_processor(SimpleLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, timeout=.25)))
                        client = TelemetryClient(SchemaValidator.bundled(), evidence_sink=Evidence(),
                                                 log_emitter=OTelLogEmitter(provider.get_logger('stress')))
                        try:
                            for item in items:
                                result = client.emit(item)
                                if not result.accepted or not result.evidence_persisted:
                                    raise AssertionError('local acceptance failed')
                            provider.force_flush()
                        finally:
                            provider.shutdown()
                    else:
                        input_path = directory / f'{phase}-input.json'
                        evidence_path = directory / f'{phase}-evidence.ndjson'
                        input_path.write_text(json.dumps(items))
                        with (directory / f'{phase}-emitter.log').open('wb') as log:
                            subprocess.run(['node', str(Path(__file__).with_name('emit.mjs')), endpoint,
                                str(input_path), str(evidence_path), '250'], check=True, timeout=30,
                                env=clean_env, stdout=log, stderr=subprocess.STDOUT)
                        with sqlite3.connect(database) as db:
                            db.executemany('INSERT INTO evidence VALUES (?,?)',
                                [(case, line) for line in evidence_path.read_text().splitlines()])

                with (directory / 'collector.log').open('wb') as log:
                    def start():
                        child = subprocess.Popen([str(binary), '--config', str(config)], stdout=log,
                                                 stderr=subprocess.STDOUT, env=clean_env)
                        try:
                            wait_ready(number, child)
                        except BaseException:
                            child.kill()
                            child.wait(timeout=5)
                            raise
                        return child
                    process = start()
                    try:
                        if mode == 'queue_healthy':
                            for index, event in enumerate(events):
                                emit([event], str(index))
                                wait_until(lambda: event['event_id'] in read_rows('committed', 'event_id', case), 'healthy queue drain')
                        elif mode == 'inflight_restart':
                            emit(events[:1], 'before')
                            if not entered.wait(5):
                                raise TimeoutError('backend did not reach committed-before-ACK boundary')
                            process.kill()
                            process.wait(timeout=5)
                            release.set()
                            process = start()
                            emit(events[1:], 'after')
                        elif mode == 'queue_saturation':
                            emit(events[:1], 'seed')
                            if not entered.wait(5):
                                raise TimeoutError('saturation never blocked a consumer')
                            emit(events[1:], 'pressure')
                            release.set()
                        else:
                            emit(events, 'all')
                        minimum = 1 if mode == 'queue_saturation' else len(events)
                        wait_until(lambda: len(read_rows('committed', 'event_id', case)) >= minimum, f'{case}: backend completion (see SQLite observations)')
                    finally:
                        release.set()
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                if mode == 'queue_saturation' and 'sending queue is full' not in (directory / 'collector.log').read_text():
                    raise AssertionError(f'{case}: collector did not report queue overflow')
                observations = [json.loads(body) for body in read_rows('attempts', 'body', case)]
                evidence = [json.loads(body) for body in read_rows('evidence', 'body', case)]
                evidence_count = len(evidence)
                if mode == 'reorder' and [item['event_id'] for item in evidence] != [item['event_id'] for item in events]:
                    raise AssertionError(f'{case}: local evidence did not retain reversed input order')
                attempts = read_rows('attempts', 'event_id', case)
                commits = read_rows('committed', 'event_id', case)
                check_projection(events, observations)
                check_delivery(mode, events, evidence_count, attempts, commits)
                summaries.append({'case': case, 'evidence': evidence_count, 'attempts': len(attempts),
                                  'committed': len(commits), 'body_and_timestamp_fidelity': True,
                                  'submitted_ids': [item['event_id'] for item in events], 'observed_ids': attempts})
                (output / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
    finally:
        release.set()
        receiver.shutdown()
        receiver.server_close()
        thread.join(timeout=5)
    return summaries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collector', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.collector.resolve(), args.output.resolve()), indent=2))
