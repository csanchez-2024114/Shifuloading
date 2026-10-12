#Siempre hay inicializar el backend con python main.py
import requests

BASE_URL = "http://localhost:5000"


def test_add():
    res = requests.get(f"{BASE_URL}/")
    assert res.status_code == 200
    assert res.text == "Este es el backend del proyecto!!"
 


