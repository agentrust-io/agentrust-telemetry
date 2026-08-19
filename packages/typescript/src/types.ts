export type Scalar = string | number | boolean;
export type NormalizedEvent = Record<string, unknown> & {
  spec_version: "0.1.0-dev";
  event_id: string;
  event_type: string;
  time_unix_nano: string;
  run_id: string;
  producer: {name: string; version: string; instance_id?: string};
};

export interface ContextIds {traceId: string; spanId: string}
export interface SpanEvent {name: string; attributes: Record<string, Scalar>; timestamp: [number, number]}
export interface SpanLike {
  spanContext(): {traceId: string; spanId: string; isRemote?: boolean; traceFlags: number};
  addEvent(name: string, attributes: Record<string, Scalar>, timestamp: [number, number]): unknown;
}
export interface LogEmitter {emit(record: Record<string, unknown>): void}
export interface EvidenceSink {append(event: NormalizedEvent): unknown}
export interface MetricEmitter {emit(event: NormalizedEvent): boolean}
