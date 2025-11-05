import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from bson import ObjectId
import io
import csv

from database import db, create_document, get_documents
from schemas import Player, Innings

app = FastAPI(title="Cricket Scorecard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utilities

def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


def strike_rate(runs: int, balls: int) -> float:
    if balls <= 0:
        return 0.0
    return round((runs / balls) * 100, 2)


# Root and health
@app.get("/")
def read_root():
    return {"message": "Cricket Scorecard API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else ("✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set")
            try:
                response["collections"] = db.list_collection_names()
                response["connection_status"] = "Connected"
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response


# Request models for endpoints
class CreatePlayerRequest(Player):
    pass


class CreateInningsRequest(Innings):
    pass


# Players endpoints
@app.post("/players")
def create_player(payload: CreatePlayerRequest):
    player_id = create_document("player", payload)
    return {"_id": player_id, "name": payload.name, "role": payload.role}


@app.get("/players")
def list_players():
    players = get_documents("player")
    result = []
    for p in players:
        pid = str(p.get("_id"))
        agg = db["innings"].aggregate([
            {"$match": {"player_id": pid}},
            {"$group": {
                "_id": "$player_id",
                "runs": {"$sum": "$runs"},
                "balls": {"$sum": "$balls"},
                "fours": {"$sum": "$fours"},
                "sixes": {"$sum": "$sixes"},
                "innings": {"$sum": 1}
            }}
        ])
        stats = next(agg, None) or {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "innings": 0}
        total_runs = stats.get("runs", 0)
        total_balls = stats.get("balls", 0)
        result.append({
            "_id": pid,
            "name": p.get("name"),
            "role": p.get("role"),
            "total_runs": total_runs,
            "total_balls": total_balls,
            "total_fours": stats.get("fours", 0),
            "total_sixes": stats.get("sixes", 0),
            "innings_count": stats.get("innings", 0),
            "strike_rate": strike_rate(total_runs, total_balls),
        })
    return result


@app.get("/players/{player_id}")
def get_player(player_id: str):
    obj_id = to_object_id(player_id)
    p = db["player"].find_one({"_id": obj_id})
    if not p:
        raise HTTPException(status_code=404, detail="Player not found")

    innings = list(db["innings"].find({"player_id": player_id}).sort("date", -1))
    # Normalize and compute SR per innings
    for inn in innings:
        inn["_id"] = str(inn["_id"]) if "_id" in inn else None
        inn["strike_rate"] = strike_rate(inn.get("runs", 0), inn.get("balls", 0))
        # Ensure date is iso string
        if isinstance(inn.get("date"), datetime):
            inn["date"] = inn["date"].isoformat()

    agg = db["innings"].aggregate([
        {"$match": {"player_id": player_id}},
        {"$group": {
            "_id": "$player_id",
            "runs": {"$sum": "$runs"},
            "balls": {"$sum": "$balls"},
            "fours": {"$sum": "$fours"},
            "sixes": {"$sum": "$sixes"},
            "innings": {"$sum": 1}
        }}
    ])
    stats = next(agg, None) or {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "innings": 0}
    total_runs = stats.get("runs", 0)
    total_balls = stats.get("balls", 0)

    return {
        "_id": str(p.get("_id")),
        "name": p.get("name"),
        "role": p.get("role"),
        "innings": innings,
        "career": {
            "total_runs": total_runs,
            "total_balls": total_balls,
            "total_fours": stats.get("fours", 0),
            "total_sixes": stats.get("sixes", 0),
            "innings_count": stats.get("innings", 0),
            "strike_rate": strike_rate(total_runs, total_balls)
        }
    }


@app.post("/innings")
def add_innings(payload: CreateInningsRequest):
    # Validate player exists
    try:
        obj_id = to_object_id(payload.player_id)
    except HTTPException:
        raise
    player = db["player"].find_one({"_id": obj_id})
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    data = payload.model_dump()
    # Default date to now
    if not data.get("date"):
        data["date"] = datetime.now(timezone.utc)

    _id = create_document("innings", data)
    return {"_id": _id}


@app.get("/players/{player_id}/export")
def export_player(player_id: str, format: Optional[str] = "csv"):
    obj_id = to_object_id(player_id)
    p = db["player"].find_one({"_id": obj_id})
    if not p:
        raise HTTPException(status_code=404, detail="Player not found")
    innings = list(db["innings"].find({"player_id": player_id}).sort("date", 1))

    if format == "json":
        # Convert ObjectIds and dates
        for inn in innings:
            inn["_id"] = str(inn["_id"]) if "_id" in inn else None
            if isinstance(inn.get("date"), datetime):
                inn["date"] = inn["date"].isoformat()
        return JSONResponse({"player": {"_id": str(p["_id"]), "name": p.get("name"), "role": p.get("role")}, "innings": innings})

    # Default CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Opposition", "Venue", "Runs", "Balls", "4s", "6s", "Out", "Strike Rate"]) 
    for inn in innings:
        d = inn.get("date")
        if isinstance(d, datetime):
            d_str = d.strftime("%Y-%m-%d")
        else:
            d_str = str(d) if d else ""
        writer.writerow([
            d_str,
            inn.get("opposition", ""),
            inn.get("venue", ""),
            inn.get("runs", 0),
            inn.get("balls", 0),
            inn.get("fours", 0),
            inn.get("sixes", 0),
            "Out" if inn.get("out", True) else "Not Out",
            strike_rate(inn.get("runs", 0), inn.get("balls", 0)),
        ])

    output.seek(0)
    filename = f"{p.get('name','player')}_career.csv"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
