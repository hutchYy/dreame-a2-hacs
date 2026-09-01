"""Async Python client for the Dreame A2 cloud API.

A faithful port of the verified TypeScript reference implementation
(webui/src/lib/dreame.ts). Pure aiohttp + stdlib — no Home Assistant imports —
so it can be unit-tested standalone.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import ssl
import time
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import DEFAULT_D, PARAMS_MAP

# ── Protocol constants (from libdreame-lib.so) ───────────────────────────────
SALT_DEFAULT = "EETjszu*XI5znHsI"
SALT_PASSWORD = "RAylYC%fmSKp7%Tq"
BASIC_AUTH = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
UA = "Dreame_Smarthome/1.5.59 (iPhone; iOS 16.0; Scale/3.00)"
RLC = "1c80b3787b2266776bcdc481f37d8fa42ba10a30af81a6df-1"
TENANT = "000000"

MAPD_CHUNK_SIZE = 3000


class DreameError(Exception):
    """A Dreame API error."""


class DreameAuthError(DreameError):
    """Authentication failed (bad credentials or unrecoverable token)."""


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """Password hash used at login (Salt B)."""
    return _md5(password + SALT_PASSWORD)


def _flatten(obj: Any) -> str:
    """Recursive stable flatten used for request signing."""
    if obj is None:
        return ""
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, list):
        return "[" + ",".join(_flatten(x) for x in obj) + "]"
    if isinstance(obj, dict):
        return "&".join(f"{k}={_flatten(obj[k])}" for k in sorted(obj.keys()))
    return str(obj)


def sign_body(body: dict, salt: str = SALT_DEFAULT) -> dict:
    """Add sign + timestamp to a request body (Salt A)."""
    ts = str(int(time.time() * 1000))
    sig = _md5(_flatten(body) + ts + salt)
    return {**body, "sign": sig, "timestamp": ts}


def _base_url(region: str) -> str:
    return f"https://{region}.iot.dreame.tech:13267"


def extract_out_d(res: dict) -> Any:
    """Pull result.out[0].d from a sendCommand response."""
    try:
        return res["data"]["result"]["out"][0]["d"]
    except (KeyError, IndexError, TypeError):
        return None


def parse_d_array(out: Any) -> list | None:
    if isinstance(out, list):
        return out
    if isinstance(out, dict) and isinstance(out.get("d"), list):
        return out["d"]
    return None


class DreameApi:
    """Talks to the Dreame cloud. One instance per config entry."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        email: str,
        pw_hash: str,
        region: str = "eu",
        token: str | None = None,
        refresh: str | None = None,
        uid: str | None = None,
        expires: float = 0,
        did: str | None = None,
        model: str | None = None,
    ) -> None:
        self._session = session
        self.email = email
        self.pw_hash = pw_hash
        self.region = region or "eu"
        self.token = token
        self.refresh = refresh
        self.uid = uid
        self.expires = expires
        self.did = did
        self.model = model
        self._lock = asyncio.Lock()  # serializes robot commands (cloud relay)
        self._ssl = ssl.create_default_context()
        self._ssl.check_hostname = False
        self._ssl.verify_mode = ssl.CERT_NONE

    # ── low-level HTTP ────────────────────────────────────────────────────
    async def _request(self, method: str, url: str, *, headers: dict, data: Any = None) -> Any:
        try:
            async with self._session.request(
                method, url, headers=headers, data=data, ssl=self._ssl,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise DreameError(f"Network error: {err}") from err
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"status": resp.status, "text": text}

    def _token_expired(self) -> bool:
        return not self.expires or time.time() >= self.expires

    # ── auth ──────────────────────────────────────────────────────────────
    async def login(self) -> None:
        """Obtain an access token from stored email + password hash."""
        body = (
            "platform=IOS&scope=all&grant_type=password"
            f"&username={quote(self.email)}&password={self.pw_hash}&type=account"
        )
        res = await self._request(
            "POST",
            f"{_base_url(self.region)}/dreame-auth/oauth/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": BASIC_AUTH,
                "Tenant-Id": TENANT,
                "User-Agent": UA,
            },
            data=body,
        )
        if not res.get("access_token"):
            raise DreameAuthError(
                res.get("message") or res.get("error_description") or "Login failed"
            )
        self.token = res["access_token"]
        self.refresh = res.get("refresh_token")
        self.uid = res.get("uid")
        self.region = res.get("region") or self.region
        self.expires = time.time() + (res.get("expires_in") or 7200) - 60
        self.did = None
        self.model = None

    async def _ensure_token(self) -> None:
        if not self.token or self._token_expired():
            await self.login()

    # ── request helpers ─────────────────────────────────────────────────
    def _client_headers(self) -> dict:
        return {
            "Tenant-Id": TENANT,
            "Dreame-Rlc": RLC,
            "User-Agent": UA,
            "Content-Type": "application/json",
            "Dreame-Auth": self.token or "",
        }

    async def _client_api(self, path: str, body: dict | None = None, method: str = "POST") -> Any:
        await self._ensure_token()
        url = f"{_base_url(self.region)}{path}"
        res = await self._request(
            method, url, headers=self._client_headers(),
            data=json.dumps(body or {}) if method != "GET" else None,
        )
        if isinstance(res, dict) and res.get("code") == 401:
            await self.login()
            res = await self._request(
                method, url, headers=self._client_headers(),
                data=json.dumps(body or {}) if method != "GET" else None,
            )
        return res

    async def _mower_api(self, path: str, body: dict) -> Any:
        """Signed command through the serialized command queue."""
        async with self._lock:
            await self._ensure_token()
            url = f"{_base_url(self.region)}{path}"
            headers = {
                "Authorization": BASIC_AUTH,
                "Dreame-Auth": self.token or "",
                "Tenant-Id": TENANT,
                "Content-Type": "application/json",
                "Dreame-Rlc": "mower_ctl",
                "Dreame-Meta": "cv=a_102050403",
                "Client_id": "dreame_appv1",
            }
            res = await self._request("POST", url, headers=headers, data=json.dumps(sign_body(body)))
            if isinstance(res, dict) and res.get("code") == 401:
                await self.login()
                headers["Dreame-Auth"] = self.token or ""
                res = await self._request("POST", url, headers=headers, data=json.dumps(sign_body(body)))
            return res

    # ── device discovery ─────────────────────────────────────────────────
    async def get_devices(self) -> Any:
        return await self._client_api(
            "/dreame-user-iot/iotuserbind/device/listV2", {"pageNum": 1, "pageSize": 50}
        )

    async def get_did(self) -> str:
        if self.did:
            return str(self.did)
        res = await self.get_devices()
        data = res.get("data") or {}
        devices = data.get("list") or (data.get("page") or {}).get("records") or []
        for d in devices:
            if "mower" in (d.get("model") or "").lower():
                self.did = str(d.get("did") or d.get("iotId"))
                self.model = d.get("model") or ""
                return self.did
        if devices:
            self.did = str(devices[0].get("did") or devices[0].get("iotId"))
            return self.did
        raise DreameError("No device found on the account")

    # ── raw command / sendCommand / properties ───────────────────────────
    async def raw_command(self, params_json: dict) -> Any:
        did = await self.get_did()
        cid = int(time.time()) % 100000
        body = {
            "data": {"did": did, "id": cid, "method": "action", "from": "mower_ctl",
                     "params": {"did": did, **params_json}},
            "did": did, "id": cid,
        }
        return await self._mower_api("/dreame-iot-com-10000/device/sendCommand", body)

    async def send_command(self, siid: int, aiid: int, params=None, d_array=None) -> Any:
        did = await self.get_did()
        cid = int(time.time()) % 100000
        body: dict = {
            "data": {"did": did, "id": cid, "method": "action", "from": "mower_ctl",
                     "params": {"did": did, "siid": siid, "aiid": aiid}},
            "did": did, "id": cid,
        }
        if d_array is not None:
            body["data"]["params"]["in"] = [{"m": "s", "t": "PRE", "d": d_array}]
        elif params is not None:
            body["data"]["params"]["in"] = params
        return await self._mower_api("/dreame-iot-com-10000/device/sendCommand", body)

    async def get_properties(self, props: list[dict]) -> Any:
        did = await self.get_did()
        body = {
            "did": did,
            "data": {"did": did, "id": 1, "method": "get_properties",
                     "params": [{"did": did, "siid": p["siid"], "piid": p["piid"]} for p in props]},
        }
        return await self._mower_api("/dreame-iot-com-10000/device/sendCommand", body)

    # ── status telemetry ──────────────────────────────────────────────────
    async def get_status(self) -> dict:
        """Battery, state code, online, session stats."""
        devices_res, mista_res = await asyncio.gather(
            self.get_devices(), self.get_mista(), return_exceptions=True,
        )
        mower = None
        if isinstance(devices_res, dict):
            data = devices_res.get("data") or {}
            records = (data.get("page") or {}).get("records") or data.get("list") or []
            mower = next((r for r in records if "mower" in (r.get("model") or "").lower()), None)
        if not mower:
            raise DreameError("No mower found on the account")

        area_mowed = area_total = time_elapsed = 0
        if isinstance(mista_res, dict):
            d = extract_out_d(mista_res)
            if isinstance(d, dict):
                area_mowed = (d.get("fin") or 0) / 100
                area_total = (d.get("total") or 0) / 100
                time_elapsed = int((d.get("prg") or 0) / 60)

        code = mower.get("latestStatus")
        online = bool(mower.get("online")) or code in (1, 2, 3, 4, 5)
        return {
            "battery": mower.get("battery"),
            "state_code": code,
            "online": online,
            "name": (mower.get("deviceInfo") or {}).get("displayName") or mower.get("model"),
            "model": mower.get("model"),
            "did": str(mower.get("did") or mower.get("iotId") or ""),
            "area_mowed": area_mowed,
            "area_total": area_total,
            "time_elapsed": time_elapsed,
        }

    async def get_mista(self) -> Any:
        return await self.raw_command({"siid": 2, "aiid": 50, "in": [{"m": "g", "t": "MISTA", "d": {}}]})

    # ── control ───────────────────────────────────────────────────────────
    async def start_mowing(self) -> Any:
        return await self.send_command(2, 50, d_array=list(DEFAULT_D))

    async def pause_mowing(self) -> Any:
        return await self.send_command(5, 4)

    async def dock(self) -> Any:
        return await self.send_command(5, 3)

    async def resume_mowing(self) -> Any:
        return await self.send_command(2, 50, params=[{"m": "a", "o": 5, "d": {}}])

    async def edge_mowing(self) -> Any:
        return await self.send_command(2, 50, params=[{"m": "a", "o": 101, "d": {}}])

    async def find_robot(self) -> Any:
        return await self.send_command(2, 50, params=[{"m": "a", "o": 9, "d": {}}])

    async def stop_mowing(self) -> Any:
        return await self.send_command(2, 50, params=[{"m": "a", "o": 3, "d": {}}])

    async def zone_mowing(self, region: list[int]) -> Any:
        return await self.send_command(2, 50, params=[{"m": "a", "p": 0, "o": 102, "d": {"region": region}}])

    async def spot_mowing(self, area: list) -> Any:
        return await self.send_command(2, 50, params=[{"m": "a", "p": 0, "o": 103, "d": {"area": area}}])

    # ── patrol (cruise) ───────────────────────────────────────────────────
    async def cruise_edge(self, edge: list[list[int]]) -> Any:
        """Patrol along an edge path (o=108). `edge` is a list of [x, y] points."""
        return await self.send_command(2, 50, params=[{"m": "a", "p": 0, "o": 108, "d": {"edge": edge}}])

    async def cruise_point(self, point: list[int]) -> Any:
        """Patrol to a single point (o=107). `point` is [x, y]."""
        return await self.send_command(2, 50, params=[{"m": "a", "p": 0, "o": 107, "d": {"point": point}}])

    # ── work history ──────────────────────────────────────────────────────
    async def get_history(self, limit: int = 15) -> list[dict]:
        """Recent mowing sessions from the work-record API."""
        did = await self.get_did()
        now = int(time.time())
        body = {
            "did": did, "uid": self.uid, "key": "4.1", "type": 3,
            "time_start": now - 180 * 86400, "time_end": now,
            "limit": limit, "from": now - 180 * 86400,
            "siid": "4", "eiid": "1", "region": self.region,
        }
        res = await self._mower_api("/dreame-user-iot/iotstatus/history", body)
        sessions = ((res or {}).get("data") or {}).get("list") or []
        out = []
        for sess in sessions:
            try:
                props = {p["piid"]: p["value"] for p in json.loads(sess.get("history") or "[]")}
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            out.append({
                "timestamp": props.get(8, 0),
                "area": props.get(2, 0),
                "duration": (props.get(3, 0) or 0) // 60,
                "battery": props.get(1, 0),
                "map_path": props.get(9, ""),
            })
        return out

    # ── maps ────────────────────────────────────────────────────────────
    async def get_map_list(self) -> list[dict]:
        """MAPL — sent with NO d field, else the robot returns only the current map."""
        res = await self.raw_command({"siid": 2, "aiid": 50, "in": [{"m": "g", "t": "MAPL"}]})
        d = extract_out_d(res)
        rows = d if isinstance(d, list) else (d.get("d") if isinstance(d, dict) else []) or []
        out = []
        for e in rows:
            if isinstance(e, list) and e:
                out.append({
                    "index": int(e[0]),
                    "is_current": bool(e[1]) if len(e) > 1 else False,
                    "created": bool(e[2]) if len(e) > 2 else True,
                    "has_backup": bool(e[3]) if len(e) > 3 else False,
                })
        return [m for m in out if m["created"]]

    async def get_active_map_index(self) -> int:
        maps = await self.get_map_list()
        for m in maps:
            if m["is_current"]:
                return m["index"]
        return maps[0]["index"] if maps else 0

    async def switch_map(self, idx: int) -> Any:
        return await self.raw_command({"siid": 2, "aiid": 50, "in": [{"m": "a", "p": 0, "o": 200, "d": {"idx": idx}}]})

    async def get_map_info(self, idx: int) -> Any:
        return await self.raw_command({"siid": 2, "aiid": 50, "in": [{"m": "g", "t": "MAPI", "d": {"idx": idx}}]})

    async def _get_map_chunk(self, start: int, size: int) -> Any:
        return await self.raw_command({"siid": 2, "aiid": 50, "in": [{"m": "g", "t": "MAPD", "d": {"start": start, "size": size}}]})

    async def fetch_map_data(self, idx: int | None = None) -> dict | None:
        """MAPI selects the map; chunked MAPD streams its JSON."""
        if idx is None:
            idx = await self.get_active_map_index()
        info = extract_out_d(await self.get_map_info(idx))
        if not isinstance(info, dict) or not info.get("size"):
            return None
        total = int(info["size"])
        full = ""
        offset = 0
        retries = 0
        while offset < total and retries < 5:
            req = min(MAPD_CHUNK_SIZE, total - offset)
            d = extract_out_d(await self._get_map_chunk(offset, req))
            chunk = d.get("data") if isinstance(d, dict) and isinstance(d.get("data"), str) else (d if isinstance(d, str) else "")
            size = (d.get("size") if isinstance(d, dict) else None) or len(chunk)
            if not chunk:
                retries += 1
                continue
            full += chunk
            offset += size
            retries = 0
        try:
            return json.loads(full)
        except json.JSONDecodeError:
            return None

    async def get_dock_pos(self) -> Any:
        return extract_out_d(await self.raw_command({"siid": 2, "aiid": 50, "in": [{"m": "g", "t": "DOCK", "d": {}}]}))

    async def fetch_mowing_trail(self, max_chunks: int = 200) -> list[list[int]]:
        """The actual mown path via MITRC. 5 bytes/point, 20-bit signed x/y.

        Params use point-offset semantics ({idx: startPoint, size: count}); the
        robot returns ~60 points per call. Stops at the end of the trail (a short
        or empty chunk) or once max_chunks is hit, to bound cloud load.
        """
        import base64

        points: list[list[int]] = []
        chunk_pts = 60
        for i in range(max_chunks):
            res = await self.raw_command(
                {"siid": 2, "aiid": 50, "in": [{"m": "g", "t": "MITRC", "d": {"idx": i * chunk_pts, "size": chunk_pts}}]}
            )
            d = extract_out_d(res)
            track = d.get("track") if isinstance(d, dict) else None
            if not isinstance(track, str) or not track:
                break
            raw = base64.b64decode(track)
            if not raw or len(raw) % 5 != 0:
                break
            n = 0
            for j in range(0, len(raw), 5):
                b = raw[j:j + 5]
                xr = ((b[2] << 28) | (b[1] << 20) | (b[0] << 12)) & 0xFFFFFFFF
                xr = xr - 0x100000000 if xr & 0x80000000 else xr
                yr = ((b[4] << 24) | (b[3] << 16) | (b[2] << 8)) & 0xFFFFFFFF
                yr = yr - 0x100000000 if yr & 0x80000000 else yr
                points.append([xr >> 12, yr >> 12])
                n += 1
            if n < chunk_pts:
                break
        return points

    async def get_robot_pose(self) -> dict | None:
        res = await self.get_properties([{"siid": 1, "piid": 4}])
        try:
            val = res["data"]["result"][0]["value"]
        except (KeyError, IndexError, TypeError):
            return None
        if not isinstance(val, list) or len(val) < 7:
            return None
        b = val[1:7]
        x = ((b[2] << 28 | b[1] << 20 | b[0] << 12) & 0xFFFFFFFF)
        x = x - 0x100000000 if x & 0x80000000 else x
        x >>= 12
        y = ((b[4] << 24 | b[3] << 16 | b[2] << 8) & 0xFFFFFFFF)
        y = y - 0x100000000 if y & 0x80000000 else y
        y >>= 12
        angle = (b[5] / 255 * 360) if len(b) > 5 else 0
        return {"x": x, "y": y, "angle": angle}

    # ── mowing preferences (per active map) ───────────────────────────────
    async def get_preferences(self, map_idx: int | None = None, region: int = 0) -> list | None:
        if map_idx is None:
            map_idx = await self.get_active_map_index()
        res = await self.raw_command(
            {"siid": 2, "aiid": 50, "in": [{"m": "g", "t": "PRE", "d": {"idx": map_idx, "region": region}}]}
        )
        return parse_d_array(extract_out_d(res))

    async def get_mowing_settings(self) -> dict:
        d = await self.get_preferences()
        if not d:
            return {}
        return {name: d[pos] for name, pos in PARAMS_MAP.items() if pos < len(d)}

    async def set_mowing_settings(self, changes: dict[str, int]) -> Any:
        """Read-modify-write the active map's PRE d[] (preserves map idx/region)."""
        map_idx = await self.get_active_map_index()
        d = await self.get_preferences(map_idx)
        d = list(d) if d and len(d) >= 18 else list(DEFAULT_D)
        # EdgeMaster (cutter_position) also bumps edge passes 1→2, like the app.
        if changes.get("cutter_position") == 1 and d[PARAMS_MAP["edge_passes"]] == 1:
            d[PARAMS_MAP["edge_passes"]] = 2
        for key, val in changes.items():
            if key in PARAMS_MAP:
                d[PARAMS_MAP[key]] = val
        return await self.send_command(2, 50, d_array=d)

    # ── device settings (type codes) ─────────────────────────────────────
    async def get_consumables(self) -> list[int]:
        """CMS → [blade_used_min, brush_used_min, maintenance_used_min]."""
        d = extract_out_d(await self.raw_command({"siid": 2, "aiid": 50, "in": [{"m": "g", "t": "CMS", "d": {}}]}))
        v = d.get("value") if isinstance(d, dict) else None
        return v if isinstance(v, list) else []

    async def get_totals(self) -> dict:
        """Lifetime totals (MIHIS): {area m², count sessions, start epoch, time min}."""
        d = extract_out_d(await self.raw_command({"siid": 2, "aiid": 50, "in": [{"m": "g", "t": "MIHIS", "d": {}}]}))
        return d if isinstance(d, dict) else {}

    async def get_cfg(self) -> dict:
        res = await self.raw_command({"siid": 2, "aiid": 50, "in": [{"m": "g", "t": "CFG"}]})
        d = extract_out_d(res)
        return d if isinstance(d, dict) else {}

    async def _set(self, t: str, data: Any) -> Any:
        return await self.raw_command({"siid": 2, "aiid": 50, "in": [{"m": "s", "t": t, "d": data}]})

    async def set_volume(self, value: int) -> Any:
        return await self._set("VOL", {"value": value})

    async def set_child_lock(self, on: bool) -> Any:
        return await self._set("CLS", {"value": 1 if on else 0})

    async def set_daytime_lights(self, on: bool) -> Any:
        return await self._set("DLS", {"value": 1 if on else 0})

    async def set_frost_protect(self, on: bool) -> Any:
        return await self._set("FDP", {"value": 1 if on else 0})

    async def set_weather_adapt(self, on: bool) -> Any:
        return await self._set("WRF", {"value": 1 if on else 0})

    async def set_pathway_avoidance(self, on: bool) -> Any:
        return await self._set("PATH", {"value": 1 if on else 0})

    async def set_auto_recharge_standby(self, on: bool) -> Any:
        return await self._set("STUN", {"value": 1 if on else 0})

    async def set_ai_photos(self, on: bool) -> Any:
        return await self._set("AOP", {"value": 1 if on else 0})

    async def set_dnd(self, on: bool, start: int, end: int) -> Any:
        return await self._set("DND", {"value": 1 if on else 0, "time": [start, end]})
