"""
Roda a auditoria fim a fim:
1. Coleta páginas (crawl do domínio e/ou URLs específicas coladas pelo usuário)
2. Roda checks técnicos de SEO determinísticos em cada página
3. Roda o agente de IA (GEO/AEO) em uma amostra de páginas (limitado por custo/tempo)
4. Gera recomendações de novos artigos com base em lacunas
5. Calcula score agregado e salva tudo

Roda em background thread pra não travar a request HTTP do usuário.
"""
import threading
from datetime import datetime
from app.audit.crawler import crawl_site, fetch_specific_urls
from app.audit.seo_checks import check_page_seo, extract_page_text
from app.audit.ai_analyst import analyze_page, recommend_content

MAX_PAGES_FOR_AI_ANALYSIS = 8  # limita quantas páginas passam pela IA por auditoria


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
            business_context = f"{site.title or site.url} — {site.description or 'sem descrição cadastrada'}"

            for i, (url, html) in enumerate(pages.items()):
                # Checks técnicos determinísticos (rápido, roda em todas as páginas)
                seo_findings = check_page_seo(url, html)
                all_findings.extend(seo_findings)

                # Análise GEO/AEO por IA (mais caro, limitado a uma amostra)
                if i < MAX_PAGES_FOR_AI_ANALYSIS:
                    page_text = extract_page_text(html)
                    if len(page_text) > 200:  # ignora páginas praticamente vazias
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

            # Score determinístico de SEO: penaliza por severidade encontrada
            seo_findings_count = len([f for f in all_findings if f.get("category") == "seo"])
            critical_count = len([f for f in all_findings if f.get("severity") == "critical"])
            seo_score = max(0, 100 - (critical_count * 15) - (seo_findings_count * 3))
            geo_score = int(sum(geo_scores) / len(geo_scores)) if geo_scores else None
            aeo_score = int(sum(aeo_scores) / len(aeo_scores)) if aeo_scores else None

            component_scores = [s for s in [seo_score, geo_score, aeo_score] if s is not None]
            overall = int(sum(component_scores) / len(component_scores)) if component_scores else None

            # Recomendações de conteúdo (lacunas)
            existing_topics = [a.search_term for a in Article.query.filter_by(site_id=site.id).all() if a.search_term]
            recs = recommend_content(business_context, existing_topics)
            for r in recs:
                db.session.add(ContentRecommendation(
                    audit_id=audit.id, site_id=site.id,
                    title_suggestion=r.get("title_suggestion", ""),
                    search_term=r.get("search_term", ""),
                    rationale=r.get("rationale", ""),
                    priority=r.get("priority", "medium"),
                ))

            audit.pages_analyzed = len(pages)
            audit.seo_score = seo_score
            audit.geo_score = geo_score
            audit.aeo_score = aeo_score
            audit.overall_score = overall
            audit.status = "done"
            audit.finished_at = datetime.utcnow()
            audit.summary = (
                f"{len(pages)} páginas analisadas. {critical_count} problemas críticos encontrados. "
                f"{len(recs)} novos tópicos de conteúdo recomendados para fechar lacunas de SEO/GEO/AEO."
            )
            db.session.commit()

        except Exception as e:
            audit.status = "failed"
            audit.error_message = str(e)
            audit.finished_at = datetime.utcnow()
            db.session.commit()
