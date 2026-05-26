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
from agents.schemas import SourceType  # noqa: E402
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
    return jsonify({
        "running": _run_lock.locked(),
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

    if mode not in ("demo", "live"):
        return jsonify({"error": f"unknown mode: {mode}"}), 400
    if _run_lock.locked():
        return jsonify({"error": "another cascade is already running"}), 409
    if mode == "live":
        blockers = _live_blockers()
        if blockers:
            return jsonify({"error": "live mode unavailable", "blockers": blockers}), 400
        if not target:
            return jsonify({"error": "target required for live mode"}), 400

    def stream():
        q: queue.Queue = queue.Queue()
        # demo runs through fake LLMs in milliseconds; pad each 'done' event
        # so the dashboard has time to animate it.
        slow = mode == "demo"

        def emit(ev: dict) -> None:
            q.put(ev)
            if slow and ev.get("status") == "done":
                time.sleep(0.55)

        def worker():
            try:
                if mode == "demo":
                    from fixtures.fake_llm import (
                        fake_finance_llm,
                        fake_gtm_llm_with_hallucination,
                        fake_security_llm,
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
                        security_llm=fake_security_llm,
                        on_event=emit,
                    )
                else:
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
                q.put({
                    "phase": "complete", "status": "done",
                    "target": brief.target,
                    "dropped": len(brief.guardrail_report.ungrounded_dropped),
                })
            except Exception as exc:
                # Make the error visible in the dashboard rather than dying silently.
                q.put({"phase": "error", "error": f"{type(exc).__name__}: {exc}"})
            finally:
                q.put(None)

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
        finally:
            try:
                _run_lock.release()
            except RuntimeError:
                pass

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
