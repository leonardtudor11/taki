"""Taki local backend — drives live cascade runs from the dashboard.

Boots a Flask app on :5001 that:
  - Serves the static frontend at /
  - Exposes POST /api/run → Server-Sent Events stream of cascade events
  - Exposes GET  /api/brief → current brief.json
  - Exposes GET  /api/status → whether a run is currently in progress

The dashboard's "▶ live demo" and "⚡ live run" buttons hit this endpoint;
the cytoscape graph animates each node as the backend StateGraph fires.

Modes:
  demo — Uses fixtures.sample.sample_bundle + the fake LLMs. No keys
         required. The fake-GTM LLM plants a Globex hallucination so the
         grounding guard catches it on screen.
  live — Scrapes the supplied target+URLs via Bright Data, then calls
         the default LLM (Vertex via ADC if GCP_PROJECT_ID, else Gemini
         AI Studio if GEMINI_API_KEY). Requires the relevant .env keys.

This is a single-user demo server. No auth — do NOT expose publicly: it
would let callers trigger arbitrary Bright Data + LLM spend.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # before importing services so .env is honored on first call

from flask import Flask, Response, jsonify, request, send_from_directory  # noqa: E402
from flask_cors import CORS  # noqa: E402

from agents import cascade_graph  # noqa: E402
from agents.schemas import BusinessProfile, CascadeMode, SourceType  # noqa: E402
from services import cache  # noqa: E402

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
FRONTEND_BRIEF = FRONTEND / "brief.json"

app = Flask(__name__, static_folder=None)
# CORS so the dashboard can be served from a different origin during dev
# (e.g. python -m http.server :8000 hitting this backend at :5001).
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Single-slot run lock. The dashboard is a single-user demo; one cascade at a
# time keeps things simple and prevents accidental double-spend on Bright Data.
_run_lock = threading.Lock()

# Persistent last-run state. Survives the SSE stream — a page refresh hits
# /api/status and learns whether the worker is still running, completed, or
# died with an error. Without this, a refresh during a long run shows the
# stale brief.json with no signal that the new cascade ever ran.
_LAST_RUN_LOCK = threading.Lock()
_LAST_RUN: dict = {
    "status": None,         # None | "running" | "completed" | "error"
    "mode": None,
    "target": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "url_errors": [],
    "last_phase": None,
    "last_event": None,
    "dropped": None,
    "stats": None,          # e.g. {"sources": 7, "competitors": ["mulhlan", "ven-to"]}
}


def _utc_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _set_last_run(**updates) -> None:
    with _LAST_RUN_LOCK:
        _LAST_RUN.update(updates)


def _push_url_error(ev: dict) -> None:
    with _LAST_RUN_LOCK:
        _LAST_RUN["url_errors"].append(ev)


def _parse_urls(args: list[str]) -> list[tuple[str, SourceType]]:
    """Mirror of run._parse_urls — kept inline so the server has no run.py dep."""
    valid = {t.value for t in SourceType}
    out: list[tuple[str, SourceType]] = []
    for a in args:
        a = (a or "").strip()
        if not a:
            continue
        url, sep, kind = a.rpartition(":")
        if sep and kind in valid:
            out.append((url, SourceType(kind)))
        else:
            out.append((a, SourceType.SITE))
    return out


# ───────────────── static frontend ─────────────────

@app.route("/")
def index():
    return send_from_directory(FRONTEND, "index.html")


@app.route("/<path:path>")
def static_files(path: str):
    target = FRONTEND / path
    if target.exists() and target.is_file():
        return send_from_directory(FRONTEND, path)
    return ("not found", 404)


# ───────────────── api: status + brief ─────────────────

@app.route("/api/status")
def api_status():
    with _LAST_RUN_LOCK:
        last_run = dict(_LAST_RUN)
        last_run["url_errors"] = list(last_run["url_errors"])
    return jsonify({
        "running": _run_lock.locked(),
        "last_run": last_run,
        "modes": {
            "demo": True,
            "live": bool(os.environ.get("BRIGHTDATA_API_KEY"))
                    and (bool(os.environ.get("GCP_PROJECT_ID"))
                         or bool(os.environ.get("GEMINI_API_KEY"))),
        },
        "live_blockers": _live_blockers(),
    })


def _live_blockers() -> list[str]:
    blockers: list[str] = []
    if not os.environ.get("BRIGHTDATA_API_KEY"):
        blockers.append("BRIGHTDATA_API_KEY not set in .env")
    if not (os.environ.get("GCP_PROJECT_ID") or os.environ.get("GEMINI_API_KEY")):
        blockers.append("GCP_PROJECT_ID (Vertex) or GEMINI_API_KEY not set in .env")
    return blockers


@app.route("/api/brief")
def api_brief():
    if not FRONTEND_BRIEF.exists():
        return jsonify({"error": "no brief.json"}), 404
    return Response(FRONTEND_BRIEF.read_text(), mimetype="application/json")


# ───────────────── api: live cascade run ─────────────────

@app.route("/api/run", methods=["POST", "OPTIONS"])
def api_run():
    """Start a cascade and stream events as Server-Sent Events.

    Body JSON:
      mode:    "demo" | "live"   (default: "demo")
      target:  str               (required for live)
      urls:    list[str]         (required for live, format "url:source_type")
    """
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(force=True, silent=True) or {}
    mode = (data.get("mode") or "demo").lower()
    target = (data.get("target") or "").strip()
    urls = data.get("urls") or []

    if mode not in ("demo", "live", "self"):
        return jsonify({"error": f"unknown mode: {mode}"}), 400
    if _run_lock.locked():
        return jsonify({"error": "another cascade is already running"}), 409
    if mode == "live":
        blockers = _live_blockers()
        if blockers:
            return jsonify({"error": "live mode unavailable", "blockers": blockers}), 400
        if not target:
            return jsonify({"error": "target required for live mode"}), 400
    if mode == "self":
        # self-mode also needs BD + LLM
        blockers = _live_blockers()
        if blockers:
            return jsonify({"error": "self mode unavailable", "blockers": blockers}), 400
        profile_data = data.get("profile") or {}
        if not profile_data.get("url"):
            return jsonify({"error": "profile.url required for self mode"}), 400
        if not profile_data.get("name"):
            return jsonify({"error": "profile.name required for self mode"}), 400

    def stream():
        q: queue.Queue = queue.Queue()
        # demo runs through fake LLMs in milliseconds; pad each 'done' event
        # so the dashboard has time to animate it.
        slow = mode == "demo"

        def emit(ev: dict) -> None:
            q.put(ev)
            # mirror the last phase/event into the persistent state so a
            # refresh during a long run can see where the cascade is.
            _set_last_run(
                last_phase=ev.get("phase"),
                last_event=ev,
            )
            if slow and ev.get("status") == "done":
                time.sleep(0.55)

        def worker():
            run_target = target if mode == "live" else (data.get("profile") or {}).get("name", "fixture")
            _set_last_run(
                status="running",
                mode=mode,
                target=run_target,
                started_at=_utc_iso(),
                finished_at=None,
                error=None,
                url_errors=[],
                last_phase=None,
                last_event=None,
                dropped=None,
                stats=None,
            )
            try:
                if mode == "demo":
                    from fixtures.fake_llm import (
                        fake_finance_llm,
                        fake_gtm_llm_with_hallucination,
                        fake_marketing_llm,
                        fake_security_llm,
                        fake_strategy_llm,
                    )
                    from fixtures.sample import sample_bundle

                    bundle = sample_bundle()
                    q.put({"phase": "fetch", "status": "start", "mode": "demo"})
                    time.sleep(0.6)
                    q.put({"phase": "fetch", "status": "done", "sources": len(bundle.sources)})
                    time.sleep(0.4)
                    graph = cascade_graph.build_graph(
                        gtm_llm=fake_gtm_llm_with_hallucination,
                        finance_llm=fake_finance_llm,
                        marketing_llm=fake_marketing_llm,
                        security_llm=fake_security_llm,
                        strategy_llm=fake_strategy_llm,
                        on_event=emit,
                    )
                elif mode == "self":
                    from services.brightdata import BrightDataClient, build_self_bundle

                    profile_data = data.get("profile") or {}
                    profile = BusinessProfile.model_validate({
                        "name":             profile_data.get("name", ""),
                        "url":              profile_data.get("url", ""),
                        "industry":         profile_data.get("industry", ""),
                        "stage":            profile_data.get("stage", "early-revenue"),
                        "goal":             profile_data.get("goal", ""),
                        "customer_segment": profile_data.get("customer_segment", ""),
                        "competitor_urls":  profile_data.get("competitor_urls", []) or [],
                        "competitor_names": profile_data.get("competitor_names", []) or [],
                    })
                    # default the main URL to a 'site' source; extra self URLs the
                    # founder supplied tag along too.
                    extra_self = profile_data.get("extra_urls", []) or []
                    self_urls = [(profile.url, SourceType.SITE)] + _parse_urls(extra_self)
                    competitor_urls = _parse_urls(profile.competitor_urls)

                    q.put({
                        "phase": "fetch", "status": "start", "mode": "self",
                        "target": profile.name,
                        "self_urls": len(self_urls),
                        "competitor_urls": len(competitor_urls),
                    })

                    # V7.6 — pre-scrape audit. Normalises URLs (adds https,
                    # strips trailing punct, lowercases host) + DNS-resolves
                    # to catch typos before they burn 30s×3 retries each
                    # in Bright Data. Audit events stream live so the
                    # dashboard can show 'fixed 1 URL · dropped 1 (no DNS)'.
                    from services.url_audit import audit_urls

                    def _emit_audit(ev: dict) -> None:
                        q.put({"phase": "audit", **ev})
                        # mirror dropped audits into last_run.url_errors so
                        # the status banner can list them after a refresh.
                        if ev.get("status") == "dropped":
                            _push_url_error({
                                "url": ev.get("original") or "",
                                "subject": ev.get("source_type", "?"),
                                "error": f"URL audit: {ev.get('reason') or 'dropped'}",
                            })

                    audited_self, audit_log_self = audit_urls(
                        self_urls, on_event=_emit_audit,
                    )
                    audited_comp, audit_log_comp = audit_urls(
                        competitor_urls, on_event=_emit_audit,
                    )
                    audit_summary = {
                        "fixed":   sum(1 for e in audit_log_self + audit_log_comp if e.status == "fixed"),
                        "dropped": sum(1 for e in audit_log_self + audit_log_comp if e.status == "dropped"),
                        "ok":      sum(1 for e in audit_log_self + audit_log_comp if e.status == "ok"),
                    }
                    q.put({"phase": "audit", "status": "summary", **audit_summary})

                    if not audited_self and not audited_comp:
                        # nothing scrape-able — emit error early instead of
                        # letting build_self_bundle raise the same conclusion.
                        from dataclasses import asdict as _asdict
                        all_drops = [_asdict(e) for e in audit_log_self + audit_log_comp]
                        raise RuntimeError(
                            "URL audit dropped every URL — nothing to scrape. "
                            f"Failures: { '; '.join(d['original'] + ': ' + (d['reason'] or 'ok?') for d in all_drops) }"
                        )

                    client = BrightDataClient()

                    def _emit_url_error(ev: dict) -> None:
                        q.put({"phase": "fetch", "status": "url_error", **ev})
                        _push_url_error(ev)

                    bundle, url_errors = build_self_bundle(
                        business_name=profile.name,
                        self_urls=audited_self,
                        competitor_urls=audited_comp,
                        client=client,
                        on_error=_emit_url_error,
                    )
                    q.put({
                        "phase": "fetch", "status": "done",
                        "sources": len(bundle.sources),
                        "competitors": bundle.competitor_names(),
                        "url_errors": len(url_errors),
                    })
                    graph = cascade_graph.build_graph(
                        on_event=emit,
                        mode=CascadeMode.SELF,
                        business_profile=profile,
                    )
                else:  # live (target-mode)
                    from services.brightdata import BrightDataClient, build_bundle

                    q.put({
                        "phase": "fetch", "status": "start", "mode": "live",
                        "target": target, "urls": len(urls),
                    })
                    client = BrightDataClient()
                    bundle = build_bundle(target, client, _parse_urls(urls))
                    q.put({
                        "phase": "fetch", "status": "done",
                        "sources": len(bundle.sources),
                    })
                    graph = cascade_graph.build_graph(on_event=emit)

                final = graph.invoke({"bundle": bundle, "events": []})
                brief = final["brief"]
                cache.save_bundle(bundle)
                cache.save_brief(brief)
                FRONTEND_BRIEF.write_text(brief.model_dump_json(indent=2))
                dropped = len(brief.guardrail_report.ungrounded_dropped)
                _set_last_run(
                    status="completed",
                    target=brief.target,
                    finished_at=_utc_iso(),
                    dropped=dropped,
                    stats={
                        "sources": len(bundle.sources),
                        "competitors": bundle.competitor_names(),
                    },
                )
                q.put({
                    "phase": "complete", "status": "done",
                    "target": brief.target,
                    "mode": brief.mode.value,
                    "dropped": dropped,
                })
            except Exception as exc:
                # Make the error visible in the dashboard AND in /api/status,
                # so a page refresh during a failed run sees what went wrong
                # instead of just the stale brief.json.
                msg = f"{type(exc).__name__}: {exc}"
                _set_last_run(status="error", finished_at=_utc_iso(), error=msg)
                q.put({"phase": "error", "error": msg})
            finally:
                # The lock follows the worker, not the SSE stream. A client
                # refresh closes the SSE generator but the worker keeps
                # running until done — releasing here keeps /api/status
                # honest (running stays true until the cascade finishes).
                q.put(None)
                try:
                    _run_lock.release()
                except RuntimeError:
                    pass

        if not _run_lock.acquire(blocking=False):
            yield f"data: {json.dumps({'phase': 'error', 'error': 'busy'})}\n\n"
            return

        threading.Thread(target=worker, daemon=True).start()
        # SSE keep-alive: emit one comment line up front so proxies don't close
        yield ": taki-stream-open\n\n"
        try:
            while True:
                try:
                    ev = q.get(timeout=1.0)
                except queue.Empty:
                    # heartbeat keeps intermediaries from buffering/closing
                    yield ": keepalive\n\n"
                    continue
                if ev is None:
                    break
                yield f"data: {json.dumps(ev)}\n\n"
        except GeneratorExit:
            # client disconnected (e.g. page refresh). The worker holds the
            # lock and continues; /api/status will still report running.
            return

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ───────────────── entrypoint ─────────────────

if __name__ == "__main__":
    port = int(os.environ.get("TAKI_BACKEND_PORT", "5001"))
    print(f"\n  Taki backend → http://localhost:{port}/")
    print(f"  modes: demo (always on) · live ({'on' if not _live_blockers() else 'BLOCKED: ' + '; '.join(_live_blockers())})\n")
    # threaded=True so SSE generators don't block the next request.
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)
