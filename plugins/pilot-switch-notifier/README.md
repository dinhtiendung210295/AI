# Pilot switch notifier

OpenCode 2 server plugin that watches the local pilot switch-event JSONL file
and inserts an informational synthetic message into the active
`pilot_multivibe` session. It does not start a model request.

Environment variables:

- `PILOT_SWITCH_EVENTS`: path to `pilot-switch-events.jsonl`.
- `PILOT_NOTIFIER_DEBUG`: optional local debug-log path.

The plugin does not read or log access tokens.
