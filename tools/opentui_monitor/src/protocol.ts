export const FRAME_LIMIT = 512 * 1024
export const SCHEMA = "monitor-view-model.v1"

export type Availability = Readonly<{ status: string; reason: string }>
export type TimelineEntry = Readonly<{
  sequence: number
  event_type: string
  source: string
  state: string
  summary: string
}>
export type MonitorViewModel = Readonly<{
  schema: typeof SCHEMA
  task_id: string
  run_id: string
  run_state: string
  stream_integrity: string
  result_gate_decision: string
  result_gate: Availability
  capabilities: Availability
  handoff_status: string
  last_sequence: number
  timeline: readonly TimelineEntry[]
  warnings: readonly string[]
}>

export class ProtocolError extends Error {}

const TOP_KEYS = [
  "capabilities", "handoff_status", "last_sequence", "result_gate", "result_gate_decision",
  "run_id", "run_state", "schema", "stream_integrity", "task_id", "timeline", "warnings",
].sort()
const AVAILABILITY_KEYS = ["reason", "status"]
const TIMELINE_KEYS = ["event_type", "sequence", "source", "state", "summary"]
const UNSAFE = /[\u0000-\u001f\u007f-\u009f\p{Cf}]/u

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new ProtocolError(`${label} must be an object`)
  return value as Record<string, unknown>
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[], label: string): void {
  const actual = Object.keys(value).sort()
  if (actual.length !== keys.length || actual.some((key, index) => key !== keys[index])) {
    throw new ProtocolError(`${label} has unknown or missing fields`)
  }
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || UNSAFE.test(value)) throw new ProtocolError(`${label} is not a safe string`)
  return value
}

function integer(value: unknown, label: string): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) throw new ProtocolError(`${label} must be a non-negative integer`)
  return value as number
}

function availability(value: unknown, label: string): Availability {
  const item = record(value, label)
  exactKeys(item, AVAILABILITY_KEYS, label)
  return Object.freeze({ status: text(item.status, `${label}.status`), reason: text(item.reason, `${label}.reason`) })
}

export function parseFrame(raw: string, expectedRunId: string, previousSequence: number | null): MonitorViewModel {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    throw new ProtocolError("invalid JSON frame")
  }
  const value = record(parsed, "frame")
  exactKeys(value, TOP_KEYS, "frame")
  if (value.schema !== SCHEMA) throw new ProtocolError("unsupported protocol schema")
  const runId = text(value.run_id, "run_id")
  if (runId !== expectedRunId) throw new ProtocolError("protocol run_id mismatch")
  const lastSequence = integer(value.last_sequence, "last_sequence")
  if (previousSequence !== null && lastSequence <= previousSequence) throw new ProtocolError("sequence did not increase")
  if (!Array.isArray(value.timeline) || value.timeline.length > 100) throw new ProtocolError("timeline must contain at most 100 entries")
  const timeline = value.timeline.map((rawEntry, index) => {
    const entry = record(rawEntry, `timeline[${index}]`)
    exactKeys(entry, TIMELINE_KEYS, `timeline[${index}]`)
    return Object.freeze({
      sequence: integer(entry.sequence, `timeline[${index}].sequence`),
      event_type: text(entry.event_type, `timeline[${index}].event_type`),
      source: text(entry.source, `timeline[${index}].source`),
      state: text(entry.state, `timeline[${index}].state`),
      summary: text(entry.summary, `timeline[${index}].summary`),
    })
  })
  if (!Array.isArray(value.warnings)) throw new ProtocolError("warnings must be an array")
  const warnings = value.warnings.map((warning, index) => text(warning, `warnings[${index}]`))
  return Object.freeze({
    schema: SCHEMA,
    task_id: text(value.task_id, "task_id"),
    run_id: runId,
    run_state: text(value.run_state, "run_state"),
    stream_integrity: text(value.stream_integrity, "stream_integrity"),
    result_gate_decision: text(value.result_gate_decision, "result_gate_decision"),
    result_gate: availability(value.result_gate, "result_gate"),
    capabilities: availability(value.capabilities, "capabilities"),
    handoff_status: text(value.handoff_status, "handoff_status"),
    last_sequence: lastSequence,
    timeline: Object.freeze(timeline),
    warnings: Object.freeze(warnings),
  })
}

export class JsonlDecoder {
  private buffer = new Uint8Array(0)
  private readonly decoder = new TextDecoder("utf-8", { fatal: true })
  private sequence: number | null = null

  constructor(private readonly expectedRunId: string) {}

  push(chunk: Uint8Array): MonitorViewModel[] {
    const joined = new Uint8Array(this.buffer.length + chunk.length)
    joined.set(this.buffer)
    joined.set(chunk, this.buffer.length)
    const frames: MonitorViewModel[] = []
    let start = 0
    for (let index = 0; index < joined.length; index += 1) {
      if (joined[index] !== 0x0a) continue
      const lineLength = index - start + 1
      if (lineLength > FRAME_LIMIT) throw new ProtocolError("protocol frame exceeds 512 KiB")
      if (index === start) throw new ProtocolError("empty protocol frame")
      let raw: string
      try {
        raw = this.decoder.decode(joined.subarray(start, index))
      } catch {
        throw new ProtocolError("protocol frame is not valid UTF-8")
      }
      const frame = parseFrame(raw, this.expectedRunId, this.sequence)
      this.sequence = frame.last_sequence
      frames.push(frame)
      start = index + 1
    }
    this.buffer = joined.slice(start)
    if (this.buffer.length >= FRAME_LIMIT) throw new ProtocolError("protocol frame exceeds 512 KiB")
    return frames
  }

  finish(): void {
    if (this.buffer.length !== 0) throw new ProtocolError("partial protocol frame at EOF")
  }
}
