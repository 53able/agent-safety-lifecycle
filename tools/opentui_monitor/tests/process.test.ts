import { afterAll, beforeAll, describe, expect, test } from "bun:test"
import { chmod, mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"

const repositoryRoot = resolve(import.meta.dir, "../../..")
const entryPath = resolve(import.meta.dir, "../src/main.ts")
const fakeWatcher = resolve(import.meta.dir, "fixtures/fake-watcher.ts")
const harness = resolve(import.meta.dir, "fixtures/pty_harness.py")
const rawModelEvidence = '"schema":"monitor-view-model.v1"'
let root = ""

function publicArguments(): string[] {
  return [
    process.execPath, "run", entryPath,
    "--python", fakeWatcher,
    "--event-root", root,
    "--allowed-parent", root,
    "--run-id", "run-1",
    "--poll-interval", "0.05",
  ]
}

async function ptyRun(mode: "signals" | "wait", behavior: string, noColor = false) {
  const pidRecord = join(root, `${mode}-${behavior}-${crypto.randomUUID()}.pid`)
  const environment: Record<string, string | undefined> = {
    ...process.env,
    FAKE_PID_RECORD: pidRecord,
    FAKE_BEHAVIOR: behavior,
  }
  if (noColor) environment["NO_COLOR"] = "1"
  else delete environment["NO_COLOR"]
  const child = Bun.spawn([
    "python3", harness, mode, pidRecord, ...publicArguments(),
  ], {
    cwd: repositoryRoot,
    stdout: "pipe",
    stderr: "pipe",
    env: environment,
  })
  const timeout = Bun.sleep(15_000).then(() => "timeout" as const)
  const result = await Promise.race([child.exited, timeout])
  if (result === "timeout") {
    child.kill("SIGKILL")
    await child.exited
    throw new Error("PTY harness exceeded hard timeout")
  }
  const stdout = await new Response(child.stdout).text()
  const stderr = await new Response(child.stderr).text()
  expect(result).toBe(0)
  expect(stderr).toBe("")
  return JSON.parse(stdout) as {
    status: number
    timed_out: boolean
    child_pid: number
    child_gone: boolean
    terminal_restored: boolean
    canonical_restored: boolean
    echo_restored: boolean
    transcript: string
  }
}

async function nonTtyRun(behavior: string) {
  const pidRecord = join(root, `non-tty-${behavior}-${crypto.randomUUID()}.pid`)
  const environment: Record<string, string | undefined> = {
    ...process.env,
    FAKE_PID_RECORD: pidRecord,
    FAKE_BEHAVIOR: behavior,
  }
  delete environment["NO_COLOR"]
  const child = Bun.spawn(publicArguments(), {
    cwd: repositoryRoot,
    stdout: "pipe",
    stderr: "pipe",
    env: environment,
  })
  const [status, stdout, stderr] = await Promise.all([
    child.exited,
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
  ])
  return { status, stdout, stderr }
}

describe("public-entry process lifecycle and routing", () => {
  beforeAll(async () => {
    root = await mkdtemp(join(tmpdir(), "opentui-lifecycle-"))
    await chmod(fakeWatcher, 0o755)
    await chmod(harness, 0o755)
  })

  afterAll(async () => {
    await rm(root, { recursive: true, force: true })
  })

  test.serial("public TTY repeated SIGINT uses OpenTUI, returns 130, restores the terminal, and reaps an uncooperative child", async () => {
    const result = await ptyRun("signals", "hang")
    expect(result.timed_out).toBeFalse()
    expect(result.status).toBe(130)
    expect(result.child_gone).toBeTrue()
    expect(result.terminal_restored).toBeTrue()
    expect(result.canonical_restored).toBeTrue()
    expect(result.echo_restored).toBeTrue()
    expect(result.transcript).toContain("Waiting for a validated projection")
    expect(result.transcript).toContain("\x1b[")
    expect(result.transcript).not.toContain(rawModelEvidence)
  }, 15_000)

  test.serial("public TTY protocol failure uses OpenTUI, restores the terminal, and returns one", async () => {
    const result = await ptyRun("wait", "invalid")
    expect(result.timed_out).toBeFalse()
    expect(result.status).toBe(1)
    expect(result.child_gone).toBeTrue()
    expect(result.terminal_restored).toBeTrue()
    expect(result.canonical_restored).toBeTrue()
    expect(result.echo_restored).toBeTrue()
    expect(result.transcript).toContain("\x1b[")
    expect(result.transcript).toContain("opentui-monitor: monitor failed")
  }, 15_000)

  test.serial("public TTY with NO_COLOR selects text fallback", async () => {
    const result = await ptyRun("wait", "valid-exit", true)
    expect(result.timed_out).toBeFalse()
    expect(result.status).toBe(7)
    expect(result.child_gone).toBeTrue()
    expect(result.terminal_restored).toBeTrue()
    expect(result.transcript).toContain(rawModelEvidence)
    expect(result.transcript).not.toContain("\x1b[")
  }, 15_000)

  test.serial("public non-TTY output selects text fallback", async () => {
    const result = await nonTtyRun("valid-exit")
    expect(result.status).toBe(7)
    expect(result.stdout).toContain(rawModelEvidence)
    expect(result.stdout).not.toContain("\x1b[")
    expect(result.stderr).toContain("opentui-monitor: monitor failed")
  })
})
