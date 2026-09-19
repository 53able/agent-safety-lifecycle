import { describe, expect, test } from "bun:test"
import { FRAME_LIMIT, JsonlDecoder, ProtocolError, parseFrame } from "../src/protocol.js"

function value(sequence = 2) {
  return {
    schema: "monitor-view-model.v1",
    task_id: "task-1",
    run_id: "run-1",
    run_state: "RUNNING",
    stream_integrity: "OK",
    result_gate_decision: "NONE",
    result_gate: { status: "UNAVAILABLE", reason: "unsupported" },
    capabilities: { status: "UNAVAILABLE", reason: "unsupported" },
    handoff_status: "NONE",
    last_sequence: sequence,
    timeline: [{ sequence, event_type: "STATE_TRANSITION", source: "validator", state: "RUNNING", summary: "safe" }],
    warnings: [],
  }
}

const encoder = new TextEncoder()
const line = (sequence = 2) => encoder.encode(JSON.stringify(value(sequence)) + "\n")

describe("strict bounded protocol", () => {
  test("accepts split chunks and multiple frames", () => {
    const decoder = new JsonlDecoder("run-1")
    const bytes = line()
    expect(decoder.push(bytes.slice(0, 10))).toEqual([])
    expect(decoder.push(bytes.slice(10))[0]?.last_sequence).toBe(2)
    const multiple = new Uint8Array([...line(3), ...line(4)])
    expect(decoder.push(multiple).map((frame) => frame.last_sequence)).toEqual([3, 4])
    decoder.finish()
  })

  test("rejects invalid UTF-8, oversize, and partial EOF", () => {
    expect(() => new JsonlDecoder("run-1").push(new Uint8Array([0xff, 0x0a]))).toThrow(ProtocolError)
    expect(() => new JsonlDecoder("run-1").push(new Uint8Array(FRAME_LIMIT).fill(0x78))).toThrow(/512 KiB/)
    const partial = new JsonlDecoder("run-1")
    partial.push(encoder.encode("{}"))
    expect(() => partial.finish()).toThrow(/partial/)
  })

  test("rejects unknown schema, fields, run mismatch, and sequence regression", () => {
    expect(() => parseFrame(JSON.stringify({ ...value(), schema: "v2" }), "run-1", null)).toThrow(/schema/)
    expect(() => parseFrame(JSON.stringify({ ...value(), extra: true }), "run-1", null)).toThrow(/fields/)
    expect(() => parseFrame(JSON.stringify(value()), "other", null)).toThrow(/run_id/)
    expect(() => parseFrame(JSON.stringify(value(2)), "run-1", 2)).toThrow(/increase/)
  })

  test("rejects control injection anywhere", () => {
    for (const injection of ["\x1b[2J", "\x00", "\x9b", "\n", "\u202e", "\ufeff"]) {
      const injected = value()
      injected.timeline[0]!.summary = injection
      expect(() => parseFrame(JSON.stringify(injected), "run-1", null)).toThrow(/safe string/)
    }
  })

  test("does not deliver earlier frames from a chunk containing a later invalid frame", () => {
    const decoder = new JsonlDecoder("run-1")
    const bytes = encoder.encode(JSON.stringify(value()) + "\n{}\n")
    expect(() => decoder.push(bytes)).toThrow(ProtocolError)
  })
})
