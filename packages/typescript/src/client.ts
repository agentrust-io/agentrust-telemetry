import {isSpanContextValid, trace} from "@opentelemetry/api";
import {hrTime, logRecord, spanAttributes} from "./projection.js";
import type {ContextIds, EvidenceSink, LogEmitter, MetricEmitter, NormalizedEvent, SpanLike} from "./types.js";
import {SchemaValidator} from "./validation.js";

export class ContextMismatchError extends Error {}
export interface EmitResult {accepted: true; spanEventEmitted: boolean; logEmitted: boolean; metricsEmitted: boolean; evidencePersisted: boolean; context?: ContextIds; projectionErrors: string[]}

export class TelemetryClient {
  constructor(readonly validator: SchemaValidator, readonly options: {spanResolver?: () => SpanLike | undefined; logEmitter?: LogEmitter; evidenceSink?: EvidenceSink; metricEmitter?: MetricEmitter} = {}) {}
  emit(event: NormalizedEvent): EmitResult {
    this.validator.validate(event);
    const span = this.options.spanResolver?.() ?? trace.getActiveSpan();
    const raw = span?.spanContext();
    const context = raw && isSpanContextValid(raw) ? {traceId: raw.traceId, spanId: raw.spanId} : undefined;
    if (context && event.trace_id !== undefined && event.trace_id !== context.traceId) throw new ContextMismatchError("event trace_id disagrees with active span");
    if (context && event.span_id !== undefined && event.span_id !== context.spanId) throw new ContextMismatchError("event span_id disagrees with active span");
    let evidencePersisted = false;
    if (this.options.evidenceSink) {this.options.evidenceSink.append(structuredClone(event)); evidencePersisted = true;}
    const projectionErrors: string[] = []; let spanEventEmitted = false; let logEmitted = false; let metricsEmitted = false;
    if (span && context) try {span.addEvent(event.event_type, spanAttributes(event), hrTime(event.time_unix_nano)); spanEventEmitted = true;} catch (error) {projectionErrors.push(failure("span", error));}
    if (this.options.logEmitter) try {this.options.logEmitter.emit(logRecord(event, context)); logEmitted = true;} catch (error) {projectionErrors.push(failure("log", error));}
    if (this.options.metricEmitter) try {metricsEmitted = this.options.metricEmitter.emit(structuredClone(event));} catch (error) {projectionErrors.push(failure("metric", error));}
    return {accepted: true, spanEventEmitted, logEmitted, metricsEmitted, evidencePersisted, ...(context ? {context} : {}), projectionErrors};
  }
}
function failure(kind: string, error: unknown): string {return `${kind} projection failed: ${error instanceof Error ? `${error.name}: ${error.message}` : String(error)}`;}
