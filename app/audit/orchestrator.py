"""Autonomous SEO/GEO/AEO execution loop."""
import threading
from datetime import datetime
from app.audit.crawler import crawl_site, fetch_specific_urls
from app.audit.seo_checks import check_page_seo, extract_page_text
from app.audit.ai_analyst import analyze_page, recommend_content

MAX_PAGES_FOR_AI_ANALYSIS = 8
AUTO_EXECUTE_PRIORITIES = {"high", "critical"}


def run_audit_async(app, audit_id: str):
    threading.Thread(target=_run_audit, args=(app, audit_id), daemon=True).start()


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
                pages.update(fetch_specific_urls([u.strip() for u in audit.input_urls.split("\n") if u.strip()]))

            if not pages:
                audit.status = "failed"
                audit.error_message = "Nenhuma página pôde ser acessada. Verifique se a URL está correta e o site está no ar."
                audit.finished_at = datetime.utcnow()
                db.session.commit()
                return

            all_findings = []
            geo_scores, aeo_scores = [], []
            business_context = f"{site.title or site.url} — {site.description or 'sem descrição cadastrada'}. Vende: {site.what_you_sell or 'não informado'}."
            ai_enabled = bool(app.config.get("ANTHROPIC_API_KEY") or app.config.get("GOOGLE_API_KEY") or app.config.get("ENABLE_OLLAMA"))

            for i, (url, html) in enumerate(pages.items()):
                all_findings.extend(check_page_seo(url, html))
                if i < MAX_PAGES_FOR_AI_ANALYSIS:
                    page_text = extract_page_text(html)
                    if len(page_text) > 200:
                        ai_result = analyze_page(url, page_text, business_context)
                        if ai_result.get("geo_score") is not None:
                            geo_scores.append(ai_result["geo_score"])
                        if ai_result.get("aeo_score") is not None:
                            aeo_scores.append(ai_result["aeo_score"])
                        all_findings.extend([{**f, "url": url, "category": "geo"} for f in ai_result.get("geo_findings", [])])
                        all_findings.extend([{**f, "url": url, "category": "aeo"} for f in ai_result.get("aeo_findings", [])])

            if not ai_enabled:
                all_findings.append({"url": site.url, "category": "ai", "severity": "warning", "title": "Análise GEO/AEO por IA não executada", "description": "O crawl e os testes técnicos foram executados, mas nenhum provedor de IA está configurado neste ambiente. Por isso GEO/AEO aparecem sem nota e não foram geradas oportunidades de conteúdo por IA.", "how_to_fix": "Configure ANTHROPIC_API_KEY, GOOGLE_API_KEY ou habilite ENABLE_OLLAMA para ativar o raciocínio e a geração autônoma."})
            elif not geo_scores and not aeo_scores:
                all_findings.append({"url": site.url, "category": "ai", "severity": "warning", "title": "Provedor de IA não retornou análise", "description": "Um provedor está configurado, mas nenhuma página elegível retornou notas GEO/AEO nesta execução.", "how_to_fix": "Verifique a chave, o modelo configurado e os logs de geração para identificar falhas do provedor."})

            for f in all_findings:
                db.session.add(AuditFinding(audit_id=audit.id, url=f.get("url"), category=f.get("category"), severity=f.get("severity", "info"), title=f.get("title", ""), description=f.get("description", ""), how_to_fix=f.get("how_to_fix", "")))

            total_pages = len(pages)
            seo_critical_pages = len({f.get("url") for f in all_findings if f.get("category") == "seo" and f.get("severity") == "critical"})
            seo_warning_pages = len({f.get("url") for f in all_findings if f.get("category") == "seo" and f.get("severity") == "warning"})
            critical_rate = seo_critical_pages / total_pages
            warning_rate = seo_warning_pages / total_pages
            seo_score = max(0, round(100 - (critical_rate * 45) - (warning_rate * 25)))
            geo_score = int(sum(geo_scores) / len(geo_scores)) if geo_scores else None
            aeo_score = int(sum(aeo_scores) / len(aeo_scores)) if aeo_scores else None
            component_scores = [s for s in [seo_score, geo_score, aeo_score] if s is not None]
            overall = int(sum(component_scores) / len(component_scores)) if component_scores else None

            existing_topics = [a.search_term for a in Article.query.filter_by(site_id=site.id).all() if a.search_term]
            recs = recommend_content(business_context, existing_topics) if ai_enabled else []
            executable_jobs = 0
            for r in recs:
                priority = r.get("priority", "medium")
                rec = ContentRecommendation(audit_id=audit.id, site_id=site.id, title_suggestion=r.get("title_suggestion", ""), search_term=r.get("search_term", ""), rationale=r.get("rationale", ""), priority=priority)
                db.session.add(rec)
                db.session.flush()
                if priority in AUTO_EXECUTE_PRIORITIES and r.get("search_term"):
                    article = Article(site_id=site.id, search_term=r["search_term"], status="scheduled", scheduled_for=datetime.utcnow())
                    db.session.add(article)
                    db.session.flush()
                    rec.status = "scheduled"
                    rec.created_article_id = article.id
                    executable_jobs += 1

            audit.pages_analyzed = total_pages
            audit.seo_score = seo_score
            audit.geo_score = geo_score
            audit.aeo_score = aeo_score
            audit.overall_score = overall
            audit.status = "done"
            audit.finished_at = datetime.utcnow()
            issue_count = sum(1 for f in all_findings if f.get("severity") in ("critical", "warning"))
            pass_count = sum(1 for f in all_findings if f.get("severity") == "pass")
            info_count = sum(1 for f in all_findings if f.get("severity") == "info")
            ai_note = "IA habilitada" if ai_enabled else "IA não configurada"
            audit.summary = f"{total_pages} páginas analisadas. {issue_count} alertas acionáveis, {pass_count} verificações aprovadas e {info_count} observações. {len(recs)} oportunidades de conteúdo geradas; {executable_jobs} jobs executáveis. {ai_note}."
            db.session.commit()

            if executable_jobs:
                from app.scheduler_jobs import process_due_articles
                threading.Thread(target=process_due_articles, args=(app,), daemon=True).start()

        except Exception as e:
            audit.status = "failed"
            audit.error_message = str(e)
            audit.finished_at = datetime.utcnow()
            db.session.commit()
