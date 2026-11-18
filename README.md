# Agente inmobiliario con OpenAI

Asistente para buscar y recomendar departamentos en Chile. Usa
herramientas locales para consultar un inventario inmobiliario externo y
un modelo de OpenAI para interpretar consultas, elegir herramientas y redactar
respuestas comerciales en espanol.

El repositorio tambien incluye tres ejemplos breves de agentes de vinos, que
sirven para mostrar la progresion desde un agente basico a uno con herramientas.

## Que puede hacer

- Buscar departamentos por ciudad, tipologia, entrega, precio en UF,
  dormitorios, banos y superficie.
- Recomendar proyectos concretos segun los criterios del cliente.
- Entregar un resumen del inventario disponible.
- Estimar una capacidad de compra referencial desde el ingreso mensual en CLP.
- Mantener historial local de la conversacion en `sessions/`.

La fuente de inventario se configura con la variable `INMOTECH_API_URL`.

## Requisitos

- Python 3.11 o superior.
- Una cuenta de OpenAI con una clave de API activa.
- Acceso a Internet para OpenAI y la API de inventario.

## Instalacion

Desde PowerShell, en la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita el archivo `.env` y agrega una clave valida. Nunca subas este archivo al
repositorio.

```env
OPENAI_API_KEY=tu_clave_de_openai
OPENAI_MODEL=gpt-5-mini
INMOTECH_API_URL=https://tu-api-de-inventario.example/propiedades
```

`OPENAI_MODEL` es opcional; si no se indica, el proyecto usa `gpt-5-mini`.
El modelo debe ser compatible con la Responses API y function calling.

## Uso

Ejecuta el asesor inmobiliario:

```powershell
.\.venv\Scripts\python.exe ia_inmo.py
```

Luego escribe una consulta cuando aparezca `Prompt:`.

Ejemplos:

```text
Busco un departamento en Santiago de 2 dormitorios y hasta 3.500 UF.
Que proyectos me recomiendas en Nunoa con entrega inmediata?
Como esta el mercado en La Florida?
Gano $2.000.000, que puedo comprar?
```

Las consultas de ingreso entregan una estimacion referencial de capacidad de
compra. No constituyen una preaprobacion bancaria.

## API FastAPI

La logica tambien esta disponible como API REST. Inicia el servidor local con:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Abre la documentacion interactiva en:

```text
http://127.0.0.1:8000/docs
```

Endpoints disponibles:

| Metodo | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/health` | Confirma que el proceso esta activo. |
| `GET` | `/ready` | Comprueba la conexion con el inventario. |
| `GET` | `/api/v1/properties` | Busca unidades con filtros por query string. |
| `GET` | `/api/v1/projects/recommendations` | Recomienda proyectos segun filtros. |
| `GET` | `/api/v1/market-summary` | Resume inventario y precios. |
| `POST` | `/api/v1/purchase-capacity` | Estima capacidad de compra desde la renta. |
| `POST` | `/api/v1/chat` | Consulta conversacional usando OpenAI. |

Ejemplos desde PowerShell:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/properties?ciudad=Santiago&dormitorios_min=2&presupuesto_max_uf=3500"

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/purchase-capacity" `
  -ContentType "application/json" `
  -Body '{"ingreso_mensual_clp": 2000000, "ciudad": "Santiago"}'

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/chat" `
  -ContentType "application/json" `
  -Body '{"mensaje": "Que proyectos me recomiendas en Santiago?"}'
```

`/api/v1/chat` necesita una clave OpenAI valida. Los endpoints de busqueda,
mercado y capacidad funcionan solo con la fuente de inventario.

## Pruebas

Ejecuta las pruebas automatizadas con:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas no consultan servicios externos: inyectan un servicio simulado para
validar rutas, filtros, errores HTTP, metricas y validacion de datos. El cliente
de inventario tambien se prueba de forma aislada.

## Integracion continua

El workflow `.github/workflows/ci.yml` se ejecuta en cada `push`, pull request
y ejecucion manual. Verifica dependencias, compila el proyecto y ejecuta las
pruebas en Python 3.11 y 3.12. No utiliza claves de OpenAI ni consulta la API
de inventario durante las pruebas.

## Observabilidad

- Cada respuesta incluye `X-Request-ID`, que permite seguir una solicitud.
- Los logs se emiten en JSON por salida estandar para facilitar su recoleccion
  por un proveedor de logs.
- `GET /metrics` expone contadores y latencias en formato Prometheus.
- `GET /health` confirma que el proceso esta activo y `GET /ready` valida la
  conexion con el inventario.

## Arquitectura

```text
Cliente HTTP
    |
    v
Routers FastAPI -> Servicios de negocio -> Cliente HTTP -> API de inventario
    |                    |
    |                    +-------------------------------> OpenAI
    v
Logs JSON + metricas Prometheus
```

La logica original en `ia_inmo.py` conserva las herramientas de dominio:

| Herramienta | Uso |
| --- | --- |
| `buscar_departamentos` | Devuelve unidades que cumplen filtros concretos. |
| `sugerir_proyectos` | Agrupa unidades y recomienda proyectos. |
| `estimar_capacidad_compra` | Calcula capacidad estimada y proyectos alcanzables. |
| `resumen_mercado` | Resume stock, precios y ciudades con mas oferta. |

## Archivos principales

| Archivo | Descripcion |
| --- | --- |
| `ia_inmo.py` | Aplicacion principal y herramientas inmobiliarias. |
| `api.py` | Punto de entrada compatible para Uvicorn. |
| `app/main.py` | Composicion FastAPI, middleware, metricas y manejo de errores. |
| `app/routers/` | Capa HTTP separada por responsabilidad. |
| `app/services/` | Casos de uso y adaptacion de la logica inmobiliaria. |
| `app/clients/` | Cliente HTTP del inventario. |
| `app/core/` | Configuracion, excepciones y observabilidad. |
| `tests/` | Pruebas de API y cliente externo aisladas. |
| `.env.example` | Plantilla de configuracion sin secretos. |
| `requirements.txt` | Dependencias Python del proyecto. |
| `00_basico.py` | Ejemplo minimo de agente de vinos. |
| `01_system_prompt.py` | Ejemplo de agente con instrucciones. |
| `02_tools.py` | Ejemplo de agente de vinos con busqueda local. |
| `data/vinos.json` | Cava utilizada por el ejemplo de vinos. |

## Notas operativas

- Si aparece `OPENAI_API_KEY no es valida`, reemplaza la clave configurada en
  `.env` o en las variables de entorno del sistema.
- Puedes cambiar el endpoint de inventario mediante `INMOTECH_API_URL` sin
  editar codigo.
- Los datos inmobiliarios cambian en origen; el agente consulta la API cada
  vez que usa una herramienta.
- El directorio `sessions/` contiene historiales locales y esta excluido de
  Git por privacidad.

## Ejemplos de vinos

Los ejemplos tambien usan la misma configuracion de OpenAI:

```powershell
.\.venv\Scripts\python.exe 00_basico.py
.\.venv\Scripts\python.exe 01_system_prompt.py
.\.venv\Scripts\python.exe 02_tools.py
```
