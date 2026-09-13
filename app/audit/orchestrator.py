"""
Autonomous SEO/GEO/AEO execution loop.

1. Collects pages.
2. Runs deterministic SEO checks.
3. Runs the AI GEO/AEO analyst.
4. Generates content-gap recommendations.
5. Converts high-priority recommendations into executable Article jobs.
6. The scheduler then generates and publishes those jobs when auto_publish is enabled.
"""
import threading
from datetime import datetime
from app.audit.crawler import crawl_site, fetch_specific_urls
from app.audit.seo_checks import check_page_seo, extract_page_text
from app.audit.ai_analyst import analyze_page, recommend_content

MAX_PAGES_FOR_AI_ANALYSIS = 8
AUTO_EXECUTE_PRIORITIES = {"high", "critical"}


def run_audit_async(app, audit_id: str):
    thread = threading.Thread(target=_run_audit, args=(app, audit_id), daemon=True)
    thread.start()


def _run_audit(app, audit_id: str):
    from app.extensions import db
    from app.models import SiteAudit, AuditFinding, ContentRecommendation, Article, Site

    with app.app_context():
        audit = SiteAudit.query.get(audit_id)
        if not audit:
            return
        site = Site.query.get(audit.site_id)
        if not site:
            return

        try:
            pages = {}
            if audit.scope in ("crawl", "both"):
                pages.update(crawl_site(site.url))
            if audit.scope in ("urls", "both") and audit.input_urls:
                urls = [u.strip() for u in audit.input_urls.split("\n") if u.strip()]
                pages.update(fetch_specific_urls(urls))

            if not pages:
                audit.status = "failed"
                audit.error_message = "Nenhuma página pôde ser acessada. Verifique se a URL está correta e o site está no ar."
                audit.finished_at = datetime.utcnow()
                db.session.commit()
                return

            all_findings = []
            geo_scores, aeo_scores = [], []
            business_context = f"{site.title or site.url} — {site.description or 'sem descrição cadastrada'}. Vende: {site.what_you_sell or 'não informado'}."

            for i, (url, html) in enumerate(pages.items()):
                seo_findings = check_page_seo(url, html)
                all_findings.extend(seo_findings)

                if i < MAX_PAGES_FOR_AI_ANALYSIS:
                    page_text = extract_page_text(html)
                    if len(page_text) > 200:
                        ai_result = analyze_page(url, page_text, business_context)
                        if ai_result.get("geo_score") is not None:
                            geo_scores.append(ai_result["geo_score"])
                        if ai_result.get("aeo_score") is not None:
                            aeo_scores.append(ai_result["aeo_score"])
                        for f in ai_result.get("geo_findings", []):
                            all_findings.append({**f, "url": url, "category": "geo"})
                        for f in ai_result.get("aeo_findings", []):
                            all_findings.append({**f, "url": url, "category": "aeo"})

            for f in all_findings:
                db.session.add(AuditFinding(
                    audit_id=audit.id, url=f.get("url"), category=f.get("category"),
                    severity=f.get("severity", "info"), title=f.get("title", ""),
                    description=f.get("description", ""), how_to_fix=f.get("how_to_fix", ""),
                ))

            seo_findings_count = len([f for f in all_findings if f.get("category") == "seo"])
            critical_count = len([f for f in all_findings if f.get("severity") == "critical"])
            seo_score = max(0, 100 - (critical_count * 15) - (seo_findings_count * 3))
            geo_score = int(sum(geo_scores) / len(geo_scores)) if geo_scores else None
            aeo_score = int(sum(aeo_scores) / len(aeo_scores)) if aeo_scores else None
            component_scores = [s for s in [seo_score, geo_score, aeo_score] if s is not None]
            overall = int(sum(component_scores) / len(component_scores)) if component_scores else None

            existing_topics = [a.search_term for a in Article.query.filter_by(site_id=site.id).all() if a.search_term]
            recs = recommend_content(business_context, existing_topics)
            executable_jobs = 0
            for r in recs:
                priority = r.get("priority", "medium")
                rec = ContentRecommendation(
                    audit_id=audit.id, site_id=site.id,
                    title_suggestion=r.get("title_suggestion", ""),
                    search_term=r.get("search_term", ""),
                    rationale=r.get("rationale", ""),
                    priority=priority,
                )
                db.session.add(rec)
                db.session.flush()

                # Executor mode: high-impact content gaps become real jobs automatically.
                # The existing 5-minute scheduler performs generation and, when enabled,
                # publication. This keeps analysis and execution decoupled and retryable.
                if priority in AUTO_EXECUTE_PRIORITIES and r.get("search_term"):
                    article = Article(
                        site_id=site.id,
                        search_term=r["search_term"],
                        status="scheduled",
                        scheduled_for=datetime.utcnow(),
                    )
                    db.session.add(article)
                    db.session.flush()
                    rec.status = "scheduled"
                    rec.created_article_id = article.id
                    executable_jobs += 1

            audit.pages_analyzed = len(pages)
            audit.seo_score = seo_score
            audit.geo_score = geo_score
            audit.aeo_score = aeo_score
            audit.overall_score = overall
            audit.status = "done"
            audit.finished_at = datetime.utcnow()
            audit.summary = (
                f"{len(pages)} páginas analisadas. {critical_count} problemas críticos encontrados. "
                f"{len(recs)} oportunidades identificadas; {executable_jobs} transformadas em jobs executáveis automaticamente."
            )
            db.session.commit()

        except Exception as e:
            audit.status = "failed"
            audit.error_message = str(e)
            audit.finished_at = datetime.utcnow()
            db.session.commit()
