"""Engine de geração de conteúdo com fallback Claude -> Gemini -> Ollama."""
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
    resp = client.messages.create(model="claude-sonnet-4-6", max_tokens=4096, system=system, messages=[{"role": "user", "content": prompt}])
    return "\n".join(b.text for b in resp.content if b.type == "text").strip()


def _try_gemini(prompt: str, system: str) -> str:
    import google.generativeai as genai
    api_key = current_app.config.get("GOOGLE_API_KEY")
    if not api_key:
        raise AIGenerationError("GOOGLE_API_KEY não configurada")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.8-flash", system_instruction=system)
    resp = model.generate_content(prompt)
    if not resp.text:
        raise AIGenerationError("Gemini retornou resposta vazia")
    return resp.text.strip()


def _try_ollama(prompt: str, system: str) -> str:
    base_url = current_app.config.get("OLLAMA_BASE_URL")
    model = current_app.config.get("OLLAMA_MODEL")
    r = requests.post(f"{base_url}/api/generate", json={"model": model, "prompt": f"{system}\n\n{prompt}", "stream": False}, timeout=180)
    r.raise_for_status()
    data = r.json()
    if not data.get("response"):
        raise AIGenerationError("Ollama retornou resposta vazia")
    return data["response"].strip()


PROVIDERS = [("claude", _try_claude), ("gemini", _try_gemini), ("ollama", _try_ollama)]


def generate_with_fallback(prompt: str, system: str = "", article_id: str = None):
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
                db.session.add(GenerationLog(article_id=article_id, provider=name, success=True, latency_ms=latency))
                db.session.commit()
            return text, name, logs
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            logs.append({"provider": name, "success": False, "error": str(e), "latency_ms": latency})
            if article_id:
                db.session.add(GenerationLog(article_id=article_id, provider=name, success=False, error_message=str(e), latency_ms=latency))
                db.session.commit()
    raise AIGenerationError(f"Todos os provedores de IA falharam: {json.dumps(logs)}")


ARTICLE_SYSTEM_PROMPT = """Você é um redator SEO sênior e especialista em conteúdo para negócios de qualquer segmento. O contexto do negócio fornecido pelo cliente é a fonte de verdade. Nunca invente serviços, produtos, preços, certificações, resultados ou políticas. Escreva em HTML limpo (h2, h3, p, ul, sem html/head/body), seja específico e verificável. Termine com uma seção FAQ com 3 a 5 perguntas e respostas úteis."""


def build_article_prompt(site, search_term: str) -> str:
    instructions = site.writing_instructions or ""
    return f"""Escreva um artigo de blog otimizado para SEO/GEO/AEO sobre: \"{search_term}\".

Negócio: {site.title or site.url}
Descrição: {site.description or ''}
O que vende: {site.what_you_sell or 'não informado'}
O que não vende: {site.what_you_dont_sell or 'não informado'}
Idioma: {site.language}
Tamanho alvo: aproximadamente {site.article_length_words} palavras.
Instruções adicionais: {instructions}

Estruture com título H1 implícito na primeira linha, depois HTML com H2/H3, uma seção de principais pontos após a introdução e FAQ no final. Responda apenas com o conteúdo solicitado."""


def generate_article_content(site, search_term: str, article_id: str = None):
    text, provider, logs = generate_with_fallback(build_article_prompt(site, search_term), system=ARTICLE_SYSTEM_PROMPT, article_id=article_id)
    lines = text.strip().split("\n", 1)
    title = lines[0].lstrip("#").strip() if lines else search_term
    content_html = lines[1].strip() if len(lines) > 1 else text
    hero_image_url = None
    try:
        from app.ai.image_engine import generate_hero_image
        hero_image_url = generate_hero_image(title, site.description or "")
    except Exception:
        pass
    return {"title": title, "content_html": content_html, "provider": provider, "logs": logs, "hero_image_url": hero_image_url}
