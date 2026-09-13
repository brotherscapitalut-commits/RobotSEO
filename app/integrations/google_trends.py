"""
Monitora termos do nicho do cliente no Google Trends. Se o interesse de busca
de um termo subir significativamente (pico), cria um ContentAlert sugerindo
priorizar um artigo sobre aquele assunto — cobrindo o gargalo de "não sabemos
o que está bombando no nosso setor agora".

Não depende de chave de API (pytrends usa scraping da interface pública do
Google Trends), mas é sujeito a rate-limit do Google: rodamos no máximo
1x/dia por site via o scheduler.
"""
import time
from datetime import datetime, timedelta
from pytrends.request import TrendReq


SPIKE_THRESHOLD_PCT = 60.0  # alerta se o interesse subir 60%+ vs baseline


def _fetch_interest_score(keyword: str, geo: str = "") -> float:
    """Retorna o interesse médio dos últimos 7 dias (escala 0-100)."""
    pytrends = TrendReq(hl="pt-BR", tz=360)
    pytrends.build_payload([keyword], timeframe="now 7-d", geo=geo)
    df = pytrends.interest_over_time()
    if df.empty or keyword not in df.columns:
        return 0.0
    return float(df[keyword].mean())


def check_site_trends(app, site_id: str):
    """Verifica todos os TrendTopics ativos de um site e cria alertas em picos."""
    from app.extensions import db
    from app.models import Site, TrendTopic, ContentAlert

    with app.app_context():
        site = Site.query.get(site_id)
        if not site:
            return

        geo = "BR" if (site.country or "").upper() == "BR" else site.country or ""
        topics = TrendTopic.query.filter_by(site_id=site.id, is_active=True).all()

        for topic in topics:
            try:
                score = _fetch_interest_score(topic.keyword, geo=geo)
            except Exception:
                continue  # rate-limit ou erro de rede: pula e tenta no próximo ciclo

            baseline = topic.baseline_score or score
            if not topic.baseline_score:
                topic.baseline_score = score
                baseline = score

            pct_change = ((score - baseline) / baseline) * 100 if baseline > 0 else 0.0

            topic.last_score = score
            topic.last_checked_at = datetime.utcnow()
            db.session.commit()

            if pct_change >= SPIKE_THRESHOLD_PCT and score >= 15:
                recent = ContentAlert.query.filter(
                    ContentAlert.site_id == site.id,
                    ContentAlert.keyword == topic.keyword,
                    ContentAlert.created_at >= datetime.utcnow() - timedelta(days=7),
                ).first()
                if recent:
                    continue

                alert = ContentAlert(
                    site_id=site.id,
                    trend_topic_id=topic.id,
                    keyword=topic.keyword,
                    reason=f"Interesse de busca subiu {pct_change:.0f}% na última semana",
                    score_before=baseline,
                    score_after=score,
                    status="new",
                )
                db.session.add(alert)
                db.session.commit()

            time.sleep(1.5)  # respeita rate-limit do Google Trends entre termos


def check_all_sites_trends(app):
    from app.models import Site
    with app.app_context():
        site_ids = [s.id for s in Site.query.all()]
    for sid in site_ids:
        check_site_trends(app, sid)


def create_article_from_alert(alert_id: str) -> str:
    """Transforma um alerta em artigo agendado imediatamente ('priorizar' o assunto)."""
    from app.extensions import db
    from app.models import ContentAlert, Article

    alert = ContentAlert.query.get(alert_id)
    if not alert:
        raise ValueError("Alerta não encontrado")

    article = Article(
        site_id=alert.site_id,
        search_term=alert.keyword,
        status="scheduled",
        scheduled_for=datetime.utcnow(),
    )
    db.session.add(article)
    db.session.commit()

    alert.status = "actioned"
    alert.created_article_id = article.id
    db.session.commit()
    return article.id
