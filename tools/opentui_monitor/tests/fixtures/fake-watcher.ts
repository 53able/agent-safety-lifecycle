#!/usr/bin/env bun
import { writeFile } from "node:fs/promises"

const record = process.env.FAKE_PID_RECORD
if (!record) throw new Error("FAKE_PID_RECORD is required")
await writeFile(record, `${process.pid}\n`, "utf8")

process.on("SIGINT", () => {})
process.on("SIGTERM", () => {})

const behavior = record.includes("invalid") ? "invalid" : (process.env.FAKE_BEHAVIOR ?? "hang")
if (behavior === "invalid") process.stdout.write("{}\n")
if (behavior === "valid" || behavior === "valid-exit") {
  process.stdout.write(JSON.stringify({
    schema: "monitor-view-model.v1",
    task_id: "task-1",
    run_id: "run-1",
    run_state: "RUNNING",
    stream_integrity: "OK",
    result_gate_decision: "NONE",
    result_gate: { status: "UNAVAILABLE", reason: "unsupported" },
    capabilities: { status: "UNAVAILABLE", reason: "unsupported" },
    handoff_status: "NONE",
    last_sequence: 1,
    timeline: [],
    warnings: [],
  }) + "\n")
}
if (behavior === "nonzero" || behavior === "valid-exit") process.exit(7)
await new Promise(() => {})
