"""
Auditoria técnica de SEO on-page.

O auditor não registra apenas falhas: ele também registra sinais positivos e
métricas úteis para que o relatório mostre o que foi realmente verificado em
cada página.
"""
import json
import re
from bs4 import BeautifulSoup


def _soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _finding(url, category, severity, title, description, how_to_fix=""):
    return {
        "url": url,
        "category": category,
        "severity": severity,
        "title": title,
        "description": description,
        "how_to_fix": how_to_fix,
    }


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def check_page_seo(url: str, html: str) -> list:
    findings = []
    soup = _soup(html)

    title_tag = soup.find("title")
    title_text = _clean_text(title_tag.get_text(" ", strip=True) if title_tag else "")
    if not title_text:
        findings.append(_finding(url, "seo", "critical", "Título ausente", "A página não tem tag <title>.", "Adicione um título único de 50-60 caracteres com a palavra-chave principal."))
    elif len(title_text) > 65:
        findings.append(_finding(url, "seo", "warning", "Título muito longo", f"Título tem {len(title_text)} caracteres e pode ser cortado no Google.", "Reduza para até 60 caracteres."))
    elif len(title_text) < 30:
        findings.append(_finding(url, "seo", "info", "Título curto", f"Título tem {len(title_text)} caracteres. Está presente, mas há espaço para comunicar melhor intenção e diferenciais.", "Considere um título mais descritivo, mantendo-o natural e específico."))
    else:
        findings.append(_finding(url, "seo", "pass", "Título verificado", f"Título presente com {len(title_text)} caracteres: “{title_text[:140]}”.", ""))

    meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    desc_content = _clean_text(meta_desc.get("content", "") if meta_desc else "")
    if not desc_content:
        findings.append(_finding(url, "seo", "critical", "Meta description ausente", "Sem meta description, o Google pode gerar um snippet da página.", "Escreva uma meta description de aproximadamente 140-160 caracteres com benefício e intenção de busca."))
    elif len(desc_content) > 165:
        findings.append(_finding(url, "seo", "warning", "Meta description longa", f"{len(desc_content)} caracteres — pode ser truncada nos resultados de busca.", "Reduza para aproximadamente 160 caracteres."))
    elif len(desc_content) < 70:
        findings.append(_finding(url, "seo", "info", "Meta description curta", f"Meta description com apenas {len(desc_content)} caracteres.", "Amplie com contexto, benefício e uma formulação alinhada à intenção de busca."))
    else:
        findings.append(_finding(url, "seo", "pass", "Meta description verificada", f"Meta description presente com {len(desc_content)} caracteres.", ""))

    h1_tags = soup.find_all("h1")
    h1_texts = [_clean_text(h.get_text(" ", strip=True)) for h in h1_tags]
    if len(h1_tags) == 0:
        findings.append(_finding(url, "seo", "critical", "H1 ausente", "Nenhum H1 encontrado — prejudica a hierarquia semântica da página.", "Adicione um H1 claro descrevendo o assunto principal da página."))
    elif len(h1_tags) > 1:
        findings.append(_finding(url, "seo", "warning", "Múltiplos H1", f"{len(h1_tags)} tags H1 encontradas: {', '.join(h1_texts[:3])}.", "Mantenha um H1 principal e transforme títulos secundários em H2/H3."))
    elif not h1_texts[0]:
        findings.append(_finding(url, "seo", "warning", "H1 vazio", "Existe um H1, mas ele não possui texto útil.", "Preencha o H1 com o assunto principal da página."))
    else:
        findings.append(_finding(url, "seo", "pass", "H1 verificado", f"H1 presente: “{h1_texts[0][:160]}”.", ""))

    canonical = soup.find("link", attrs={"rel": re.compile(r"canonical", re.I)})
    if not canonical or not canonical.get("href"):
        findings.append(_finding(url, "seo", "warning", "Canonical ausente", "Sem tag canonical válida, há menos controle sobre a URL preferencial para indexação.", "Adicione <link rel='canonical' href='...'> apontando para a URL canônica."))
    else:
        findings.append(_finding(url, "seo", "pass", "Canonical verificada", f"Canonical encontrada: {canonical.get('href')[:300]}.", ""))

    imgs = soup.find_all("img")
    imgs_no_alt = [i for i in imgs if not _clean_text(i.get("alt", ""))]
    if imgs_no_alt:
        findings.append(_finding(url, "seo", "warning", "Imagens sem texto alternativo", f"{len(imgs_no_alt)} de {len(imgs)} imagens sem atributo alt.", "Adicione alt descritivo nas imagens de conteúdo; mantenha alt vazio apenas para imagens puramente decorativas."))
    elif imgs:
        findings.append(_finding(url, "seo", "pass", "Imagens e alt verificados", f"{len(imgs)} imagens encontradas e todas possuem atributo alt.", ""))
    else:
        findings.append(_finding(url, "seo", "info", "Nenhuma imagem encontrada", "A página não possui imagens <img> detectáveis.", "Use imagens relevantes quando elas ajudarem a explicar o conteúdo, sem adicionar mídia apenas por SEO."))

    json_ld_scripts = soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)})
    valid_json_ld = 0
    for script in json_ld_scripts:
        try:
            payload = json.loads(script.string or "{}")
            valid_json_ld += 1
            if not isinstance(payload, (dict, list)):
                raise ValueError("JSON-LD não é objeto nem lista")
        except (json.JSONDecodeError, TypeError, ValueError):
            findings.append(_finding(url, "aeo", "critical", "JSON-LD inválido", "Há um bloco de dados estruturados com JSON malformado ou em formato inesperado.", "Corrija a sintaxe e valide o JSON-LD antes de publicar."))
    if not json_ld_scripts:
        findings.append(_finding(url, "aeo", "warning", "Nenhum schema.org (JSON-LD)", "Não foi encontrado JSON-LD. Isso reduz sinais estruturados para mecanismos de busca e respostas baseadas em entidades.", "Adicione schema relevante ao tipo de página, como Organization, LocalBusiness, Service, Article ou FAQPage quando aplicável."))
    elif valid_json_ld == len(json_ld_scripts):
        findings.append(_finding(url, "aeo", "pass", "Dados estruturados verificados", f"{valid_json_ld} bloco(s) JSON-LD válidos encontrados.", ""))

    og_title = soup.find("meta", attrs={"property": re.compile(r"^og:title$", re.I)})
    og_desc = soup.find("meta", attrs={"property": re.compile(r"^og:description$", re.I)})
    og_image = soup.find("meta", attrs={"property": re.compile(r"^og:image$", re.I)})
    missing_og = [name for name, tag in (("og:title", og_title), ("og:description", og_desc), ("og:image", og_image)) if not tag or not _clean_text(tag.get("content", ""))]
    if missing_og:
        findings.append(_finding(url, "seo", "info", "Open Graph incompleto", f"Metadados ausentes: {', '.join(missing_og)}.", "Complete og:title, og:description e og:image para melhorar a apresentação quando a URL for compartilhada."))
    else:
        findings.append(_finding(url, "seo", "pass", "Open Graph verificado", "og:title, og:description e og:image estão presentes.", ""))

    viewport = soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
    if not viewport:
        findings.append(_finding(url, "seo", "warning", "Viewport ausente", "A página não declara viewport para dispositivos móveis.", "Adicione meta viewport responsiva."))

    html_tag = soup.find("html")
    lang = _clean_text(html_tag.get("lang", "") if html_tag else "")
    if not lang:
        findings.append(_finding(url, "seo", "warning", "Idioma da página ausente", "A tag html não informa o idioma principal.", "Adicione lang na tag <html>, por exemplo lang='pt-BR'."))
    else:
        findings.append(_finding(url, "seo", "pass", "Idioma declarado", f"Idioma HTML declarado como {lang}.", ""))

    robots_meta = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    robots_content = _clean_text(robots_meta.get("content", "") if robots_meta else "")
    if "noindex" in robots_content.lower():
        findings.append(_finding(url, "seo", "critical", "Página marcada como noindex", f"Meta robots contém: {robots_content}.", "Remova noindex se esta página deve aparecer nos mecanismos de busca."))

    main = soup.find("main") or soup.body or soup
    visible_text = _clean_text(main.get_text(" ", strip=True))
    word_count = len(re.findall(r"\b\w+[\w'-]*\b", visible_text, flags=re.UNICODE))
    if word_count < 120:
        findings.append(_finding(url, "content", "warning", "Conteúdo muito enxuto", f"Foram detectadas aproximadamente {word_count} palavras de conteúdo visível.", "Avalie se a página precisa responder melhor à intenção de busca com informações, entidades, benefícios, evidências ou FAQs úteis."))
    elif word_count < 300:
        findings.append(_finding(url, "content", "info", "Conteúdo enxuto", f"Foram detectadas aproximadamente {word_count} palavras de conteúdo visível.", "Compare a profundidade com a intenção da página e acrescente detalhes somente onde eles realmente ajudam o usuário."))
    else:
        findings.append(_finding(url, "content", "pass", "Profundidade de conteúdo verificada", f"Foram detectadas aproximadamente {word_count} palavras de conteúdo visível.", ""))

    links = [a.get("href", "") for a in soup.find_all("a", href=True)]
    internal_links = [href for href in links if href.startswith("/") or href.startswith("#") or urlparse(url).netloc == urlparse(urljoin(url, href)).netloc]
    if not internal_links:
        findings.append(_finding(url, "content", "info", "Sem links internos detectáveis", "Nenhum link interno foi encontrado no HTML analisado.", "Adicione links contextuais para páginas importantes quando isso ajudar a navegação e a distribuição de autoridade interna."))
    else:
        findings.append(_finding(url, "content", "pass", "Malha interna verificada", f"{len(internal_links)} links internos detectados.", ""))

    faq_questions = soup.find_all(string=re.compile(r"\?\s*$"))
    question_headings = [h for h in soup.find_all(["h2", "h3", "h4"]) if "?" in _clean_text(h.get_text(" ", strip=True))]
    faq_schema = any("faqpage" in (script.get_text(" ") or "").lower() for script in json_ld_scripts)
    if not question_headings and not faq_schema:
        findings.append(_finding(url, "aeo", "info", "Estrutura de perguntas/FAQ não detectada", "Não foram encontrados headings em formato de pergunta nem FAQPage no HTML.", "Para páginas que respondem dúvidas, adicione perguntas reais e respostas diretas; use FAQPage apenas quando o conteúdo realmente se qualificar."))
    else:
        findings.append(_finding(url, "aeo", "pass", "Sinais de respostas diretas detectados", f"Perguntas em headings: {len(question_headings)}; FAQPage: {'sim' if faq_schema else 'não' }.", ""))

    return findings


def extract_page_text(html: str) -> str:
    soup = _soup(html)
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:8000]
