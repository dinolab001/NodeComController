from fastapi import APIRouter

router = APIRouter()

DATA: dict = {"message": "hello world from NodeCom controller 1", "version": "1.0.3"}

@router.get("/")
def read_root():
    global DATA
    return DATA
