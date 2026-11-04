import { Plugin } from "@opencode/plugin"
import type { Schema } from "effect"
import { isAbsolute, resolve } from "node:path"
import { PeerOrchestrator, type Worker } from "./rpc.js"

const STORAGE_KEY = "workers"
const MAX_TASKS = 8

interface Task {
  title: string
  prompt: string
  directory?: string
}

async function readWorkers(ctx: { storage: { get(key: string): Promise<unknown> } }): Promise<Worker[]> {
  const stored = await ctx.storage.get(STORAGE_KEY)
  if (!Array.isArray(stored)) return []
  return (stored as Worker[]).slice().sort((a, b) => a.createdAt - b.createdAt)
}

export default Plugin.define({
  id: "peer-orchestrator",
  async setup(ctx) {
    // Expose the worker inventory to the Desktop GUI. The GUI also subscribes
    // to the `spawned` event so tabs open without polling.
    const registration = await ctx.rpc.register(PeerOrchestrator, {
      workers: async (input) => {
        const filter = (input as { directory?: string } | undefined)?.directory
        const workers = await readWorkers(ctx)
        return {
          workers: filter ? workers.filter((worker) => worker.directory === filter) : workers,
        }
      },
    })

    await ctx.tool.transform((editor) => {
      editor.add({
        name: "spawn_peers",
        description:
          "Create independent top-level OpenCode sessions (peers), each with its own chat and tab, and send each " +
          "one an initial prompt concurrently. Use this when the user asks for parallel workers or an orchestrator. " +
          "These are root sessions, not subagents: no parentID is set. Returns each worker's session ID.",
        input: {
          type: "object",
          properties: {
            tasks: {
              type: "array",
              minItems: 1,
              maxItems: MAX_TASKS,
              items: {
                type: "object",
                properties: {
                  title: {
                    type: "string",
                    description: "Short title for the worker session tab.",
                  },
                  prompt: {
                    type: "string",
                    description: "Initial user prompt sent to the worker session.",
                  },
                  directory: {
                    type: "string",
                    description:
                      "Optional working directory. Defaults to the orchestrator session's directory.",
                  },
                },
                required: ["title", "prompt"],
                additionalProperties: false,
              },
            },
          },
          required: ["tasks"],
          additionalProperties: false,
        },
        execute: async (rawInput, context) => {
          const input = rawInput as { tasks?: Task[] }
          const tasks = Array.isArray(input.tasks) ? input.tasks : []

          if (tasks.length === 0) {
            return { content: "spawn_peers requires at least one task." }
          }
          if (tasks.length > MAX_TASKS) {
            return { content: `spawn_peers accepts at most ${MAX_TASKS} tasks per call.` }
          }

          for (const task of tasks) {
            if (!task.title?.trim() || !task.prompt?.trim()) {
              return { content: "Every task needs a non-empty title and prompt." }
            }
          }

          await context.progress({ status: "creating", count: tasks.length })

          // Each task creates its own root session. parentID is deliberately
          // never passed: these must be top-level peers, not subagent children.
          const results = await Promise.allSettled(
            tasks.map(async (task, index) => {
              const directory = task.directory
                ? isAbsolute(task.directory)
                  ? task.directory
                  : resolve(ctx.location.directory, task.directory)
                : ctx.location.directory

              const session = await ctx.session.create({
                title: task.title.trim(),
                ...(task.directory ? { location: { directory } } : {}),
              })


              if (session.parentID) {
                throw new Error(
                  `Session ${session.id} was created with parentID ${session.parentID}; ` +
                    "peer sessions must be root sessions.",
                )
              }

              return { index, task, directory, session }
            }),
          )

          const created = results.flatMap((result) =>
            result.status === "fulfilled" ? [result.value] : [],
          )
          const failures = results.flatMap((result, index) =>
            result.status === "rejected"
              ? [`${tasks[index]?.title ?? `task ${index + 1}`}: ${String(result.reason)}`]
              : [],
          )

          if (created.length === 0) {
            return {
              content: `Failed to create any peer session.\n${failures.join("\n")}`,
            }
          }

          // Send all initial prompts without waiting for any worker to finish.
          // `session.prompt` resolves when the prompt is admitted to the
          // session inbox, not when the worker's turn completes.
          await context.progress({ status: "prompting", count: created.length })
          await Promise.all(
            created.map(({ session, task }) =>
              ctx.session.prompt({
                sessionID: session.id,
                text: task.prompt,
              }),
            ),
          )

          const workers: Worker[] = created.map(({ task, directory, session }) => ({
            sessionID: session.id,
            title: session.title ?? task.title.trim(),
            directory,
            prompt: task.prompt,
            createdAt: Date.now(),
          }))

          const previous = await readWorkers(ctx)
          await ctx.storage.set(STORAGE_KEY, [...previous, ...workers] as unknown as Schema.Json)

          // Live notification for the GUI. A missed event is recoverable with
          // the "Open orchestrator workers" command, which reads the same
          // inventory through RPC.
          try {
            await registration.events.emit("spawned", { workers })
          } catch (error) {
            console.warn("[peer-orchestrator] could not emit spawned event", error)
          }

          const lines = workers.map(
            (worker) => `- ${worker.sessionID}  ${worker.title}  (${worker.directory})`,
          )
          const failureLines =
            failures.length > 0 ? `\nFailures:\n${failures.map((line) => `- ${line}`).join("\n")}` : ""

          return {
            content:
              `Created ${workers.length} top-level peer session(s), all root sessions without parentID. ` +
              `Initial prompts were admitted concurrently.\n\n${lines.join("\n")}${failureLines}`,
            metadata: { workers },
          }
        },
      })
    })
  },
})
