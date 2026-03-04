import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI()


db: dict[int, dict] = {}
counter: int = 0


class Item(BaseModel):
    name: str
    description: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@app.post("/items", status_code=201)
def create_item(item: Item):
    global counter
    counter += 1
    db[counter] = item.dict()
    return {"id": counter, **db[counter]}


@app.get("/items")
def get_all_items():
    return [{"id": k, **v} for k, v in db.items()]


@app.get("/items/{item_id}")
def get_item(item_id: int):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"id": item_id, **db[item_id]}


@app.put("/items/{item_id}")
def update_item(item_id: int, item: ItemUpdate):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.name is not None:
        db[item_id]["name"] = item.name
    if item.description is not None:
        db[item_id]["description"] = item.description
    return {"id": item_id, **db[item_id]}


@app.delete("/items/{item_id}")
def delete_item(item_id: int):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    deleted = db.pop(item_id)
    return {"id": item_id, **deleted}


if __name__ == '__main__':
    uvicorn.run("main:app", reload=True)