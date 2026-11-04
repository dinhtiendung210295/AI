# peer-orchestrator

OpenCode 2 plugin that turns one session into an orchestrator of **independent top-level peer sessions**.
Each peer gets its own root session, its own composer in OpenCode Desktop, and its own tab. They are not
subagents: `parentID` is never set.

Built and tested against **OpenCode Desktop / CLI 2.2.5** (`@opencode/plugin@2.2.5`).

## Parts

| Part | Export | File |
| --- | --- | --- |
| Server | `.` | `src/index.ts` |
| RPC contract | `./rpc` | `src/rpc.ts` |
| Desktop GUI | `./gui-experimental` | `dist/gui-experimental.cjs` |

### Server (`src/index.ts`)

- `Plugin.define({ id: "peer-orchestrator", setup })`
- Registers the `spawn_peers` tool with `ctx.tool.transform`.
- Registers the RPC implementation with `ctx.rpc.register`.

`spawn_peers` input:

```json
{
  "tasks": [
    {
      "title": "Peer A",
      "prompt": "Investigate the parser and report findings.",
      "directory": "optional/working/directory"
    }
  ]
}
```

Behaviour:

1. Calls `ctx.session.create({ title, location? })` for every task. **`parentID` is never passed.**
2. Checks the returned session and fails the task if a `parentID` is present.
3. Sends every initial prompt with `Promise.all` and `ctx.session.prompt(...)`.
   `session.prompt` resolves when the prompt is admitted to the session inbox, so the call does not
   wait for worker turns to finish.
4. Persists the worker inventory in plugin storage and emits the RPC event `spawned`.
5. Returns every root session ID in the tool result.

Limit: 8 tasks per call.

### GUI (`src/gui.tsx` → `dist/gui-experimental.cjs`)

- Subscribes to `rpc.peer-orchestrator.spawned` and calls
  `ctx.tabs.open({ server, id }, { focus: false })` for each new root session.
- Adds the command **Open orchestrator workers**, also available as `/open-workers` in the composer.
  It calls the RPC method `workers` and opens the stored sessions again, so a missed event is recoverable.
- Resolves the Desktop sidecar by preferring the `builtin` server from `ctx.servers`.

## Build

Node and npm are required only for development or rebuilding the GUI; Bun is not needed.

```powershell
cd plugins/peer-orchestrator
npm install
npm run typecheck
npm run build
```

`npm run build` writes the single CommonJS GUI bundle `dist/gui-experimental.cjs` with the
`@opencode/plugin/gui/vite` preset. The built bundle is committed, so a normal install does not
need a build step.

## Load

Register the plugin directory in the global OpenCode config:

`%USERPROFILE%\.config\opencode\opencode.jsonc`

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugins": ["C:/path/to/AI/plugins/peer-orchestrator"]
}
```

Use the absolute path of the directory on that machine, with forward slashes on Windows.

OpenCode watches config and plugin files. After a GUI rebuild the Desktop reloads the GUI bundle.
If the window does not pick it up, use **Settings > Extensions > Plugins > Reload**.

## Use on another machine

1. Clone the repository and install the plugin dependencies:

   ```powershell
   git clone https://github.com/dinhtiendung210295/AI.git
   cd AI/plugins/peer-orchestrator
   npm install
   ```

2. Run `npm run build` only if you changed `src/gui.tsx` or `src/rpc.ts`. The committed
   `dist/gui-experimental.cjs` already works with OpenCode Desktop 2.2.x.

3. Add the absolute plugin directory to the global config at
   `%USERPROFILE%\.config\opencode\opencode.jsonc`. Create the file if it does not exist, or add
   one entry to the existing `plugins` array:

   ```jsonc
   {
     "$schema": "https://opencode.ai/config.json",
     "plugins": ["C:/Users/<you>/AI/plugins/peer-orchestrator"]
   }
   ```

   On macOS/Linux use a POSIX path such as `/home/<you>/AI/plugins/peer-orchestrator`.

4. Open **Settings > Extensions > Plugins** and confirm `peer-orchestrator` is active, or run
   `/reload` in the TUI. Ask the agent to call `spawn_peers`, or use `/open-workers` in the
   composer.

## Use

Ask the primary agent to call the tool, for example:

```text
Use spawn_peers with 3 tasks:
1. title "Peer A", prompt "Reply with PEER_A_OK"
2. title "Peer B", prompt "Reply with PEER_B_OK"
3. title "Peer C", prompt "Reply with PEER_C_OK"
```

Or call it directly when a Code Mode tool surface exposes `spawn_peers`.

Reopen missed worker tabs with:

- the command palette: **Open orchestrator workers**, or
- the composer slash command: `/open-workers`.

## Verify

The returned text lists each worker session ID. To inspect a session with the bundled CLI:

```powershell
$cli = "$env:LOCALAPPDATA\Programs\ai.opencode.desktop\resources\opencode-cli.exe"
& $cli api get "/api/session/<session-id>"
```

A peer session must have **no `parentID` field**, its own `location.directory`, and a normal chat composer
in Desktop. Subagent children do have `parentID` and are not listed as top-level tabs.

## Notes

- The GUI API is experimental (`./gui-experimental`), per OpenCode 2 documentation.
- RPC events are live-only. The command reads persisted state, which covers a window that missed an event.
- Worker prompts are stored locally in plugin storage to support reopening tabs.
- The tool must be allowed by the orchestrator agent's permissions (`subagent` is not used at all).
