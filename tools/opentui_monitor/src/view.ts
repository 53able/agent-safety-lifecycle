import { TextRenderable, type RenderContext } from "@opentui/core"
import type { MonitorViewModel } from "./protocol.js"

function truncate(value: string, width: number): string {
  if (width <= 0) return ""
  if (Bun.stringWidth(value) <= width) return value
  if (width === 1) return "…"
  let output = ""
  for (const character of value) {
    if (Bun.stringWidth(output + character + "…") > width) break
    output += character
  }
  return output + "…"
}

function pad(value: string, width: number): string {
  const clipped = truncate(value, width)
  return clipped + " ".repeat(Math.max(0, width - Bun.stringWidth(clipped)))
}

function summaryLines(model: MonitorViewModel): string[] {
  return [
    "Safety monitor (read-only)",
    `Task: ${model.task_id}`,
    `Run: ${model.run_id}`,
    `State: ${model.run_state}`,
    `Stream: ${model.stream_integrity}`,
    `Handoff: ${model.handoff_status}`,
    `Result: ${model.result_gate_decision} (${model.result_gate.status})`,
    `Capabilities: ${model.capabilities.status}`,
    `Last sequence: ${model.last_sequence}`,
  ]
}

function timelineLines(model: MonitorViewModel): string[] {
  return [
    "Timeline",
    ...model.timeline.map((entry) => `${entry.sequence} ${entry.event_type} [${entry.source}] ${entry.state}: ${entry.summary}`),
    ...model.warnings.map((warning) => `Warning: ${warning}`),
  ]
}

export function formatView(model: MonitorViewModel, columns: number): string {
  const width = Math.max(1, Math.floor(columns))
  const summary = summaryLines(model)
  const timeline = timelineLines(model)
  if (width < 80) {
    return [...summary, ...timeline].map((line) => truncate(line, width)).join("\n")
  }
  const leftWidth = Math.floor((width - 1) * 0.42)
  const rightWidth = width - leftWidth - 1
  const rows = Math.max(summary.length, timeline.length)
  return Array.from({ length: rows }, (_, index) => (
    `${pad(summary[index] ?? "", leftWidth)} ${truncate(timeline[index] ?? "", rightWidth)}`
  )).join("\n")
}

export type MonitorView = Readonly<{
  renderable: TextRenderable
  update(model: MonitorViewModel, columns: number): void
}>

export function createMonitorView(context: RenderContext, model: MonitorViewModel, columns: number): MonitorView {
  const renderable = new TextRenderable(context, {
    id: "monitor-view",
    width: "100%",
    height: "100%",
    overflow: "hidden",
    content: formatView(model, columns),
  })
  return {
    renderable,
    update(nextModel, nextColumns) {
      renderable.content = formatView(nextModel, nextColumns)
      context.requestRender()
    },
  }
}
