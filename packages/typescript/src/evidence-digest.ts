import {createHash} from "node:crypto";
import canonicalize from "canonicalize";
import type {NormalizedEvent} from "./types.js";

// Internal: shared by the accumulator that builds the chain and the TRACE
// finalizer that re-checks it. Not re-exported from index.ts.
const GENESIS_DIGEST = Buffer.alloc(32);

export function entryDigest(sequence: number, previousDigest: string | undefined, event: NormalizedEvent): string {
  const canonical = canonicalize(event);
  if (canonical === undefined) throw new TypeError("event has no canonical JSON representation");
  const sequenceBytes = Buffer.alloc(8);
  sequenceBytes.writeBigUInt64BE(BigInt(sequence));
  const previous = previousDigest ? Buffer.from(previousDigest, "hex") : GENESIS_DIGEST;
  if (previous.length !== 32) throw new TypeError("previous digest must be 32 bytes");
  return createHash("sha256").update(previous).update(sequenceBytes).update(canonical, "utf8").digest("hex");
}
