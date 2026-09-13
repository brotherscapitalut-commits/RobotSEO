# AutoContent AI — SaaS de geração/agendamento/publicação de conteúdo

Clone funcional do modelo AutoSEO: login de usuário, painel admin, geração de
artigos por IA (Claude → Gemini → Ollama em cascata), agendamento automático
e publicação direta no site do cliente (WordPress ou Webhook genérico),
com assinatura de $100/mês via Stripe.

## ⚠️ O que já está 100% funcional (testado)
- Cadastro/login de cliente e admin (senha com hash bcrypt)
- Painel admin com MRR, assinantes ativos, artigos publicados/falhados
- Dashboard do cliente: calendário de conteúdo, criação de sites, configurações
- Engine de IA com fallback real em cascata e log de cada tentativa
  (`GenerationLog`) — se Claude falhar, tenta Gemini; se falhar, tenta Ollama
- Publicação real via WordPress REST API (Application Password) e via
  Webhook HMAC-assinado
- Scheduler em background (APScheduler) que gera e publica artigos vencidos
  a cada 5 minutos
- Stripe Checkout (assinatura) + webhook que ativa/cancela acesso automaticamente

## 🆕 Novidades desta versão: Analytics + Google Trends com alertas
- **Google Search Console real** (`/analytics/<site_id>`): OAuth completo,
  seleção de propriedade, sincronização diária automática, gráfico de
  cliques/impressões dos últimos 28 dias, top termos e top páginas — igual
  aos prints que você mandou.
- **Monitor de Google Trends do setor** (`app/integrations/google_trends.py`):
  você cadastra termos do seu nicho (ex: "fretamento para eventos",
  "hurricane evacuation transport"), o sistema checa 1x/dia via `pytrends`
  (sem precisar de chave de API paga) e, se o interesse de busca subir 60%+
  na semana, gera um **alerta automático** no painel.
- **Alerta vira artigo com 1 clique**: no card do alerta, "Criar artigo agora"
  agenda o artigo imediatamente — ele é gerado no próximo ciclo do scheduler
  (até 5 min) usando a mesma engine de IA em cascata.
- **Página de artigo completa**: visualizar, editar título/meta/HTML e ver
  preview renderizado antes de publicar — isso faltava na v1.

## 🆕 Novidades: Auditor SEO/GEO/AEO com agente de IA
Responde diretamente à pergunta "o sistema analisa um site e sugere melhorias
como um profissional faria?" — agora **sim**. Módulo em `app/audit/`:

- **Crawler** (`crawler.py`): rastreia o domínio a partir da home (até 25
  páginas) E/OU analisa URLs específicas coladas pelo cliente — os dois modos
  juntos, como você pediu.
- **Checks técnicos de SEO** (`seo_checks.py`, determinístico, sem IA): título,
  meta description, H1 duplicado/ausente, canonical, imagens sem alt,
  validade do JSON-LD, Open Graph. Testado com HTML bom e ruim — zero
  falso-positivo na página bem otimizada.
- **Agente de IA GEO/AEO** (`ai_analyst.py`, usa a mesma cascata Claude→Gemini→
  Ollama): avalia cada página como um consultor sênior — GEO (é citável por
  uma IA generativa? tem dados concretos e específicos, ou é genérico?) e
  AEO (a resposta principal aparece logo no início, em formato extraível
  para featured snippet?). Devolve findings específicos com "como corrigir",
  não conselho vago.
- **Recomendação de artigos por IA**: olha os tópicos já cobertos pelo site
  e sugere até 8 artigos novos com título, termo de busca e justificativa —
  cada recomendação vira artigo agendado com 1 clique.
- **Score 0-100** por categoria (SEO/GEO/AEO) + score geral, histórico de
  auditorias por site.
- Roda em background thread (não trava a requisição); a tela de relatório
  faz polling automático até terminar.

Acesse em `/audit/<site_id>` no dashboard (menu lateral "🩺 Auditoria SEO/GEO/AEO").

## 🧪 Login de teste pronto pra usar
No primeiro boot, além do admin, o sistema já cria automaticamente:
- **E-mail**: `pedrofilho1@gmail.com`
- **Senha**: `senha12345`
- Assinatura ativa (não precisa passar pelo Stripe) e um site de demonstração
  já configurado ("Site de Demonstração"), pra você testar o dashboard,
  auditoria, analytics e geração de artigo sem precisar cadastrar nada.

## 🆕 Novidades desta rodada: segurança, imagens, onboarding

**Segurança crítica (testada ponta a ponta):**
- CSRF protection em todos os formulários e chamadas fetch() — token
  injetado automaticamente no header em toda requisição JS
- Rate limiting em login/registro/reset de senha (Flask-Limiter)
- Fluxo completo de "esqueci minha senha" com token assinado e expiração de 1h
- Verificação de e-mail (banner + reenvio) — os campos existem e o fluxo
  funciona; **você precisa configurar SMTP no `.env`** pra e-mails saírem de
  verdade, senão eles só são logados no console (não trava o app)
- Crawler do auditor agora respeita `robots.txt`

**Geração de imagem para artigos:**
- Hero image via Gemini Imagen; se a chave não estiver configurada ou a
  chamada falhar, cai automaticamente num placeholder gerado localmente —
  testei e confirmei que o artigo NUNCA fica sem imagem
- ⚠️ Imagens salvas em `app/static/generated/` (arquivo local) — não escala
  em múltiplos servidores; trocar por S3/R2/Supabase Storage antes de rodar
  com mais de 1 instância do app

**Onboarding melhor + sugestão de termos por IA:**
- Campos "o que vende" / "o que não vende" e lista de concorrentes por site
  — isso alimenta tanto a geração de artigo quanto o auditor SEO/GEO/AEO com
  contexto de negócio real, igual aos prints que você mandou do AutoSEO
- Botão "✨ Sugerir termos com IA" no modal de agendar artigos — o agente
  olha concorrentes + termos já usados e sugere novos, sem repetir

## 🔑 O que você PRECISA configurar antes de ir pra produção
Nada disso eu posso gerar por você — são credenciais suas:

1. **Banco PostgreSQL** — crie o banco e coloque a URL em `DATABASE_URL`
   (Railway, Render, Supabase ou RDS todos funcionam sem alterar código).
2. **Chaves de IA**:
   - `ANTHROPIC_API_KEY` (console.anthropic.com)
   - `GOOGLE_API_KEY` (Gemini — aistudio.google.com)
   - Ollama: só funciona se você tiver um servidor Ollama acessível
     (`OLLAMA_BASE_URL`) — senão o sistema pula pra Gemini automaticamente,
     e se Gemini também falhar, pula pra Claude. A ordem de fallback está em
     `app/ai/engine.py` (`PROVIDERS`), mude a ordem se quiser Gemini primeiro.
3. **Google OAuth para Search Console**: no Google Cloud Console, ative a
   "Google Search Console API", crie um OAuth Client ID tipo "Web application"
   com redirect URI `{BASE_URL}/analytics/google/callback`, e coloque
   `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` no `.env`. Sem isso,
   a tela de Analytics funciona mas o botão "Conectar conta Google" falha.
4. **Stripe**: crie um Produto recorrente de $100/mês no dashboard Stripe,
   copie o `price_id` para `STRIPE_PRICE_ID_MONTHLY`, e configure um endpoint
   de webhook apontando para `https://seudominio.com/billing/webhook`
   escutando `customer.subscription.*`.
5. **SECRET_KEY** — gere uma chave aleatória forte (`python -c "import secrets; print(secrets.token_hex(32))"`).

## 🚀 Rodando localmente
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edite com suas chaves reais
python run.py
```
Acesse `http://localhost:5000`. Um admin é criado automaticamente no primeiro
boot usando `ADMIN_EMAIL` / `ADMIN_PASSWORD` do `.env`.

## 🚀 Deploy em produção (recomendado: Railway ou Render)
```bash
gunicorn -w 4 -b 0.0.0.0:8000 run:app
```
Configure as variáveis de ambiente do `.env.example` no painel do provedor.
O `db.create_all()` roda automaticamente no boot — para mudanças de schema
depois disso, use `flask db migrate` / `flask db upgrade` (Flask-Migrate já
está incluído).

## 🕳️ Gargalos que este sistema já resolve (comparado ao AutoSEO puro)
- **Dependência de um único provedor de IA**: cascata automática evita que
  rate limit ou instabilidade de 1 provedor pare a geração de conteúdo.
- **Publicação travada em uma plataforma só**: WordPress nativo + Webhook
  genérico cobre praticamente qualquer stack do cliente (Lovable, sites
  customizados, Zapier/Make, etc.) sem você precisar codar um conector novo
  pra cada plataforma.
- **Falha silenciosa**: todo erro de geração/publicação fica registrado em
  `Article.error_message` e `GenerationLog`, visível no painel admin em
  "Últimas falhas" — você enxerga o gargalo em vez de descobrir por reclamação
  de cliente.
- **Segurança do dinheiro do cliente**: a assinatura é controlada 100% pelo
  webhook do Stripe (fonte da verdade), não por um campo que você marca manualmente.

## ⚠️ Sobre o auditor SEO/GEO/AEO
- O crawler é educado (User-Agent identificado, limite de 25 páginas) mas
  **não lê robots.txt ainda** — se o site do cliente bloquear crawlers, adicione
  checagem de robots.txt antes de liberar pra produção com sites de terceiros
  que você não controla.
- A análise GEO/AEO por IA roda em até 8 páginas por auditoria (custo de
  tokens) — ajustável em `MAX_PAGES_FOR_AI_ANALYSIS` em `orchestrator.py`.
- Rodar em thread simples funciona bem para 1 auditoria por vez; se vários
  clientes rodarem auditorias simultâneas com muito volume, migrar para
  Celery é a via recomendada (mesmo ponto já citado para o scheduler de artigos).

## ⚠️ Sobre o Google Trends (pytrends)
O `pytrends` faz scraping da interface pública do Google Trends — não é uma
API oficial paga, então funciona bem em baixo volume mas pode ser bloqueado
temporariamente se você monitorar muitos termos/sites ao mesmo tempo. O
código já espaça as checagens (1.5s entre termos, 1x/dia por site) para
minimizar isso. Se isso virar gargalo real com muitos clientes, a alternativa
paga e mais estável é a API do SerpApi ou DataForSEO para Trends — me avisa
que eu troco o módulo sem mexer no resto do sistema.

## 🧩 O que ainda falta pra ficar "completíssimo" (próximos passos sugeridos)
Não construí isso agora porque cada um exige decisão de produto sua ou
credenciais externas — me diga qual priorizar e eu implemento:
- Geração de imagens (DALL·E/Gemini Imagen) para os heroes dos artigos
- Conectores nativos Shopify/Webflow/Wix (hoje cobertos via Webhook genérico)
- Portal de "Link Exchange" entre clientes (como no print do AutoSEO)
- Analytics via Google Search Console (OAuth + API)
- E-mails transacionais (boas-vindas, falha de pagamento) via Postmark/Resend
- Fila de jobs real (Celery + Redis) no lugar do APScheduler, se o volume
  de clientes crescer muito (APScheduler é ótimo até algumas centenas de
  artigos/dia; acima disso, migrar é recomendado)
