"""
Gera a imagem de capa (hero image) de um artigo. Usa o Gemini (Imagen) por
já estarmos com a chave do Google configurada para texto; se a chave não
estiver disponível ou a chamada falhar, cai num placeholder gerado
localmente (sem custo, sem dependência externa) pra nunca deixar o artigo
sem imagem.

As imagens são salvas em app/static/generated/ e servidas como arquivo
estático — troque por upload a um bucket (S3/R2/Supabase Storage) quando for
para produção com múltiplos servidores (arquivo local não escala horizontalmente).
"""
import os
import uuid
from flask import current_app

GENERATED_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "generated")


def _ensure_dir():
    os.makedirs(GENERATED_DIR, exist_ok=True)


def _generate_placeholder(prompt: str, filename: str) -> str:
    """Cria uma imagem placeholder simples com o título, caso a IA de imagem falhe/não esteja configurada."""
    from PIL import Image, ImageDraw, ImageFont

    _ensure_dir()
    img = Image.new("RGB", (1200, 630), color=(18, 18, 31))
    draw = ImageDraw.Draw(img)

    for x in range(1200):
        ratio = x / 1200
        r = int(18 + ratio * 60)
        g = int(18 + ratio * 40)
        b = int(31 + ratio * 100)
        draw.line([(x, 0), (x, 630)], fill=(r, g, b))

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
    except IOError:
        font = ImageFont.load_default()

    words = prompt.split()
    lines, current = [], ""
    for w in words:
        test = f"{current} {w}".strip()
        if len(test) > 30:
            lines.append(current)
            current = w
        else:
            current = test
    lines.append(current)
    lines = lines[:4]

    y = 630 // 2 - (len(lines) * 55) // 2
    for line in lines:
        draw.text((80, y), line, fill=(255, 255, 255), font=font)
        y += 55

    path = os.path.join(GENERATED_DIR, filename)
    img.save(path, "JPEG", quality=85)
    return f"/static/generated/{filename}"


def _generate_with_gemini(prompt: str, filename: str) -> str:
    import google.generativeai as genai

    api_key = current_app.config.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY não configurada")

    genai.configure(api_key=api_key)
    model = genai.ImageGenerationModel("imagen-3.0-generate-001")
    result = model.generate_images(prompt=prompt, number_of_images=1, aspect_ratio="16:9")

    if not result or not result.images:
        raise RuntimeError("Gemini Imagen não retornou nenhuma imagem")

    _ensure_dir()
    path = os.path.join(GENERATED_DIR, filename)
    result.images[0].save(path)
    return f"/static/generated/{filename}"


def generate_hero_image(article_title: str, business_context: str = "") -> str:
    """Retorna a URL relativa (ex: /static/generated/xxx.jpg) da imagem gerada."""
    filename = f"{uuid.uuid4().hex}.jpg"
    prompt = (
        f"Fotografia profissional e realista para artigo de blog sobre: {article_title}. "
        f"Contexto do negócio: {business_context}. Estilo corporativo, luz natural, "
        f"sem texto sobreposto, alta qualidade editorial."
    )
    try:
        return _generate_with_gemini(prompt, filename)
    except Exception as e:
        current_app.logger.info(f"[imagem] Gemini Imagen indisponível ({e}), usando placeholder.")
        return _generate_placeholder(article_title, filename)
