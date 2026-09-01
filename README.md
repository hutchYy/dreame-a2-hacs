# Dreame A2 Mower — Home Assistant integration

Full control and setup of the **Dreame A2 robot mower (G2568A)** inside Home
Assistant, including a **live map**. Self-contained Python — it talks directly
to the Dreame cloud (a port of the verified reverse-engineered protocol), so it
needs no external service.

> Authorized security research on hardware owned by the operator.

## Features

- **Lawn mower entity** — start / pause / dock (start resumes when paused).
- **Live map camera** — the active map rendered with zones, dock, robot pose and
  mowing trajectory. Refreshed on a slow cadence; pose updates each poll.
- **Active-map selector** — switch which stored map the robot uses. All
  settings and the map are map-aware (resolved from the robot's `MAPL`).
- **Sensors** — battery, state, area mowed / total, session time.
- **Binary sensors** — online, problem, charging.
- **Mowing settings** — cutting height, cutting pattern, automatic edge mowing,
  safe edge mowing, **EdgeMaster** (blade disc to the side), edge/LiDAR obstacle
  avoidance, obstacle height & keep-distance, efficient mode.
- **Device settings** — frost protection, weather adaptation, pathway obstacle
  avoidance, child lock, daytime lights, auto-recharge-after-standby, AI obstacle
  photos, navigation path, volume.
- **Buttons** — find robot, mow edges, stop, refresh map.

## Install

### HACS (custom repository)
1. HACS → ⋮ → **Custom repositories** → add this repo, category **Integration**.
2. Install **Dreame A2 Mower**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Dreame A2 Mower**.
4. Enter your Dreame Smartlife **email**, **password**, and **region** (`eu`,
   `us`, `sg`, `cn`, `ru`). The password is exchanged for a token and only its
   salted hash is stored.

### Manual
Copy `custom_components/dreame_a2/` into your HA `config/custom_components/`,
restart, then add the integration as above.

## The map card

Add a Picture Entity (or Picture Glance) card pointing at the camera:

```yaml
type: picture-entity
entity: camera.dreame_a2_map
camera_view: auto
name: Lawn
```

## MCP — expose the mower to LLMs

Two ways, depending on what you want:

### A. Home Assistant's built-in MCP Server (recommended, native)
Home Assistant ships a **Model Context Protocol Server** integration that
exposes HA's Assist tools/entities over MCP. Once this integration's entities
are added:

1. **Settings → Voice assistants → Expose** — expose the Dreame entities to
   Assist (the lawn mower, switches, selects, sensors).
2. **Add Integration → Model Context Protocol Server** (enables the `/mcp_server`
   SSE endpoint).
3. Point any MCP client (Claude, etc.) at that endpoint with a long-lived access
   token. The mower is now controllable through HA's own MCP server — no extra
   process.

### B. Standalone Dreame MCP server (richer, protocol-level tools)
The repo's `mcp-server/` is a dedicated Streamable-HTTP MCP server with 32
mower-specific tools (map switching, per-map settings, destructive map edits,
raw commands). Use it when you want fine-grained protocol control rather than
HA's generic entity tools. See `mcp-server/README.md`.

## Notes & limits

- **Cloud polling** every 30 s (map every ~120 s; both are chunked cloud calls
  serialized through the robot's command queue).
- Mowing settings are **per-map**; this integration reads/writes the robot's
  **active** map. EdgeMaster maps to `cutter_position` (verified against the
  mobile app), and enabling it bumps edge passes 1→2 like the app.
- Manual/Bluetooth-only features (e.g. live remote drive) are not exposed —
  those require BLE, not the cloud API.
