"""
Engine de geração de conteúdo com fallback em cascata.
Ordem: Claude (Anthropic) -> Gemini (Google) -> Ollama (local).

Mesmo padrão de resiliência usado no motor_phoenix.py: se um provedor falhar
(rate limit, timeout, chave ausente, erro 5xx), tenta o próximo automaticamente
e registra tudo em GenerationLog para você identificar gargalos.
"""
import time
import json
import requests
from flask import current_app


class AIGenerationError(Exception):
    pass


def _try_claude(prompt: str, system: str) -> str:
    import anthropic

    api_key = current_app.config.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise AIGenerationError("ANTHROPIC_API_KEY não configurada")

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [b.text for b in resp.content if b.type == "text"]
    return "\n".join(text_blocks).strip()


def _try_gemini(prompt: str, system: str) -> str:
    import google.generativeai as genai

    api_key = current_app.config.get("GOOGLE_API_KEY")
    if not api_key:
        raise AIGenerationError("GOOGLE_API_KEY não configurada")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        "gemini-1.5-pro", system_instruction=system
    )
    resp = model.generate_content(prompt)
    if not resp.text:
        raise AIGenerationError("Gemini retornou resposta vazia")
    return resp.text.strip()


def _try_ollama(prompt: str, system: str) -> str:
    base_url = current_app.config.get("OLLAMA_BASE_URL")
    model = current_app.config.get("OLLAMA_MODEL")

    r = requests.post(
        f"{base_url}/api/generate",
        json={
            "model": model,
            "prompt": f"{system}\n\n{prompt}",
            "stream": False,
        },
        timeout=180,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("response"):
        raise AIGenerationError("Ollama retornou resposta vazia")
    return data["response"].strip()


PROVIDERS = [
    ("claude", _try_claude),
    ("gemini", _try_gemini),
    ("ollama", _try_ollama),
]


def generate_with_fallback(prompt: str, system: str = "", article_id: str = None):
    """
    Tenta cada provedor em ordem. Retorna (texto, provedor_usado, logs).
    Levanta AIGenerationError somente se TODOS os provedores falharem
    (garante que a geração de artigo nunca trava por causa de 1 provedor fora do ar).
    """
    from app.models import GenerationLog
    from app.extensions import db

    logs = []
    for name, fn in PROVIDERS:
        start = time.time()
        try:
            text = fn(prompt, system)
            latency = int((time.time() - start) * 1000)
            logs.append({"provider": name, "success": True, "latency_ms": latency})
            if article_id:
                db.session.add(GenerationLog(
                    article_id=article_id, provider=name,
                    success=True, latency_ms=latency,
                ))
                db.session.commit()
            return text, name, logs
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            logs.append({"provider": name, "success": False, "error": str(e)})
            if article_id:
                db.session.add(GenerationLog(
                    article_id=article_id, provider=name,
                    success=False, error_message=str(e), latency_ms=latency,
                ))
                db.session.commit()
            continue

    raise AIGenerationError(
        f"Todos os provedores de IA falharam: {json.dumps(logs)}"
    )


ARTICLE_SYSTEM_PROMPT = """Você é um redator SEO especialista em conteúdo B2B para o \
setor de transporte/fretamento de ônibus e vans. Escreva em HTML limpo \
(use <h2>, <h3>, <p>, <ul>, sem <html>/<head>/<body>). Inclua dados concretos, \
seja específico, evite generalidades vagas. Sempre termine com uma seção de \
FAQ (perguntas frequentes) em formato <h2>FAQ</h2> com 3 a 5 perguntas."""


def build_article_prompt(site, search_term: str) -> str:
    instructions = site.writing_instructions or ""
    return f"""Escreva um artigo de blog otimizado para SEO sobre: "{search_term}"

Site: {site.title or site.url}
Descrição do negócio: {site.description or ''}
Idioma: {site.language}
Tamanho alvo: aproximadamente {site.article_length_words} palavras.
Instruções adicionais do cliente: {instructions}

Estruture com título H1 implícito no início (primeira linha em texto puro, \
sem tag), depois o corpo em HTML com H2/H3, uma seção "Principais Pontos" \
em lista logo após a introdução, e termine com FAQ."""


def generate_article_content(site, search_term: str, article_id: str = None):
    prompt = build_article_prompt(site, search_term)
    text, provider, logs = generate_with_fallback(
        prompt, system=ARTICLE_SYSTEM_PROMPT, article_id=article_id
    )
    lines = text.strip().split("\n", 1)
    title = lines[0].lstrip("#").strip() if lines else search_term
    content_html = lines[1].strip() if len(lines) > 1 else text

    hero_image_url = None
    try:
        from app.ai.image_engine import generate_hero_image
        hero_image_url = generate_hero_image(title, site.description or "")
    except Exception:
        pass  # imagem é um bônus; nunca deve travar a geração do artigo

    return {
        "title": title,
        "content_html": content_html,
        "provider": provider,
        "logs": logs,
        "hero_image_url": hero_image_url,
    }
