from datetime import datetime
from flask import Flask, redirect, url_for, render_template
from flask_login import current_user
from config import Config
from app.extensions import db, login_manager, bcrypt, migrate, scheduler, csrf, mail, limiter


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)

    from app.auth import bp as auth_bp
    from app.dashboard import bp as dashboard_bp
    from app.admin import bp as admin_bp
    from app.billing import bp as billing_bp
    from app.analytics import bp as analytics_bp
    from app.audit_routes import bp as audit_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(audit_bp)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("admin.dashboard" if current_user.is_admin else "dashboard.home"))
        faqs = [
            ("O que o AutoSEO AI faz?", "Ele rastreia seu site, identifica problemas e oportunidades de SEO, GEO e AEO, prioriza ações e transforma recomendações em conteúdo e tarefas executáveis."),
            ("Ele realmente executa as mudanças?", "O núcleo atual já gera conteúdo, agenda publicações e publica por WordPress ou Webhook. A arquitetura permite ampliar a execução com conectores adicionais."),
            ("Qual a diferença entre SEO, GEO e AEO?", "SEO melhora descoberta em buscadores; GEO melhora a capacidade de uma marca ser encontrada e citada por sistemas generativos; AEO estrutura respostas para mecanismos de resposta e snippets."),
            ("Preciso configurar as chaves de IA agora?", "Não. A aplicação aceita as credenciais por variáveis de ambiente e usa a cascata de provedores configurada no backend."),
            ("Como funciona a assinatura?", "A cobrança é preparada com Stripe Checkout e webhook. Você adiciona as credenciais e o Price ID no ambiente de produção."),
        ]
        schema = {
            "@context": "https://schema.org", "@graph": [
                {"@type": "SoftwareApplication", "name": "AutoSEO AI", "applicationCategory": "BusinessApplication", "operatingSystem": "Web", "description": "Plataforma autônoma de SEO, GEO e AEO para analisar, decidir e executar otimizações.", "offers": {"@type": "Offer", "price": "100", "priceCurrency": "USD", "priceSpecification": {"@type": "UnitPriceSpecification", "billingDuration": "P1M"}}},
                {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]}
            ]
        }
        return render_template("landing.html", faqs=faqs, schema=schema, now=datetime.utcnow())

    with app.app_context():
        db.create_all()
        _seed_admin(app)

    from app.scheduler_jobs import start_scheduler
    start_scheduler(app, scheduler)

    return app


def _seed_admin(app):
    from app.models import User

    email = app.config["ADMIN_EMAIL"]
    if not User.query.filter_by(email=email).first():
        admin = User(email=email, name="Administrador", role="admin",
                     subscription_status="active", email_verified=True)
        admin.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(admin)
        db.session.commit()
        print(f"[seed] Admin criado: {email}")
