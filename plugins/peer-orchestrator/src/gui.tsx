import { Command, Plugin } from "@opencode/plugin/gui"
import { PeerOrchestrator, type Worker } from "./rpc.js"

function workersFrom(value: unknown): Worker[] {
  const workers = (value as { workers?: unknown } | undefined)?.workers
  return Array.isArray(workers) ? (workers as Worker[]) : []
}

export default Plugin.define({
  i18n: {
    en: {
      "command.open": "Open orchestrator workers",
      "command.open.description": "Open every peer session created by spawn_peers as a Desktop tab",
      "command.group": "Orchestrator",
      "toast.opened": "Opened orchestrator workers",
      "toast.none": "No orchestrator workers yet",
      "toast.error": "Could not open orchestrator workers",
    },
  },
  setup(ctx) {
    // The plugin server runs on the Desktop's own sidecar. Opening a tab needs
    // the host key of that server, so prefer the builtin one.
    const resolveServer = () => {
      const builtin = ctx.servers
        .list()
        .map((id) => ctx.servers.get(id))
        .find((server) => server?.builtin)
      return builtin?.id ?? ctx.sessions.current()?.server.id
    }

    const openWorkers = (workers: Worker[]) => {
      const server = resolveServer()
      if (!server || workers.length === 0) return false
      for (const worker of workers) {
        ctx.tabs.open({ server, id: worker.sessionID }, { focus: false })
      }
      return true
    }

    // Live notification from the server plugin. If the window misses it, the
    // command below reads the same inventory over RPC.
    let unsubscribe: (() => void) | undefined
    try {
      unsubscribe = ctx.client.rpc(PeerOrchestrator).events.on("spawned", (event) => {
        openWorkers(workersFrom(event.data))
      })
    } catch (error) {
      console.warn(`[peer-orchestrator] could not subscribe to spawned events: ${String(error)}`)
    }

    ctx.add(Command, (): Command => ({
      id: "open-workers",
      title: ctx.t("command.open"),
      description: ctx.t("command.open.description"),
      group: ctx.t("command.group"),
      keywords: "orchestrator peer worker session tab spawn",
      slash: { name: "open-workers" },
      run: async () => {
        try {
          const result = await ctx.client.rpc(PeerOrchestrator).workers({})
          const workers = workersFrom(result)
          if (workers.length === 0) {
            ctx.toast.show({ title: ctx.t("toast.none") })
            return
          }
          openWorkers(workers)
          ctx.toast.show({
            title: ctx.t("toast.opened"),
            description: String(workers.length),
          })
        } catch (error) {
          ctx.toast.show({
            title: ctx.t("toast.error"),
            description: String(error),
            variant: "error",
          })
        }
      },
    }))

    return () => unsubscribe?.()
  },
})
