"""
Agente de IA que analisa o conteúdo já publicado (via texto extraído das
páginas) e atua como um especialista sênior de SEO/GEO/AEO faria:

- GEO (Generative Engine Optimization): a página tem dados concretos e
  verificáveis, fontes citáveis, linguagem que uma IA generativa reproduziria
  com confiança numa resposta (em vez de texto vago e genérico)?
- AEO (Answer Engine Optimization): a página responde a pergunta principal
  logo no início, em formato direto o suficiente para virar featured
  snippet / resposta de voz?
- Recomendações de novos artigos: com base em lacunas de conteúdo, sugere
  títulos + termos de busca + justificativa de por que aquilo fecha um gargalo.

Usa a mesma engine de fallback Claude->Gemini->Ollama já existente, pedindo
JSON estruturado.
"""
import json
import re
from app.ai.engine import generate_with_fallback, AIGenerationError


ANALYST_SYSTEM_PROMPT = """Você é um consultor sênior de SEO, GEO (Generative \
Engine Optimization) e AEO (Answer Engine Optimization), com 15 anos de \
experiência posicionando sites no topo do Google e sendo citado por \
ChatGPT, Perplexity e Google AI Overviews. Você é extremamente específico, \
nunca dá conselho genérico como "escreva conteúdo de qualidade" — sempre diz \
exatamente o que falta e por quê. Responda SEMPRE em JSON válido, sem \
markdown, sem texto fora do JSON."""


def _build_page_analysis_prompt(url: str, page_text: str, business_context: str) -> str:
    return f"""Analise esta página como consultor GEO/AEO.

Contexto do negócio: {business_context}
URL: {url}
Conteúdo extraído da página:
\"\"\"
{page_text}
\"\"\"

Avalie e responda em JSON no formato exato:
{{
  "geo_score": <0-100, quão citável essa página seria por uma IA generativa>,
  "aeo_score": <0-100, quão bem ela responderia diretamente a uma pergunta do usuário>,
  "geo_findings": [
    {{"severity": "critical|warning|info", "title": "...", "description": "...", "how_to_fix": "..."}}
  ],
  "aeo_findings": [
    {{"severity": "critical|warning|info", "title": "...", "description": "...", "how_to_fix": "..."}}
  ]
}}

Critérios GEO: presença de números/dados concretos e verificáveis, \
especificidade (evitar generalidades tipo "melhor qualidade"), estrutura \
que facilita extração por IA (listas, definições claras), autoridade \
demonstrada (certificações, anos de experiência, credenciais citáveis).

Critérios AEO: primeiro parágrafo responde a pergunta principal de forma \
direta, existe seção de perguntas frequentes, headings em formato de \
pergunta quando aplicável, resposta cabe em 40-60 palavras extraíveis."""


def _build_recommendations_prompt(business_context: str, existing_topics: list, competitor_gaps: str) -> str:
    topics_str = "\n".join(f"- {t}" for t in existing_topics) or "(nenhum ainda)"
    return f"""Você é consultor de conteúdo SEO/GEO/AEO para este negócio:
{business_context}

Tópicos que o site JÁ cobre:
{topics_str}

Aja como faria um especialista sênior tentando colocar este site em 1º lugar \
nas buscas orgânicas E ser citado por IAs. Sugira até 8 novos artigos que \
preencham lacunas reais (não repita os tópicos já cobertos). Priorize temas \
com intenção transacional clara e que aproveitem diferenciais verificáveis \
do negócio (certificações, dados operacionais, nicho geográfico/vertical).

Responda em JSON:
{{
  "recommendations": [
    {{
      "title_suggestion": "título do artigo",
      "search_term": "termo de busca alvo",
      "rationale": "por que isso fecha uma lacuna de SEO/GEO/AEO, seja específico",
      "priority": "high|medium|low"
    }}
  ]
}}"""


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def analyze_page(url: str, page_text: str, business_context: str) -> dict:
    prompt = _build_page_analysis_prompt(url, page_text, business_context)
    try:
        text, provider, _ = generate_with_fallback(prompt, system=ANALYST_SYSTEM_PROMPT)
        data = _parse_json_response(text)
        data["_provider"] = provider
        return data
    except (AIGenerationError, json.JSONDecodeError, ValueError) as e:
        return {
            "geo_score": None, "aeo_score": None,
            "geo_findings": [], "aeo_findings": [],
            "_error": str(e),
        }


def recommend_content(business_context: str, existing_topics: list, competitor_gaps: str = "") -> list:
    prompt = _build_recommendations_prompt(business_context, existing_topics, competitor_gaps)
    try:
        text, provider, _ = generate_with_fallback(prompt, system=ANALYST_SYSTEM_PROMPT)
        data = _parse_json_response(text)
        return data.get("recommendations", [])
    except (AIGenerationError, json.JSONDecodeError, ValueError):
        return []


def _build_search_terms_prompt(business_context: str, competitors: list, existing_topics: list) -> str:
    competitors_str = ", ".join(competitors) or "(nenhum cadastrado)"
    topics_str = "\n".join(f"- {t}" for t in existing_topics) or "(nenhum ainda)"
    return f"""Você é estrategista de SEO/GEO/AEO para este negócio:
{business_context}

Concorrentes conhecidos: {competitors_str}

Termos de busca já em uso (não repita):
{topics_str}

Sugira até 10 termos de busca de alto potencial para novos artigos, misturando \
intenção transacional (pronto pra comprar/contratar) e informacional \
(pesquisando/comparando). Pense como alguém tentando roubar tráfego dos \
concorrentes E aparecer em respostas de IA generativa sobre este nicho.

Responda em JSON:
{{
  "terms": [
    {{"term": "...", "intent": "transactional|informational", "category": "categoria curta"}}
  ]
}}"""


def suggest_search_terms(business_context: str, competitors: list, existing_topics: list) -> list:
    prompt = _build_search_terms_prompt(business_context, competitors, existing_topics)
    try:
        text, provider, _ = generate_with_fallback(prompt, system=ANALYST_SYSTEM_PROMPT)
        data = _parse_json_response(text)
        return data.get("terms", [])
    except (AIGenerationError, json.JSONDecodeError, ValueError):
        return []
