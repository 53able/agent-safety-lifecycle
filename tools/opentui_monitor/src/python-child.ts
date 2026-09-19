import { JsonlDecoder, type MonitorViewModel } from "./protocol.js"

const STDERR_LIMIT = 16 * 1024

export type ChildHandle = Readonly<{
  kill(signal: NodeJS.Signals): void
  readonly exited: Promise<number>
  readonly done: Promise<number>
}>

export type WatchArguments = Readonly<{
  python: string
  repositoryRoot: string
  eventRoot: string
  allowedParent: string
  runId: string
  pollInterval: string
  format: "text" | "view-model-jsonl"
}>

export function pythonArgv(options: WatchArguments): string[] {
  return [
    options.python, "-m", "tools.safety_monitor", "watch",
    "--event-root", options.eventRoot,
    "--allowed-parent", options.allowedParent,
    "--run-id", options.runId,
    "--poll-interval", options.pollInterval,
    "--format", options.format,
  ]
}

async function drain(stream: ReadableStream<Uint8Array>, consume: (chunk: Uint8Array) => void): Promise<void> {
  const reader = stream.getReader()
  try {
    while (true) {
      const result = await reader.read()
      if (result.done) return
      consume(result.value)
    }
  } finally {
    reader.releaseLock()
  }
}

export function spawnProtocolWatcher(
  options: WatchArguments,
  onModel: (model: MonitorViewModel) => void,
): ChildHandle {
  const child = Bun.spawn(pythonArgv(options), {
    cwd: options.repositoryRoot,
    stdin: "ignore",
    stdout: "pipe",
    stderr: "pipe",
  })
  const decoder = new JsonlDecoder(options.runId)
  let stderrBytes = 0

  const stdoutTask = drain(child.stdout, (chunk) => {
    for (const model of decoder.push(chunk)) onModel(model)
  }).then(() => decoder.finish())
  const stderrTask = drain(child.stderr, (chunk) => {
    // Drain concurrently to avoid deadlock, but never render or echo child text.
    stderrBytes = Math.min(STDERR_LIMIT, stderrBytes + chunk.length)
  })

  // Promise.all installs handlers on every pipe/exit promise while still rejecting
  // immediately when decoding or onModel fails. Process termination belongs to the
  // adapter's single bounded ShutdownController, not this transport helper.
  const done = Promise.all([stdoutTask, stderrTask, child.exited]).then(([, , code]) => code)

  return {
    kill: (signal) => child.kill(signal),
    exited: child.exited,
    done,
  }
}

export function spawnTextWatcher(options: WatchArguments): ChildHandle {
  const child = Bun.spawn(pythonArgv({ ...options, format: "text" }), {
    cwd: options.repositoryRoot,
    stdin: "ignore",
    stdout: "inherit",
    stderr: "inherit",
  })
  return {
    kill: (signal) => child.kill(signal),
    exited: child.exited,
    done: child.exited,
  }
}
