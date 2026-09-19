#!/usr/bin/env bun
import { CliRenderEvents, TextRenderable, createCliRenderer, type CliRenderer, type KeyEvent } from "@opentui/core"
import { resolve } from "node:path"
import { spawnProtocolWatcher, spawnTextWatcher, type ChildHandle, type WatchArguments } from "./python-child.js"
import type { MonitorViewModel } from "./protocol.js"
import { formatView } from "./view.js"

const FAILURE_DIAGNOSTIC = "opentui-monitor: monitor failed\n"

type RendererHandle = Pick<CliRenderer, "destroy">
type Wait = (milliseconds: number) => Promise<void>
type ShutdownKind = "interrupt" | "failure"

export class ShutdownController {
  private operation: Promise<void> | null = null
  private rendererDestroyed = false

  constructor(
    private readonly child: ChildHandle,
    private readonly renderer?: RendererHandle,
    private readonly wait: Wait = (milliseconds) => Bun.sleep(milliseconds),
  ) {}

  private destroyRenderer(): void {
    if (this.rendererDestroyed) return
    this.rendererDestroyed = true
    try {
      this.renderer?.destroy()
    } catch {
      // Cleanup is best-effort only after the one public destroy call. A cleanup
      // exception must not restore default SIGINT handling or skip child reaping.
    }
  }

  private signal(signal: NodeJS.Signals): void {
    try {
      this.child.kill(signal)
    } catch {
      // The child may have exited between the race result and this signal.
    }
  }

  private async exitedWithin(milliseconds: number): Promise<boolean> {
    return await Promise.race([
      this.child.exited.then(() => true, () => true),
      this.wait(milliseconds).then(() => false),
    ])
  }

  private shutdown(kind: ShutdownKind): Promise<void> {
    if (this.operation) return this.operation
    this.operation = (async () => {
      try {
        if (kind === "interrupt") {
          this.signal("SIGINT")
          if (await this.exitedWithin(2000)) return
        }
        this.signal("SIGTERM")
        if (await this.exitedWithin(2000)) return
        this.signal("SIGKILL")
        await this.child.exited.catch(() => undefined)
      } finally {
        // Ordering is intentional: the child is reaped before terminal teardown.
        this.destroyRenderer()
      }
    })()
    return this.operation
  }

  ctrlC(): Promise<void> {
    return this.shutdown("interrupt")
  }

  failure(): Promise<void> {
    return this.shutdown("failure")
  }

  async complete(): Promise<void> {
    if (this.operation) await this.operation
    else this.destroyRenderer()
  }
}

export type Arguments = Readonly<{
  python: string
  eventRoot: string
  allowedParent: string
  runId: string
  pollInterval: string
}>

type TextHandle = { content: any }

export type OpenTuiDependencies = Readonly<{
  createRenderer: () => Promise<CliRenderer>
  createText: (renderer: CliRenderer) => TextHandle
  spawnWatcher: typeof spawnProtocolWatcher
  writeDiagnostic: () => void
  wait: Wait
}>

const defaultOpenTuiDependencies: OpenTuiDependencies = {
  createRenderer: () => createCliRenderer({
    exitOnCtrlC: false,
    exitSignals: [],
    useMouse: false,
    consoleMode: "disabled",
  }),
  createText: (renderer) => new TextRenderable(renderer, {
    id: "monitor-view",
    width: "100%",
    height: "100%",
    overflow: "hidden",
    content: "Waiting for a validated projection…",
  }),
  spawnWatcher: spawnProtocolWatcher,
  writeDiagnostic: () => { process.stderr.write(FAILURE_DIAGNOSTIC) },
  wait: (milliseconds) => Bun.sleep(milliseconds),
}

function usageError(message: string): never {
  throw new Error(`argument error: ${message}`)
}

export function parseArguments(argv: readonly string[]): Arguments {
  const values = new Map<string, string>()
  const allowed = new Set(["--python", "--event-root", "--allowed-parent", "--run-id", "--poll-interval"])
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index]
    const value = argv[index + 1]
    if (name === undefined || value === undefined || !allowed.has(name) || value.startsWith("--")) usageError("expected option/value pairs")
    if (values.has(name)) usageError(`duplicate ${name}`)
    values.set(name, value)
  }
  const eventRoot = values.get("--event-root")
  const allowedParent = values.get("--allowed-parent")
  const runId = values.get("--run-id")
  if (!eventRoot || !allowedParent || !runId) usageError("--event-root, --allowed-parent, and --run-id are required")
  return {
    python: values.get("--python") ?? "python3",
    eventRoot,
    allowedParent,
    runId,
    pollInterval: values.get("--poll-interval") ?? "0.5",
  }
}

export function presentationMode(isTTY: boolean, noColorPresent: boolean): "text" | "opentui" {
  return !isTTY || noColorPresent ? "text" : "opentui"
}

function childOptions(arguments_: Arguments, format: WatchArguments["format"]): WatchArguments {
  return {
    ...arguments_,
    format,
    repositoryRoot: resolve(import.meta.dir, "../../.."),
  }
}

function normalizedChildStatus(code: number): number {
  if (code >= 1 && code <= 125) return code
  return 1
}

export async function runText(arguments_: Arguments): Promise<number> {
  const child = spawnTextWatcher(childOptions(arguments_, "text"))
  const controller = new ShutdownController(child)
  let interrupting = false
  let resolveInterrupt!: (status: number) => void
  const interrupted = new Promise<number>((resolveStatus) => { resolveInterrupt = resolveStatus })
  const onSignal = () => {
    interrupting = true
    void controller.ctrlC().then(() => resolveInterrupt(130))
  }
  process.on("SIGINT", onSignal)
  try {
    const childResult = child.done.then(async (code) => {
      if (interrupting) {
        await controller.ctrlC()
        return 130
      }
      await controller.complete()
      process.stderr.write(FAILURE_DIAGNOSTIC)
      return normalizedChildStatus(code)
    })
    return await Promise.race([childResult, interrupted])
  } finally {
    await controller.complete()
    process.off("SIGINT", onSignal)
  }
}

export async function runOpenTui(
  arguments_: Arguments,
  dependencies: OpenTuiDependencies = defaultOpenTuiDependencies,
): Promise<number> {
  let renderer: CliRenderer | undefined
  let controller: ShutdownController | undefined
  let removeListeners = () => {}
  let diagnosticWritten = false
  let standaloneRendererDestroyed = false
  const destroyStandaloneRenderer = () => {
    if (standaloneRendererDestroyed) return
    standaloneRendererDestroyed = true
    try { renderer?.destroy() } catch { /* cleanup attempt completed */ }
  }
  const writeDiagnostic = () => {
    if (diagnosticWritten) return
    diagnosticWritten = true
    dependencies.writeDiagnostic()
  }

  try {
    renderer = await dependencies.createRenderer()
    const text = dependencies.createText(renderer)
    renderer.root.add(text as never)
    let current: MonitorViewModel | null = null
    let resolveLifecycleFailure!: () => void
    const lifecycleFailure = new Promise<void>((resolveFailure) => { resolveLifecycleFailure = resolveFailure })
    let failed = false
    const reportLifecycleFailure = () => {
      if (failed) return
      failed = true
      resolveLifecycleFailure()
    }
    const child = dependencies.spawnWatcher(childOptions(arguments_, "view-model-jsonl"), (model) => {
      current = model
      text.content = formatView(model, renderer!.width)
      renderer!.requestRender()
    })
    controller = new ShutdownController(child, renderer, dependencies.wait)

    const onResize = (width: number) => {
      try {
        if (current) {
          text.content = formatView(current, width)
          renderer!.requestRender()
        }
      } catch {
        reportLifecycleFailure()
      }
    }
    let interrupting = false
    let resolveInterrupt!: () => void
    const interrupted = new Promise<void>((resolveStatus) => { resolveInterrupt = resolveStatus })
    const interrupt = () => {
      interrupting = true
      void controller!.ctrlC().then(resolveInterrupt)
    }
    const onCtrlC = (event: KeyEvent) => {
      if (event.ctrl && event.name === "c") {
        event.preventDefault()
        event.stopPropagation()
        interrupt()
      }
    }
    const onSignal = interrupt
    renderer.on(CliRenderEvents.RESIZE, onResize)
    renderer.keyInput.on("keypress", onCtrlC)
    process.on("SIGINT", onSignal)
    removeListeners = () => {
      process.off("SIGINT", onSignal)
      renderer!.keyInput.off("keypress", onCtrlC)
      renderer!.off(CliRenderEvents.RESIZE, onResize)
    }

    const outcome = await Promise.race([
      child.done.then(
        (code) => ({ kind: "child" as const, code }),
        () => ({ kind: "failure" as const }),
      ),
      lifecycleFailure.then(() => ({ kind: "failure" as const })),
      interrupted.then(() => ({ kind: "interrupt" as const })),
    ])

    if (outcome.kind === "interrupt" || interrupting) {
      await controller.ctrlC()
      return 130
    }
    if (outcome.kind === "failure") {
      await controller.failure()
      if (interrupting) return 130
      writeDiagnostic()
      return 1
    }

    await controller.complete()
    writeDiagnostic()
    return normalizedChildStatus(outcome.code)
  } catch {
    if (controller) await controller.failure()
    else destroyStandaloneRenderer()
    writeDiagnostic()
    return 1
  } finally {
    // Signal handling stays installed until the bounded shutdown and renderer
    // teardown above have completed.
    removeListeners()
    if (controller) await controller.complete()
    else destroyStandaloneRenderer()
  }
}

export async function main(argv: readonly string[] = process.argv.slice(2)): Promise<number> {
  let arguments_: Arguments
  try {
    arguments_ = parseArguments(argv)
  } catch {
    process.stderr.write("opentui-monitor: invalid arguments\n")
    return 2
  }
  if (presentationMode(Boolean(process.stdout.isTTY), "NO_COLOR" in process.env) === "text") {
    return await runText(arguments_)
  }
  return await runOpenTui(arguments_)
}

if (import.meta.main) process.exitCode = await main()
