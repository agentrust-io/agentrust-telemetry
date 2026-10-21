"""Real OTLP collector experiment, synthetic events and a local SQLite observer."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from google.protobuf import json_format
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest, ExportLogsServiceResponse,
)
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from agentrust_telemetry import OTelLogEmitter, SchemaValidator, TelemetryClient

ROOT = Path(__file__).resolve().parents[2]
BINARY_SHA = 'd4fa834fae73cb37e6058955a3833894d1ec815a1fc3529b0c2aaa99d8b22a2e'


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def wait_ready(number, process):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('collector exited; inspect collector.log')
        try:
            with socket.create_connection(('127.0.0.1', number), timeout=.1):
                return
        except OSError:
            time.sleep(.02)
    raise TimeoutError('collector readiness')


def run(binary, out):
    if hashlib.sha256(binary.read_bytes()).hexdigest() != BINARY_SHA:
        raise ValueError('collector binary digest differs from pinned 0.163.2 Linux amd64')
    out.mkdir(parents=True, exist_ok=False)
    database = out / 'observations.sqlite'
    with sqlite3.connect(database) as db:
        db.executescript('CREATE TABLE attempts(case_id TEXT,event_id TEXT);'
                         'CREATE TABLE committed(case_id TEXT,event_id TEXT, PRIMARY KEY(case_id,event_id));'
                         'CREATE TABLE evidence(case_id TEXT,event_id TEXT,body TEXT);')
    state = {'case': '', 'mode': '', 'requests': 0}
    lock = threading.Lock()

    class Receiver(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            if self.headers.get('Content-Encoding') == 'gzip':
                body = gzip.decompress(body)
            request = ExportLogsServiceRequest()
            if 'json' in self.headers.get('Content-Type', ''):
                json_format.Parse(body.decode(), request)
            else:
                request.ParseFromString(body)
            ids = [next(v.value.string_value for v in record.body.kvlist_value.values
                        if v.key == 'event_id')
                   for resource in request.resource_logs for scope in resource.scope_logs
                   for record in scope.log_records]
            with lock:
                case, mode = state['case'], state['mode']
                state['requests'] += 1
                number = state['requests']
            with sqlite3.connect(database) as db:
                db.executemany('INSERT INTO attempts VALUES (?,?)', [(case, i) for i in ids])
                if not (mode == 'partial' or (mode == 'retry' and number == 1)):
                    db.executemany('INSERT OR IGNORE INTO committed VALUES (?,?)', [(case, i) for i in ids])
            if mode == 'lost_ack' and number == 1:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            response = ExportLogsServiceResponse()
            if mode == 'partial':
                response.partial_success.rejected_log_records = len(ids)
                response.partial_success.error_message = 'synthetic controlled refusal'
            payload = response.SerializeToString()
            self.send_response(503 if mode == 'retry' and number == 1 else 200)
            self.send_header('Content-Type', 'application/x-protobuf')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    receiver = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    summaries = []
    clean_env = {k: v for k, v in os.environ.items()
                 if k.lower() not in {'http_proxy', 'https_proxy', 'all_proxy'}}
    try:
        for language in ('python', 'typescript'):
            for mode in ('healthy', 'retry', 'lost_ack', 'partial', 'duplicate', 'restart'):
                case = f'{language}-{mode}'
                directory = out / case
                directory.mkdir()
                with lock:
                    state.update(case=case, mode=mode, requests=0)
                number = port()
                config = directory / 'collector.json'
                config.write_text(json.dumps({
                    'receivers': {'otlp': {'protocols': {'http': {'endpoint': f'127.0.0.1:{number}'}}}},
                    'exporters': {'otlp_http': {
                        'endpoint': f'http://127.0.0.1:{receiver.server_port}',
                        'sending_queue': {'enabled': False},
                        'retry_on_failure': {'enabled': True, 'initial_interval': '50ms',
                                             'max_interval': '100ms', 'max_elapsed_time': '1s'},
                    }},
                    'service': {'telemetry': {'metrics': {'level': 'none'}}, 'pipelines': {'logs': {'receivers': ['otlp'], 'exporters': ['otlp_http']}}},
                }, indent=2))
                event = json.loads((ROOT / 'conformance/fixtures/valid/usage.json').read_text())
                event['event_id'] = str(uuid4())
                events = [event, event] if mode == 'duplicate' else [event]
                (directory / 'input.json').write_text(json.dumps(events))
                with (directory / 'collector.log').open('wb') as log:
                    process = subprocess.Popen([str(binary), '--config', str(config)],
                                               stdout=log, stderr=subprocess.STDOUT, env=clean_env)
                    try:
                        wait_ready(number, process)
                        if mode == 'restart':
                            process.terminate(); process.wait(timeout=5)
                            process = subprocess.Popen([str(binary), '--config', str(config)],
                                                       stdout=log, stderr=subprocess.STDOUT, env=clean_env)
                            wait_ready(number, process)
                        endpoint = f'http://127.0.0.1:{number}/v1/logs'
                        if language == 'python':
                            class Evidence:
                                def append(self, item):
                                    with sqlite3.connect(database) as db:
                                        db.execute('INSERT INTO evidence VALUES (?,?,?)',
                                                   (case, item['event_id'], json.dumps(item)))
                            provider = LoggerProvider()
                            provider.add_log_record_processor(SimpleLogRecordProcessor(
                                OTLPLogExporter(endpoint=endpoint, timeout=4)))
                            client = TelemetryClient(SchemaValidator.bundled(), evidence_sink=Evidence(),
                                log_emitter=OTelLogEmitter(provider.get_logger('acceptance')))
                            try:
                                for item in events:
                                    result = client.emit(item)
                                    assert result.accepted and result.evidence_persisted and result.log_emitted
                                provider.force_flush()
                            finally:
                                provider.shutdown()
                        else:
                            with (directory / 'emitter.log').open('wb') as emitter_log:
                                subprocess.run(['node', str(Path(__file__).with_name('emit.mjs')), endpoint,
                                    str(directory / 'input.json'), str(directory / 'evidence.ndjson')],
                                    check=True, timeout=15, env=clean_env,
                                    stdout=emitter_log, stderr=subprocess.STDOUT)
                            rows = [json.loads(x) for x in (directory / 'evidence.ndjson').read_text().splitlines()]
                            with sqlite3.connect(database) as db:
                                db.executemany('INSERT INTO evidence VALUES (?,?,?)',
                                    [(case, x['event_id'], json.dumps(x)) for x in rows])
                    finally:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill(); process.wait()
                with sqlite3.connect(database) as db:
                    counts = {table: db.execute(f'SELECT count(*) FROM {table} WHERE case_id=?', (case,)).fetchone()[0]
                              for table in ('evidence', 'attempts', 'committed')}
                assert counts['evidence'] == len(events), (case, counts)
                assert counts['committed'] == (0 if mode == 'partial' else 1), (case, counts)
                assert counts['attempts'] >= (2 if mode in {'retry', 'lost_ack', 'duplicate'} else 1), (case, counts)
                summaries.append({'case': case, **counts})
                (out / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
    finally:
        receiver.shutdown(); receiver.server_close(); thread.join(timeout=5)
    return summaries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collector', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.collector.resolve(), args.output.resolve()), indent=2))
