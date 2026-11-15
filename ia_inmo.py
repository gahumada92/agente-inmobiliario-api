import json
import math
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError

from openai import APIConnectionError, AuthenticationError, RateLimitError
from strands import Agent, tool
from strands.models.openai_responses import OpenAIResponsesModel
from strands.session.file_session_manager import FileSessionManager

from app.clients.inmotech import InmotechClient
from app.core.config import settings

# La URL de inventario y el modelo se pueden ajustar sin modificar el codigo.
API_URL = settings.inmotech_api_url
OPENAI_MODEL = settings.openai_model
CLP_POR_UF_REFERENCIA = 39000.0
TASA_ANUAL_REFERENCIAL = 4.5
PLAZO_ANOS_REFERENCIAL = 30
ESFUERZO_MAXIMO_REFERENCIAL = 25.0
PIE_REFERENCIAL = 20.0
def normalizar_texto(valor: str) -> str:
    return (valor or "").strip().lower()


def extraer_monto_clp(texto: str) -> float | None:
    coincidencias = re.findall(r"[\d\.\,]+", texto or "")
    for coincidencia in coincidencias:
        limpio = coincidencia.replace(".", "").replace(",", "")
        if limpio.isdigit():
            valor = float(limpio)
            if valor > 0:
                return valor
    return None


def es_consulta_capacidad_compra(texto: str) -> bool:
    texto_normalizado = normalizar_texto(texto)
    palabras_clave = [
        "gano",
        "sueldo",
        "ingreso",
        "renta",
        "puedo comprar",
        "me alcanza",
    ]
    return any(palabra in texto_normalizado for palabra in palabras_clave)


def a_float(valor) -> float | None:
    if valor in (None, ""):
        return None
    texto = str(valor).strip()
    try:
        return float(texto)
    except ValueError:
        texto = texto.replace(",", ".")
        try:
            return float(texto)
        except ValueError:
            return None


def maximo_en_rango(valor) -> int | None:
    if valor in (None, ""):
        return None
    numeros = [int(item) for item in re.findall(r"\d+", str(valor))]
    if not numeros:
        return None
    return max(numeros)


def minimo_en_rango(valor) -> int | None:
    if valor in (None, ""):
        return None
    numeros = [int(item) for item in re.findall(r"\d+", str(valor))]
    if not numeros:
        return None
    return min(numeros)


def cargar_propiedades() -> list[dict]:
    return InmotechClient(API_URL).listar_propiedades()


def normalizar_presupuesto(presupuesto: float) -> tuple[float, str]:
    if not presupuesto:
        return 0, ""
    # Si llega un numero demasiado alto para ser UF, asumimos que el usuario
    # escribio CLP y lo convertimos de forma aproximada a UF para filtrar mejor.
    if presupuesto >= 50000:
        presupuesto_uf = round(presupuesto / CLP_POR_UF_REFERENCIA, 2)
        return (
            presupuesto_uf,
            (
                f"Se interpreto el presupuesto {presupuesto:,.0f} como CLP "
                f"y se convirtio de forma referencial a {presupuesto_uf} UF."
            ),
        )
    return presupuesto, ""


def cuota_uf_a_monto_credito_uf(
    cuota_mensual_uf: float,
    tasa_anual: float = TASA_ANUAL_REFERENCIAL,
    plazo_anos: int = PLAZO_ANOS_REFERENCIAL,
) -> float:
    if cuota_mensual_uf <= 0:
        return 0
    tasa_mensual = tasa_anual / 100 / 12
    meses = plazo_anos * 12
    if tasa_mensual <= 0:
        return cuota_mensual_uf * meses
    factor = (1 - math.pow(1 + tasa_mensual, -meses)) / tasa_mensual
    return cuota_mensual_uf * factor


def monto_credito_a_valor_propiedad_uf(
    monto_credito_uf: float, pie_porcentaje: float = PIE_REFERENCIAL
) -> float:
    if monto_credito_uf <= 0:
        return 0
    porcentaje_financiado = 1 - (pie_porcentaje / 100)
    if porcentaje_financiado <= 0:
        return monto_credito_uf
    return monto_credito_uf / porcentaje_financiado


def filtrar_propiedades(
    propiedades: list[dict],
    ciudad: str = "",
    tipologia: str = "",
    tipo: str = "",
    entrega: str = "",
    presupuesto_max_uf: float = 0,
    dormitorios_min: int = 0,
    banios_min: int = 0,
    superficie_min: float = 0,
    texto_libre: str = "",
) -> list[dict]:
    resultados = []
    for propiedad in propiedades:
        monto = a_float(propiedad.get("monto_estimado"))
        superficie = a_float(propiedad.get("superficie"))
        dormitorios = maximo_en_rango(propiedad.get("dormitorios"))
        banios = maximo_en_rango(propiedad.get("banios"))
        tipologias = " | ".join(propiedad.get("tipologia") or [])
        texto_indexable = " ".join(
            [
                str(propiedad.get("nombre") or ""),
                str(propiedad.get("condominio") or ""),
                str(propiedad.get("direccion") or ""),
                str(propiedad.get("ciudad") or ""),
                tipologias,
            ]
        )

        if ciudad and not coincide_texto(propiedad.get("ciudad", ""), ciudad):
            continue
        if tipologia and not coincide_texto(tipologias, tipologia):
            continue
        if tipo and not coincide_texto(propiedad.get("tipo", ""), tipo):
            continue
        if entrega and not coincide_texto(propiedad.get("entrega", ""), entrega):
            continue
        if presupuesto_max_uf and (monto is None or monto > presupuesto_max_uf):
            continue
        if dormitorios_min and (dormitorios is None or dormitorios < dormitorios_min):
            continue
        if banios_min and (banios is None or banios < banios_min):
            continue
        if superficie_min and (superficie is None or superficie < superficie_min):
            continue
        if texto_libre and not coincide_texto(texto_indexable, texto_libre):
            continue

        resultados.append(propiedad)

    resultados.sort(
        key=lambda item: (
            a_float(item.get("monto_estimado")) is None,
            a_float(item.get("monto_estimado")) or 0,
        )
    )
    return resultados


def formatear_propiedad(propiedad: dict) -> dict:
    return {
        "id": propiedad.get("id"),
        "nombre": propiedad.get("nombre"),
        "condominio": propiedad.get("condominio"),
        "tipo": propiedad.get("tipo"),
        "ciudad": propiedad.get("ciudad"),
        "direccion": propiedad.get("direccion"),
        "tipologia": propiedad.get("tipologia") or [],
        "dormitorios": propiedad.get("dormitorios"),
        "banios": propiedad.get("banios"),
        "superficie_m2": propiedad.get("superficie"),
        "m2_utiles": propiedad.get("m2_utiles"),
        "m2_terraza": propiedad.get("m2_terraza"),
        "entrega": propiedad.get("entrega"),
        "monto_estimado_uf": propiedad.get("monto_estimado"),
        "valor_cuota": propiedad.get("valor_cuota"),
        "bono": propiedad.get("bono_badge_text"),
        "estacionamiento": propiedad.get("estacionamiento"),
        "bodega": propiedad.get("bodega"),
        "foto": (propiedad.get("fotos") or [None])[0],
    }


def nombre_proyecto(propiedad: dict) -> str:
    return (
        propiedad.get("condominio")
        or propiedad.get("nombre")
        or f"Proyecto {propiedad.get('id', '')}".strip()
    )


def tipologias_unicas(propiedades: list[dict]) -> list[str]:
    tipologias = []
    vistas = set()
    for propiedad in propiedades:
        for tipologia in propiedad.get("tipologia") or []:
            clave = normalizar_texto(tipologia)
            if clave and clave not in vistas:
                vistas.add(clave)
                tipologias.append(tipologia)
    return tipologias


def formatear_rango(minimo, maximo, sufijo: str = "") -> str | None:
    def formatear_valor(valor):
        if isinstance(valor, float) and valor.is_integer():
            return str(int(valor))
        return str(valor)

    if minimo is None and maximo is None:
        return None
    if minimo is not None and maximo is not None:
        if minimo == maximo:
            return f"{formatear_valor(minimo)}{sufijo}"
        return f"{formatear_valor(minimo)} a {formatear_valor(maximo)}{sufijo}"
    valor = minimo if minimo is not None else maximo
    return f"{formatear_valor(valor)}{sufijo}"


def formatear_clp(valor: float | int | None) -> str | None:
    if valor is None:
        return None
    return f"${int(round(valor)):,}".replace(",", ".")


def elegir_tipologia_sugerida(
    tipologias: list[str], tipologia: str = "", dormitorios_min: int = 0
) -> str | None:
    if not tipologias:
        return None
    if tipologia:
        for item in tipologias:
            if coincide_texto(item, tipologia):
                return item
    if dormitorios_min:
        for item in tipologias:
            numeros = [int(valor) for valor in re.findall(r"\d+", item)]
            if numeros and max(numeros) >= dormitorios_min:
                return item
    return tipologias[0]


def construir_resumen_comercial(proyecto: dict) -> str:
    partes = [
        f'Proyecto "{proyecto["proyecto"]}" en {proyecto.get("ciudad") or "ubicacion no informada"}',
    ]
    if proyecto.get("rango_compra_uf"):
        partes.append(f"rango de compra aprox. {proyecto['rango_compra_uf']}")
    if proyecto.get("tipologia_sugerida"):
        partes.append(f"tipologia sugerida {proyecto['tipologia_sugerida']}")
    if proyecto.get("tipologias"):
        partes.append(
            "tipologias disponibles " + ", ".join(proyecto["tipologias"][:4])
        )
    if proyecto.get("entrega"):
        partes.append(f"entrega {proyecto['entrega']}")
    if proyecto.get("bono"):
        partes.append(str(proyecto["bono"]))
    return ". ".join(partes) + "."


def construir_respuesta_capacidad(payload: dict) -> str:
    ingreso = formatear_clp(payload.get("ingreso_mensual_clp"))
    capacidad = payload.get("capacidad_estimativa", {})
    cuota = formatear_clp(capacidad.get("cuota_maxima_clp"))
    valor_max = formatear_rango(
        capacidad.get("valor_propiedad_max_estimado_uf"),
        capacidad.get("valor_propiedad_max_estimado_uf"),
        " UF",
    )
    proyectos = payload.get("proyectos_sugeridos", [])[:3]

    partes = [
        (
            f"Con una renta de {ingreso} mensuales, hoy podrias mirar propiedades "
            f"de hasta {valor_max} aprox., considerando una cuota referencial de {cuota}."
        )
    ]

    if proyectos:
        recomendaciones = " ".join(
            [
                f"Te recomendaria revisar {proyecto['resumen_comercial']}"
                for proyecto in proyectos
            ]
        )
        partes.append(recomendaciones)

    partes.append(
        "Esto es una referencia inicial; la aprobacion final depende de la evaluacion comercial y del pie disponible."
    )
    return " ".join(partes)


def resumir_proyecto(
    nombre: str,
    propiedades: list[dict],
    tipologia_preferida: str = "",
    dormitorios_min: int = 0,
) -> dict:
    precios = [
        a_float(propiedad.get("monto_estimado"))
        for propiedad in propiedades
        if a_float(propiedad.get("monto_estimado")) is not None
    ]
    superficies = [
        a_float(propiedad.get("superficie"))
        for propiedad in propiedades
        if a_float(propiedad.get("superficie")) is not None
    ]
    dormitorios_minimos = [
        minimo_en_rango(propiedad.get("dormitorios"))
        for propiedad in propiedades
        if minimo_en_rango(propiedad.get("dormitorios")) is not None
    ]
    dormitorios_max = [
        maximo_en_rango(propiedad.get("dormitorios"))
        for propiedad in propiedades
        if maximo_en_rango(propiedad.get("dormitorios")) is not None
    ]

    muestra = propiedades[0]
    tipologias = tipologias_unicas(propiedades)
    precio_desde = min(precios) if precios else None
    precio_hasta = max(precios) if precios else None
    superficie_desde = min(superficies) if superficies else None
    superficie_hasta = max(superficies) if superficies else None
    dormitorios_desde = min(dormitorios_minimos) if dormitorios_minimos else None
    dormitorios_hasta = max(dormitorios_max) if dormitorios_max else None
    return {
        "proyecto": nombre,
        "tipo": muestra.get("tipo"),
        "ciudad": muestra.get("ciudad"),
        "direccion": muestra.get("direccion"),
        "entrega": muestra.get("entrega"),
        "bono": muestra.get("bono_badge_text"),
        "precio_desde_uf": precio_desde,
        "precio_hasta_uf": precio_hasta,
        "rango_compra_uf": formatear_rango(precio_desde, precio_hasta, " UF"),
        "superficie_desde_m2": superficie_desde,
        "superficie_hasta_m2": superficie_hasta,
        "rango_superficie_m2": formatear_rango(superficie_desde, superficie_hasta, " m2"),
        "dormitorios_desde": dormitorios_desde,
        "dormitorios_hasta": dormitorios_hasta,
        "rango_dormitorios": formatear_rango(dormitorios_desde, dormitorios_hasta, "D"),
        "tipologias": tipologias,
        "tipologia_sugerida": elegir_tipologia_sugerida(
            tipologias,
            tipologia=tipologia_preferida,
            dormitorios_min=dormitorios_min,
        ),
        "cantidad_unidades": len(propiedades),
        "ejemplos": [formatear_propiedad(propiedad) for propiedad in propiedades[:3]],
    }


def puntuar_proyecto(
    proyecto: dict,
    ciudad: str = "",
    tipologia: str = "",
    tipo: str = "",
    entrega: str = "",
    presupuesto_max_uf: float = 0,
    dormitorios_min: int = 0,
    banios_min: int = 0,
    superficie_min: float = 0,
    texto_libre: str = "",
) -> tuple[int, list[str]]:
    puntaje = 0
    motivos = []

    if ciudad and coincide_texto(proyecto.get("ciudad", ""), ciudad):
        puntaje += 3
        motivos.append(f"esta en {proyecto.get('ciudad')}")
    if tipo and coincide_texto(proyecto.get("tipo", ""), tipo):
        puntaje += 2
        motivos.append(f"es de tipo {proyecto.get('tipo')}")
    if entrega and coincide_texto(proyecto.get("entrega", ""), entrega):
        puntaje += 2
        motivos.append(f"tiene {proyecto.get('entrega')}")
    if presupuesto_max_uf and proyecto.get("precio_desde_uf") is not None:
        if proyecto["precio_desde_uf"] <= presupuesto_max_uf:
            puntaje += 4
            motivos.append(f"parte desde {proyecto['precio_desde_uf']} UF")
    if dormitorios_min and proyecto.get("dormitorios_hasta") is not None:
        if proyecto["dormitorios_hasta"] >= dormitorios_min:
            puntaje += 3
            motivos.append(f"alcanza hasta {proyecto['dormitorios_hasta']} dormitorios")
    if superficie_min and proyecto.get("superficie_hasta_m2") is not None:
        if proyecto["superficie_hasta_m2"] >= superficie_min:
            puntaje += 2
            motivos.append(
                f"ofrece hasta {proyecto['superficie_hasta_m2']} m2 aproximados"
            )
    if tipologia:
        tipologias = " | ".join(proyecto.get("tipologias") or [])
        if coincide_texto(tipologias, tipologia):
            puntaje += 3
            motivos.append(f"incluye tipologias {tipologias}")
    if texto_libre:
        texto = " ".join(
            [
                str(proyecto.get("proyecto") or ""),
                str(proyecto.get("direccion") or ""),
                str(proyecto.get("ciudad") or ""),
                " | ".join(proyecto.get("tipologias") or []),
            ]
        )
        if coincide_texto(texto, texto_libre):
            puntaje += 2
            motivos.append("coincide con la busqueda libre")
    if proyecto.get("bono"):
        puntaje += 1
        motivos.append(proyecto["bono"])
    if banios_min:
        banios_proyecto = [
            maximo_en_rango(propiedad.get("banios"))
            for propiedad in proyecto.get("ejemplos", [])
            if maximo_en_rango(propiedad.get("banios")) is not None
        ]
        if banios_proyecto and max(banios_proyecto) >= banios_min:
            puntaje += 1
            motivos.append(f"tiene opciones de hasta {max(banios_proyecto)} banos")

    return puntaje, motivos[:4]


def coincide_texto(valor: str, filtro: str) -> bool:
    if not filtro:
        return True
    return normalizar_texto(filtro) in normalizar_texto(valor)


@tool
def buscar_departamentos(
    ciudad: str = "",
    tipologia: str = "",
    tipo: str = "",
    entrega: str = "",
    presupuesto_max_uf: float = 0,
    dormitorios_min: int = 0,
    banios_min: int = 0,
    superficie_min: float = 0,
    texto_libre: str = "",
) -> str:
    """Busca departamentos usando la API inmobiliaria de Inmotech.

    Usa esta herramienta siempre que el usuario pida opciones de departamentos,
    propiedades o proyectos.

    Args:
        ciudad: Ciudad o comuna a filtrar, por ejemplo Santiago, Nunoa o La Florida.
        tipologia: Tipologia o formato, por ejemplo Estudio, 1D-1B, 2D2B o Home Studio.
        tipo: Tipo de propiedad, por ejemplo SemiNuevo o Proyecto.
        entrega: Estado de entrega, por ejemplo Entrega Inmediata o Entrega Futura.
        presupuesto_max_uf: Maximo presupuesto en UF. Deja 0 si no aplica.
        dormitorios_min: Minimo de dormitorios. Deja 0 si no aplica.
        banios_min: Minimo de banos. Deja 0 si no aplica.
        superficie_min: Minimo de superficie total en m2. Deja 0 si no aplica.
        texto_libre: Texto para buscar por nombre, condominio o direccion.
    """
    try:
        propiedades = cargar_propiedades()
    except HTTPError as error:
        return f"No pude consultar la API inmobiliaria. HTTP {error.code}."
    except URLError as error:
        return f"No pude conectar con la API inmobiliaria: {error.reason}."
    except Exception as error:
        return f"Ocurrio un error consultando la API inmobiliaria: {error}"

    presupuesto_normalizado, nota_presupuesto = normalizar_presupuesto(
        presupuesto_max_uf
    )

    resultados = filtrar_propiedades(
        propiedades=propiedades,
        ciudad=ciudad,
        tipologia=tipologia,
        tipo=tipo,
        entrega=entrega,
        presupuesto_max_uf=presupuesto_normalizado,
        dormitorios_min=dormitorios_min,
        banios_min=banios_min,
        superficie_min=superficie_min,
        texto_libre=texto_libre,
    )

    if not resultados:
        return (
            "No encontre departamentos con esos criterios en la API de Inmotech. "
            "Prueba con otra ciudad, tipologia o un presupuesto mas amplio."
        )

    payload = [formatear_propiedad(item) for item in resultados[:8]]
    return json.dumps(
        {
            "total_resultados": len(resultados),
            "fuente": API_URL,
            "nota_presupuesto": nota_presupuesto,
            "resultados": payload,
        },
        ensure_ascii=False,
        indent=2,
    )


@tool
def sugerir_proyectos(
    ciudad: str = "",
    tipologia: str = "",
    tipo: str = "",
    entrega: str = "",
    presupuesto_max_uf: float = 0,
    dormitorios_min: int = 0,
    banios_min: int = 0,
    superficie_min: float = 0,
    texto_libre: str = "",
) -> str:
    """Sugiere proyectos concretos de la API segun los datos del cliente.

    Usa esta herramienta cuando el usuario pida recomendacion, sugerencias o
    mejores opciones en vez de una lista plana de unidades.
    """
    try:
        propiedades = cargar_propiedades()
    except HTTPError as error:
        return f"No pude consultar la API inmobiliaria. HTTP {error.code}."
    except URLError as error:
        return f"No pude conectar con la API inmobiliaria: {error.reason}."
    except Exception as error:
        return f"Ocurrio un error consultando la API inmobiliaria: {error}"

    presupuesto_normalizado, nota_presupuesto = normalizar_presupuesto(
        presupuesto_max_uf
    )

    filtradas = filtrar_propiedades(
        propiedades=propiedades,
        ciudad=ciudad,
        tipologia=tipologia,
        tipo=tipo,
        entrega=entrega,
        presupuesto_max_uf=presupuesto_normalizado,
        dormitorios_min=dormitorios_min,
        banios_min=banios_min,
        superficie_min=superficie_min,
        texto_libre=texto_libre,
    )

    if not filtradas:
        return (
            "No encontre proyectos para sugerir con esos criterios. "
            "Prueba ampliando presupuesto, ciudad o tipologia."
        )

    proyectos = {}
    for propiedad in filtradas:
        clave = " | ".join(
            [
                normalizar_texto(nombre_proyecto(propiedad)),
                normalizar_texto(propiedad.get("ciudad") or ""),
                normalizar_texto(propiedad.get("tipo") or ""),
            ]
        )
        proyectos.setdefault(clave, []).append(propiedad)

    recomendados = []
    for propiedades_proyecto in proyectos.values():
        resumen = resumir_proyecto(
            nombre_proyecto(propiedades_proyecto[0]),
            propiedades_proyecto,
            tipologia_preferida=tipologia,
            dormitorios_min=dormitorios_min,
        )
        puntaje, motivos = puntuar_proyecto(
            resumen,
            ciudad=ciudad,
            tipologia=tipologia,
            tipo=tipo,
            entrega=entrega,
            presupuesto_max_uf=presupuesto_max_uf,
            dormitorios_min=dormitorios_min,
            banios_min=banios_min,
            superficie_min=superficie_min,
            texto_libre=texto_libre,
        )
        resumen["puntaje_ajuste"] = puntaje
        resumen["motivos"] = motivos
        resumen["resumen_comercial"] = construir_resumen_comercial(resumen)
        recomendados.append(resumen)

    recomendados.sort(
        key=lambda proyecto: (
            -proyecto["puntaje_ajuste"],
            proyecto.get("precio_desde_uf") is None,
            proyecto.get("precio_desde_uf") or 0,
        )
    )

    return json.dumps(
        {
            "fuente": API_URL,
            "criterios": {
                "ciudad": ciudad,
                "tipologia": tipologia,
                "tipo": tipo,
                "entrega": entrega,
                "presupuesto_max_uf": presupuesto_normalizado,
                "dormitorios_min": dormitorios_min,
                "banios_min": banios_min,
                "superficie_min": superficie_min,
                "texto_libre": texto_libre,
            },
            "nota_presupuesto": nota_presupuesto,
            "proyectos_sugeridos": recomendados[:5],
        },
        ensure_ascii=False,
        indent=2,
    )


@tool
def estimar_capacidad_compra(
    ingreso_mensual_clp: float,
    ciudad: str = "",
    tipologia: str = "",
    dormitorios_min: int = 0,
) -> str:
    """Estima que propiedad puede comprar el cliente segun su ingreso mensual.

    Usa esta herramienta cuando el usuario hable de sueldo, renta, ingreso o
    capacidad de compra en CLP.
    """
    if ingreso_mensual_clp <= 0:
        return "Necesito un ingreso mensual mayor a 0 para estimar capacidad de compra."

    esfuerzo_maximo_porcentaje = ESFUERZO_MAXIMO_REFERENCIAL
    pie_porcentaje = PIE_REFERENCIAL
    tasa_anual = TASA_ANUAL_REFERENCIAL
    plazo_anos = PLAZO_ANOS_REFERENCIAL

    cuota_maxima_clp = ingreso_mensual_clp * (ESFUERZO_MAXIMO_REFERENCIAL / 100)
    cuota_maxima_uf = round(cuota_maxima_clp / CLP_POR_UF_REFERENCIA, 2)
    monto_credito_uf = round(
        cuota_uf_a_monto_credito_uf(
            cuota_maxima_uf,
            tasa_anual=TASA_ANUAL_REFERENCIAL,
            plazo_anos=PLAZO_ANOS_REFERENCIAL,
        ),
        2,
    )
    valor_propiedad_max_uf = round(
        monto_credito_a_valor_propiedad_uf(
            monto_credito_uf,
            pie_porcentaje=PIE_REFERENCIAL,
        ),
        2,
    )

    try:
        propiedades = cargar_propiedades()
    except HTTPError as error:
        return f"No pude consultar la API inmobiliaria. HTTP {error.code}."
    except URLError as error:
        return f"No pude conectar con la API inmobiliaria: {error.reason}."
    except Exception as error:
        return f"Ocurrio un error consultando la API inmobiliaria: {error}"

    filtradas = filtrar_propiedades(
        propiedades=propiedades,
        ciudad=ciudad,
        tipologia=tipologia,
        tipo="",
        entrega="",
        presupuesto_max_uf=valor_propiedad_max_uf,
        dormitorios_min=dormitorios_min,
        banios_min=0,
        superficie_min=0,
        texto_libre="",
    )

    proyectos = {}
    for propiedad in filtradas:
        clave = " | ".join(
            [
                normalizar_texto(nombre_proyecto(propiedad)),
                normalizar_texto(propiedad.get("ciudad") or ""),
                normalizar_texto(propiedad.get("tipo") or ""),
            ]
        )
        proyectos.setdefault(clave, []).append(propiedad)

    recomendados = []
    for propiedades_proyecto in proyectos.values():
        resumen = resumir_proyecto(
            nombre_proyecto(propiedades_proyecto[0]),
            propiedades_proyecto,
            tipologia_preferida=tipologia,
            dormitorios_min=dormitorios_min,
        )
        puntaje, motivos = puntuar_proyecto(
            resumen,
            ciudad=ciudad,
            tipologia=tipologia,
            tipo="",
            entrega="",
            presupuesto_max_uf=valor_propiedad_max_uf,
            dormitorios_min=dormitorios_min,
            banios_min=0,
            superficie_min=0,
            texto_libre="",
        )
        resumen["puntaje_ajuste"] = puntaje
        resumen["motivos"] = motivos
        resumen["resumen_comercial"] = construir_resumen_comercial(resumen)
        recomendados.append(resumen)

    recomendados.sort(
        key=lambda proyecto: (
            -proyecto["puntaje_ajuste"],
            proyecto.get("precio_desde_uf") is None,
            proyecto.get("precio_desde_uf") or 0,
        )
    )

    payload = {
        "fuente": API_URL,
        "ingreso_mensual_clp": ingreso_mensual_clp,
        "supuestos": {
            "esfuerzo_maximo_porcentaje": ESFUERZO_MAXIMO_REFERENCIAL,
            "pie_porcentaje": PIE_REFERENCIAL,
            "tasa_anual": TASA_ANUAL_REFERENCIAL,
            "plazo_anos": PLAZO_ANOS_REFERENCIAL,
            "uf_referencial_clp": CLP_POR_UF_REFERENCIA,
        },
        "capacidad_estimativa": {
            "cuota_maxima_clp": round(cuota_maxima_clp, 0),
            "cuota_maxima_uf": cuota_maxima_uf,
            "monto_credito_estimado_uf": monto_credito_uf,
            "valor_propiedad_max_estimado_uf": valor_propiedad_max_uf,
        },
        "nota": (
            "Esta es una estimacion referencial basada en esfuerzo de pago, "
            "pie, tasa y plazo. La aprobacion final depende de evaluacion comercial."
        ),
        "proyectos_sugeridos": recomendados[:5],
    }
    payload["respuesta_asesor"] = construir_respuesta_capacidad(payload)

    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


@tool
def resumen_mercado(ciudad: str = "", tipo: str = "") -> str:
    """Resume la oferta inmobiliaria disponible en la API de Inmotech.

    Args:
        ciudad: Ciudad o comuna a filtrar. Deja vacio para todo el inventario.
        tipo: Tipo de propiedad, por ejemplo SemiNuevo o Proyecto.
    """
    try:
        propiedades = cargar_propiedades()
    except HTTPError as error:
        return f"No pude consultar la API inmobiliaria. HTTP {error.code}."
    except URLError as error:
        return f"No pude conectar con la API inmobiliaria: {error.reason}."
    except Exception as error:
        return f"Ocurrio un error consultando la API inmobiliaria: {error}"

    filtradas = []
    for propiedad in propiedades:
        if ciudad and not coincide_texto(propiedad.get("ciudad", ""), ciudad):
            continue
        if tipo and not coincide_texto(propiedad.get("tipo", ""), tipo):
            continue
        filtradas.append(propiedad)

    if not filtradas:
        return "No encontre propiedades para generar un resumen con esos filtros."

    montos = [a_float(item.get("monto_estimado")) for item in filtradas]
    montos = [item for item in montos if item is not None]

    ciudades = {}
    for item in filtradas:
        clave = item.get("ciudad") or "Sin ciudad"
        ciudades[clave] = ciudades.get(clave, 0) + 1

    top_ciudades = sorted(ciudades.items(), key=lambda item: item[1], reverse=True)[:5]

    return json.dumps(
        {
            "fuente": API_URL,
            "total_propiedades": len(filtradas),
            "precio_min_uf": min(montos) if montos else None,
            "precio_max_uf": max(montos) if montos else None,
            "precio_promedio_uf": round(sum(montos) / len(montos), 2) if montos else None,
            "ciudades_con_mas_oferta": [
                {"ciudad": ciudad_nombre, "cantidad": cantidad}
                for ciudad_nombre, cantidad in top_ciudades
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


modelo = OpenAIResponsesModel(
    model_id=OPENAI_MODEL,
)


_after_tool = False


def callback_handler(**kwargs):
    global _after_tool
    if "reasoningText" in kwargs:
        print(f"Pensando: {kwargs['reasoningText']}", end="", flush=True)
    if "data" in kwargs:
        if _after_tool:
            print("\n")
            _after_tool = False
        print(kwargs["data"], end="", flush=True)
    if "current_tool_use" in kwargs:
        _after_tool = True
        herramienta = kwargs["current_tool_use"]
        if herramienta.get("name"):
            print(f"\n\nHerramienta: {herramienta['name']}")
        if herramienta.get("input"):
            print(f"Parametros: {herramienta['input']}")


session_manager = FileSessionManager(
    # Se inicia una sesion nueva para no mezclar el historial de Ollama con OpenAI.
    session_id="agente_inmobiliario_openai_v1",
    storage_dir=str(Path("./sessions")),
)

agente = Agent(
    model=modelo,
    callback_handler=callback_handler,
    system_prompt=(
        "Eres un asesor inmobiliario experto en departamentos en Chile. "
        "Hablas como un ejecutivo comercial cercano, claro y profesional, "
        "orientado a ayudar a un cliente real a tomar una buena decision. "
        "Tu base de conocimiento operativa es la API de Inmotech en tiempo real. "
        "Tu trabajo es ayudar al usuario a encontrar departamentos segun presupuesto, "
        "ubicacion, tipologia, cantidad de dormitorios, banos y fecha de entrega.\n\n"
        "Reglas:\n"
        "1. Siempre responde en espanol.\n"
        "2. Si el usuario habla de sueldo, renta, ingreso mensual o pregunta que puede comprar con lo que gana, usa primero estimar_capacidad_compra.\n"
        "3. Cuando el usuario pida una recomendacion, sugerencia o mejores opciones, usa primero sugerir_proyectos.\n"
        "4. Usa buscar_departamentos cuando el usuario pida opciones concretas o quiera ver unidades.\n"
        "5. Usa resumen_mercado solo cuando el usuario pregunte por panorama, rangos de precios o stock general.\n"
        "6. Nunca uses resumen_mercado para responder preguntas de capacidad de compra basadas en ingreso.\n"
        "7. Basa tus respuestas solo en los datos entregados por las herramientas; no inventes proyectos ni precios.\n"
        "8. Si faltan criterios, propone opciones utiles con los datos disponibles y sugiere como refinar la busqueda.\n"
        "9. Prioriza respuestas claras, comerciales y breves, maximo 3 parrafos.\n"
        "10. Cuando sugieras proyectos, recomienda 2 a 4 proyectos concretos de la API y explica por que encajan con los criterios del usuario.\n"
        "11. Si el usuario pide recomendacion, nunca respondas solo con un resumen general del mercado: debes mencionar nombres de proyectos reales del resultado.\n"
        "12. Si detectas que el usuario escribio presupuesto en pesos chilenos, explica brevemente que la API trabaja en UF y usa la interpretacion referencial entregada por la herramienta.\n"
        "13. Cuando respondas una pregunta de ingreso mensual, indica la capacidad estimada en UF, la cuota referencial y luego recomienda proyectos reales.\n"
        "14. Cuando sugieras proyectos, menciona explicitamente el rango de compra aproximado en UF, la tipologia sugerida y las tipologias disponibles del proyecto.\n"
        "15. Si la herramienta sugerir_proyectos o estimar_capacidad_compra entrega un campo resumen_comercial, reutilizalo de forma casi literal para no omitir datos clave.\n"
        "16. Nunca abrevies ni recortes el nombre del proyecto; mencionalo exactamente como venga en la herramienta.\n"
        "17. No inventes filtros adicionales para capacidad de compra: si el usuario solo menciona ingreso, no agregues por tu cuenta ciudad, tipo, entrega, tipologia ni supuestos financieros.\n"
        "18. Si estimar_capacidad_compra entrega proyectos_sugeridos, no cierres con una pregunta de seguimiento: debes recomendar al menos 2 proyectos concretos en la misma respuesta.\n"
        "19. Si estimar_capacidad_compra entrega un campo respuesta_asesor, usalo como base principal para responder y no recalcules ni reformatees el monto por tu cuenta.\n"
        "20. Cuando recomiendes propiedades, menciona ciudad, direccion, tipologia, superficie, dormitorios, banos, UF estimada, entrega y bono si existe.\n"
        "21. Habla como asesor comercial, no como informe tecnico: evita encabezados frios como 'Resumen del resultado' o 'Notas'.\n"
        "22. Usa un tono natural, empatico y orientado al cliente, por ejemplo: 'Con esa renta, hoy podrias mirar opciones en este rango...' o 'Las alternativas que mejor te calzan son...'.\n"
        "23. Evita listas excesivamente rigidas o lenguaje robotico; suena conversacional pero preciso.\n"
        "24. Si hay advertencias o supuestos, mencionalos de forma breve y amable al final, sin sonar legalista.\n"
        "25. Si recuerdas preferencias previas del usuario, usalas para personalizar la recomendacion solo cuando el usuario vuelva a pedirlas de forma consistente."
    ),
    tools=[
        buscar_departamentos,
        sugerir_proyectos,
        estimar_capacidad_compra,
        resumen_mercado,
    ],
    session_manager=session_manager,
)


def ejecutar_consulta_agente(pregunta: str) -> None:
    """Ejecuta una consulta que requiere el modelo de OpenAI."""
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "Falta OPENAI_API_KEY. Agregala al entorno o a un archivo .env."
        )

    try:
        agente(pregunta)
    except AuthenticationError:
        raise SystemExit(
            "OPENAI_API_KEY no es valida. Reemplazala por una clave activa de OpenAI."
        )
    except RateLimitError:
        raise SystemExit(
            "OpenAI rechazo la solicitud por limite de uso o facturacion. Intenta mas tarde."
        )
    except APIConnectionError:
        raise SystemExit("No pude conectar con la API de OpenAI. Revisa tu conexion.")


if __name__ == "__main__":
    pregunta = input("Prompt: ")
    print("\nAgente: ", end="", flush=True)
    if es_consulta_capacidad_compra(pregunta):
        monto = extraer_monto_clp(pregunta)
        if monto:
            respuesta = estimar_capacidad_compra(ingreso_mensual_clp=monto)
            try:
                payload = json.loads(respuesta)
                print(payload.get("respuesta_asesor", respuesta), end="", flush=True)
            except json.JSONDecodeError:
                print(respuesta, end="", flush=True)
        else:
            ejecutar_consulta_agente(pregunta)
    else:
        ejecutar_consulta_agente(pregunta)
    print("\n")
