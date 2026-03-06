import time
import httpx
import redis
import json
import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from .database import engine, SessionLocal
from . import models


for i in range(10):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        models.Base.metadata.create_all(bind=engine)
        break
    except Exception as e:
        print(f"DB not ready, retry {i+1}/10: {e}")
        time.sleep(2)
else:
    raise RuntimeError("Could not connect to database after 10 retries")

app = FastAPI()

redis_client = redis.Redis(
    host="redis",
    port=6379,
    decode_responses=True
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None



@app.get("/ping")
def ping():
    return "ok"


@app.post("/items", status_code=201)
def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    db_item = models.Item(name=item.name, description=item.description)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return {"id": db_item.id, "name": db_item.name, "description": db_item.description}


@app.get("/items")
def get_all_items(db: Session = Depends(get_db)):
    items = db.query(models.Item).all()
    return [{"id": i.id, "name": i.name, "description": i.description} for i in items]


@app.get("/items/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"id": item.id, "name": item.name, "description": item.description}


@app.put("/items/{item_id}")
def update_item(item_id: int, item: ItemUpdate, db: Session = Depends(get_db)):
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.name is not None:
        db_item.name = item.name
    if item.description is not None:
        db_item.description = item.description
    db.commit()
    db.refresh(db_item)
    return {"id": db_item.id, "name": db_item.name, "description": db_item.description}


@app.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(db_item)
    db.commit()
    return {"id": item_id, "name": db_item.name, "description": db_item.description}

CACHE_TTL = 600

@app.get("/weather")
def get_weather(city: str, db: Session = Depends(get_db)):
    cache_key = f"weather:{city.lower()}"

    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    with httpx.Client() as client:
        geo_response = client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1}
        )

    if geo_response.status_code != 200:
        raise HTTPException(status_code=502, detail="Geocoding API error")

    geo_data = geo_response.json()

    if not geo_data.get("results"):
        raise HTTPException(status_code=404, detail=f"City '{city}' not found")

    lat = geo_data["results"][0]["latitude"]
    lon = geo_data["results"][0]["longitude"]
    city_name = geo_data["results"][0]["name"]

    with httpx.Client() as client:
        weather_response = client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m"
            }
        )

    if weather_response.status_code != 200:
        raise HTTPException(status_code=502, detail="Weather API error")

    temperature = weather_response.json()["current"]["temperature_2m"]

    db_weather = db.query(models.Weather).filter(models.Weather.city == city_name).first()
    if db_weather:
        db_weather.temperature = temperature
    else:
        db_weather = models.Weather(city=city_name, temperature=temperature)
        db.add(db_weather)
    db.commit()


    result = {"city": city_name, "temperature": temperature}
    redis_client.setex(cache_key, CACHE_TTL, json.dumps(result))

    return result


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)