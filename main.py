import os

import requests
import json
import logging
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

from flask import Flask, flash, redirect, render_template, request, url_for

from app.analysis import find_candidates
from app.auth import init_auth
from app.clients.plex_client import PlexClient
from app.clients.radarr_client import RadarrClient
from app.clients.seerr_client import SeerrClient
from app.clients.sonarr_client import SonarrClient
from app.config import load_config
from app.health import check_all_services
from app.notify import send_discord
from app.storage import (
    add_exception,
    load_candidates,
    load_decisions,
    load_exceptions,
    load_exceptions_full,
    record_decision,
    save_candidates,
)

app = Flask(__name__)

LOG_FILE = os.environ.get("LOG_FILE", "/logs/plex-cleaner.log")
SNOOZE_FILE = os.environ.get("SNOOZE_FILE", "/data/snoozed.json")
SNOOZE_DAYS = 90


def setup_logging():
    try:  # roteert zelf: max 4 bestanden van 1 MB
        h = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError as exc:
        print(f"Logbestand niet beschikbaar: {exc}")
        return
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(h)


setup_logging()


def load_snoozed():
    try:
        with open(SNOOZE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_snoozed(data):
    with open(SNOOZE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
init_auth(app)  # zet secret_key + blokkeert alles behalve /login


def build_results(config):
    plex = PlexClient(config.services["plex"])
    radarr_index = RadarrClient(config.services["radarr"]).build_tmdb_index()
    sonarr_index = SonarrClient(config.services["sonarr"]).build_tvdb_index()

    sections = plex.get_libraries().get("MediaContainer", {}).get("Directory", [])
    key_by_title = {s.get("title"): s.get("key") for s in sections}
    excluded_keys = load_exceptions()
    decisions = load_decisions()
    snoozed = load_snoozed()
    now_iso = datetime.now(timezone.utc).isoformat()

    results, errors = [], []
    for library_name in config.libraries:
        key = key_by_title.get(library_name)
        if key is None:
            errors.append(f"Bibliotheek '{library_name}' niet gevonden in Plex")
            continue
        try:
            data = plex.get_library_items(key)
        except Exception as exc:
            errors.append(f"Kon '{library_name}' niet ophalen: {exc}")
            continue

        items = data.get("MediaContainer", {}).get("Metadata", [])
        for c in find_candidates(
            items,
            config.never_watched_min_age_days,
            config.fully_watched_min_days_since_watch,
        ):
            if c.rating_key in excluded_keys or snoozed.get(c.rating_key, "") > now_iso:
                continue
            arr_match = None
            if c.type == "movie" and c.tmdb_id:
                arr_match = radarr_index.get(c.tmdb_id)
            elif c.type == "show" and c.tvdb_id:
                arr_match = sonarr_index.get(c.tvdb_id)
            results.append({
                "library": library_name,
                "candidate": c,
                "decision": (lambda a: None if a == "snoozed" else a)(decisions.get(c.rating_key, {}).get("action")),
                "arr_match": arr_match,
            })
    save_candidates([{"library": r["library"], "candidate": r["candidate"]} for r in results])
    return results, errors


@app.route("/")
def dashboard():
    config = load_config()
    decisions = load_decisions()
    data = load_candidates() or {}
    rows = data.get("results", [])
    scanned_at = None
    if data.get("scanned_at"):
        scanned_at = datetime.fromisoformat(data["scanned_at"]).astimezone().strftime("%d-%m-%Y %H:%M")
    total = len(rows)
    deletable = sum(1 for r in rows if r["candidate"].get("deletable"))
    stats = {
        "scanned_at": scanned_at,
        "total": total,
        "deletable": deletable,
        "approved": sum(1 for d in decisions.values() if d.get("action") == "approved"),
        "excluded": len(load_exceptions()),
        "dry_run": config.dry_run,
    }
    return render_template("index.html", stats=stats)


@app.route("/health")
def health():
    return render_template("health.html", statuses=check_all_services(load_config()))


@app.route("/candidates")
def candidates():
    config = load_config()
    results, errors = build_results(config)
    return render_template(
        "candidates.html",
        results=results,
        errors=errors,
        total_count=len(results),
        dry_run=config.dry_run,
    )


def run_scan():
    results, errors = build_results(load_config())
    pending = [r for r in results if r["decision"] is None]
    deletable = sum(1 for r in pending if r["candidate"].deletable)
    info = len(pending) - deletable
    app.logger.info("Scan klaar: %s te beoordelen, %s alleen-info, %s fouten", deletable, info, len(errors))
    sent = False
    if deletable:
        sent = send_discord(
            f"🧹 Plex Cleaner: {deletable} bekeken titels wachten op jouw beoordeling "
            f"(+ {info} alleen-info). Open {os.environ.get('APP_URL', 'http://localhost:8090')}/candidates"
        )
    return {"pending_deletable": deletable, "pending_info": info, "errors": errors, "discord_sent": sent}


@app.route("/scan", methods=["POST"])  # cron: X-Scan-Token, zie auth.py
def scan():
    return run_scan()


@app.route("/scan-now", methods=["POST"])  # knop op het dashboard
def scan_now():
    r = run_scan()
    if r["pending_deletable"]:
        flash(f"Scan klaar: {r['pending_deletable']} titels te beoordelen (+ {r['pending_info']} alleen-info). "
              f"Discord-melding {'verstuurd' if r['discord_sent'] else 'NIET verstuurd'}.", "success")
    else:
        flash("Scan klaar: er is niets nieuws om te beoordelen.", "info")
    for e in r["errors"]:
        flash(e, "error")
    return redirect(url_for("dashboard"))


@app.route("/action/<rating_key>/exclude", methods=["POST"])
def exclude(rating_key):
    add_exception(rating_key, title=request.form.get("title", ""))
    app.logger.info("UITGESLOTEN %s '%s'", rating_key, request.form.get("title", ""))
    return redirect(url_for("candidates"))


@app.route("/action/<rating_key>/approve", methods=["POST"])
def approve(rating_key):
    # Registreert alleen de goedkeuring; verwijderen kan alleen via delete-now.
    record_decision(rating_key, "approved", title=request.form.get("title", ""))
    app.logger.info("GOEDGEKEURD %s '%s'", rating_key, request.form.get("title", ""))
    return redirect(url_for("candidates"))


def media_matches(config, cand, arr_id):
    """Veiligheid: de Plex-bestanden moeten in de map staan die Radarr/Sonarr beheert."""
    plex = config.services["plex"]
    url = f"{plex.url}/library/metadata/{cand['rating_key']}" + ("/allLeaves" if cand["type"] == "show" else "")
    r = requests.get(url, headers={"X-Plex-Token": plex.api_key, "Accept": "application/json"},
                     timeout=plex.timeout_seconds)
    r.raise_for_status()
    files = [m["Media"][0]["Part"][0]["file"] for m in r.json()["MediaContainer"].get("Metadata", []) if m.get("Media")]
    if cand["type"] == "movie":
        items = RadarrClient(config.services["radarr"]).get_movies()
    else:
        items = SonarrClient(config.services["sonarr"]).get_series()
    arr = next((i for i in items if i["id"] == int(arr_id)), None)
    if not files or not arr:
        return False
    folder = arr["path"].rstrip("/").split("/")[-1]
    return all(folder in f.split("/") for f in files)


@app.route("/action/<rating_key>/delete-now", methods=["POST"])
def delete_now(rating_key):
    config = load_config()
    arr_id = request.form.get("arr_id", "")
    # type/titel/tmdb komen uit onze eigen scan, niet uit het formulier
    cand = next((r["candidate"] for r in (load_candidates() or {}).get("results", [])
                 if r["candidate"]["rating_key"] == rating_key), None)

    if config.dry_run:
        flash("DRY-RUN is actief: verwijderen is geblokkeerd.", "error")
    elif load_decisions().get(rating_key, {}).get("action") != "approved":
        flash("Eerst goedkeuren, daarna pas verwijderen.", "error")
    elif cand is None or not cand.get("deletable"):
        flash("Alleen bekeken, verwijderbare titels uit de laatste scan kunnen worden verwijderd.", "error")
    elif not arr_id.isdigit() or cand["type"] not in ("movie", "show"):
        flash("Geen geldige Radarr/Sonarr-koppeling: niets verwijderd.", "error")
    else:
        try:
            safe = media_matches(config, cand, arr_id)
        except Exception as exc:
            app.logger.error("Veiligheidscontrole fout '%s': %s", cand["title"], exc)
            safe = False
        if not safe:
            flash("Veiligheidscontrole mislukt: de Plex-bestanden horen niet bij deze Radarr/Sonarr-titel. Niets verwijderd.", "error")
            return redirect(url_for("candidates"))
        title, media_type = cand["title"], cand["type"]
        try:
            if media_type == "movie":
                RadarrClient(config.services["radarr"]).delete_movie(int(arr_id))
            else:
                SonarrClient(config.services["sonarr"]).delete_series(int(arr_id))
        except Exception as exc:
            app.logger.error("Verwijderen mislukt '%s': %s", title, exc)
            flash(f"Fout bij verwijderen: {exc}", "error")
            return redirect(url_for("candidates"))

        record_decision(rating_key, "deleted", title=title)
        app.logger.warning("VERWIJDERD %s '%s' arr_id=%s", media_type, title, arr_id)
        note = ""
        seerr = config.services.get("seerr")
        if seerr and seerr.api_key and cand.get("tmdb_id"):  # best effort: Radarr/Sonarr is al gelukt
            try:
                client = SeerrClient(seerr)
                media_id = client.find_media_id(media_type, cand["tmdb_id"])
                if media_id:
                    client.delete_media(media_id)
                    note = " Seerr-aanvraag opgeschoond."
                else:
                    note = " (Niet bekend in Seerr.)"
            except Exception as exc:
                app.logger.warning("Seerr opschonen mislukt '%s': %s", title, exc)
                note = f" Let op: Seerr is niet opgeschoond ({exc})."
        else:
            note = " Let op: Seerr is niet opgeschoond (geen API-sleutel of tmdb-id)."
        flash(f"'{title}' verwijderd via Radarr/Sonarr (incl. bestanden).{note}", "success")
    return redirect(url_for("candidates"))


@app.route("/action/<rating_key>/snooze", methods=["POST"])
def snooze(rating_key):
    title = request.form.get("title", "")
    until = (datetime.now(timezone.utc) + timedelta(days=SNOOZE_DAYS)).isoformat()
    data = load_snoozed()
    data[rating_key] = until
    save_snoozed(data)
    record_decision(rating_key, "snoozed", title=title)
    app.logger.info("UITGESTELD %s '%s' tot %s", rating_key, title, until[:10])
    flash(f"'{title}' wordt {SNOOZE_DAYS} dagen niet voorgesteld.", "info")
    return redirect(url_for("candidates"))


@app.route("/logs")
def logs():
    flt = request.args.get("filter", "alles")
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        lines = []
    if flt == "fouten":
        lines = [l for l in lines if " ERROR " in l]
    elif flt == "waarschuwingen":
        lines = [l for l in lines if " ERROR " in l or " WARNING " in l]
    return render_template("logs.html", lines=list(reversed(lines[-300:])), filter=flt)


@app.route("/history")
def history():
    exclude_rows = [
        {"rating_key": k, "title": d.get("title", "(onbekende titel)"), "at": d.get("excluded_at", "")}
        for k, d in load_exceptions_full().get("details", {}).items()
    ]
    exclude_rows.sort(key=lambda r: r["at"], reverse=True)
    decision_rows = [
        {"rating_key": k, "title": d.get("title", "(onbekende titel)"),
         "action": d.get("action", ""), "at": d.get("decided_at", "")}
        for k, d in load_decisions().items()
    ]
    decision_rows.sort(key=lambda r: r["at"], reverse=True)
    return render_template("history.html", exclude_rows=exclude_rows, decision_rows=decision_rows)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
