from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from pathlib import PurePosixPath
import re
from urllib.parse import urlparse, urlunparse
from uuid import UUID


MAX_PORTAL_IMAGE_BYTES = 4 * 1024 * 1024
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LOCAL_COVER_PATTERN = re.compile(
    r"^/portal-assets/books/[A-Za-z0-9][A-Za-z0-9._-]*\.(?:webp|png|jpe?g)$",
    re.IGNORECASE,
)
_DATA_URL_PATTERN = re.compile(
    r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\r\n]+)$",
    re.IGNORECASE,
)
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


DEFAULT_PORTAL_PAGE = {
    "meta": {
        "title": "Formação do Investidor — Conhecimento para decidir melhor",
        "description": (
            "Formação do Investidor: plataforma de análises, backtests e uma biblioteca "
            "para decisões financeiras mais conscientes."
        ),
    },
    "brand": {"monogram": "FI", "primary": "Formação", "secondary": "do Investidor"},
    "navigation": {
        "skip": "Ir para o conteúdo",
        "books": "Livros",
        "purpose": "Nossa proposta",
        "platform": "Acessar plataforma",
        "admin": "Ajustes da página",
    },
    "hero": {
        "eyebrow": "Conhecimento, método e autonomia",
        "title": "Invista com mais clareza em cada decisão.",
        "intro": (
            "Uma formação que conecta fundamentos, análise técnica, estratégia e "
            "comportamento — acompanhada por uma plataforma criada para transformar "
            "dados em decisões consistentes."
        ),
        "primary_action": "Entrar na Plataforma de Investimentos",
        "secondary_action": "Conhecer os livros",
        "proof": ["Fundamentos", "Análise técnica", "Backtests", "Psicologia"],
        "collection_title": "Uma jornada completa",
        "collection_subtitle": "Do primeiro investimento ao sistema próprio.",
    },
    "purpose": {
        "eyebrow": "Formação aplicada",
        "title": "Aprender, analisar e agir com método.",
        "items": [
            {
                "number": "01",
                "title": "Entenda o valor",
                "body": "Construa uma base sólida para avaliar ativos, risco, preço e qualidade antes de investir.",
            },
            {
                "number": "02",
                "title": "Teste a estratégia",
                "body": "Use evidências históricas e filtros técnicos para separar convicção de simples intuição.",
            },
            {
                "number": "03",
                "title": "Decida com disciplina",
                "body": "Organize carteira, processo e comportamento para atravessar diferentes ciclos de mercado.",
            },
        ],
    },
    "books": {
        "eyebrow": "Biblioteca Formação do Investidor",
        "title": "Sete obras. Uma mesma busca por autonomia.",
        "intro": (
            "Conteúdo progressivo para quem quer compreender investimentos, estruturar "
            "processos e transformar conhecimento em ação."
        ),
        "primary_title": "Coleção principal",
        "primary_subtitle": "Do zero ao Trade System vencedor",
        "complementary_title": "Patrimônio, estratégia e transformação",
        "complementary_subtitle": "Obras complementares",
        "details_label": "Sobre esta obra",
    },
    "platform": {
        "eyebrow": "Plataforma de Investimentos",
        "title": "Conhecimento encontra dados quando chega a hora de decidir.",
        "body": (
            "Consulte mercados, filtre ativos, organize sua carteira e valide estratégias "
            "por meio de backtests em um ambiente único."
        ),
        "button": "Acessar a plataforma",
    },
    "footer": {
        "disclaimer": (
            "Conteúdo educacional. Informações e ferramentas não constituem "
            "recomendação de investimento."
        ),
        "platform": "Plataforma de Investimentos",
    },
}


DEFAULT_PORTAL_BOOKS = (
    {
        "slug": "formacao-investidor-fundamentos",
        "collection": "primary",
        "kicker": "Formação do Investidor • Volume 1",
        "title": "Fundamentos",
        "summary": "Da organização financeira às classes de ativos, preço versus valor, tributação e construção de uma carteira resiliente.",
        "description": "Um guia para criar bases sólidas, compreender o ambiente econômico e tomar as primeiras decisões com segurança e visão de longo prazo.",
        "alt_text": "Capa de Formação do Investidor — Fundamentos",
        "fallback_cover_path": "/portal-assets/books/formacao-investidor-fundamentos.webp",
        "position": 10,
        "hero_position": 2,
        "is_published": True,
        "sales_links": [],
    },
    {
        "slug": "formacao-investidor-analise-tecnica",
        "collection": "primary",
        "kicker": "Formação do Investidor • Volume 2",
        "title": "Análise Técnica",
        "summary": "Gráficos, price action, médias, RSI, MACD, Bollinger, volume, gestão de risco e construção de um processo tático.",
        "description": "Para quem deseja interpretar o comportamento dos preços, reconhecer contextos e usar indicadores sem abandonar método e disciplina.",
        "alt_text": "Capa de Formação do Investidor — Análise Técnica",
        "fallback_cover_path": "/portal-assets/books/formacao-investidor-analise-tecnica.webp",
        "position": 20,
        "hero_position": 1,
        "is_published": True,
        "sales_links": [],
    },
    {
        "slug": "formacao-investidor-trade-system-psicologia",
        "collection": "primary",
        "kicker": "Formação do Investidor • Volume 3",
        "title": "Trade System e Psicologia do Investidor",
        "summary": "Comportamento, vieses, risco, consistência e a engenharia de um sistema de investimento replicável.",
        "description": "Uma ponte entre a estratégia e sua execução no mundo real, com foco no controle emocional e na tomada de decisão consistente.",
        "alt_text": "Capa de Formação do Investidor — Trade System e Psicologia do Investidor",
        "fallback_cover_path": "/portal-assets/books/formacao-investidor-trade-system-psicologia.webp",
        "position": 30,
        "hero_position": 3,
        "is_published": True,
        "sales_links": [],
    },
    {
        "slug": "jogo-dos-imoveis",
        "collection": "complementary",
        "kicker": "Mercado imobiliário",
        "title": "O Jogo dos Imóveis",
        "summary": "Como comprar bem, multiplicar patrimônio e construir renda no mercado imobiliário brasileiro — do primeiro imóvel ao portfólio completo.",
        "description": "Ciclos, diligência jurídica, financiamento, consórcio, leilões, locação e FIIs reunidos em uma visão prática de construção patrimonial.",
        "alt_text": "Capa de O Jogo dos Imóveis",
        "fallback_cover_path": "/portal-assets/books/jogo-dos-imoveis.webp",
        "position": 40,
        "hero_position": None,
        "is_published": True,
        "sales_links": [],
    },
    {
        "slug": "engenharia-trade-system",
        "collection": "complementary",
        "kicker": "Estratégia quantitativa",
        "title": "A Engenharia do Trade System",
        "summary": "Do Backtest ao Capital Real.",
        "description": "Validação, Monte Carlo, walk-forward, risco de ruína, dimensionamento e fricções reais para levar uma estratégia além do resultado histórico.",
        "alt_text": "Capa de A Engenharia do Trade System",
        "fallback_cover_path": "/portal-assets/books/engenharia-trade-system.webp",
        "position": 50,
        "hero_position": None,
        "is_published": True,
        "sales_links": [],
    },
    {
        "slug": "metodo-agir",
        "collection": "complementary",
        "kicker": "Mudança comportamental",
        "title": "Método A.G.I.R.",
        "summary": "A ciência prática para transformar micro-ações diárias em resultados exponenciais.",
        "description": "Um sistema de ação mínima, gatilhos, indicadores e redução de atrito para construir hábitos sustentáveis e retomar o caminho após recaídas.",
        "alt_text": "Capa de Método A.G.I.R.",
        "fallback_cover_path": "/portal-assets/books/metodo-agir.webp",
        "position": 60,
        "hero_position": None,
        "is_published": True,
        "sales_links": [],
    },
    {
        "slug": "caos-criativo",
        "collection": "complementary",
        "kicker": "Filosofia e individuação",
        "title": "O Caos Criativo",
        "summary": "A jornada da individuação além do eterno retorno.",
        "description": "Uma investigação sobre sentido, sofrimento e transformação que aproxima Nietzsche, Jung e Dostoiévski da experiência contemporânea.",
        "alt_text": "Capa de O Caos Criativo",
        "fallback_cover_path": "/portal-assets/books/caos-criativo.webp",
        "position": 70,
        "hero_position": None,
        "is_published": True,
        "sales_links": [],
    },
)


_TEXT_LIMITS = {
    "meta.title": 180,
    "meta.description": 500,
    "hero.title": 240,
    "hero.intro": 1200,
    "platform.title": 300,
    "platform.body": 1200,
    "footer.disclaimer": 1000,
    "purpose.items.*.body": 800,
}


def _text(value, *, field: str, required: bool = True, maximum: int | None = None) -> str:
    clean = str(value or "").strip()
    if required and not clean:
        raise ValueError(f"portal_text_required:{field}")
    limit = maximum or _TEXT_LIMITS.get(field, 500)
    if len(clean) > limit:
        raise ValueError(f"portal_text_too_long:{field}")
    if _CONTROL_PATTERN.search(clean):
        raise ValueError(f"portal_text_control_character:{field}")
    if "<" in clean or ">" in clean:
        raise ValueError(f"portal_text_html_not_allowed:{field}")
    return clean


def _merge_known(target: dict, patch: dict, *, path: str = "") -> dict:
    if not isinstance(patch, dict):
        raise ValueError(f"portal_content_object_required:{path or 'root'}")
    for key, value in patch.items():
        field = f"{path}.{key}" if path else key
        if key not in target:
            raise ValueError(f"portal_content_unknown_field:{field}")
        if isinstance(target[key], dict):
            target[key] = _merge_known(deepcopy(target[key]), value, path=field)
        else:
            target[key] = deepcopy(value)
    return target


def validate_portal_page(content: dict) -> dict:
    """Validate the complete fixed page schema and return a detached clean copy."""
    merged = _merge_known(deepcopy(DEFAULT_PORTAL_PAGE), content)
    for section, values in merged.items():
        if not isinstance(values, dict):
            raise ValueError(f"portal_content_object_required:{section}")
        for key, value in list(values.items()):
            field = f"{section}.{key}"
            if field == "hero.proof":
                if not isinstance(value, list) or not 1 <= len(value) <= 8:
                    raise ValueError("portal_proof_items_invalid")
                values[key] = [_text(item, field="hero.proof", maximum=80) for item in value]
            elif field == "purpose.items":
                if not isinstance(value, list) or not 1 <= len(value) <= 6:
                    raise ValueError("portal_purpose_items_invalid")
                cleaned_items = []
                for item in value:
                    if not isinstance(item, dict) or set(item) != {"number", "title", "body"}:
                        raise ValueError("portal_purpose_item_invalid")
                    cleaned_items.append({
                        "number": _text(item["number"], field="purpose.items.*.number", maximum=12),
                        "title": _text(item["title"], field="purpose.items.*.title", maximum=160),
                        "body": _text(item["body"], field="purpose.items.*.body"),
                    })
                values[key] = cleaned_items
            elif isinstance(value, str):
                values[key] = _text(value, field=field)
            else:
                raise ValueError(f"portal_content_text_required:{field}")
    return merged


def merge_portal_page(current: dict | None, patch: dict) -> dict:
    """Merge a partial administrative edit without accepting arbitrary fields."""
    base = validate_portal_page(current or DEFAULT_PORTAL_PAGE)
    return validate_portal_page(_merge_known(base, patch))


def normalize_https_url(value: object, *, field: str = "url") -> str:
    clean = str(value or "").strip()
    if not clean or len(clean) > 1000:
        raise ValueError(f"portal_https_url_invalid:{field}")
    parsed = urlparse(clean)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"portal_https_url_invalid:{field}")
    if parsed.fragment and len(parsed.fragment) > 200:
        raise ValueError(f"portal_https_url_invalid:{field}")
    return urlunparse(parsed._replace(scheme="https"))


def normalize_sales_links(values: object) -> list[dict]:
    supplied = [] if values is None else values
    if not isinstance(supplied, (list, tuple)) or len(supplied) > 3:
        raise ValueError("portal_sales_link_limit")
    result, seen = [], set()
    for position, item in enumerate(supplied, start=1):
        if not isinstance(item, dict) or set(item) - {"label", "url", "position"}:
            raise ValueError("portal_sales_link_invalid")
        label = _text(item.get("label"), field="sales_link.label", maximum=100)
        url = normalize_https_url(item.get("url"), field="sales_link.url")
        normalized = url.casefold()
        if normalized in seen:
            raise ValueError("portal_sales_link_duplicate")
        seen.add(normalized)
        result.append({"label": label, "url": url, "position": position})
    return result


def normalize_book(values: dict, *, partial: bool = False) -> dict:
    if not isinstance(values, dict):
        raise ValueError("portal_book_object_required")
    allowed = {
        "slug", "collection", "kicker", "title", "summary", "description",
        "alt_text", "fallback_cover_path", "cover_media_id", "position",
        "hero_position", "is_published",
    }
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"portal_book_unknown_field:{sorted(unknown)[0]}")
    required = {"slug", "collection", "title", "alt_text"}
    if not partial and not required.issubset(values):
        raise ValueError(f"portal_book_required:{sorted(required - set(values))[0]}")
    result = {}
    if "slug" in values:
        slug = str(values.get("slug") or "").strip().lower()
        if len(slug) > 100 or not _SLUG_PATTERN.fullmatch(slug):
            raise ValueError("portal_book_slug_invalid")
        result["slug"] = slug
    if "collection" in values:
        collection = str(values.get("collection") or "").strip().lower()
        if collection not in {"primary", "complementary"}:
            raise ValueError("portal_book_collection_invalid")
        result["collection"] = collection
    for field, maximum, required_text in (
        ("kicker", 180, False), ("title", 255, True), ("summary", 1500, False),
        ("description", 5000, False), ("alt_text", 500, True),
    ):
        if field in values:
            result[field] = _text(
                values.get(field), field=f"book.{field}", required=required_text, maximum=maximum,
            )
    if "fallback_cover_path" in values:
        path = str(values.get("fallback_cover_path") or "").strip()
        if path:
            normalized = "/" + str(PurePosixPath(path.lstrip("/")))
            if ".." in PurePosixPath(normalized).parts or not _LOCAL_COVER_PATTERN.fullmatch(normalized):
                raise ValueError("portal_book_cover_path_invalid")
            result["fallback_cover_path"] = normalized
        else:
            result["fallback_cover_path"] = None
    if "cover_media_id" in values:
        try:
            result["cover_media_id"] = None if values.get("cover_media_id") in (None, "") else UUID(str(values["cover_media_id"]))
        except (TypeError, ValueError):
            raise ValueError("portal_book_cover_media_invalid")
    if "position" in values:
        position = int(values.get("position") or 0)
        if not 0 <= position <= 100000:
            raise ValueError("portal_book_position_invalid")
        result["position"] = position
    if "hero_position" in values:
        hero = values.get("hero_position")
        if hero in (None, ""):
            result["hero_position"] = None
        else:
            hero = int(hero)
            if hero not in {1, 2, 3}:
                raise ValueError("portal_book_hero_position_invalid")
            result["hero_position"] = hero
    if "is_published" in values:
        if not isinstance(values["is_published"], bool):
            raise ValueError("portal_book_publication_invalid")
        result["is_published"] = values["is_published"]
    return result


@dataclass(frozen=True)
class PortalImageUpload:
    filename: str
    content_type: str
    content: bytes
    sha256: str
    size_bytes: int


def decode_portal_image(data_url: object, filename: object) -> PortalImageUpload:
    """Decode a bounded data URL and verify that MIME and file signature agree."""
    match = _DATA_URL_PATTERN.fullmatch(str(data_url or "").strip())
    if match is None:
        raise ValueError("portal_image_data_url_invalid")
    content_type = match.group(1).lower()
    encoded = re.sub(r"\s+", "", match.group(2))
    if len(encoded) > ((MAX_PORTAL_IMAGE_BYTES + 2) // 3) * 4:
        raise ValueError("portal_image_size_invalid")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("portal_image_base64_invalid")
    if not content or len(content) > MAX_PORTAL_IMAGE_BYTES:
        raise ValueError("portal_image_size_invalid")
    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
    }
    if not signatures.get(content_type, False):
        raise ValueError("portal_image_signature_invalid")
    supplied_name = PurePosixPath(str(filename or "cover").replace("\\", "/")).name
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", supplied_name).strip(".-") or "cover"
    expected_extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[content_type]
    if not safe_stem.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        safe_stem += expected_extension
    elif content_type == "image/jpeg" and safe_stem.lower().endswith(".jpeg"):
        pass
    elif not safe_stem.lower().endswith(expected_extension):
        safe_stem = str(PurePosixPath(safe_stem).with_suffix(expected_extension))
    return PortalImageUpload(
        filename=safe_stem[:255],
        content_type=content_type,
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )
