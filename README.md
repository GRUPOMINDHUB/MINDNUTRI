<p align="center">
  <img src="mindnutri_painel/agente_app/assets/logo_mindhub.png" alt="Mindhub Logo" width="200"/>
</p>

<h1 align="center">Mindnutri</h1>
<p align="center">
  <strong>Agente de IA para Fichas Técnicas de Alimentação via WhatsApp</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Django-5.x-092E20?logo=django&logoColor=white" alt="Django"/>
  <img src="https://img.shields.io/badge/OpenAI-GPT--4.1-412991?logo=openai&logoColor=white" alt="OpenAI"/>
  <img src="https://img.shields.io/badge/Claude-Vision-D97706?logo=anthropic&logoColor=white" alt="Claude"/>
  <img src="https://img.shields.io/badge/WhatsApp-Evolution_API-25D366?logo=whatsapp&logoColor=white" alt="WhatsApp"/>
  <img src="https://img.shields.io/badge/Pagamentos-Asaas-0066FF" alt="Asaas"/>
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker"/>
</p>

---

## 📋 Índice

- [Visão Geral](#-visão-geral)
- [Arquitetura](#-arquitetura)
- [Funcionalidades](#-funcionalidades)
- [Stack Tecnológica](#-stack-tecnológica)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação](#-instalação)
- [Configuração](#️-configuração)
- [Execução](#-execução)
- [Endpoints da API](#-endpoints-da-api)
- [Fluxo do Agente WhatsApp](#-fluxo-do-agente-whatsapp)
- [Painel Administrativo](#️-painel-administrativo)
- [Sistema de Pagamentos](#-sistema-de-pagamentos)
- [Testes](#-testes)
- [Deploy em Produção](#-deploy-em-produção)
- [Custos Operacionais](#-custos-operacionais)
- [Licença](#-licença)

---

## 🎯 Visão Geral

O **Mindnutri** é uma plataforma SaaS completa do ecossistema **Mindhub** que automatiza a criação de fichas técnicas e operacionais para estabelecimentos de alimentação. Através de um agente conversacional no WhatsApp, donos de restaurantes, hamburguerias, pizzarias e confeitarias podem gerar documentos profissionais com cálculos precisos de custo, rendimento e modo de preparo — tudo por meio de uma conversa natural.

### O que o sistema faz

1. **Conversa com o cliente** via WhatsApp usando IA (GPT-4.1)
2. **Coleta ingredientes, quantidades e preços** de forma conversacional
3. **Calcula custos** com fatores de correção (FC) e índice de cocção (IC)
4. **Gera fichas técnicas** em XLSX com layout profissional Mindhub
5. **Gera fichas operacionais** em PDF com foto do prato
6. **Gerencia assinaturas** e pagamentos via Asaas (Cartão/Pix)
7. **Fornece um painel web** completo para o gestor administrar tudo

---

## 🏗 Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                           MINDNUTRI                                 │
│                                                                     │
│  Cliente WhatsApp ──→ Evolution API ──→ Webhook Django              │
│                                              │                      │
│                              GPT-4.1 (OpenAI) ───── Agente IA      │
│                              Claude (Vision/Áudio)      │           │
│                                                         │           │
│                                    Gera XLSX + PDF ─────┘           │
│                                         │                           │
│                                    Envia arquivo de volta            │
│                                                                     │
│  Asaas ──webhook──→ Django ──→ Ativa / Bloqueia / Renova            │
│                         │                                           │
│                    SQLite / PostgreSQL                               │
│                         │                                           │
│                    Painel Web (Django) ──→ Gestor                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Componentes Principais

| Componente | Responsabilidade |
|---|---|
| **Agente IA** (`agente_app/`) | Núcleo conversacional, geração de fichas, processamento de mídia |
| **Painel Web** (`painel/`) | Dashboard, gestão de assinantes, financeiro, configurações |
| **Assinaturas** (`assinaturas/`) | Ciclo de vida de pagamentos (Asaas), webhooks financeiros |
| **Utilidades** (`utils/`) | WhatsApp (Evolution API), Asaas, banco de dados, mídia, storage |
| **Gerador** (`agente_app/gerador/`) | Geração de XLSX (openpyxl) e PDF (ReportLab) |
| **Evolution API** (Docker) | Gateway WhatsApp self-hosted (QR Code) |

---

## ✨ Funcionalidades

### Agente WhatsApp (IA)
- 🤖 Conversação natural com GPT-4.1 via function calling
- 🎙️ Transcrição de áudio via OpenAI Whisper
- 📸 Visão computacional via Claude (extração de ingredientes de fotos)
- 📊 Geração de **Fichas Técnicas (XLSX)** com layout profissional
- 📄 Geração de **Fichas Operacionais (PDF)** em paisagem com foto
- 🧮 Cálculo automático de custo, FC, IC, rendimento e porções
- 🍳 Detecção inteligente de ingredientes manipulados (subfichas)
- 📋 Base de conhecimento de perdas por cocção editável
- 💬 Mensagens do bot 100% configuráveis pelo painel
- 🔄 Controle de estado da conversa com expiração automática (2h)
- ♻️ Detecção de abandono e retomada de conversa (≥60 min)

### Painel Administrativo
- 📈 Dashboard com métricas em tempo real (assinantes, fichas, receita)
- 👥 Gestão completa de assinantes (filtros, busca, edição, status)
- 📁 Histórico de fichas geradas por assinante
- 🔔 Central de notificações (inadimplência, limites, erros)
- 💰 Painel financeiro integrado com Asaas (cobranças, atrasados, inadimplentes)
- ⚙️ Configuração da IA (prompt editável em 4 seções + parâmetros)
- 💬 Chat preview para testar o agente direto no painel
- 📱 Conexão WhatsApp (status, QR Code, reconectar)
- 🎫 Sistema de cupons de desconto
- 💲 Precificação configurável do plano
- 📉 Base de perdas de ingredientes editável

### Sistema de Pagamentos
- 💳 Cobrança por cartão de crédito (payment links)
- 📲 Cobrança por Pix (QR Code + copia e cola)
- 🔄 Ciclo completo: criar → pagar → ativar → usar → renovar → bloquear
- 🎫 Cupons de desconto no primeiro pagamento
- 🔁 Idempotência de webhooks (proteção contra duplicatas)
- ⏰ Tarefas agendadas: verificação de vencimentos, reset de fichas mensais

---

## 🛠 Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| **Backend** | Python 3.11+, Django 5.x |
| **IA Conversacional** | OpenAI GPT-4.1 (function calling) |
| **Visão Computacional** | Anthropic Claude (análise de imagens) |
| **Transcrição de Áudio** | OpenAI Whisper |
| **WhatsApp Gateway** | Evolution API (Docker, self-hosted) |
| **Pagamentos** | Asaas (Cartão + Pix) |
| **Banco de Dados** | SQLite (dev) / PostgreSQL (prod) |
| **Geração XLSX** | openpyxl |
| **Geração PDF** | ReportLab |
| **Infraestrutura** | Docker Compose (PostgreSQL, Redis, Evolution API) |
| **Tunnel (dev)** | ngrok |

---

## 📁 Estrutura do Projeto

```
mindnutri_completo/
│
├── docker-compose.yml              # Evolution API + PostgreSQL + Redis
├── MINDNUTRI_GUIA_COMPLETO.md      # Guia de instalação detalhado
│
├── mindnutri_painel/               # ← Projeto Django principal
│   ├── manage.py                   # Ponto de entrada Django
│   ├── .env                        # Variáveis de ambiente (não versionado)
│   ├── .env.example                # Template de configuração
│   ├── db.sqlite3                  # Banco local (não versionado)
│   │
│   ├── core/                       # Configuração do Django
│   │   ├── settings.py             # Settings (12-factor, .env)
│   │   ├── urls.py                 # Roteamento raiz
│   │   └── wsgi.py                 # WSGI entry point
│   │
│   ├── agente_app/                 # Agente conversacional WhatsApp
│   │   ├── nucleo.py               # Núcleo: fluxos, IA, geração (~1900 linhas)
│   │   ├── prompt.py               # System prompt (fallback)
│   │   ├── views.py                # Webhooks (WhatsApp + Asaas)
│   │   ├── urls.py                 # Rotas do agente
│   │   ├── tests.py                # Testes unitários (18 test cases)
│   │   ├── assets/                 # Logo Mindhub
│   │   └── gerador/                # Geradores de documentos
│   │       ├── xlsx_gerador.py     # Ficha Técnica (XLSX)
│   │       └── pdf_gerador.py      # Ficha Operacional (PDF)
│   │
│   ├── painel/                     # Painel web do gestor
│   │   ├── models.py               # 10 modelos Django
│   │   ├── views.py                # Views + APIs JSON (~1170 linhas)
│   │   ├── urls.py                 # 30+ rotas
│   │   ├── prompt_defaults.py      # Prompt padrão da IA (4 seções)
│   │   ├── mensagem_defaults.py    # Mensagens padrão do bot
│   │   ├── perdas_defaults.py      # Base de perdas de ingredientes
│   │   ├── mensagens_cache.py      # Cache de mensagens com interpolação
│   │   ├── templates/              # Templates HTML
│   │   ├── static/                 # CSS, JS, assets
│   │   └── management/commands/
│   │       ├── popular_dados.py    # Seed de dados de exemplo
│   │       └── run_tarefas.py      # Tarefas agendadas (loop contínuo)
│   │
│   ├── assinaturas/                # Sistema de assinaturas
│   │   ├── asaas_client.py         # Cliente HTTP Asaas (class-based)
│   │   └── servico_assinaturas.py  # Ciclo de vida completo
│   │
│   ├── utils/                      # Utilitários compartilhados
│   │   ├── whatsapp.py             # Evolution API (enviar/receber/mídia)
│   │   ├── asaas.py                # Integração direta Asaas + webhooks
│   │   ├── banco.py                # Camada de acesso ao banco
│   │   ├── midia.py                # Whisper + Claude Vision
│   │   └── storage.py              # Armazenamento de arquivos
│   │
│   └── exemplos/                   # Fichas de demonstração
│       ├── exemplo_hamburguer.xlsx/pdf
│       ├── exemplo_pizza.xlsx/pdf
│       └── exemplo_sobremesa.xlsx/pdf
│
├── mindnutri_agente/               # Módulo auxiliar (setup + docs)
│   ├── setup.py                    # Script de inicialização
│   ├── requirements.txt            # Dependências Python
│   └── README.md                   # Documentação do agente
│
└── mindnutri_assinaturas/          # (Reservado para expansão)
```

---

## 📦 Pré-requisitos

| Requisito | Versão Mínima |
|---|---|
| Python | 3.11+ |
| Docker Desktop | Qualquer versão recente |
| ngrok | Para desenvolvimento local (webhooks) |
| Conta OpenAI | API Key com acesso ao GPT-4.1 e Whisper |
| Conta Anthropic | API Key com acesso ao Claude (Vision) |
| Conta Asaas | API Key (sandbox para testes, produção para Go-Live) |

---

## 🚀 Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/GRUPOMINDHUB/MINDNUTRI.git
cd MINDNUTRI
```

### 2. Criar e ativar o ambiente virtual

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Instalar dependências

```bash
pip install django anthropic openai requests openpyxl reportlab Pillow python-dotenv httpx
```

### 4. Subir os containers Docker (Evolution API)

```bash
docker-compose up -d
```

Isso inicia:
- **Evolution API** (porta 8080) — Gateway WhatsApp
- **PostgreSQL** — Banco da Evolution API
- **Redis** — Cache da Evolution API

### 5. Configurar variáveis de ambiente

```bash
cd mindnutri_painel
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/macOS
```

Edite o `.env` com suas chaves (veja a seção [Configuração](#️-configuração)).

### 6. Inicializar o banco de dados

```bash
cd mindnutri_painel
python manage.py migrate
python manage.py createsuperuser
python manage.py popular_dados   # Dados de exemplo (opcional)
```

### 7. Conectar o WhatsApp

```bash
# Criar instância na Evolution API
curl -X POST http://localhost:8080/instance/create ^
  -H "apikey: SUA_CHAVE_EVOLUTION" ^
  -H "Content-Type: application/json" ^
  -d "{\"instanceName\": \"mindnutri\", \"qrcode\": true}"
```

Acesse o painel web em `http://127.0.0.1:8000` → Conexão WhatsApp → Escanear QR Code.

---

## ⚙️ Configuração

### Variáveis de Ambiente (`.env`)

```env
# ── IA ────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...          # Claude (Vision + análise de imagens)
OPENAI_API_KEY=sk-...                 # GPT-4.1 + Whisper

# ── WhatsApp (Evolution API) ──────────────────────────────────────
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=Mindnutri1417!
EVOLUTION_INSTANCE=mindnutri

# ── Pagamentos (Asaas) ────────────────────────────────────────────
ASAAS_API_KEY=$aact_...
ASAAS_BASE_URL=https://sandbox.asaas.com/api/v3  # Trocar para prod em Go-Live
ASAAS_WEBHOOK_TOKEN=                               # Token opcional para validar webhooks

# ── Django ────────────────────────────────────────────────────────
DJANGO_SECRET_KEY=sua-chave-secreta-forte
DJANGO_DEBUG=True                                  # False em produção

# ── Plano ─────────────────────────────────────────────────────────
PLANO_VALOR=89.90                                  # Valor mensal da assinatura
PLANO_FICHAS_LIMITE=30                             # Fichas por mês

# ── Gestor ────────────────────────────────────────────────────────
GESTOR_WHATSAPP=5511999999999                      # WhatsApp para alertas

# ── Storage ───────────────────────────────────────────────────────
STORAGE_TYPE=local
STORAGE_LOCAL_PATH=./arquivos_gerados
```

### Onde obter as chaves

| Serviço | URL |
|---|---|
| **OpenAI** | https://platform.openai.com/api-keys |
| **Anthropic** | https://console.anthropic.com |
| **Asaas (Sandbox)** | https://sandbox.asaas.com → Configurações → Integrações |
| **Asaas (Produção)** | https://www.asaas.com → Configurações → Integrações |

---

## ▶️ Execução

Abra **3 terminais** separados com o ambiente virtual ativado:

### Terminal 1 — Servidor Django

```bash
cd mindnutri_painel
python manage.py runserver
```

O painel estará disponível em `http://127.0.0.1:8000`.

### Terminal 2 — Tarefas Agendadas

```bash
cd mindnutri_painel
python manage.py run_tarefas --loop --intervalo 60
```

Executa a cada 60 minutos:
- Verificação de limites de fichas
- Às 9h: verificação de vencimentos + reset de fichas mensais

### Terminal 3 — ngrok (desenvolvimento)

```bash
ngrok http 8000
```

Configure os webhooks com a URL gerada:
- **Evolution API**: `https://SEU_TUNNEL.ngrok-free.app/webhook/whatsapp/`
- **Asaas**: `https://SEU_TUNNEL.ngrok-free.app/webhook/asaas/`

---

## 🔌 Endpoints da API

### Webhooks (Externos)

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/webhook/whatsapp/` | Recebe mensagens da Evolution API |
| `POST` | `/webhook/asaas/` | Recebe eventos de pagamento do Asaas |

### Painel Web (Autenticado)

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/` | Dashboard principal |
| `GET` | `/assinantes/` | Lista de assinantes |
| `GET` | `/assinantes/<id>/` | Detalhe do assinante |
| `GET` | `/fichas/` | Fichas técnicas geradas |
| `GET` | `/notificacoes/` | Central de notificações |
| `GET` | `/financeiro/` | Painel financeiro |
| `GET` | `/configuracoes/` | Configuração da IA |

### APIs JSON (Internas)

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/api/stats/` | Estatísticas do dashboard |
| `GET` | `/api/conexao/status/` | Status WhatsApp + serviços |
| `GET` | `/api/conexao/qrcode/` | QR Code para emparelhar |
| `POST` | `/api/conexao/acao/` | Desconectar / Reiniciar |
| `POST` | `/api/salvar-prompt/` | Salvar configuração do prompt IA |
| `POST` | `/api/salvar-parametros/` | Salvar max_tokens / temperatura |
| `POST` | `/api/preview-chat/` | Testar o agente no painel |
| `GET` | `/api/financeiro/dados/` | Cobranças + métricas financeiras |
| `POST` | `/api/financeiro/nova-cobranca/` | Criar cobrança manual |
| `POST` | `/api/financeiro/reenviar/` | Reenviar link de pagamento |
| `GET` | `/api/mensagens/` | Mensagens configuráveis do bot |
| `POST` | `/api/salvar-mensagens/` | Salvar mensagens editadas |
| `GET` | `/api/perdas/` | Base de perdas de ingredientes |
| `POST` | `/api/salvar-perdas/` | Atualizar perdas |
| `GET` | `/api/precificacao/` | Preço do plano + cupons |
| `POST` | `/api/cupom/salvar/` | Criar/editar cupom |

---

## 🤖 Fluxo do Agente WhatsApp

### Fluxo Pré-Assinatura (Onboarding)

```mermaid
graph TD
    A[Primeiro contato] --> B[Boas-vindas + escolha de nicho]
    B --> C[Envia exemplo XLSX + PDF do nicho]
    C --> D[Pergunta interesse]
    D -->|Sim| E[Apresenta oferta R$ 89,90/mês]
    D -->|Não| F[Encerra com cordialidade]
    E -->|Quer assinar| G[Coleta dados via LLM: Nome + Instagram]
    G --> H[Escolha: Cartão ou Pix]
    H --> I[Gera link de pagamento Asaas]
    I --> J[Aguarda confirmação via webhook]
    J --> K[✅ Ativa acesso — 30 fichas/mês]
```

### Fluxo Assinante Ativo (Geração de Fichas)

```mermaid
graph TD
    A[Mensagem do assinante] --> B{Saudação?}
    B -->|Sim| C[Menu principal]
    B -->|Não| D[Conversa com IA GPT-4.1]
    D --> E{Tool call detectada?}
    E -->|gerar_ficha_tecnica| F[Valida ingredientes + preços]
    E -->|gerar_subficha| G[Calcula custo de item manipulado]
    E -->|texto normal| H[Responde naturalmente]
    F --> I[Monta resumo calculado por Python]
    I --> J{Usuário confirma?}
    J -->|Sim| K[Gera XLSX + calcula custos]
    K --> L[Envia XLSX via WhatsApp]
    L --> M{Quer PDF operacional?}
    M -->|Sim| N[Coleta foto do prato]
    N --> O[Gera PDF em paisagem]
    O --> P[Envia PDF via WhatsApp]
    J -->|Não| D
```

### Tipos de Mídia Suportados

| Tipo | Processamento |
|---|---|
| **Texto** | Processado diretamente pela IA |
| **Áudio/PTT** | Transcrito via OpenAI Whisper → processado como texto |
| **Imagem** | Analisada via Claude Vision (extrai ingredientes) |
| **Foto (fluxo PDF)** | Salva e incorporada na Ficha Operacional |
| **Documento** | Registrado como recebido |

---

## 🖥️ Painel Administrativo

### Modelos de Dados

| Modelo | Descrição |
|---|---|
| `Assinante` | Dados do cliente, status, plano, fichas |
| `FichaTecnica` | Registro de cada ficha gerada (XLSX/PDF) |
| `Notificacao` | Alertas do sistema (6 tipos, 3 níveis) |
| `Conversa` | Histórico de mensagens por telefone |
| `Ingrediente` | Ingredientes cadastrados por assinante |
| `EstadoConversa` | Máquina de estados da conversa (FSM) |
| `ConfiguracaoIA` | Prompt e parâmetros da IA (singleton) |
| `MensagemBot` | Mensagens configuráveis do bot (60+) |
| `PerdaIngrediente` | Base de perdas por cocção (150+ itens) |
| `Cupom` | Cupons de desconto |
| `WebhookProcessado` | Idempotência de webhooks |

### Segurança

- Autenticação Django padrão (login/logout)
- CSRF protection em todas as views
- Webhooks com verificação de token (Asaas)
- HTTPS forçado em produção (HSTS + SSL redirect)
- Cookies seguros em produção
- Sentry (opcional) para monitoramento de erros

---

## 💰 Sistema de Pagamentos

### Ciclo de Vida

```
pendente → (paga) → ativo → (usa fichas) → (vence) → inadimplente → (paga) → ativo
                                                    → (cancela) → cancelado
```

### Métodos Suportados

- **Cartão de Crédito**: via payment links do Asaas
- **Pix**: cobrança com QR Code e código copia e cola

### Webhooks Processados

| Evento Asaas | Ação |
|---|---|
| `PAYMENT_CONFIRMED` | Ativa assinante, reseta fichas, notifica gestor |
| `PAYMENT_RECEIVED` | Mesmo que CONFIRMED |
| `PAYMENT_OVERDUE` | Marca como inadimplente, envia aviso |
| `SUBSCRIPTION_INACTIVATED` | Cancela acesso |

### Proteções

- **Idempotência atômica**: webhooks duplicados são ignorados (`WebhookProcessado`)
- **Lock por telefone**: processamento serializado por usuário (thread-safe)
- **Retry com backoff**: chamadas à OpenAI com retry exponencial

---

## 🧪 Testes

```bash
cd mindnutri_painel
python manage.py test agente_app
```

### Cobertura dos Testes

| Área | Testes |
|---|---|
| Helpers de detecção | `_quer_comecar_do_zero`, `_eh_resposta_sim/nao` |
| Normalização de ingredientes | Conversão g→kg, ml→L, cálculo de peso bruto com FC |
| Modo de preparo | Separação por linhas, remoção de numeração |
| Formatação operacional | Conversão de unidades para display (500g, 200ml) |
| Cálculo de custo | Custo total com FC, custo por porção, edge cases |
| Resumo calculado | Validação de porções, rendimento, custos formatados |
| Subfichas | Custo por kg, rendimento zero (fallback), formatação |
| Processamento de mídia | Áudio, imagem, documento, foto no fluxo PDF |
| Método de pagamento | Cartão, Pix, entradas inválidas |
| Idempotência webhook | Registro, duplicatas, limpeza de antigos |

---

## 🚢 Deploy em Produção

### Checklist

- [ ] Contratar VPS (Hetzner CX21 ou similar — ~R$ 70/mês)
- [ ] Instalar Ubuntu 22.04 + Python + Docker + nginx + certbot
- [ ] Trocar SQLite por **PostgreSQL** (`DATABASE_URL` no `.env`)
- [ ] Configurar `DJANGO_DEBUG=False`
- [ ] Trocar `ASAAS_BASE_URL` para `https://api.asaas.com/v3`
- [ ] Configurar domínio próprio (ex: `api.mindnutri.com.br`)
- [ ] Gerar certificado SSL via Let's Encrypt
- [ ] Substituir ngrok pela URL do servidor nos webhooks
- [ ] Usar Gunicorn + nginx como reverse proxy
- [ ] Configurar `DJANGO_SECRET_KEY` com uma chave forte e única
- [ ] Configurar `SENTRY_DSN` para monitoramento de erros
- [ ] Gerar política de privacidade e termos de uso (LGPD)
- [ ] Testar fluxo completo antes de divulgar

### Variáveis de Produção

```env
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=chave-unica-gerada-com-secrets-token-hex
DJANGO_ALLOWED_HOSTS=api.mindnutri.com.br
ASAAS_BASE_URL=https://api.asaas.com/v3
DATABASE_URL=postgresql://user:pass@localhost:5432/mindnutri
SENTRY_DSN=https://xxx@sentry.io/xxx
```

---

## 💵 Custos Operacionais

| Serviço | Custo Mensal Estimado |
|---|---|
| VPS (Hetzner CX21) | ~R$ 70 |
| OpenAI GPT-4.1 (por ficha) | ~R$ 0,10 – 0,30 |
| OpenAI Whisper (por áudio) | ~R$ 0,01/min |
| Anthropic Claude (por imagem) | ~R$ 0,02 – 0,05 |
| Asaas (por cobrança) | 0,99% + R$ 0,49 |
| Evolution API (self-hosted) | Incluso no VPS |
| **Total com 50 clientes** | **~R$ 300 – 500/mês** |
| **Receita com 50 clientes** | **~R$ 4.495/mês** |

---

## 📄 Licença

Projeto proprietário — **Grupo Mindhub**. Todos os direitos reservados.

---

<p align="center">
  <sub>Desenvolvido com ❤️ pelo <strong>Grupo Mindhub</strong> — Ecossistema de Gestão para Alimentação</sub>
</p>
