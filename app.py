"""API mínima para agregar y listar ventas en la base MySQL que lee Estela."""

import html
import logging
import re
from datetime import date
from decimal import Decimal
from typing import Optional
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from db import ErrorBD, conectar, consultar

# Mismos valores y mismo orden que los ENUM del esquema.
ZONAS = ("centro", "norte", "sur", "caribe")
ESTADOS = ("confirmada", "cancelada", "pendiente")

SELECT_VENTAS = "SELECT id, fecha, zona, vendedor_id, monto, estado FROM ventas"

log = logging.getLogger("estela-backend")
app = FastAPI(title="Estela backend", version="1.0")


# ---------- Validación ----------


class VentaNueva(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha: date
    zona: str
    vendedor_id: int
    monto: Optional[Decimal] = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    estado: str = "confirmada"

    @field_validator("fecha", mode="before")
    @classmethod
    def _fecha_texto(cls, valor):
        if not isinstance(valor, (str, date)):
            raise ValueError("debe ser una fecha en formato AAAA-MM-DD")
        return valor

    @field_validator("fecha")
    @classmethod
    def _fecha_rango(cls, valor):
        if valor.year < 1000:
            raise ValueError("debe estar entre 1000-01-01 y 9999-12-31")
        return valor

    @field_validator("zona")
    @classmethod
    def _zona(cls, valor):
        if valor not in ZONAS:
            raise ValueError(f"'{valor}' no es válida; use una de: {', '.join(ZONAS)}")
        return valor

    @field_validator("estado")
    @classmethod
    def _estado(cls, valor):
        if valor not in ESTADOS:
            raise ValueError(f"'{valor}' no es válido; use uno de: {', '.join(ESTADOS)}")
        return valor


MENSAJES = {
    "missing": "es obligatorio",
    "extra_forbidden": "no es un campo permitido",
    "json_invalid": "el cuerpo no es un JSON válido",
    "model_attributes_type": "el cuerpo debe ser un objeto JSON",
    "dict_type": "el cuerpo debe ser un objeto JSON",
    "string_type": "debe ser texto",
    "date_parsing": "no es una fecha válida (formato AAAA-MM-DD)",
    "date_from_datetime_parsing": "no es una fecha válida (formato AAAA-MM-DD)",
    "date_from_datetime_inexact": "no es una fecha válida (formato AAAA-MM-DD)",
    "date_type": "no es una fecha válida (formato AAAA-MM-DD)",
    "int_parsing": "debe ser un número entero",
    "int_type": "debe ser un número entero",
    "int_from_float": "debe ser un número entero",
    "decimal_parsing": "debe ser un número o null",
    "decimal_type": "debe ser un número o null",
    "finite_number": "debe ser un número finito",
    "greater_than_equal": "no puede ser negativo",
    "decimal_max_places": "admite a lo sumo 2 decimales",
    "decimal_max_digits": "es demasiado grande (máximo 99999999.99)",
    "decimal_whole_digits": "es demasiado grande (máximo 99999999.99)",
}


def errores_en_espanol(errores):
    """Convierte los errores de Pydantic en frases cortas en español."""
    salida = []
    for error in errores:
        campos = [str(parte) for parte in error["loc"] if parte != "body"]
        if error["type"] == "json_invalid":
            campos = []  # loc trae la posición del carácter, no un campo
        if error["type"] == "value_error":
            mensaje = str(error.get("ctx", {}).get("error", error["msg"]))
        else:
            mensaje = MENSAJES.get(error["type"], "valor no válido")
        salida.append(f"{'.'.join(campos)}: {mensaje}" if campos else mensaje)
    return salida


@app.exception_handler(RequestValidationError)
async def _error_validacion(request, exc):
    return JSONResponse(status_code=422, content={"detail": errores_en_espanol(exc.errors())})


@app.exception_handler(ErrorBD)
async def _error_bd(request, exc):
    log.warning("Error de base de datos: %s", exc)  # el mensaje ya viene sin credenciales
    return JSONResponse(status_code=503, content={"detail": f"base de datos no disponible: {exc}"})


# ---------- Datos ----------


def venta_json(fila):
    return {
        "id": fila["id"],
        "fecha": fila["fecha"].isoformat(),
        "zona": fila["zona"],
        "vendedor_id": fila["vendedor_id"],
        "monto": None if fila["monto"] is None else float(fila["monto"]),
        "estado": fila["estado"],
    }


def vendedor_json(fila):
    return {"id": fila["id"], "nombre": fila["nombre"], "activo": bool(fila["activo"])}


def crear_venta(venta: VentaNueva):
    """Inserta la venta en una sola conexión y la devuelve tal como quedó en la base."""
    with conectar() as con:
        existe = consultar(
            "SELECT 1 FROM vendedores WHERE id = %s", (venta.vendedor_id,), con
        )
        if not existe:
            raise HTTPException(422, detail=[f"el vendedor {venta.vendedor_id} no existe"])
        consultar(
            "INSERT INTO ventas (fecha, zona, vendedor_id, monto, estado)"
            " VALUES (%s, %s, %s, %s, %s)",
            (venta.fecha, venta.zona, venta.vendedor_id, venta.monto, venta.estado),
            con,
        )
        nuevo_id = consultar("SELECT LAST_INSERT_ID() AS id", conexion=con)[0]["id"]
        fila = consultar(SELECT_VENTAS + " WHERE id = %s", (nuevo_id,), con)[0]
    return venta_json(fila)


def valores_enum(columnas):
    """Convierte filas de information_schema ("enum('a','b')") en {columna: ['a', 'b']}."""
    return {
        f["columna"]: [v.replace("''", "'") for v in re.findall(r"'((?:[^']|'')*)'", f["tipo"])]
        for f in columnas
    }


# ---------- Endpoints JSON ----------


@app.get("/salud")
def salud():
    try:
        with conectar() as con:
            consultar("SELECT 1", conexion=con)
            version = consultar("SELECT VERSION() AS v", conexion=con)[0]["v"]
            cifrado = consultar("SHOW SESSION STATUS LIKE 'Ssl_cipher'", conexion=con)
    except ErrorBD as error:
        return JSONResponse(status_code=503, content={"ok": False, "motivo": str(error)})
    tls = cifrado[0]["Value"] if cifrado else None
    return {"ok": True, "mysql": version, "tls": tls or None}


@app.get("/vendedores")
def listar_vendedores():
    filas = consultar("SELECT id, nombre, activo FROM vendedores ORDER BY id")
    return [vendedor_json(f) for f in filas]


@app.get("/ventas")
def listar_ventas():
    return [venta_json(f) for f in consultar(SELECT_VENTAS + " ORDER BY id")]


@app.post("/ventas", status_code=201)
def nueva_venta(venta: VentaNueva):
    return crear_venta(venta)


# ---------- Página HTML ----------


@app.post("/ventas/formulario")
async def formulario(request: Request):
    # Se lee el cuerpo a mano para no depender de python-multipart.
    campos = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    datos = {clave: valores[0].strip() for clave, valores in campos.items()}
    if datos.get("monto", "") == "":
        datos["monto"] = None
    try:
        venta = crear_venta(VentaNueva.model_validate(datos))
    except ValidationError as error:
        mensaje = "; ".join(errores_en_espanol(error.errors()))
        return RedirectResponse("/?" + urlencode({"error": mensaje}), status_code=303)
    except HTTPException as error:
        mensaje = "; ".join(error.detail)
        return RedirectResponse("/?" + urlencode({"error": mensaje}), status_code=303)
    return RedirectResponse("/?" + urlencode({"ok": venta["id"]}), status_code=303)


def _opciones(valores, elegido=None):
    return "".join(
        f'<option value="{html.escape(str(valor))}"{" selected" if valor == elegido else ""}>'
        f"{html.escape(texto)}</option>"
        for valor, texto in valores
    )


def _fila_venta(venta, nombres):
    monto = "—" if venta["monto"] is None else f"{venta['monto']:,.2f}"
    vendedor = nombres.get(venta["vendedor_id"], str(venta["vendedor_id"]))
    celdas = (
        f"<td>{venta['id']}</td>",
        f"<td>{venta['fecha']}</td>",
        f"<td>{html.escape(venta['zona'])}</td>",
        f"<td>{html.escape(vendedor)}</td>",
        f"<td class='num'>{monto}</td>",
        f"<td>{html.escape(venta['estado'])}</td>",
    )
    return "<tr>" + "".join(celdas) + "</tr>"


@app.get("/", response_class=HTMLResponse)
def inicio(ok: Optional[str] = None, error: Optional[str] = None):
    with conectar() as con:
        enums = valores_enum(
            consultar(
                "SELECT COLUMN_NAME AS columna, COLUMN_TYPE AS tipo"
                " FROM information_schema.COLUMNS"
                " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ventas'"
                " AND COLUMN_NAME IN ('zona', 'estado')",
                conexion=con,
            )
        )
        vendedores = [
            vendedor_json(f)
            for f in consultar("SELECT id, nombre, activo FROM vendedores ORDER BY id", conexion=con)
        ]
        ventas = [venta_json(f) for f in consultar(SELECT_VENTAS + " ORDER BY id", conexion=con)]

    nombres = {v["id"]: v["nombre"] for v in vendedores}
    filas = "".join(_fila_venta(v, nombres) for v in ventas) or (
        "<tr><td colspan='6'>No hay ventas. Corre <code>py init_db.py</code>.</td></tr>"
    )

    aviso = ""
    if ok:
        aviso = f"<p class='ok'>Venta #{html.escape(ok)} agregada.</p>"
    if error:
        aviso = f"<p class='error'>No se agregó la venta: {html.escape(error)}</p>"

    zonas = _opciones([(z, z) for z in enums.get("zona", [])])
    estados = _opciones([(e, e) for e in enums.get("estado", [])], "confirmada")
    opciones_vendedores = _opciones(
        [(v["id"], v["nombre"] + ("" if v["activo"] else " (inactivo)")) for v in vendedores]
    )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ventas · Estela</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
  th, td {{ border-bottom: 1px solid #ddd; padding: .4rem .6rem; text-align: left; }}
  th {{ background: #f4f4f4; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  form {{ display: grid; grid-template-columns: max-content 1fr; gap: .5rem 1rem; max-width: 420px; }}
  form button {{ grid-column: 2; justify-self: start; padding: .4rem 1rem; }}
  .ok {{ background: #e6f6e6; padding: .6rem; border-radius: 4px; }}
  .error {{ background: #fde8e8; padding: .6rem; border-radius: 4px; }}
</style>
</head>
<body>
<h1>Ventas</h1>
{aviso}
<table>
  <thead><tr><th>#</th><th>Fecha</th><th>Zona</th><th>Vendedor</th><th class="num">Monto</th><th>Estado</th></tr></thead>
  <tbody>{filas}</tbody>
</table>

<h2>Agregar venta</h2>
<form method="post" action="/ventas/formulario">
  <label for="fecha">Fecha</label>
  <input id="fecha" name="fecha" type="date" required value="{date.today().isoformat()}">
  <label for="zona">Zona</label>
  <select id="zona" name="zona" required>{zonas}</select>
  <label for="vendedor_id">Vendedor</label>
  <select id="vendedor_id" name="vendedor_id" required>{opciones_vendedores}</select>
  <label for="monto">Monto</label>
  <input id="monto" name="monto" type="number" min="0" step="0.01" placeholder="vacío = sin monto">
  <label for="estado">Estado</label>
  <select id="estado" name="estado" required>{estados}</select>
  <button type="submit">Agregar</button>
</form>
<p><small>JSON: <a href="/ventas">/ventas</a> · <a href="/vendedores">/vendedores</a> · <a href="/salud">/salud</a> · <a href="/docs">/docs</a></small></p>
</body>
</html>"""
