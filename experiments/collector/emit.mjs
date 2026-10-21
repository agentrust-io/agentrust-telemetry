import fs from 'node:fs';
import {LoggerProvider, SimpleLogRecordProcessor} from '@opentelemetry/sdk-logs';
import {OTLPLogExporter} from '@opentelemetry/exporter-logs-otlp-http';
import {SchemaValidator, TelemetryClient} from '../../packages/typescript/dist/index.js';
const [endpoint, input, evidence] = process.argv.slice(2);
const provider = new LoggerProvider({processors: [new SimpleLogRecordProcessor(new OTLPLogExporter({url: endpoint}))]});
const logger = provider.getLogger('agentrust-collector-acceptance');
const client = new TelemetryClient(SchemaValidator.bundled(), {
  evidenceSink: {append(event) {
    const fd = fs.openSync(evidence, 'a');
    try {fs.writeSync(fd, JSON.stringify(event) + '\n'); fs.fsyncSync(fd);} finally {fs.closeSync(fd);}
  }},
  logEmitter: {emit(record) {logger.emit({body: record.body, eventName: record.event_name});}},
});
for (const event of JSON.parse(fs.readFileSync(input, 'utf8'))) {
  const result = client.emit(event);
  if (!result.accepted || !result.evidencePersisted || !result.logEmitted) throw new Error('Local acceptance failed');
  await provider.forceFlush();
}
await provider.shutdown();
