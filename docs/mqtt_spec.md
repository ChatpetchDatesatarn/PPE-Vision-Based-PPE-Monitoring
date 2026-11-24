# MQTT Specification v3 — AI Smart Safety Monitoring

v3 (2026-10-15): DeepStream = perception, CiRA CORE = decision, Tapo C200C over RTSP, video over WebRTC (not MQTT).
Dashboard-side details (UI mapping, HTTP API): see `dashboard/README.md`.

Broker: Mosquitto (Docker) on the Jetson
- 1883 = MQTT/TCP (DeepStream, CiRA, recorder, simulator)
- 9001 = WebSocket (Dashboard connects via nginx `ws://<Jetson>:8080/mqtt`)

Time = ISO 8601 with +07:00. `<cam>` = camera id, e.g. `cam01`. Prefix = `factory/safety/`.
Coordinates (`bbox`, zone points) are normalized 0–1 of the frame. `bbox` = [x, y, w, h].

## Topics

| Topic | Publisher | Subscribers | Payload | QoS / retain |
|---|---|---|---|---|
| `<cam>/ds/violation` | DeepStream | CiRA | JSON candidate violation | 1 / no |
| `<cam>/snapshot/<snapshot_id>` | DeepStream | recorder | raw JPEG bytes (annotated, ~640 px wide) | 1 / no |
| `<cam>/event` | CiRA (normal) or DeepStream (fallback) | Dashboard, recorder | JSON official event | 1 / no |
| `<cam>/status` | DeepStream | Dashboard | JSON heartbeat every 5 s, LWT `{"online":false}` | 1 / yes |
| `cira/status` | CiRA | Dashboard, DeepStream | JSON heartbeat every 10 s | 1 / yes |
| `ack` | Dashboard | Dashboard, recorder | JSON staff confirmation | 1 / no |
| `<cam>/config/zones` | Dashboard (zone editor) | DeepStream | JSON zone polygons | 1 / yes |
| `<cam>/frame` | simulator only (legacy v2) | — | raw JPEG | 0 / no |

Live video is NOT on MQTT: DeepStream (OSD, boxes burned in) → RTSP :8555 → MediaMTX → WebRTC (WHEP `/webrtc/<cam>/whep`).

## 1) ds/violation (DeepStream → CiRA)
Sent when a condition has held ≥ hold time (no_helmet/no_vest 2 s, restricted_zone 0.5 s), then re-sent every 5 s while it persists.
DeepStream does NOT apply cooldown — that is CiRA's job. The snapshot is published BEFORE this message.
```json
{ "camera_id": "cam01", "ts": "2026-10-15T10:15:11+07:00", "type": "no_helmet",
  "track_id": 7, "conf": 0.82, "zone_id": "line-1", "bbox": [0.41, 0.22, 0.18, 0.55],
  "snapshot_id": "cam01-20261015-101511-007", "repeat": 0, "zone_overlap": 0.18 }
```
`type`: `no_helmet` | `no_vest` | `restricted_zone` | `unknown_visibility`. `repeat` = 0 first time, then 1, 2, ...
`zone_overlap` (0.0–1.0): how much of the person's box is inside its zone (the fraction the restricted-zone
check measured for that person), **debug only** — CiRA ignores it.

## 2) event (CiRA → Dashboard, recorder)
CiRA filters (conf), applies policy (camera/zone/shift), cooldown 30 s per (camera, track, type), assigns severity and event_id.
```json
{ "event_id": "cam01-20261015-101512-007-nh", "ts": "2026-10-15T10:15:12+07:00",
  "camera_id": "cam01", "zone_id": "line-1", "type": "no_helmet", "severity": "high",
  "track_id": 7, "confidence": 0.82, "bbox": [0.41, 0.22, 0.18, 0.55],
  "snapshot_id": "cam01-20261015-101511-007", "via": "cira" }
```
| field | values |
|---|---|
| `severity` | `critical` (restricted_zone) · `high` (no_helmet) · `warning` (no_vest) · `info` (unknown_visibility) — default mapping, policy may change it |
| `via` | `cira` normally; `fallback` when DeepStream publishes directly because `cira/status` is older than 15 s |
| `event_id` | `<cam>-YYYYMMDD-HHMMSS-<track_id, 3 digits>-<type code>` (+07:00); type code `nh` = no_helmet, `nv` = no_vest, `rz` = restricted_zone, `uv` = unknown_visibility. The code keeps two types of one person in the same second apart (the recorder keeps only the first event of an id) |
| `snapshot_id` | image at `/data/snapshots/<snapshot_id>.jpg`; may be missing. `<cam>-YYYYMMDD-HHMMSS-<track_id, 3 digits>` = time of that picture; a new picture comes with every `ds/violation` (repeats too) |

**Note (2026-10-16):** CiRA's `decide.js` (ส้ม) must build `event_id` in this same format, with the type code.

## 3) <cam>/status (DeepStream heartbeat, retained, every 5 s)
```json
{ "camera_id": "cam01", "name": "CAM 01 - Main Entrance", "ts": "2026-10-15T10:15:12+07:00",
  "online": true, "camera_connected": true, "fps_in": 29.8, "fps_infer": 14.9,
  "last_frame_age_s": 0.1, "resolution": "1920x1080", "model": "ppe_v1",
  "persons": 3, "compliant": 2, "violating": 1, "stream_path": "cam01" }
```
- DeepStream down = `online:false` (LWT) or `ts` older than 15 s
- Camera down = `online:true` and `camera_connected:false`

## 4) cira/status (CiRA heartbeat, retained, every 10 s)
```json
{ "online": true, "ts": "2026-10-15T10:15:10+07:00", "flow": "safety_decision_v1",
  "received": 128, "published": 41, "filtered": 87 }
```
CiRA may not support LWT → consumers treat `ts` older than 30 s (Dashboard) / 15 s (DeepStream fallback) as offline.

## 5) ack (Dashboard)
```json
{ "event_id": "cam01-20261015-101512-007-nh", "status": "resolved", "by": "dashboard",
  "note": "", "ts": "2026-10-15T10:16:00+07:00" }
```
`status`: `resolved` | `false_alarm` (used for the false-alarm rate in test results).

## 6) <cam>/config/zones (Dashboard → DeepStream, retained)
```json
{ "camera_id": "cam01", "ts": "2026-10-15T10:20:00+07:00",
  "zones": [ { "id": "zone-a", "name": "Machine area",
               "points": [[0.10,0.55],[0.45,0.55],[0.45,0.95],[0.10,0.95]],
               "mode": "overlap", "min_overlap": 0.10 } ] }
```
Restricted-zone check — three modes (whole-system default set by the app `--zone-mode` / `--zone-overlap`):
- **overlap** (default): a person is in a zone when `area(bbox ∩ polygon) / area(bbox) ≥ min_overlap`
  (default `0.10`). Catches people standing in the zone even when their feet are hidden or cut off.
- **foot** (old rule): the foot point (bottom-centre of the bbox) is inside the polygon.
- **bottom**: the bottom 25 % band of the bbox overlaps the polygon `≥ min_overlap` (for occluded feet).

Polygons may be concave; a self-intersecting (bow-tie) polygon is used anyway but logs a warning. `mode` and
`min_overlap` are **optional per-zone fields** that override the system default for that zone only — the rest
of the `config/zones` shape is unchanged and the Dashboard need not send them. The measured fraction is
echoed back in `ds/violation.zone_overlap` for debugging.

## Changes from v2
- Added `ds/violation`, `snapshot/<id>`, `cira/status`, `config/zones`
- `event` gains `severity`, `snapshot_id`, `via`; `snapshot_b64` removed
- `status` gains camera/fps/person-count fields
- 2026-10-16: `event_id` ends with a type code (`-nh` / `-nv` / `-rz` / `-uv`); every `ds/violation` (repeats too) gets its own snapshot
- `frame` (JPEG over MQTT) replaced by WebRTC video; kept only for the old simulator
- 2026-10-22: restricted-zone modes (`overlap` default / `foot` / `bottom`), optional per-zone `mode` /
  `min_overlap` in `config/zones`, and `zone_overlap` (debug) in `ds/violation`
