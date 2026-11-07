from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


class PageElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.logo_src = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "img" and attrs.get("alt") == "Abarpay":
            self.logo_src = attrs.get("src")


def test_inicio_sirve_logo_oficial_y_conserva_navegacion():
    client = TestClient(app)
    page = client.get("/")
    assert page.status_code == 200
    elements = PageElements()
    elements.feed(page.text)
    assert len(elements.ids) == len(set(elements.ids)), "IDs duplicados en la página"
    assert {"atras", "tabs", "tienda", "v-home", "v-inventario"} <= set(elements.ids)
    assert elements.logo_src, "El encabezado debe mostrar el logo oficial"

    logo = client.get(elements.logo_src)
    assert logo.status_code == 200
    assert logo.headers["content-type"].startswith("image/jpeg")
    official = Path(__file__).resolve().parents[2] / "assets/branding/logo.jpeg"
    assert logo.content == official.read_bytes()
