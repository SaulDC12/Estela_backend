"""Acceso a MySQL. conectar() y consultar() son las únicas funciones que tocan PyMySQL."""

import os
from contextlib import contextmanager
from pathlib import Path

import pymysql
import pymysql.cursors

# En local se lee .env (solo si existe); en Render las variables vienen del panel.
_ENV = Path(__file__).with_name(".env")
if _ENV.exists():
    from dotenv import load_dotenv

    load_dotenv(_ENV)


class ErrorBD(Exception):
    """Error de base de datos con el mensaje ya limpio de credenciales."""


def _variable(nombre):
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise ErrorBD(f"falta la variable de entorno {nombre}")
    return valor


def _limpiar(error):
    """Convierte un error de PyMySQL en texto sin host, usuario, clave ni base."""
    if len(error.args) == 2:
        texto = f"MySQL {error.args[0]}: {error.args[1]}"
    else:
        texto = str(error) or type(error).__name__
    for nombre in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        secreto = os.environ.get(nombre, "").strip()
        if secreto:
            texto = texto.replace(secreto, "***")
    return texto


@contextmanager
def conectar():
    """Abre una conexión nueva y la cierra siempre al salir del `with`."""
    try:
        puerto = int(os.environ.get("DB_PORT", "").strip() or "3306")
    except ValueError:
        raise ErrorBD("DB_PORT debe ser un número") from None
    try:
        conexion = pymysql.connect(
            host=_variable("DB_HOST"),
            port=puerto,
            user=_variable("DB_USER"),
            password=_variable("DB_PASSWORD"),
            database=_variable("DB_NAME"),
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=10,
            cursorclass=pymysql.cursors.DictCursor,
        )
    except pymysql.Error as error:
        raise ErrorBD(_limpiar(error)) from None
    try:
        yield conexion
    finally:
        try:
            conexion.close()
        except pymysql.Error:
            pass


def consultar(sql, parametros=None, conexion=None):
    """Ejecuta una sentencia y devuelve sus filas como lista de dicts.

    Los valores van SIEMPRE en `parametros` (marcadores %s), nunca dentro de `sql`.
    Sin `conexion`, abre una propia y la cierra al terminar.
    """
    if conexion is None:
        with conectar() as propia:
            return consultar(sql, parametros, propia)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return list(cursor.fetchall())
    except pymysql.Error as error:
        raise ErrorBD(_limpiar(error)) from None
