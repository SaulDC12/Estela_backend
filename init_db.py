"""Crea las tablas de Estela y carga los datos iniciales. Se puede correr varias veces.

Uso (desde la laptop, con el .env local):  py init_db.py
"""

import sys

from db import ErrorBD, conectar, consultar

# El esquema es idéntico al que usa Estela: no cambiar nombres, tipos,
# nulabilidad ni el orden de los valores de los ENUM.
TABLAS = (
    """
    CREATE TABLE IF NOT EXISTS vendedores (
        id       INT PRIMARY KEY AUTO_INCREMENT,
        nombre   VARCHAR(100) NOT NULL,
        activo   BOOLEAN NOT NULL DEFAULT TRUE
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS ventas (
        id           INT PRIMARY KEY AUTO_INCREMENT,
        fecha        DATE NOT NULL,
        zona         ENUM('centro', 'norte', 'sur', 'caribe') NOT NULL,
        vendedor_id  INT NOT NULL,
        monto        DECIMAL(10, 2) NULL,
        estado       ENUM('confirmada', 'cancelada', 'pendiente') NOT NULL DEFAULT 'confirmada',
        FOREIGN KEY (vendedor_id) REFERENCES vendedores(id)
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
    """,
)

# Se insertan con id explícito para que las ventas apunten a 1..4 como en la base local.
VENDEDORES = (
    (1, "Ana Rojas", True),
    (2, "Luis Vargas", True),
    (3, "Marta Solís", True),
    (4, "Eva Jiménez", False),
)

VENTAS = (
    ("2026-01-05", "centro", 1, "1800.00", "confirmada"),
    ("2026-01-20", "centro", 2, "2100.00", "confirmada"),
    ("2026-01-08", "sur", 3, "900.00", "confirmada"),
    ("2026-01-15", "sur", 1, "1200.00", "confirmada"),
    ("2026-01-22", "sur", 2, "1300.00", "confirmada"),
    ("2026-01-10", "norte", 4, "500.00", "confirmada"),
    ("2026-01-18", "norte", 3, "300.00", "confirmada"),
    ("2026-01-25", "norte", 4, "0.00", "cancelada"),
    ("2026-02-01", "caribe", 3, None, "pendiente"),
)


def main():
    with conectar() as con:
        for sql in TABLAS:
            consultar(sql, conexion=con)
        print("Tablas listas: vendedores, ventas.")

        # Todo o nada: si algo falla, la conexión se cierra sin COMMIT y MySQL deshace.
        consultar("START TRANSACTION", conexion=con)
        hay = consultar("SELECT COUNT(*) AS n FROM vendedores FOR UPDATE", conexion=con)[0]["n"]
        if hay:
            consultar("ROLLBACK", conexion=con)
            print(f"vendedores ya tiene {hay} filas: no se cargan datos iniciales.")
            return
        for fila in VENDEDORES:
            consultar(
                "INSERT INTO vendedores (id, nombre, activo) VALUES (%s, %s, %s)", fila, con
            )
        for fila in VENTAS:
            consultar(
                "INSERT INTO ventas (fecha, zona, vendedor_id, monto, estado)"
                " VALUES (%s, %s, %s, %s, %s)",
                fila,
                con,
            )
        consultar("COMMIT", conexion=con)
        print(f"Datos iniciales cargados: {len(VENDEDORES)} vendedores, {len(VENTAS)} ventas.")


if __name__ == "__main__":
    try:
        main()
    except ErrorBD as error:
        sys.exit(f"Error: {error}")
