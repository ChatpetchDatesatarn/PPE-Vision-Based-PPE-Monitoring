# Docker on Jetson Nano (v2)

| container | Purpose |
|---|---|
| `mosquitto` | MQTT broker (1883, WebSocket 9001) |
| `recorder` | Stores events + snapshot images from CiRA in volume `safety-data` (`events.json`, `snapshots/`) |
| `dashboard` | nginx at `http://<Jetson IP>:8080` — serves the Dashboard, `/data` (history + images), `/mqtt` (WebSocket → mosquitto) |

CiRA CORE runs natively on the Jetson (not in Docker) and sends to `localhost:1883`
The mosquitto installed by the CiRA installer must be masked (`sudo systemctl mask mosquitto`) so it doesn't take port 1883

## Update / start
From the PC, copy the updated files to the Jetson, then:
```bash
cd ~/safety/legacy/docker_v2
docker-compose up -d --build --remove-orphans   # --remove-orphans removes the old alert container
docker-compose ps
```

## Test (no CiRA needed)
On the PC: `pip install paho-mqtt pillow` then
```powershell
python tools/simulate_events.py --host <JETSON_LAN_IP>     # or <JETSON_TAILSCALE_IP> from outside
```
Open `http://<Jetson IP>:8080` — you should see the real-time frame + events with images

## Daily commands
```bash
docker-compose ps
docker-compose logs -f recorder
docker-compose restart dashboard
docker run --rm -v 11docker_safety-data:/d alpine du -sh /d     # how much space history + images use
```

## Using Claude
There is no `claude-dev` container — use Claude Code on the laptop: `ssh jetson` (LAN) / `ssh jetson-remote` (Tailscale)
