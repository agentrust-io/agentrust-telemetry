import {createHash} from "node:crypto";
import canonicalize from "canonicalize";
import type {NormalizedEvent} from "./types.js";
import {SchemaValidator} from "./validation.js";

export type Completeness = "complete" | "incomplete" | "unknown";
export const CANONICALIZATION_PROFILE = "rfc8785-jcs-v1";
const GENESIS_DIGEST = Buffer.alloc(32);

export class EvidenceError extends Error {}
export class EvidencePersistenceError extends EvidenceError {}

export interface EvidenceEntry {
  sequence: number;
  eventId: string;
  previousDigest?: string;
  digest: string;
  event: NormalizedEvent;
}

export interface EvidenceSnapshot {
  runId: string;
  entries: readonly EvidenceEntry[];
  chainDigest?: string;
  canonicalizationProfile: typeof CANONICALIZATION_PROFILE;
  completeness: Completeness;
  sealed: boolean;
}

export type DurableAppend = (entry: EvidenceEntry) => boolean;

export class EvidenceAccumulator {
  readonly #entries: EvidenceEntry[] = [];
  readonly #eventIds = new Set<string>();
  #sealed = false;
  #completeness: Completeness = "unknown";
  #mutating = false;

  constructor(
    readonly runId: string,
    readonly validator: SchemaValidator,
    readonly options: {durableAppend?: DurableAppend; maxEvents?: number} = {},
  ) {
    if (!runId) throw new EvidenceError("runId must be a non-empty string");
    if ((options.maxEvents ?? 10_000) < 1) throw new EvidenceError("maxEvents must be at least 1");
  }

  get mode(): "memory" | "callback" { return this.options.durableAppend ? "callback" : "memory"; }

  append(event: NormalizedEvent): EvidenceEntry {
    this.validator.validate(event);
    const eventCopy = structuredClone(event);
    if (eventCopy.run_id !== this.runId) throw new EvidenceError("event run_id does not match accumulator runId");
    if (this.#mutating) throw new EvidenceError("reentrant evidence mutation is not supported");
    this.#mutating = true;
    try {
      if (this.#sealed) throw new EvidenceError("evidence run is sealed");
      if (this.#eventIds.has(eventCopy.event_id)) throw new EvidenceError(`duplicate event_id: ${eventCopy.event_id}`);
      if (this.#entries.length >= (this.options.maxEvents ?? 10_000)) throw new EvidenceError(`evidence run exceeds maxEvents=${this.options.maxEvents ?? 10_000}`);
      const sequence = this.#entries.length;
      const previousDigest = this.#entries.at(-1)?.digest;
      let digest: string;
      try { digest = entryDigest(sequence, previousDigest, eventCopy); }
      catch (error) { throw new EvidenceError(`event_id=${eventCopy.event_id} cannot be canonicalized under ${CANONICALIZATION_PROFILE}`, {cause: error}); }
      const entry: EvidenceEntry = {sequence, eventId: eventCopy.event_id, ...(previousDigest ? {previousDigest} : {}), digest, event: eventCopy};
      if (this.options.durableAppend) {
        let acknowledged: boolean;
        try { acknowledged = this.options.durableAppend(cloneEntry(entry)); }
        catch (error) { throw new EvidencePersistenceError(`durable evidence callback failed for event_id=${entry.eventId}`, {cause: error}); }
        if (acknowledged !== true) throw new EvidencePersistenceError(`durable evidence callback did not acknowledge event_id=${entry.eventId}`);
      }
      this.#entries.push(cloneEntry(entry));
      this.#eventIds.add(entry.eventId);
      return cloneEntry(entry);
    } finally { this.#mutating = false; }
  }

  seal(completeness: Completeness): EvidenceSnapshot {
    if (!(["complete", "incomplete", "unknown"] as const).includes(completeness)) throw new EvidenceError(`unsupported completeness: ${String(completeness)}`);
    if (this.#mutating) throw new EvidenceError("reentrant evidence mutation is not supported");
    if (this.#sealed) throw new EvidenceError("evidence run is already sealed");
    this.#sealed = true;
    this.#completeness = completeness;
    return this.snapshot();
  }

  snapshot(): EvidenceSnapshot {
    const entries = this.#entries.map(cloneEntry);
    const chainDigest = entries.at(-1)?.digest;
    return {runId: this.runId, entries, ...(chainDigest ? {chainDigest} : {}), canonicalizationProfile: CANONICALIZATION_PROFILE, completeness: this.#sealed ? this.#completeness : "unknown", sealed: this.#sealed};
  }
}

function entryDigest(sequence: number, previousDigest: string | undefined, event: NormalizedEvent): string {
  const canonical = canonicalize(event);
  if (canonical === undefined) throw new TypeError("event has no canonical JSON representation");
  const sequenceBytes = Buffer.alloc(8);
  sequenceBytes.writeBigUInt64BE(BigInt(sequence));
  const previous = previousDigest ? Buffer.from(previousDigest, "hex") : GENESIS_DIGEST;
  if (previous.length !== 32) throw new TypeError("previous digest must be 32 bytes");
  return createHash("sha256").update(previous).update(sequenceBytes).update(canonical, "utf8").digest("hex");
}

function cloneEntry(entry: EvidenceEntry): EvidenceEntry { return structuredClone(entry); }
