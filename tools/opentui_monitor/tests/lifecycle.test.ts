import { describe, expect, test } from "bun:test"
import { CliRenderEvents, type CliRenderer } from "@opentui/core"
import { ShutdownController, parseArguments, presentationMode, runOpenTui, type OpenTuiDependencies } from "../src/main.js"
import { pythonArgv, type ChildHandle } from "../src/python-child.js"
import type { MonitorViewModel } from "../src/protocol.js"

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const model: MonitorViewModel = Object.freeze({
  schema: "monitor-view-model.v1",
  task_id: "task-1",
  run_id: "run-1",
  run_state: "RUNNING",
  stream_integrity: "OK",
  result_gate_decision: "NONE",
  result_gate: Object.freeze({ status: "UNAVAILABLE", reason: "unsupported" }),
  capabilities: Object.freeze({ status: "UNAVAILABLE", reason: "unsupported" }),
  handoff_status: "NONE",
  last_sequence: 2,
  timeline: Object.freeze([]),
  warnings: Object.freeze([]),
})

const arguments_ = {
  python: "python3",
  eventRoot: "/events",
  allowedParent: "/allowed",
  runId: "run-1",
  pollInterval: "0.5",
}

function fakeRenderer(events: string[], requestRender: () => void = () => {}): {
  renderer: CliRenderer
  emitResize(width: number): void
} {
  let resize: ((width: number) => void) | undefined
  const renderer = {
    width: 80,
    root: { add: () => { events.push("add") } },
    requestRender,
    destroy: () => { events.push("destroy") },
    on: (event: string, callback: (width: number) => void) => {
      if (event === CliRenderEvents.RESIZE) resize = callback
    },
    off: (event: string) => {
      if (event === CliRenderEvents.RESIZE) resize = undefined
    },
    keyInput: { on: () => {}, off: () => {} },
  } as unknown as CliRenderer
  return { renderer, emitResize: (width) => resize?.(width) }
}

function dependencies(overrides: Partial<OpenTuiDependencies>): OpenTuiDependencies {
  const setup = fakeRenderer([])
  return {
    createRenderer: async () => setup.renderer,
    createText: () => ({ content: "waiting" }),
    spawnWatcher: () => { throw new Error("spawn not configured") },
    writeDiagnostic: () => {},
    wait: async () => {},
    ...overrides,
  }
}

function uncooperativeChild(events: string[]): { child: ChildHandle; exit: ReturnType<typeof deferred<number>> } {
  const exit = deferred<number>()
  return {
    exit,
    child: {
      exited: exit.promise,
      done: exit.promise,
      kill(signal) {
        events.push(signal)
        if (signal === "SIGKILL") {
          events.push("exit")
          exit.resolve(137)
        }
      },
    },
  }
}

describe("lifecycle and fallback", () => {
  test("non-TTY and NO_COLOR choose text without OpenTUI", () => {
    expect(presentationMode(false, false)).toBe("text")
    expect(presentationMode(true, true)).toBe("text")
    expect(presentationMode(true, false)).toBe("opentui")
  })

  test("interrupt shutdown is bounded, idempotent, escalates, and destroys after exit", async () => {
    const events: string[] = []
    const { child } = uncooperativeChild(events)
    const controller = new ShutdownController(child, { destroy: () => { events.push("destroy") } }, async () => {})
    const first = controller.ctrlC()
    const second = controller.ctrlC()
    expect(first).toBe(second)
    await first
    await controller.complete()
    expect(events).toEqual(["SIGINT", "SIGTERM", "SIGKILL", "exit", "destroy"])
  })

  test("failure shutdown skips SIGINT but uses the same bounded controller", async () => {
    const events: string[] = []
    const { child } = uncooperativeChild(events)
    const controller = new ShutdownController(child, { destroy: () => { events.push("destroy") } }, async () => {})
    expect(controller.failure()).toBe(controller.failure())
    await controller.failure()
    expect(events).toEqual(["SIGTERM", "SIGKILL", "exit", "destroy"])
  })

  test("protocol failure rejects into bounded failure shutdown", async () => {
    const events: string[] = []
    const setup = fakeRenderer(events)
    const { child } = uncooperativeChild(events)
    const status = await runOpenTui(arguments_, dependencies({
      createRenderer: async () => setup.renderer,
      spawnWatcher: () => ({ ...child, done: Promise.reject(new Error("invalid protocol")) }),
      writeDiagnostic: () => { events.push("diagnostic") },
    }))
    expect(status).toBe(1)
    expect(events).toEqual(["add", "SIGTERM", "SIGKILL", "exit", "destroy", "diagnostic"])
  })

  test("onModel renderer update failure shuts down, restores renderer, and diagnoses once", async () => {
    const events: string[] = []
    const setup = fakeRenderer(events)
    const { child, exit } = uncooperativeChild(events)
    const status = await runOpenTui(arguments_, dependencies({
      createRenderer: async () => setup.renderer,
      createText: () => {
        let content = "waiting"
        return {
          get content() { return content },
          set content(_value: string) { throw new Error("update failed") },
        }
      },
      spawnWatcher: (_options, onModel) => ({
        ...child,
        done: Promise.resolve().then(() => { onModel(model); return exit.promise }),
      }),
      writeDiagnostic: () => { events.push("diagnostic") },
    }))
    expect(status).toBe(1)
    expect(events).toEqual(["add", "SIGTERM", "SIGKILL", "exit", "destroy", "diagnostic"])
  })

  test("resize requestRender failure joins lifecycle race and cleans up", async () => {
    const events: string[] = []
    let throwRender = false
    const setup = fakeRenderer(events, () => {
      if (throwRender) throw new Error("resize render failed")
      events.push("render")
    })
    const ready = deferred<void>()
    const { child, exit } = uncooperativeChild(events)
    const running = runOpenTui(arguments_, dependencies({
      createRenderer: async () => setup.renderer,
      spawnWatcher: (_options, onModel) => ({
        ...child,
        done: Promise.resolve().then(() => {
          onModel(model)
          ready.resolve()
          return exit.promise
        }),
      }),
      writeDiagnostic: () => { events.push("diagnostic") },
    }))
    await ready.promise
    throwRender = true
    setup.emitResize(40)
    expect(await running).toBe(1)
    expect(events.slice(-5)).toEqual(["SIGTERM", "SIGKILL", "exit", "destroy", "diagnostic"])
  })

  test("renderer construction failure destroys an initialized renderer and returns one", async () => {
    const events: string[] = []
    const setup = fakeRenderer(events)
    const status = await runOpenTui(arguments_, dependencies({
      createRenderer: async () => setup.renderer,
      createText: () => { throw new Error("initialization failed") },
      writeDiagnostic: () => { events.push("diagnostic") },
    }))
    expect(status).toBe(1)
    expect(events).toEqual(["destroy", "diagnostic"])
  })

  test("child nonzero is diagnosed after renderer cleanup", async () => {
    const events: string[] = []
    const setup = fakeRenderer(events)
    const child: ChildHandle = {
      exited: Promise.resolve(7),
      done: Promise.resolve(7),
      kill: () => { events.push("unexpected-signal") },
    }
    const status = await runOpenTui(arguments_, dependencies({
      createRenderer: async () => setup.renderer,
      spawnWatcher: () => child,
      writeDiagnostic: () => { events.push("diagnostic") },
    }))
    expect(status).toBe(7)
    expect(events).toEqual(["add", "destroy", "diagnostic"])
  })

  test("child command is argv-only and preserves hostile values as one argument", () => {
    const hostile = "run; touch /tmp/not-created"
    const argv = pythonArgv({
      python: "python3",
      repositoryRoot: "/repo",
      eventRoot: "/events with spaces",
      allowedParent: "/allowed",
      runId: hostile,
      pollInterval: "0.5",
      format: "view-model-jsonl",
    })
    expect(argv).toContain(hostile)
    expect(argv).toContain("/events with spaces")
    expect(argv[0]).toBe("python3")
  })

  test("argument parser rejects unknown options and has no command string", () => {
    expect(() => parseArguments(["--shell", "yes"])).toThrow()
    expect(parseArguments(["--event-root", "e", "--allowed-parent", "a", "--run-id", "r"]).python).toBe("python3")
  })
})
