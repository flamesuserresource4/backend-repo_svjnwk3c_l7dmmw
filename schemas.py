from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# Each Pydantic model here maps to a MongoDB collection using its lowercase name
# Example: class Player -> collection "player"

class Player(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Player full name")
    role: Optional[str] = Field(None, description="Role: Batter, Bowler, All-rounder, Keeper")

class Innings(BaseModel):
    player_id: str = Field(..., description="MongoDB ObjectId string of the player")
    runs: int = Field(..., ge=0, le=400, description="Runs scored")
    balls: int = Field(..., ge=0, le=400, description="Balls faced")
    fours: int = Field(0, ge=0, le=200, description="Number of 4s")
    sixes: int = Field(0, ge=0, le=200, description="Number of 6s")
    out: bool = Field(True, description="Was the batter out?")
    opposition: Optional[str] = Field(None, max_length=100, description="Opposition/team name")
    venue: Optional[str] = Field(None, max_length=100, description="Venue or ground")
    date: Optional[datetime] = Field(None, description="Date of the innings (defaults to now)")
