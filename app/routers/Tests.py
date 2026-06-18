from fastapi import FastAPI
from fastapi import  APIRouter,HTTPException
from app.schemas.test import Get, Post, Put, Delete
router=APIRouter(prefix="/app/", tags=["App"])

app=FastAPI()


items = []
next_id = 1


# ----------------------------- POST
@app.post("/items")
def create_item(data: Post):
    global next_id
    new_item = {
        "id": next_id,
        "name": data.name,
        "family": data.family,
    }
    items.append(new_item)
    next_id += 1
    return new_item


# ----------------------------- GET
@app.get("/items/{item_id}")
def get_item(item_id: int):
    for item in items:
        if item["id"] == item_id:
            return item
    raise HTTPException(404, "Item not found")


# ----------------------------- PUT
@app.put("/items/{item_id}")
def update_item(item_id: int, data: Put):
    for item in items:
        if item["id"] == item_id:
            item["name"] = data.name
            item["family"] = data.family
            return item
    raise HTTPException(404, "Item not found")


# ----------------------------- DELETE
@app.delete("/items/{item_id}")
def delete_item(item_id: int, data: Delete):
    for item in items:
        if item["id"] == item_id:
            items.remove(item)
            return {"message": "Item deleted"}
    raise HTTPException(404, "Item not found")
