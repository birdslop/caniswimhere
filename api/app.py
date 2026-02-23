"""
Can I Swim Here? — API
~~~~~~~~~~~~~~~~~~~~~~
FastAPI backend serving spatial queries and live water quality data
from the UK Water Pollution Observatory PostGIS database.
"""
import os
import pathlib
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, Response

from api.db import pool
from api.routes import nearby, readings, detail, research

# Optional password gate — set SITE_PASSWORD env var to enable.
_SITE_PASSWORD = os.getenv("SITE_PASSWORD")

_FRONTEND = pathlib.Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the database pool on startup, close on shutdown."""
    pool.open()
    yield
    pool.close()


_DESCRIPTION = """
## Open data on sewage overflows, water quality, and bathing water safety across England, Wales and Scotland

**Can I Swim Here?** is a public-interest platform built on open data from the
[Environment Agency](https://environment.data.gov.uk/),
[Natural Resources Wales](https://naturalresources.wales/),
[SEPA](https://www.sepa.org.uk/), and
[Scottish Water](https://www.scottishwater.co.uk/).
It combines permit records, annual return spill counts, near-real-time storm
overflow discharge alerts (NSOH), WIMS water quality sampling, and bathing
water classifications from across England, Wales and Scotland into a single
queryable dataset.

### Who is this for?

| Audience | Use case |
|---|---|
| **Journalists & researchers** | Investigate spill patterns, rank polluters, identify at-risk bathing waters, and download data as CSV for analysis. |
| **Campaign groups & NGOs** | Evidence-based advocacy with authoritative, linkable data. |
| **Developers** | Build dashboards, alerts, or apps on top of these JSON endpoints. |
|| **Curious citizens** | Explore whether your local river or beach is affected by sewage discharges. |

&nbsp;

### Endpoint groups

- **Swim Map** (`/api/nearby`, `/api/detail`, `/api/readings`) — powers the
  interactive map at the site root. Returns nearby sites, live verdicts, and
  water quality readings for a given location.
- **Research** (`/api/research/*`) — bulk query, ranking, and export endpoints
  designed for data journalism and analysis. Supports filtering, sorting,
  pagination, and CSV download.

### Data sources

- **Overflow permits & annual returns** — Environment Agency / NRW EDM dataset (2024 reporting year) for England and Wales; Scottish Water live overflow data
- **Live overflow status** — National Storm Overflow Hub (NSOH) via water company ArcGIS feeds (England & Scotland), updated every 15 minutes
- **Water quality** — WIMS sampling data (E. coli, intestinal enterococci, and more)
- **Bathing water classifications** — Environment Agency, NRW, and SEPA designations and compliance history
- **Recreation sites** — Designated bathing waters across England, Wales and Scotland plus additional swim spots

### Quick start

1. Browse the endpoints below or jump straight to **Research** for bulk data.
2. Add `?format=csv` to any Research endpoint that supports it to download results.
3. All responses are JSON by default. No authentication is required.
4. Rate limiting is not currently enforced — please be considerate with bulk requests.

&nbsp;

### Known limitations & data caveats

This platform is built on the best available open data, but there are important
limitations to be aware of when interpreting the numbers:

- **Annual returns are published once a year.** Spill counts and durations in
  the Research endpoints come from the Environment Agency's Event Duration
  Monitoring (EDM) annual return. The current dataset reflects the **2024
  reporting year**. There is no historical trend data available through this
  mechanism — each year's return replaces the last.
- **Spill counts are likely undercounts.** EDM monitors are not always
  operational. The `edm_operational_pct` field shows what percentage of the
  year each monitor was recording. An overflow with 90% uptime may have
  missed spills during the other 10%. Some overflows have no monitor at all
  and report zero spills by default.
- **Live overflow data (NSOH) only began in January 2025.** The near-real-time
  discharge status comes from water company ArcGIS feeds mandated by the
  National Storm Overflow Hub. Coverage and reliability vary by company.
  Some monitors report as "Offline" rather than giving a discharge status.
- **No live overflow data for Wales.** Dŵr Cymru Welsh Water operates a
  near-real-time storm overflow map on their corporate website, but unlike
  every other water company in Britain, the underlying data is served through
  a proprietary, non-public system rather than an open ArcGIS feed. We cannot
  integrate their live discharge status until they publish an open data
  service. Annual spill counts for Welsh overflows are still included from
  the 2024 EDM return.
- **Scottish overflows lack annual spill counts.** Scottish Water publishes
  live overflow locations and discharge status, but does not yet provide
  EDM-style annual return data through an open dataset. Scottish overflow
  records show locations and real-time status only.
- **Distance calculations are straight-line, not along waterways.** When we
  say an overflow is "2 km from a bathing water", that is the crow-flies
  distance between the discharge point and the bathing site. Pollution
  travels along watercourses, so the actual impact distance may be shorter
  or longer depending on river connectivity.
- **Water quality sampling is periodic, not continuous.** WIMS data comes from
  spot samples taken by the Environment Agency, typically during the bathing
  season (May–September). A site may have only a handful of samples per year.
  Results reflect conditions at the moment of sampling, not ongoing water quality.
- **Bathing water classifications can lag behind conditions.** Official
  classifications (Excellent, Good, Sufficient, Poor) are based on the
  preceding four years of sampling data, so a beach that has recently
  deteriorated may still carry an older, more favourable rating.
- **Not all overflows discharge to swimming locations.** Many overflows
  discharge into watercourses that do not reach bathing waters. Proximity
  alone does not confirm impact — local geography, tidal flow, and dilution
  all play a role.

### Licence

Source data is published under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
This API and the derived dataset are provided as-is for public benefit.
"""

app = FastAPI(
    title="Can I Swim Here?",
    description=_DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,  # we serve a custom docs page with site header
    openapi_tags=[
        {
            "name": "Research",
            "description": (
                "Bulk query, ranking, and export endpoints for journalists, "
                "researchers, and developers. All endpoints support JSON responses; "
                "those returning lists also support `?format=csv` for download."
            ),
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def password_gate(request: Request, call_next):
    """If SITE_PASSWORD is set, require HTTP Basic Auth on every request."""
    if not _SITE_PASSWORD:
        return await call_next(request)
    # Let healthcheck through without auth so Railway deployments succeed
    if request.url.path == "/api/health":
        return await call_next(request)
    import base64
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            _, password = decoded.split(":", 1)
            if secrets.compare_digest(password, _SITE_PASSWORD):
                return await call_next(request)
        except Exception:
            pass
    return Response(
        "Unauthorized",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Can I Swim Here?"'},
    )


app.include_router(nearby.router, prefix="/api")
app.include_router(readings.router, prefix="/api")
app.include_router(detail.router, prefix="/api")
app.include_router(research.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve the frontend
app.mount("/static", StaticFiles(directory=str(_FRONTEND)), name="static")


# Robots and favicon
from fastapi.responses import PlainTextResponse

@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return PlainTextResponse(
        "User-agent: *\nAllow: /\n",
        headers={"Cache-Control": "public, max-age=86400"},
    )

_FAVICON_SVG = """
<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'>
  <rect width='64' height='64' rx='12' fill='#1a365d'/>
  <text x='32' y='40' font-size='34' text-anchor='middle' dominant-baseline='middle'>🏊</text>
</svg>
"""

@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    return Response(_FAVICON_SVG, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=604800"})


@app.get("/")
def index():
    return FileResponse(str(_FRONTEND / "index.html"))


@app.get("/explorer")
def explorer():
    return FileResponse(str(_FRONTEND / "explorer.html"))


@app.get("/docs", include_in_schema=False)
def custom_docs():
    """Swagger UI wrapped in the site header."""
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>API Docs — Can I Swim Here?</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { overflow-x: hidden; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  #site-header {
    background: #1a365d; color: #fff;
    padding: 12px 20px; display: flex; align-items: center; gap: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,.15); position: sticky; top: 0; z-index: 1000;
    flex-wrap: wrap;
  }
  #site-header h1 { font-size: 1.3rem; font-weight: 700; white-space: nowrap; }
  #site-header h1 a { color: #fff; text-decoration: none; }
  #site-header h1 span { font-weight: 400; color: #cbd5e0; }
  #site-header .spacer { flex: 1; }
  #site-header a.nav-link {
    color: #cbd5e0; text-decoration: none; font-weight: 600; font-size: .9rem; white-space: nowrap;
  }
  #site-header a.nav-link:hover { color: #fff; text-decoration: underline; }
  #site-header a.nav-link.active { color: #fff; border-bottom: 2px solid #fff; padding-bottom: 2px; }
  #swagger-ui { overflow-x: hidden; }
  .swagger-ui .wrapper { max-width: 100vw; overflow-x: hidden; padding: 0 8px; }
  .nav-links { display: flex; gap: 12px; }
  @media (max-width: 640px) {
    #site-header { gap: 8px; padding: 12px 14px; }
    #site-header h1 { width: 100%; font-size: 1.25rem; }
    #site-header .spacer { display: none; }
    .nav-links { width: 100%; justify-content: space-between; }
    #site-header a.nav-link { font-size: .95rem; padding: 4px 0; }
  }
</style>
</head>
<body>
<div id="site-header">
  <h1><a href="/">🏊 Can I Swim Here?</a> <span>— API Docs</span></h1>
  <span class="spacer"></span>
  <div class="nav-links">
    <a href="/" class="nav-link">Swim Map</a>
    <a href="/explorer" class="nav-link">Data Explorer</a>
    <a href="/docs" class="nav-link active">API Docs</a>
  </div>
</div>
<div id="swagger-ui"></div>
<div style="max-width:900px;margin:30px auto;padding:0 20px">
  <div style="background:#fff;border-radius:8px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.08);line-height:1.6;font-size:.9rem;color:#2d3748">
    <p id="docs-last-updated" style="margin:0 0 10px;color:#718096;font-size:.85rem">Live discharge snapshot: loading…</p>
    <p style="margin:0 0 10px;font-weight:700;color:#1a365d">Support This Project</p>
    <p style="margin:0 0 10px">Can I Swim Here? is an entirely self-funded project. Any donations help to continue the project by paying for things like hosting, maintenance and the ability to update the site. Any help is most welcome and warmly received, thank you!</p>
    <p style="margin:0 0 10px"><a href="https://buymeacoffee.com/caniswimhere" target="_blank" rel="noopener" style="display:inline-block;background:#ffdd00;color:#000;font-weight:700;padding:8px 18px;border-radius:6px;text-decoration:none;font-size:.9rem">☕ Buy Me a Coffee</a></p>
    <p style="margin:0;color:#718096;font-size:.82rem">Questions, feedback or data requests? Get in touch: <a href="mailto:caniswimhere@proton.me" style="color:#3182ce">caniswimhere@proton.me</a></p>
    <p style="margin:10px 0 0;color:#718096;font-size:.82rem"><strong style="color:#4a5568">Methodology & Corrections.</strong> Live discharge status comes from company feeds via the National Storm Overflow Hub and updates throughout the day; annual spill counts come from the 2024 EDM return. If you spot an error, email us — substantive corrections will be made promptly and noted.</p>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({
  url: '/openapi.json',
  dom_id: '#swagger-ui',
  docExpansion: 'list',
  deepLinking: true,
  presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
  layout: 'BaseLayout',
});

// Last updated label
fetch('/api/research/live-summary').then(r=>r.json()).then(d=>{
  if (!d || !d.last_polled) return;
  const dt = new Date(d.last_polled);
  const fmt = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London', day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit'});
  document.getElementById('docs-last-updated').textContent = 'Live discharge snapshot updated ' + fmt.format(dt) + ' UK. Annual spill data: 2024 EDM (published spring 2025).';
}).catch(()=>{});
</script>
</body>
</html>
""")
