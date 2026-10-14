import os
from typing import NoReturn

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


app = FastAPI(title="FastAPI stack fixture")
MARKERS = {"Marker A": "marker-a", "Marker B": "marker-b"}


class Record(BaseModel):
    value: str


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required")
    return value


def _read_markers() -> dict[str, str | None]:
    with psycopg.connect(_database_url(), connect_timeout=3) as connection:
        rows = connection.execute(
            "SELECT record_id, value FROM beta_records WHERE record_id IN (%s, %s)",
            ("marker-a", "marker-b"),
        ).fetchall()
    found = {record_id: value for record_id, value in rows}
    return {record_id: found.get(record_id) for record_id in ("marker-a", "marker-b")}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>FastAPI stack fixture</title></head>
<body><main><h1>FastAPI stack fixture</h1>
<label for="value">Value</label><input id="value" autocomplete="off">
<button id="add-value" type="button">Add value</button><ul id="values"></ul>
<p id="fixture-error" role="alert" hidden></p></main>
<script>
const input = document.querySelector("#value");
const values = document.querySelector("#values");
const error = document.querySelector("#fixture-error");
const pathForValue = { "Marker A": "/api/records/marker-a", "Marker B": "/api/records/marker-b" };
async function refresh() {
  const response = await fetch("/api/records", { cache: "no-store" });
  if (!response.ok) throw new Error("record read failed");
  const record = await response.json();
  values.replaceChildren();
  for (const value of Object.values(record.records)) {
    if (value === null) continue;
    const item = document.createElement("li");
    item.textContent = value;
    values.append(item);
  }
}
document.querySelector("#add-value").addEventListener("click", async () => {
  error.hidden = true;
  const endpoint = pathForValue[input.value];
  if (!endpoint) { error.textContent = "Only Marker A or Marker B is accepted."; error.hidden = false; return; }
  const response = await fetch(endpoint, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ value: input.value })
  });
  if (!response.ok) { error.textContent = "Could not save value."; error.hidden = false; return; }
  await refresh();
});
void refresh().catch(() => { error.textContent = "Database is not ready."; error.hidden = false; });
</script></body></html>"""


@app.get("/healthz")
def healthz() -> dict[str, object]:
    try:
        with psycopg.connect(_database_url(), connect_timeout=3) as connection:
            table = connection.execute(
                "SELECT to_regclass('public.beta_records')"
            ).fetchone()[0]
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    if table != "beta_records":
        raise HTTPException(status_code=503, detail="database schema unavailable")
    return {"ok": True, "framework": "fastapi", "database": "ready"}


@app.get("/api/status")
def status() -> dict[str, object]:
    try:
        records = _read_markers()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"ok": True, "framework": "fastapi", "message": "database-backed fixture", "records": records}


@app.get("/api/records")
def read_markers() -> dict[str, dict[str, str | None]]:
    try:
        return {"records": _read_markers()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.post("/api/records/marker-a")
def write_marker_a(record: Record) -> dict[str, str]:
    return _write_marker("Marker A") if record.value == "Marker A" else _reject_marker()


@app.post("/api/records/marker-b")
def write_marker_b(record: Record) -> dict[str, str]:
    return _write_marker("Marker B") if record.value == "Marker B" else _reject_marker()


def _reject_marker() -> NoReturn:
    raise HTTPException(status_code=400, detail="only the fixed journey marker is accepted")


def _write_marker(value: str) -> dict[str, str]:
    record_id = MARKERS[value]
    with psycopg.connect(_database_url(), connect_timeout=3) as connection:
        connection.execute(
            "INSERT INTO beta_records (record_id, value) VALUES (%s, %s) "
            "ON CONFLICT (record_id) DO UPDATE SET value = EXCLUDED.value",
            (record_id, value),
        )
    return {"id": record_id, "value": value}


def main() -> None:
    port = os.environ.get("PORT")
    if port is None:
        raise SystemExit("PORT is required")
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(port))


if __name__ == "__main__":
    main()
