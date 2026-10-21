# Plex Cleaner

A small self-hosted web app that **proposes** watched, old media for removal from your Plex library. It never deletes anything on its own: every removal needs your manual approval, and deletion goes through the Radarr/Sonarr APIs (so they stay in sync), followed by an optional Seerr cleanup.

> The web interface is currently in **Dutch**. Translation (English) is planned.

## Rules it follows
- Only content that is **watched** and not viewed for N days can be deleted.
- Never-watched content is shown **for information only**, never deletable.
- Partially watched series are never proposed.
- `dry_run: true` is the default: nothing can be deleted until you turn it off.
- No automatic deletes. Approve -> delete, one title at a time.
- A safety check compares the Plex file path with the Radarr/Sonarr folder before deleting.

## Features
Dashboard, candidates (approve / never suggest again / snooze 90 days), history, health status, in-app rotating log, login with brute-force lockout (session expires after 8 hours), monthly scan via cron with an optional Discord notification, manual "scan now" button.

## Install
Requires Docker + Docker Compose, and Plex, Radarr and Sonarr reachable from the container (Seerr optional).

```bash
git clone <this repo> && cd plex-cleaner
mkdir -p appdata/{config,data,logs,reports} && sudo chown -R 1000:1000 appdata
cp config.example.yaml appdata/config/config.yaml   # edit the URLs
cp .env.example .env                                # fill in keys
docker compose run --rm plex-cleaner python -m app.auth   # prints the 4 login lines for .env
docker compose up -d --build
```
Open `http://<host>:8090`. Quote `APP_PASSWORD_HASH` in single quotes (it contains `$`).

Use `DATA_DIR` in `.env` to store data elsewhere (it must be writable by uid 1000).

## Monthly scan (optional)
```cron
0 9 1 * * curl -s -m 300 -X POST -H "X-Scan-Token: $(grep ^SCAN_TOKEN= /path/to/.env | cut -d= -f2)" http://localhost:8090/scan
```
Set `DISCORD_WEBHOOK_URL` to get a message when items are waiting for review (set `APP_URL` for the link in it).

## Security
- Do not expose port 8090 to the internet; put it behind a VPN or reverse proxy with HTTPS.
- Keep `.env` private (it is in `.gitignore`). No secrets live in the code.
- The container runs as a non-root user and needs no Docker socket.
- Deleting removes files from disk (`deleteFiles=true` in Radarr/Sonarr). Test with a title you can restore first.

## Disclaimer
Provided as-is, no warranty. You are responsible for what you delete. MIT licensed.
