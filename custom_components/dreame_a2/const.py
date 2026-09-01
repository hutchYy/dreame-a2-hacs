"""Constants for the Dreame A2 mower integration."""
from __future__ import annotations

DOMAIN = "dreame_a2"

# Config entry keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_REGION = "region"
CONF_DID = "did"

REGIONS = ["eu", "us", "sg", "cn", "ru"]
DEFAULT_REGION = "eu"

# Polling
DEFAULT_SCAN_INTERVAL = 30  # seconds; map refreshed less often (see coordinator)
MAP_REFRESH_INTERVAL = 120  # seconds

# Robot state codes (mower.latestStatus) → labels, verified in the web dashboard.
STATE_MOWING = 1
STATE_PAUSED = 2
STATE_RETURNING = 3
STATE_ERROR = 4
STATE_CHARGING_PENDING = 5
STATE_DOCKED = 6

STATE_LABELS = {
    STATE_MOWING: "mowing",
    STATE_PAUSED: "paused",
    STATE_RETURNING: "returning",
    STATE_ERROR: "error",
    STATE_CHARGING_PENDING: "charging",
    STATE_DOCKED: "docked",
}

# Mowing preference d[] positions (PRE array). Verified against the RN plugin
# cvt2Payload/payload2Cvt. EdgeMaster is cutter_position (10), NOT walk_mode.
PARAMS_MAP = {
    "mode": 0,
    "profile_id": 1,  # actually the map index in the setter
    "zone_id": 2,
    "efficient_mode": 3,
    "cut_height": 4,  # cm*10
    "direction_mode": 5,  # 0=off,1=crisscross,2=chequerboard
    "mow_direction": 6,  # wire = 180 - UI angle
    "edge_auto": 7,
    "edge_walk_mode": 8,
    "edge_obstacle_avoidance": 9,
    "cutter_position": 10,  # EdgeMaster
    "edge_passes": 11,
    "lidar_obstacle": 12,
    "obstacle_height": 13,
    "obstacle_distance": 14,
    "obstacle_ai": 15,
    "edge_safe": 16,
    "obstacle_sensitivity": 17,
}

DEFAULT_D = [0, 0, 0, 0, 60, 0, 102, 1, 1, 1, 1, 1, 1, 15, 20, 7, 1, 2]

# Consumable max life in minutes (RN plugin ConsumableItem). CMS returns used
# minutes; remaining % = 100 - used/max*100.
CONSUMABLE_MAX = {"blade": 6000, "brush": 30000, "maintenance": 3600}

MANUFACTURER = "Dreame"
MODEL_NAME = "A2 Robot Mower (G2568A)"
