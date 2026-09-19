import { expect, test } from "bun:test"
import { mkdtemp, readdir, readFile, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"

const repositoryRoot = resolve(import.meta.dir, "../../..")

async function tree(root: string, relative = ""): Promise<string[]> {
  const directory = join(root, relative)
  const entries = await readdir(directory, { withFileTypes: true })
  const output: string[] = []
  for (const entry of entries) {
    const path = join(relative, entry.name)
    output.push(path)
    if (entry.isDirectory()) output.push(...await tree(root, path))
  }
  return output.sort()
}

async function hash(path: string): Promise<string> {
  const hasher = new Bun.CryptoHasher("sha256")
  hasher.update(await readFile(path))
  return hasher.digest("hex")
}

test("Python bridge leaves event bytes, hash, and directory tree unchanged", async () => {
  const root = await mkdtemp(join(tmpdir(), "opentui-monitor-"))
  const eventRoot = join(root, "events")
  const artifactRoot = join(root, "artifacts")
  const log = join(eventRoot, "run-1", "events.ndjson")
  try {
    const setup = Bun.spawn([
      "python3", "-m", "tools.safety_monitor", "vertical-slice",
      "--allowed-parent", root,
      "--event-root", eventRoot,
      "--artifact-root", artifactRoot,
      "--task-id", "task-1",
      "--run-id", "run-1",
      "--envelope-hash", `sha256:${"0".repeat(64)}`,
    ], { cwd: repositoryRoot, stdout: "ignore", stderr: "pipe" })
    expect(await setup.exited).toBe(0)
    const beforeBytes = await readFile(log)
    const beforeHash = await hash(log)
    const beforeTree = await tree(root)

    const watcher = Bun.spawn([
      "python3", "-m", "tools.safety_monitor", "watch",
      "--allowed-parent", root,
      "--event-root", eventRoot,
      "--run-id", "run-1",
      "--poll-interval", "0.05",
      "--format", "view-model-jsonl",
    ], { cwd: repositoryRoot, stdin: "ignore", stdout: "pipe", stderr: "pipe" })
    const reader = watcher.stdout.getReader()
    const first = await reader.read()
    expect(first.done).toBeFalse()
    expect(new TextDecoder().decode(first.value)).toContain("monitor-view-model.v1")
    reader.releaseLock()
    watcher.kill("SIGINT")
    expect(await watcher.exited).toBe(130)

    expect(await readFile(log)).toEqual(beforeBytes)
    expect(await hash(log)).toBe(beforeHash)
    expect(await tree(root)).toEqual(beforeTree)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}, 15_000)
