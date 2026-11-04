import { Rpc } from "@opencode/plugin/rpc"

/**
 * A root session created by the orchestrator. It has no parentID: it is a
 * top-level peer session, not a subagent child.
 */
export interface Worker {
  /** Root session id. */
  sessionID: string
  /** Human-readable worker title. */
  title: string
  /** Directory the session was created in. */
  directory: string
  /** Prompt delivered to the session. */
  prompt: string
  /** Admission time, Unix milliseconds. */
  createdAt: number
}

const workerSchema = {
  type: "object",
  properties: {
    sessionID: { type: "string" },
    title: { type: "string" },
    directory: { type: "string" },
    prompt: { type: "string" },
    createdAt: { type: "number" },
  },
  required: ["sessionID", "title", "directory", "prompt", "createdAt"],
  additionalProperties: false,
} as const

/**
 * RPC contract shared by the server part and the Desktop GUI part.
 * The server registers the implementation; the GUI calls `workers` and
 * subscribes to `spawned`.
 */
export const PeerOrchestrator = Rpc.define({
  id: "peer-orchestrator",
  methods: {
    workers: {
      input: {
        type: "object",
        properties: {
          directory: { type: "string" },
        },
        additionalProperties: false,
      },
      output: {
        type: "object",
        properties: {
          workers: {
            type: "array",
            items: workerSchema,
          },
        },
        required: ["workers"],
        additionalProperties: false,
      },
    },
  },
  events: {
    spawned: {
      schema: {
        type: "object",
        properties: {
          workers: {
            type: "array",
            items: workerSchema,
          },
        },
        required: ["workers"],
        additionalProperties: false,
      },
    },
  },
})
