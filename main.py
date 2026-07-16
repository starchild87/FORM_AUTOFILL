from fastapi import FastAPI, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
import os
import re

app = FastAPI()
app.mount("/static", StaticFiles(directory="."), name="static")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
PHONE_RE = re.compile(r"^\+?1?\d{10,15}$")

def ok(msg: str) -> HTMLResponse:
    return HTMLResponse(f'<span class="ok">✓ {msg}</span>')

def err(msg: str) -> HTMLResponse:
    return HTMLResponse(f'<span class="err">✗ {msg}</span>')

@app.get("/", response_class=HTMLResponse)
async def home():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.post("/validate/name", response_class=HTMLResponse)
async def validate_name(name: str = Form(...)):
    name = name.strip()
    if len(name) < 2:
        return err("Name must be at least 2 characters.")
    if not re.match(r"^[A-Za-z ,.'-]+$", name):
        return err("Name contains invalid characters.")
    return ok("Looks good.")

@app.post("/validate/address", response_class=HTMLResponse)
async def validate_address(address: str = Form(...)):
    address = address.strip()
    if len(address) < 5:
        return err("Address is too short.")
    return ok("Address format looks good.")

@app.post("/validate/phone", response_class=HTMLResponse)
async def validate_phone(phone: str = Form(...)):
    digits = re.sub(r"\D", "", phone)
    if not PHONE_RE.match(digits):
        return err("Enter a valid phone number.")
    return ok("Phone number looks good.")

# Backend proxy to Google Places Autocomplete
@app.get("/address/suggest", response_class=HTMLResponse)
async def address_suggest(address: str = Query(default="")):
    q = address.strip()
    if len(q) < 3:
        return HTMLResponse("")

    if not GOOGLE_API_KEY:
        return HTMLResponse("<div class='msg err'>Server missing GOOGLE_API_KEY.</div>", status_code=500)

    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": q,
        "key": GOOGLE_API_KEY,
        "types": "address",
        # optional biasing:
        # "components": "country:us",
        # "location": "37.7749,-122.4194",
        # "radius": 50000,
    }

    async with httpx.AsyncClient(timeout=6.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    status = data.get("status")
    if status not in ("OK", "ZERO_RESULTS"):
        # Don't leak internals to UI; log this in real app
        return HTMLResponse("<div class='msg err'>Address lookup unavailable.</div>", status_code=502)

    predictions = data.get("predictions", [])[:5]
    if not predictions:
        return HTMLResponse("<div class='msg err'>No matches found.</div>")

    # Keep only description + place_id in HTML data attrs
    items = []
    for p in predictions:
        desc = (p.get("description") or "").replace("'", "&#39;")
        pid = (p.get("place_id") or "").replace("'", "&#39;")
        items.append(f"<li data-address='{desc}' data-place-id='{pid}'>{desc}</li>")

    return HTMLResponse(f"<ul class='suggestions'>{''.join(items)}</ul>")

# Optional: place details endpoint (if you want normalized address parts)
@app.get("/address/details")
async def address_details(place_id: str):
    if not GOOGLE_API_KEY:
        return JSONResponse({"error": "Server missing GOOGLE_API_KEY"}, status_code=500)

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "key": GOOGLE_API_KEY,
        "fields": "formatted_address,address_component,geometry",
    }

    async with httpx.AsyncClient(timeout=6.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    status = data.get("status")
    if status != "OK":
        return JSONResponse({"error": "details lookup failed", "status": status}, status_code=502)

    result = data.get("result", {})
    return {
        "formatted_address": result.get("formatted_address"),
        "address_components": result.get("address_components", []),
        "location": result.get("geometry", {}).get("location"),
    }

@app.post("/submit")
async def submit(name: str = Form(...), address: str = Form(...), phone: str = Form(...)):
    # Final validation should happen here too
    return JSONResponse({"ok": True, "name": name, "address": address, "phone": phone})