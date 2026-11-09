# estela-backend

Backend mínimo (FastAPI + PyMySQL) para probar **Estela** contra una base **MySQL real en la nube**.

```
Navegador ──HTTP──> Backend FastAPI (Render, gratis) ──┐
                                                       ├──> MySQL 8.4 (Clever Cloud, plan DEV gratis)
Estela (laptop) ───────── PyMySQL, puerto TCP ─────────┘
```

Sirve para dos cosas:

1. **Crear y llenar el esquema** (`init_db.py`) con las mismas tablas que usa Estela.
2. **Agregar y listar ventas desde el navegador**, para que en la demostración Estela vea la venta nueva al volver a ejecutarse.

Es un proyecto de prueba universitario, no de producción: no tiene autenticación.

## Archivos

| Archivo | Qué hace |
|---|---|
| `app.py` | La API FastAPI y la página HTML con el formulario. |
| `db.py` | `conectar()` y `consultar()`: las únicas funciones que tocan PyMySQL. |
| `init_db.py` | Crea las tablas y carga los datos iniciales. Se puede correr varias veces. |
| `requirements.txt` | fastapi, uvicorn[standard], PyMySQL>=1.2, python-dotenv |
| `.python-version` | `3.11`; Render lo usa para elegir la versión de Python. |
| `.env.example` | Plantilla de las variables de entorno. |

## Endpoints

| Método y ruta | Qué hace |
|---|---|
| `GET /` | Página con la tabla de ventas y un formulario para agregar una. |
| `GET /salud` | `{"ok": true, "mysql": "8.4.x", "tls": "<cifrado o null>"}`; 503 con el motivo si la base no responde. |
| `GET /vendedores` | Lista de vendedores en JSON. |
| `GET /ventas` | Lista de ventas en JSON, ordenadas por `id`. |
| `POST /ventas` | Crea una venta y responde 201 con la venta creada. |
| `POST /ventas/formulario` | Lo usa el formulario de `/`; al terminar vuelve a `/`. |

Ejemplo de cuerpo para `POST /ventas` (`monto` y `estado` son opcionales):

```json
{"fecha": "2026-03-01", "zona": "caribe", "vendedor_id": 2, "monto": 1234.50, "estado": "confirmada"}
```

Si el cuerpo no es válido, la respuesta es 422 con los errores en español:

```json
{"detail": ["zona: 'este' no es válida; use una de: centro, norte, sur, caribe", "el vendedor 99 no existe"]}
```

La documentación interactiva queda en `/docs`.

## 1. Crear la base en Clever Cloud

1. En [Clever Cloud](https://www.clever-cloud.com/) crea un add-on **MySQL**, plan **DEV** (gratis), versión 8.4.
2. En el panel del add-on copia los valores de *host*, *port*, *user*, *password* y *database name*.

Ese usuario **no puede crear bases**, así que el código no usa `CREATE DATABASE` ni `USE`: trabaja sobre la base que trae `DB_NAME`. Además, la base DEV es compartida y acepta **muy pocas conexiones simultáneas**: por eso el backend abre una conexión por petición y la cierra siempre, sin pool.

## 2. Probar en local (PowerShell en Windows)

```powershell
cd estela-backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt

Copy-Item .env.example .env
notepad .env        # llena DB_HOST, DB_PORT, DB_USER, DB_PASSWORD y DB_NAME con los datos de Clever Cloud

py init_db.py       # crea las tablas y carga los datos iniciales
py init_db.py       # la segunda vez no duplica nada

py -m uvicorn app:app --reload
```

Abre <http://127.0.0.1:8000/> para ver la página y <http://127.0.0.1:8000/salud> para comprobar la conexión.

Para probar la API desde PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/ventas
Invoke-RestMethod http://127.0.0.1:8000/ventas -Method Post -ContentType "application/json" `
  -Body '{"fecha": "2026-03-01", "zona": "caribe", "vendedor_id": 2, "monto": 1234.50}'
```

> `init_db.py` se corre **una sola vez, desde la laptop**, con el `.env` local. Render no lo ejecuta al arrancar.

El `.env` solo se lee si existe; nunca se sube al repositorio (está en `.gitignore`).

## 3. Desplegar en Render

1. Sube este proyecto a su propio repositorio de GitHub. Revisa que `.env` **no** esté incluido.
2. En [Render](https://render.com/): **New → Web Service** y conecta el repositorio.
3. Configura:
   - **Runtime:** Python 3. La versión sale de `.python-version`.
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free
4. En **Environment** agrega las cinco variables con los valores del panel de Clever Cloud: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` y `DB_NAME`.
5. Crea el servicio. Cuando termine, abre `https://<tu-servicio>.onrender.com/salud`: debe responder `"ok": true`.

**Ojo con el plan gratis:** el servicio **se duerme** tras unos 15 minutos sin visitas. La primera petición después de eso lo despierta y puede tardar casi un minuto en responder. Antes de la demostración abre `/salud` una vez para despertarlo.

## 4. Conectar Estela a la misma base

En el `conexiones.ini` del proyecto de Estela, pon en la sección `[ventas]` los mismos datos de Clever Cloud:

```ini
[ventas]
host = xxxxx-mysql.services.clever-cloud.com
puerto = 3306
usuario = uxxxxxxxx
clave = ********
base = bxxxxxxxx
```

Y ejecútalo:

```powershell
py -m estela.consola.cli ejecutar ejemplos/MiProyecto
```

Para la demostración, agrega una venta desde el formulario en la URL de Render y vuelve a ejecutar Estela.

Ten en cuenta que el reporte de `MiProyecto` descarta las ventas sin monto o con monto 0, y solo muestra las zonas cuyo total supera 1500. Una venta de caribe por 500 o más, por ejemplo, hace que CARIBE aparezca en el reporte.

## Esquema

Es **idéntico** al que usa Estela; no hay que cambiarlo. Estela ordena un `ENUM` según el orden en que se declararon sus valores.

```sql
CREATE TABLE IF NOT EXISTS vendedores (
    id       INT PRIMARY KEY AUTO_INCREMENT,
    nombre   VARCHAR(100) NOT NULL,
    activo   BOOLEAN NOT NULL DEFAULT TRUE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ventas (
    id           INT PRIMARY KEY AUTO_INCREMENT,
    fecha        DATE NOT NULL,
    zona         ENUM('centro', 'norte', 'sur', 'caribe') NOT NULL,
    vendedor_id  INT NOT NULL,
    monto        DECIMAL(10, 2) NULL,
    estado       ENUM('confirmada', 'cancelada', 'pendiente') NOT NULL DEFAULT 'confirmada',
    FOREIGN KEY (vendedor_id) REFERENCES vendedores(id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

`init_db.py` carga 4 vendedores (con `id` 1 a 4) y 9 ventas, pero **solo si `vendedores` está vacía**. La carga se hace en una sola transacción, así que si falla a la mitad no queda nada a medias.

## Seguridad

- Toda sentencia que lleva valores del usuario usa parámetros `%s` de PyMySQL; no se arma SQL concatenando ni con f-strings.
- Las credenciales salen solo de variables de entorno. Los mensajes de error reemplazan host, usuario, clave y base por `***`.
- No hay endpoints para borrar ni para modificar en masa.
- PyMySQL 1.2 o más nuevo cifra la conexión con TLS cuando el servidor lo ofrece. `/salud` muestra el cifrado que se usó.
