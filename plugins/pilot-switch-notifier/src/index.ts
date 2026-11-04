import { Plugin } from "@opencode/plugin"
import { appendFileSync, closeSync, openSync, readFileSync, statSync, unlinkSync, writeFileSync } from "node:fs"
import { readFile, stat } from "node:fs/promises"

const EVENTS = process.env.PILOT_SWITCH_EVENTS ?? "C:/Users/admin/AppData/Local/MultiVibe-Codex-Pilot/pilot-switch-events.jsonl"
const DEBUG = process.env.PILOT_NOTIFIER_DEBUG ?? "C:/Users/admin/AppData/Local/Temp/pilot-notifier-debug.log"
const LOCK = DEBUG + ".lock"
const OFFSET = "C:/Users/admin/AppData/Local/Temp/pilot-notifier-offset.txt"

type SwitchEvent = {
  ts?: number
  from?: number
  to?: number
  reason?: string
  reason_text?: string
  to_primary_left?: number
  to_weekly_left?: number
}

function debug(message: string) {
  try {
    appendFileSync(DEBUG, `${new Date().toISOString()} ${message}\n`)
  } catch {}
}

function readOffset(): number {
  try {
    const value = Number(readFileSync(OFFSET, "utf8"))
    return Number.isFinite(value) ? value : -1
  } catch {
    return -1
  }
}

function writeOffset(value: number) {
  try {
    writeFileSync(OFFSET, String(value))
  } catch {}
}

export default Plugin.define({
  id: "pilot-switch-notifier",
  async setup(ctx) {
    let offset = readOffset()
    if (offset < 0) {
      try {
        offset = (await stat(EVENTS)).size
      } catch {
        offset = 0
      }
      writeOffset(offset)
    }
    debug(`setup offset=${offset} dir=${ctx.location.directory}`)

    const notify = async (event: SwitchEvent) => {
      let session
      try {
        const page = await ctx.session.list({ directory: ctx.location.directory, limit: 50 })
        session = page.data.find(
          (item) => item.model?.providerID === "pilot_multivibe" && !item.time?.archived,
        )
        if (!session) {
          const all = await ctx.session.list({ limit: 50 })
          session = all.data.find(
            (item) => item.model?.providerID === "pilot_multivibe" && !item.time?.archived,
          )
        }
      } catch (error) {
        debug(`list error ${String(error)}`)
        return
      }
      debug(`event to=${event.to} from=${event.from} session=${session?.id ?? "none"}`)
      if (!session) return
      const from = event.from ? `#${event.from} → ` : ""
      const reason = event.reason_text ?? event.reason ?? "đổi tài khoản"
      const text =
        `🔄 Đã chuyển tài khoản ${from}#${event.to}\n` +
        `Lý do: ${reason}.\n` +
        `#${event.to} còn: 5 giờ ${Math.round(event.to_primary_left ?? 0)}% · ` +
        `tuần ${Math.round(event.to_weekly_left ?? 0)}%.`
      try {
        await ctx.session.synthetic({ sessionID: session.id, text, description: "account switch" })
        debug(`notified session=${session.id}`)
      } catch (error) {
        debug(`synthetic error ${String(error)}`)
      }
    }

    const check = async () => {
      let lock
      try {
        lock = openSync(LOCK, "wx")
      } catch {
        try {
          if (Date.now() - statSync(LOCK).mtimeMs > 30_000) unlinkSync(LOCK)
        } catch {}
        return
      }
      try {
        let info
        try {
          info = await stat(EVENTS)
        } catch {
          return
        }
        offset = readOffset()
        if (offset < 0 || info.size < offset) offset = 0
        if (info.size === offset) return
        debug(`reading ${info.size - offset} bytes (offset=${offset})`)
        const buffer = await readFile(EVENTS)
        const chunk = buffer.subarray(offset).toString("utf8")
        writeOffset(info.size)
        for (const line of chunk.split(/\r?\n/)) {
          if (!line.trim()) continue
          try {
            await notify(JSON.parse(line) as SwitchEvent)
          } catch (error) {
            debug(`event error ${String(error)}`)
          }
        }
      } finally {
        closeSync(lock)
        try {
          unlinkSync(LOCK)
        } catch {}
      }
    }

    const timer = setInterval(
      () => void check().catch((error) => debug(`check error ${String(error)}`)),
      3000,
    )
    debug("setup ready")
    return () => clearInterval(timer)
  },
})
