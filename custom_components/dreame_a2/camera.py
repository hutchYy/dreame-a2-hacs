"""Camera platform: renders the live lawn map to a PNG."""
from __future__ import annotations

import io
import math

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameConfigEntry
from .entity import DreameEntity

INT_MAX = 2147483647
IMG_W, IMG_H = 900, 700
PAD = 40

# Zone fill/stroke palette (RGBA)
ZONE_COLORS = [
    ((82, 183, 136), (149, 213, 178)),
    ((99, 155, 253), (163, 196, 255)),
    ((249, 168, 37), (253, 216, 53)),
    ((239, 83, 80), (239, 154, 154)),
    ((171, 71, 188), (206, 147, 216)),
    ((38, 198, 218), (128, 222, 234)),
]
BG = (10, 13, 18)
DOCK_COLOR = (76, 201, 240)
ROBOT_COLOR = (255, 87, 51)
TRAJ_COLOR = (247, 37, 133)


async def async_setup_entry(
    hass: HomeAssistant, entry: DreameConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DreameMapCamera(entry.runtime_data)])


class DreameMapCamera(DreameEntity, Camera):
    _attr_translation_key = "map"

    def __init__(self, coordinator) -> None:
        DreameEntity.__init__(self, coordinator, "map")
        Camera.__init__(self)
        self._cache_key = None
        self._cache_png: bytes | None = None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and (self.coordinator.data or {}).get("map") is not None

    async def async_camera_image(self, width=None, height=None) -> bytes | None:
        data = self.coordinator.data or {}
        map_data = data.get("map")
        if not map_data:
            return None
        pose = data.get("pose")
        key = (self.coordinator._map_ts, tuple(pose.values()) if pose else None, data.get("active_map"))
        if key == self._cache_key and self._cache_png is not None:
            return self._cache_png
        png = await self.hass.async_add_executor_job(
            _render, map_data, data.get("dock"), pose
        )
        self._cache_key = key
        self._cache_png = png
        return png


def _render(map_data: dict, dock, pose) -> bytes | None:
    from PIL import Image, ImageDraw  # imported lazily; ships with HA

    zones = [z for z in map_data.get("map", []) if z.get("type") == 0 and z.get("data")]
    pts: list[list[float]] = []
    for z in zones:
        for p in z["data"]:
            if p and p[0] != INT_MAX:
                pts.append(p)
    if not pts:
        return None

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = (max_x - min_x) or 1
    span_y = (max_y - min_y) or 1
    scale = min((IMG_W - 2 * PAD) / span_x, (IMG_H - 2 * PAD) / span_y)

    def sx(x: float) -> float:
        return PAD + (x - min_x) * scale

    def sy(y: float) -> float:
        return IMG_H - PAD - (y - min_y) * scale  # flip Y

    img = Image.new("RGB", (IMG_W, IMG_H), BG)
    d = ImageDraw.Draw(img, "RGBA")

    # Zones
    for i, z in enumerate(zones):
        poly = [(sx(p[0]), sy(p[1])) for p in z["data"] if p and p[0] != INT_MAX]
        if len(poly) < 3:
            continue
        fill, stroke = ZONE_COLORS[i % len(ZONE_COLORS)]
        d.polygon(poly, fill=fill + (70,), outline=stroke + (255,))
        cx = sum(x for x, _ in poly) / len(poly)
        cy = sum(y for _, y in poly) / len(poly)
        label = z.get("name") or f"Zone {z.get('id', i)}"
        d.text((cx, cy), label, fill=(255, 255, 255, 220), anchor="mm")

    # Trajectory
    for traj in map_data.get("trajectory", []) or []:
        line = traj.get("data") if isinstance(traj, dict) else None
        if not line:
            continue
        seg = [(sx(p[0]), sy(p[1])) for p in line if p and p[0] != INT_MAX]
        if len(seg) >= 2:
            d.line(seg, fill=TRAJ_COLOR + (110,), width=2)

    # Dock
    dpt = None
    if isinstance(dock, dict) and isinstance(dock.get("dock"), dict):
        dpt = (dock["dock"].get("x"), dock["dock"].get("y"))
    elif isinstance(map_data.get("dock"), list) and len(map_data["dock"]) >= 2:
        dpt = (map_data["dock"][0], map_data["dock"][1])
    if dpt and dpt[0] is not None:
        x, y = sx(dpt[0]), sy(dpt[1])
        d.rectangle([x - 9, y - 6, x + 9, y + 6], fill=DOCK_COLOR + (255,))
        d.text((x, y - 16), "DOCK", fill=DOCK_COLOR + (255,), anchor="mm")

    # Robot pose
    if pose and pose.get("x") is not None:
        x, y = sx(pose["x"]), sy(pose["y"])
        d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=ROBOT_COLOR + (255,), outline=(255, 255, 255, 255))
        ang = math.radians(pose.get("angle") or 0)
        d.line([(x, y), (x + 16 * math.cos(ang), y - 16 * math.sin(ang))], fill=(255, 255, 255, 255), width=2)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
