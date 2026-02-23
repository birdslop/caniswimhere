"""
/api/readings — live data proxy endpoints.

Fetches real-time / recent data from EA APIs on demand.
Nothing is stored; all data is proxied and returned.
"""
import httpx
from fastapi import APIRouter, Query, HTTPException

router = APIRouter(tags=["Swim Map"])

EA_TIMEOUT = 15.0

# ── Water quality readings (WIMS) ─────────────────────────────────

WIMS_BASE = "https://environment.data.gov.uk/water-quality"
WIMS_HEADERS = {"Accept": "application/ld+json"}


@router.get("/readings/wq/{notation}")
async def wq_readings(
    notation: str,
    limit: int = Query(20, ge=1, le=100),
):
    """Return recent water quality observations for a WIMS sampling point."""
    url = (
        f"{WIMS_BASE}/sampling-point/{notation}/observation"
        f"?limit={limit}"
    )
    async with httpx.AsyncClient(timeout=EA_TIMEOUT) as client:
        resp = await client.get(url, headers=WIMS_HEADERS)
    if resp.status_code != 200:
        raise HTTPException(502, f"EA WIMS API returned {resp.status_code}")
    data = resp.json()
    members = data.get("member", data.get("items", []))
    return {
        "notation": notation,
        "count": len(members),
        "observations": members,
    }


# ── Flood monitoring station readings ─────────────────────────────

HYDRO_BASE = "https://environment.data.gov.uk/flood-monitoring"


@router.get("/readings/station/{reference}")
async def station_readings(
    reference: str,
    limit: int = Query(24, ge=1, le=500),
):
    """Return recent readings from a flood monitoring / hydrology station."""
    url = f"{HYDRO_BASE}/id/stations/{reference}/readings.json?_sorted&_limit={limit}"
    async with httpx.AsyncClient(timeout=EA_TIMEOUT) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise HTTPException(502, f"EA Hydrology API returned {resp.status_code}")
    data = resp.json()
    items = data.get("items", [])
    return {
        "station_reference": reference,
        "count": len(items),
        "readings": items,
    }


# ── Bathing water risk prediction ─────────────────────────────────

BWQ_BASE = "https://environment.data.gov.uk/doc/bathing-water-quality"


@router.get("/readings/bathing/{eubwid}")
async def bathing_risk(eubwid: str):
    """Return latest risk prediction for a designated bathing water."""
    url = f"{BWQ_BASE}/in-season/latest.json?bathingWater.eubwidNotation={eubwid}"
    async with httpx.AsyncClient(timeout=EA_TIMEOUT) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise HTTPException(502, f"EA BWQ API returned {resp.status_code}")
    data = resp.json()
    items = data.get("items", data.get("result", {}).get("items", []))
    return {
        "eubwid": eubwid,
        "count": len(items),
        "assessments": items,
    }
