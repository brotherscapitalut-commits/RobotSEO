"""
Jobs autônomos do AutoSEO AI.

- A cada 5 min: executa artigos vencidos.
- A cada 24h: monitora tendências.
- A cada 24h: sincroniza Search Console conectado.
- A cada 24h: roda uma nova auditoria nos sites com assinatura ativa,
  transformando oportunidades de alta prioridade em jobs executáveis.
"""
from datetime import datetime, timedelta


def process_due_articles(app):
    from app.extensions import db
    from app.models import Article, Site
    from app.ai.engine import generate_article_content, AIGenerationError
    from app.publishers.webhook import publish_article

    with app.app_context():
        now = datetime.utcnow()
        due = Article.query.filter(
            Article.status == "scheduled",
            Article.scheduled_for <= now,
        ).all()

        for article in due:
            article.status = "generating"
            db.session.commit()

            site = Site.query.get(article.site_id)
            if not site or not site.owner.has_active_subscription:
                article.status = "failed"
                article.error_message = "Site sem assinatura ativa"
                db.session.commit()
                continue

            try:
                result = generate_article_content(
                    site, article.search_term, article_id=article.id
                )
                article.title = result["title"]
                article.content_html = result["content_html"]
                article.ai_provider_used = result["provider"]
                article.hero_image_url = result.get("hero_image_url")
                article.status = "ready"
                db.session.commit()

                if site.auto_publish:
                    url = publish_article(site, article)
                    article.status = "published"
                    article.published_at = datetime.utcnow()
                    article.published_url = url
                    db.session.commit()

            except AIGenerationError as e:
                article.status = "failed"
                article.error_message = str(e)
                db.session.commit()
            except Exception as e:
                article.status = "ready"
                article.error_message = f"Falha ao publicar: {e}"
                db.session.commit()


def _run_autonomous_audits_job(app):
    """Inicia no máximo uma auditoria por site a cada 24h."""
    from app.extensions import db
    from app.models import Site, SiteAudit
    from app.audit.orchestrator import run_audit_async

    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(hours=23)
        for site in Site.query.all():
            if not site.owner or not site.owner.has_active_subscription:
                continue

            recent = SiteAudit.query.filter(
                SiteAudit.site_id == site.id,
                SiteAudit.created_at >= cutoff,
            ).order_by(SiteAudit.created_at.desc()).first()
            if recent and recent.status in ("running", "done"):
                continue

            audit = SiteAudit(
                site_id=site.id,
                scope="crawl",
                status="running",
            )
            db.session.add(audit)
            db.session.commit()
            run_audit_async(app, audit.id)


def _check_trends_job(app):
    from app.integrations.google_trends import check_all_sites_trends
    try:
        check_all_sites_trends(app)
    except Exception as e:
        app.logger.warning(f"Falha ao checar Google Trends: {e}")


def _sync_gsc_job(app):
    """Sincroniza métricas do Search Console de todos os sites conectados, 1x/dia."""
    from app.models import Site, GoogleConnection
    from app.integrations.google_search_console import sync_search_metrics

    with app.app_context():
        connections = GoogleConnection.query.filter(
            GoogleConnection.gsc_property_url.isnot(None)
        ).all()
        for conn in connections:
            site = Site.query.get(conn.site_id)
            if not site or not site.owner or not site.owner.has_active_subscription:
                continue
            try:
                sync_search_metrics(site, conn)
            except Exception as e:
                app.logger.warning(f"Falha ao sincronizar GSC do site {site.id}: {e}")


def start_scheduler(app, scheduler):
    scheduler.add_job(
        func=lambda: process_due_articles(app),
        trigger="interval",
        minutes=5,
        id="process_due_articles",
        replace_existing=True,
    )
    scheduler.add_job(
        func=lambda: _check_trends_job(app),
        trigger="interval",
        hours=24,
        id="check_google_trends",
        replace_existing=True,
    )
    scheduler.add_job(
        func=lambda: _sync_gsc_job(app),
        trigger="interval",
        hours=24,
        id="sync_gsc_metrics",
        replace_existing=True,
    )
    scheduler.add_job(
        func=lambda: _run_autonomous_audits_job(app),
        trigger="interval",
        hours=24,
        id="autonomous_site_audits",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
