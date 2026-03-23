from fastapi import APIRouter

router = APIRouter(prefix="/example", tags=["example"])


@router.get("/")
def read_items(): ...


@router.get("/{id}")
def read_item(): ...


@router.post("/")
def create_item(): ...


@router.put("/{id}")
def update_item(): ...


@router.delete("/{id}")
def delete_item(): ...
