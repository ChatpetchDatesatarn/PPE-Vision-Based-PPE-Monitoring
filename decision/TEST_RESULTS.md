# CiRA decision flow — live test results

Tested against the **running** CiRA (`safety_decision_v1.npj`) on the Jetson, 2026-10-21 21:46–21:49 +07.
Fake `ds/violation` messages were published from inside the mosquitto container
(`docker exec mosquitto mosquitto_pub -t factory/safety/cam01/ds/violation …`). Events were captured on
`factory/safety/cam01/event`, heartbeats on `factory/safety/cira/status`. DeepStream ran with `--events off`
(no real violations), so every event below came only from the test. All 14 test events were deleted from the
recorder afterwards (`track_id 800–899`, 14 rows → events 0). Test track ids: 801–820.

| # | Case | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | `no_helmet` conf 0.82 (track 801) | 1 event, severity high, id `…-nh` | `cam01-20261021-214620-801-nh`, high, via:cira | PASS |
| 2 | `no_helmet` conf 0.39 (track 802) | no event (< 0.40) | no event | PASS |
| 3 | same track 803 every 5 s for 40 s | 2 events (cooldown 30 s) | events at 21:46:19 and 21:46:53 (34 s apart) | PASS |
| 4 | `no_helmet` + `no_vest` same second (track 804) | 2 events, different ids | `…-804-nh` (high) + `…-804-nv` (warning) | PASS |
| 5 | two tracks 805 + 806 at once | 2 events | `…-805-nh` + `…-806-nh` | PASS |
| 6 | `restricted_zone` + `zone_id=zone-a` (track 807) | critical, zone_id preserved | `…-807-rz`, severity critical, `zone_id:"zone-a"` | PASS |
| 7 | `unknown_visibility` conf 0.90 (track 808) | no event (type disabled) | no event | PASS |
| 8 | broken JSON `{bad json`, then valid JSON with no `track_id` | no event, flow does not die | no event for either; bursts 810–814 after still fired | PASS |
| 9 | `docker restart mosquitto` (down a few seconds) | CiRA reconnects by itself | after restart, track 820 → event via:cira; heartbeat resumed | PASS |
| 10 | CiRA down → DeepStream fallback → CiRA up | events switch cira → fallback (≤15 s) → cira | see "Fallback (case 10)" below | PASS |
| 11 | `received == published + filtered` each heartbeat | counts add up | `received 23 = 14 + 9`, later `24 = 15 + 9` | PASS |
| 12 | ts / event_id are BKK, no milliseconds | `…THH:MM:SS+07:00`, `…-HHMMSS-…` | e.g. `2026-10-21T21:46:19+07:00`, `…-214619-…` | PASS |
| 13 | heartbeat every 10 ± 1 s | ~10 s spacing | deltas 9.8, 9.8, 10.0, 10.1, 10.0, 10.0, 10.1 s | PASS |
| 14 | burst of 5 different tracks at once (810–814) | 5 events | all 5 published (`…-810-nh` … `…-814-nh`) | PASS |

13 of 14 PASS (case 10 belongs to phase 2). No case failed.

## Fallback (case 10) — clip `clean_ppe_01.mp4`, `--events on --realtime`

DeepStream decides `cira` vs `fallback` from the `factory/safety/cira/status` heartbeat
(`violations.Fallback`, `CIRA_STALE_S = 15 s`): if no fresh heartbeat for 15 s it publishes the event itself
with `via:"fallback"`. Recorder timeline (one person, track 1):

| Time | event | via |
|---|---|---|
| 22:45:01 | no_helmet | **cira** (CiRA up) |
| 22:45:03 | no_vest | **cira** |
| 22:45:17 | `cira-stop` | — |
| 22:45:26 | no_helmet | **fallback** (9 s after stop, ≤ 15 s) |
| 22:45:54 | no_vest | **fallback** |
| 22:45:57 | no_helmet | **fallback** |
| 22:48:30→22:49:59 | `cira-up` (89 s) | — |
| 22:50:19 | no_helmet | **cira** (recovered) |
| 22:50:21 | no_vest | **cira** |

So: `cira` → stop → `fallback` within 9 s → `cira-up` → back to `cira`. Events are sparse because there is one
track and both CiRA and the fallback apply a 30 s per-(camera,track,type) cooldown. All test events + 27 test
snapshots were deleted afterwards (events 0, snapshots 0); the live app was restored with `--events off`.

## Notes
- Case 9: CiRA's MqttSub/MqttPub nodes auto-reconnect to the broker after it restarts — **no manual step
  needed**. The counters keep their previous values (they live in the `decide_state` global, not in the broker).
- Case 11 cross-check: of the 22 new messages that reached the decide node, 13 became events and 9 were
  filtered; the broken-JSON message was dropped by the MqttSub node before the JS ran (so it is not counted),
  which is why `received` rose by 22, not by every `mosquitto_pub` sent.
- The ES5 unit tests (`tests/test_decide_es5.js`, 15 checks) cover the same logic offline on Node; both the
  unit tests and this live run agree.
