import uuid
from datetime import datetime
from flask_login import UserMixin
from flask import current_app
from app.extensions import db, bcrypt


def gen_uuid():
    return str(uuid.uuid4())


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255))
    role = db.Column(db.String(20), default="customer")  # customer | admin
    email_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Assinatura
    stripe_customer_id = db.Column(db.String(120))
    stripe_subscription_id = db.Column(db.String(120))
    subscription_status = db.Column(db.String(30), default="inactive")
    # inactive | trialing | active | past_due | canceled

    sites = db.relationship("Site", backref="owner", cascade="all, delete-orphan")

    def set_password(self, raw):
        self.password_hash = bcrypt.generate_password_hash(raw).decode("utf-8")

    def check_password(self, raw):
        return bcrypt.check_password_hash(self.password_hash, raw)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def has_active_subscription(self):
        return self.subscription_status in ("active", "trialing")

    @property
    def has_full_access(self):
        """Full product access, including an explicit local test allowlist."""
        if self.has_active_subscription or self.is_admin:
            return True
        if not current_app.config.get("DEV_BYPASS_SUBSCRIPTION", False):
            return False
        allowed_emails = current_app.config.get("DEV_BYPASS_EMAILS", set())
        return (self.email or "").strip().lower() in allowed_emails


class Site(db.Model):
    __tablename__ = "sites"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(255))
    description = db.Column(db.Text)
    language = db.Column(db.String(10), default="pt")
    country = db.Column(db.String(10), default="BR")

    # Publicação
    publish_method = db.Column(db.String(30), default="webhook")  # wordpress | webhook
    wp_base_url = db.Column(db.String(500))
    wp_username = db.Column(db.String(255))
    wp_app_password = db.Column(db.String(255))  # WordPress Application Password
    webhook_url = db.Column(db.String(500))
    webhook_secret = db.Column(db.String(255), default=gen_uuid)

    # Preferências de conteúdo
    writing_instructions = db.Column(db.Text)
    article_length_words = db.Column(db.Integer, default=1500)
    publish_frequency_per_week = db.Column(db.Integer, default=3)
    auto_publish = db.Column(db.Boolean, default=False)

    # Onboarding: contexto de negócio pra IA gerar conteúdo melhor
    what_you_sell = db.Column(db.Text)      # uma linha por item
    what_you_dont_sell = db.Column(db.Text)  # uma linha por item

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    articles = db.relationship("Article", backref="site", cascade="all, delete-orphan")
    competitors = db.relationship("Competitor", backref="site", cascade="all, delete-orphan")


class SearchTerm(db.Model):
    __tablename__ = "search_terms"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    site_id = db.Column(db.String(36), db.ForeignKey("sites.id"), nullable=False)
    term = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(120))
    intent = db.Column(db.String(30))  # informational | transactional
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Article(db.Model):
    __tablename__ = "articles"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    site_id = db.Column(db.String(36), db.ForeignKey("sites.id"), nullable=False)

    title = db.Column(db.String(500))
    search_term = db.Column(db.String(500))
    content_html = db.Column(db.Text)
    meta_description = db.Column(db.String(500))
    hero_image_url = db.Column(db.String(1000))

    status = db.Column(db.String(30), default="scheduled")
    # scheduled | generating | ready | published | failed

    ai_provider_used = db.Column(db.String(30))  # claude | gemini | ollama
    scheduled_for = db.Column(db.DateTime)
    published_at = db.Column(db.DateTime)
    published_url = db.Column(db.String(1000))
    error_message = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class GoogleConnection(db.Model):
    """Credenciais OAuth do Google (Search Console) por site."""
    __tablename__ = "google_connections"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    site_id = db.Column(db.String(36), db.ForeignKey("sites.id"), nullable=False, unique=True)

    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    token_expiry = db.Column(db.DateTime)
    gsc_property_url = db.Column(db.String(500))  # ex: sc-domain:phoenixbusorlando.com
    last_synced_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SearchMetric(db.Model):
    """Snapshot diário de métricas do Search Console (clicks, impressions, ctr, position)."""
    __tablename__ = "search_metrics"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    site_id = db.Column(db.String(36), db.ForeignKey("sites.id"), nullable=False)

    date = db.Column(db.Date, nullable=False)
    query = db.Column(db.String(500))
    page = db.Column(db.String(1000))
    clicks = db.Column(db.Integer, default=0)
    impressions = db.Column(db.Integer, default=0)
    ctr = db.Column(db.Float, default=0.0)
    position = db.Column(db.Float, default=0.0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TrendTopic(db.Model):
    """Termos de mercado monitorados no Google Trends para o nicho do site."""
    __tablename__ = "trend_topics"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    site_id = db.Column(db.String(36), db.ForeignKey("sites.id"), nullable=False)

    keyword = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    baseline_score = db.Column(db.Float, default=0.0)
    last_score = db.Column(db.Float, default=0.0)
    last_checked_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ContentAlert(db.Model):
    """Alerta gerado automaticamente quando um termo do nicho tem pico de interesse."""
    __tablename__ = "content_alerts"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    site_id = db.Column(db.String(36), db.ForeignKey("sites.id"), nullable=False)
    trend_topic_id = db.Column(db.String(36), db.ForeignKey("trend_topics.id"))

    keyword = db.Column(db.String(255))
    reason = db.Column(db.String(500))  # ex: "Interesse subiu 340% nos últimos 7 dias"
    score_before = db.Column(db.Float)
    score_after = db.Column(db.Float)
    status = db.Column(db.String(20), default="new")  # new | actioned | dismissed
    created_article_id = db.Column(db.String(36), db.ForeignKey("articles.id"))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Competitor(db.Model):
    __tablename__ = "competitors"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    site_id = db.Column(db.String(36), db.ForeignKey("sites.id"), nullable=False)
    domain = db.Column(db.String(255), nullable=False)
    note = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SiteAudit(db.Model):
    """Uma execução de auditoria SEO/GEO/AEO sobre o site ou um conjunto de URLs."""
    __tablename__ = "site_audits"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    site_id = db.Column(db.String(36), db.ForeignKey("sites.id"), nullable=False)

    scope = db.Column(db.String(20), default="crawl")  # crawl | urls
    input_urls = db.Column(db.Text)  # URLs específicas coladas pelo usuário, uma por linha
    status = db.Column(db.String(20), default="running")  # running | done | failed
    pages_analyzed = db.Column(db.Integer, default=0)

    overall_score = db.Column(db.Integer)  # 0-100
    seo_score = db.Column(db.Integer)
    geo_score = db.Column(db.Integer)
    aeo_score = db.Column(db.Integer)

    summary = db.Column(db.Text)  # resumo executivo gerado pela IA
    error_message = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)

    findings = db.relationship("AuditFinding", backref="audit", cascade="all, delete-orphan")
    recommendations = db.relationship("ContentRecommendation", backref="audit", cascade="all, delete-orphan")


class AuditFinding(db.Model):
    """Um problema/oportunidade específico encontrado numa página."""
    __tablename__ = "audit_findings"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    audit_id = db.Column(db.String(36), db.ForeignKey("site_audits.id"), nullable=False)

    url = db.Column(db.String(1000))
    category = db.Column(db.String(20))  # seo | geo | aeo
    severity = db.Column(db.String(20))  # critical | warning | info
    title = db.Column(db.String(500))
    description = db.Column(db.Text)
    how_to_fix = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ContentRecommendation(db.Model):
    """Sugestão de artigo/tópico gerada pelo agente de análise para melhorar rankings."""
    __tablename__ = "content_recommendations"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    audit_id = db.Column(db.String(36), db.ForeignKey("site_audits.id"), nullable=False)
    site_id = db.Column(db.String(36), db.ForeignKey("sites.id"), nullable=False)

    title_suggestion = db.Column(db.String(500))
    search_term = db.Column(db.String(500))
    rationale = db.Column(db.Text)  # por que esse artigo ajuda SEO/GEO/AEO
    priority = db.Column(db.String(20), default="medium")  # high | medium | low
    status = db.Column(db.String(20), default="suggested")  # suggested | scheduled | dismissed
    created_article_id = db.Column(db.String(36), db.ForeignKey("articles.id"))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class GenerationLog(db.Model):
    """Log de cada tentativa de geração por provedor, para diagnosticar gargalos de IA."""
    __tablename__ = "generation_logs"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    article_id = db.Column(db.String(36), db.ForeignKey("articles.id"))
    provider = db.Column(db.String(30))
    success = db.Column(db.Boolean)
    error_message = db.Column(db.Text)
    latency_ms = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
