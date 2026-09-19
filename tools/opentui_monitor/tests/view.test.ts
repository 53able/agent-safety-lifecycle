import { describe, expect, test } from "bun:test"
import { createTestRenderer } from "@opentui/core/testing"
import type { MonitorViewModel } from "../src/protocol.js"
import { createMonitorView } from "../src/view.js"

const model: MonitorViewModel = Object.freeze({
  schema: "monitor-view-model.v1",
  task_id: "task-安全",
  run_id: "run-1",
  run_state: "RUNNING",
  stream_integrity: "OK",
  result_gate_decision: "NONE",
  result_gate: Object.freeze({ status: "UNAVAILABLE", reason: "unsupported" }),
  capabilities: Object.freeze({ status: "UNAVAILABLE", reason: "unsupported" }),
  handoff_status: "NONE",
  last_sequence: 2,
  timeline: Object.freeze([
    Object.freeze({ sequence: 1, event_type: "RUN_CREATED", source: "validator", state: "PLANNED", summary: "created" }),
    Object.freeze({ sequence: 2, event_type: "STATE_TRANSITION", source: "validator", state: "RUNNING", summary: "started" }),
  ]),
  warnings: Object.freeze([]),
})

describe("OpenTUI in-memory view", () => {
  for (const width of [40, 80, 120]) {
    test(`keeps required status and timeline at ${width} columns`, async () => {
      const setup = await createTestRenderer({ width, height: 20 })
      try {
        const view = createMonitorView(setup.renderer, model, width)
        setup.renderer.root.add(view.renderable)
        await setup.renderOnce()
        const frame = setup.captureCharFrame()
        for (const required of ["State:", "Stream:", "Handoff:", "Result:", "Capabilities:", "Last sequence:", "Timeline"]) {
          expect(frame).toContain(required)
        }
        expect(frame).not.toContain("\x1b")
        expect(setup.captureSpans().cols).toBe(width)
      } finally {
        setup.renderer.destroy()
      }
    })
  }

  test("model update and resize relayout without continuous rendering", async () => {
    const setup = await createTestRenderer({ width: 80, height: 20 })
    try {
      const view = createMonitorView(setup.renderer, model, 80)
      setup.renderer.root.add(view.renderable)
      await setup.waitForVisualIdle()
      const idleFrames = setup.renderer.getStats().nativeFrameCount
      await Bun.sleep(20)
      expect(setup.renderer.getStats().nativeFrameCount).toBe(idleFrames)

      view.update(Object.freeze({ ...model, run_state: "RETRYING", last_sequence: 3 }), 80)
      await setup.waitForVisualIdle()
      expect(setup.captureCharFrame()).toContain("State: RETRYING")

      setup.resize(40, 20)
      view.update(Object.freeze({ ...model, run_state: "RETRYING", last_sequence: 3 }), 40)
      await setup.waitForVisualIdle()
      expect(setup.captureCharFrame()).toContain("Last sequence: 3")
      expect(setup.captureSpans().cols).toBe(40)
    } finally {
      setup.renderer.destroy()
    }
  })
})
