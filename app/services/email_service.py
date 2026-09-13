"""
Envio de e-mails transacionais via SMTP (Flask-Mail). Se as credenciais SMTP
não estiverem configuradas no .env, os e-mails são apenas logados no console
em vez de falhar — assim o app nunca quebra por falta de config de e-mail,
mas você vê exatamente o que seria enviado (útil em dev).
"""
from flask import current_app, render_template_string
from flask_mail import Message
from app.extensions import mail


def _mail_configured() -> bool:
    return bool(current_app.config.get("MAIL_USERNAME") and current_app.config.get("MAIL_PASSWORD"))


def send_email(to: str, subject: str, html_body: str):
    if not _mail_configured():
        current_app.logger.info(f"[email simulado] Para: {to} | Assunto: {subject}\n{html_body[:300]}")
        return False
    msg = Message(subject=subject, recipients=[to], html=html_body,
                  sender=current_app.config.get("MAIL_DEFAULT_SENDER"))
    mail.send(msg)
    return True


_BASE_EMAIL_TEMPLATE = """
<div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 24px;">
  <p style="font-weight: 800; font-size: 18px; color: #6a3ffb;">AutoContent AI</p>
  {{ body|safe }}
  <p style="color: #94a3b8; font-size: 12px; margin-top: 32px;">Se você não reconhece esta ação, ignore este e-mail.</p>
</div>
"""


def send_welcome_email(user):
    body = f"<h2>Bem-vindo, {user.name or user.email}!</h2><p>Sua conta foi criada. Finalize a assinatura para começar a gerar conteúdo automaticamente.</p>"
    send_email(user.email, "Bem-vindo ao AutoContent AI", render_template_string(_BASE_EMAIL_TEMPLATE, body=body))


def send_verification_email(user, verify_url):
    body = f"<h2>Confirme seu e-mail</h2><p>Clique no link para verificar sua conta:</p><p><a href='{verify_url}'>{verify_url}</a></p>"
    send_email(user.email, "Confirme seu e-mail — AutoContent AI", render_template_string(_BASE_EMAIL_TEMPLATE, body=body))


def send_password_reset_email(user, reset_url):
    body = f"<h2>Redefinir senha</h2><p>Clique no link abaixo para criar uma nova senha (válido por 1 hora):</p><p><a href='{reset_url}'>{reset_url}</a></p>"
    send_email(user.email, "Redefinir sua senha — AutoContent AI", render_template_string(_BASE_EMAIL_TEMPLATE, body=body))


def send_payment_failed_email(user):
    body = "<h2>Problema com seu pagamento</h2><p>Não conseguimos processar sua cobrança. Atualize seu método de pagamento para continuar usando o AutoContent AI sem interrupções.</p>"
    send_email(user.email, "Ação necessária: pagamento falhou", render_template_string(_BASE_EMAIL_TEMPLATE, body=body))


def send_article_published_email(user, article):
    body = f"<h2>Novo artigo publicado!</h2><p><strong>{article.title}</strong> já está no ar.</p><p><a href='{article.published_url}'>Ver artigo</a></p>"
    send_email(user.email, f"Publicado: {article.title}", render_template_string(_BASE_EMAIL_TEMPLATE, body=body))


def send_trend_alert_email(user, alert):
    body = f"<h2>🔥 Oportunidade de conteúdo</h2><p>O termo <strong>{alert.keyword}</strong> teve um pico de interesse: {alert.reason}</p>"
    send_email(user.email, f"Alerta de tendência: {alert.keyword}", render_template_string(_BASE_EMAIL_TEMPLATE, body=body))
