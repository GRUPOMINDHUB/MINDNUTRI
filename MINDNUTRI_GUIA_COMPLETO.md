# Mindnutri — Guia Completo de Instalação e Operação
### Ecossistema Mindhub · Versão 1.0 · Windows

---

## Visão geral do sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                        MINDNUTRI                                │
│                                                                 │
│  Cliente WhatsApp ──→ Evolution API ──→ Agente (Django)         │
│                                              │                  │
│                              Claude API ─────┘                  │
│                              Whisper API (áudio)                │
│                                              │                  │
│                          Gera XLSX / PDF ────┘                  │
│                              │                                  │
│                         Envia arquivo de volta ao cliente       │
│                                                                 │
│  Asaas ──webhook──→ Agente ──→ Ativa / Bloqueia / Renova        │
│                         │                                       │
│                    SQLite (banco compartilhado)                 │
│                         │                                       │
│                    Painel Web (Django) ──→ Gestor               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Estrutura de pastas

```
mindnutri/
├── mindnutri_painel/         ← Painel web do gestor (Django)
│   ├── manage.py
│   ├── core/                 ← Settings, URLs raiz
│   └── painel/               ← App: models, views, templates
│
├── mindnutri_agente/         ← Agente WhatsApp (Django)
│   ├── manage.py             ← MESMO manage.py — mesmo projeto Django
│   ├── config.py             ← Variáveis de ambiente
│   ├── agente/               ← Núcleo, prompt, views, URLs
│   ├── gerador/              ← Gera XLSX e PDF
│   ├── utils/                ← Banco, WhatsApp, Asaas, Mídia, Storage
│   ├── assets/               ← Logo Mindhub
│   ├── exemplos/             ← Fichas de demonstração
│   └── arquivos_gerados/     ← Fichas dos clientes
│
├── mindnutri_assinaturas/    ← Sistema de cobranças
│   ├── asaas_client.py
│   ├── servico_assinaturas.py
│   ├── webhook_handler.py
│   └── tarefas.py
│
├── db.sqlite3                ← Banco único compartilhado
├── venv/                     ← Ambiente virtual Python
└── .env                      ← Todas as configurações
```

> O painel e o agente compartilham o mesmo banco SQLite e o mesmo
> ambiente virtual. São dois apps Django no mesmo projeto.

---

## PASSO 1 — Instalar o Python

Acesse https://www.python.org/downloads/ e baixe o Python 3.11 ou superior.

**Durante a instalação, marque obrigatoriamente:**
☑ Add Python to PATH

Verifique no CMD:
```
python --version
```

---

## PASSO 2 — Criar a estrutura de pastas

Abra o CMD e execute:

```
mkdir mindnutri
cd mindnutri
python -m venv venv
venv\Scripts\activate
```

Você verá `(venv)` no início da linha — isso indica que o ambiente está ativo.

---

## PASSO 3 — Instalar todas as dependências

```
pip install django anthropic openai requests openpyxl reportlab Pillow python-dotenv httpx
```

---

## PASSO 4 — Copiar os módulos

Extraia os três ZIPs dentro da pasta `mindnutri\`:

```
mindnutri\
├── mindnutri_painel\      ← conteúdo do ZIP do painel
├── mindnutri_agente\      ← conteúdo do ZIP do agente
└── mindnutri_assinaturas\ ← conteúdo do ZIP das assinaturas
```

---

## PASSO 5 — Configurar o arquivo .env

Dentro de `mindnutri_agente\`, copie o arquivo de exemplo:

```
copy mindnutri_agente\.env.example mindnutri_agente\.env
```

Abra o `.env` no Bloco de Notas e preencha:

```env
# Anthropic — obrigatório
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI Whisper — obrigatório para transcrição de áudio
OPENAI_API_KEY=sk-...

# Evolution API — WhatsApp
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=sua-chave-evolution
EVOLUTION_INSTANCE=mindnutri

# Asaas — pagamentos
ASAAS_API_KEY=$aact_...
ASAAS_BASE_URL=https://sandbox.asaas.com/api/v3

# Seu número para receber alertas
GESTOR_WHATSAPP=5511999999999

# Plano
PLANO_VALOR=59.90
PLANO_FICHAS_LIMITE=30
```

**Onde obter as chaves:**
- Anthropic: https://console.anthropic.com → API Keys
- OpenAI: https://platform.openai.com → API Keys
- Asaas Sandbox: https://sandbox.asaas.com → Configurações → Integrações

---

## PASSO 6 — Inicializar o banco de dados

```
cd mindnutri_painel
python manage.py migrate
python manage.py createsuperuser
python manage.py popular_dados
cd ..
```

O `migrate` cria todas as tabelas. O `createsuperuser` cria seu login do painel. O `popular_dados` insere dados de exemplo para visualização.

---

## PASSO 7 — Executar o setup do agente

```
cd mindnutri_agente
python setup.py
cd ..
```

Isso cria as pastas `assets/`, `exemplos/`, copia a logo Mindhub e inicializa o banco do agente.

---

## PASSO 8 — Testar a integração com o Asaas

```
cd mindnutri_assinaturas
python testar_asaas.py
cd ..
```

Todos os testes devem passar com ✓ antes de continuar.

---

## PASSO 9 — Instalar o Docker e a Evolution API

### 9.1 Instale o Docker Desktop
https://www.docker.com/products/docker-desktop/

Após instalar, abra o Docker Desktop e aguarde inicializar.

### 9.2 Crie o arquivo `docker-compose.yml`

Dentro da pasta `mindnutri\`, crie o arquivo `docker-compose.yml`:

```yaml
version: '3'
services:
  evolution-api:
    image: atendai/evolution-api:latest
    ports:
      - "8080:8080"
    environment:
      - SERVER_URL=http://localhost:8080
      - AUTHENTICATION_TYPE=apikey
      - AUTHENTICATION_API_KEY=TROQUE_POR_UMA_CHAVE_FORTE
      - DATABASE_ENABLED=false
      - QRCODE_LIMIT=30
    restart: unless-stopped
```

Substitua `TROQUE_POR_UMA_CHAVE_FORTE` pela mesma chave que colocou no `.env` em `EVOLUTION_API_KEY`.

### 9.3 Suba a Evolution API

```
docker-compose up -d
```

Verifique se está rodando:
```
docker ps
```

### 9.4 Conecte o WhatsApp

Crie a instância pelo CMD:

```
curl -X POST http://localhost:8080/instance/create ^
  -H "apikey: SUA_CHAVE_EVOLUTION" ^
  -H "Content-Type: application/json" ^
  -d "{\"instanceName\": \"mindnutri\", \"qrcode\": true}"
```

Acesse no navegador: `http://localhost:8080/instance/connect/mindnutri`

Escaneie o QR Code com o WhatsApp do número dedicado ao Mindnutri.

---

## PASSO 10 — Expor para internet (ngrok)

Para que os webhooks do Asaas e da Evolution API cheguem ao seu computador local, use o ngrok.

### 10.1 Instale o ngrok
https://ngrok.com/download → baixe para Windows, extraia e execute.

### 10.2 Autentique
```
ngrok config add-authtoken SEU_TOKEN_NGROK
```

### 10.3 Exponha a porta 8000
```
ngrok http 8000
```

Anote a URL gerada, exemplo: `https://abc123.ngrok-free.app`

---

## PASSO 11 — Configurar webhooks

### Evolution API — receber mensagens do WhatsApp

No CMD, configure o webhook da instância:

```
curl -X POST http://localhost:8080/webhook/set/mindnutri ^
  -H "apikey: SUA_CHAVE_EVOLUTION" ^
  -H "Content-Type: application/json" ^
  -d "{\"url\": \"https://abc123.ngrok-free.app/webhook/whatsapp/\", \"events\": [\"messages.upsert\"]}"
```

### Asaas — receber eventos de pagamento

No painel do Asaas Sandbox:
1. Configurações → Notificações → Webhooks → Novo webhook
2. URL: `https://abc123.ngrok-free.app/webhook/asaas/`
3. Marque: PAYMENT_CONFIRMED, PAYMENT_RECEIVED, PAYMENT_OVERDUE, SUBSCRIPTION_INACTIVATED

---

## PASSO 12 — Rodar o sistema

Abra **3 janelas do CMD** separadas, todas com o `venv` ativado (`venv\Scripts\activate`):

### Janela 1 — Servidor Django (painel + agente)
```
cd mindnutri_painel
python manage.py runserver
```

### Janela 2 — Tarefas agendadas
```
cd mindnutri_assinaturas
python tarefas.py --loop --intervalo 60
```

### Janela 3 — ngrok (se necessário)
```
ngrok http 8000
```

---

## PASSO 13 — Verificar que tudo funciona

| O que testar | Como testar |
|---|---|
| Painel web | Acesse http://127.0.0.1:8000 e faça login |
| WhatsApp conectado | Verifique no Docker: `docker logs evolution-api_evolution-api_1` |
| Agente respondendo | Mande "oi" para o número do WhatsApp |
| Exemplo sendo enviado | Responda "sim" e escolha um nicho |
| Asaas sandbox | `python mindnutri_assinaturas/testar_asaas.py` |

---

## Rotina diária de operação

```
1. Abra o Docker Desktop (Evolution API sobe automaticamente)
2. Ative o venv: venv\Scripts\activate
3. Rode o servidor: python mindnutri_painel\manage.py runserver
4. Rode as tarefas: python mindnutri_assinaturas\tarefas.py --loop
5. Se precisar de webhook externo: ngrok http 8000
```

---

## URLs do sistema

| URL | O que é |
|-----|---------|
| `http://127.0.0.1:8000/` | Painel web do gestor |
| `http://127.0.0.1:8000/login/` | Login do painel |
| `http://127.0.0.1:8000/assinantes/` | Lista de assinantes |
| `http://127.0.0.1:8000/fichas/` | Fichas geradas |
| `http://127.0.0.1:8000/notificacoes/` | Central de alertas |
| `http://127.0.0.1:8000/webhook/whatsapp/` | Recebe mensagens WA |
| `http://127.0.0.1:8000/webhook/asaas/` | Recebe eventos Asaas |

---

## Ir para produção (checklist)

Quando quiser sair do ambiente local e lançar de verdade:

- [ ] Contratar servidor VPS (Hetzner ou Contabo — R$ 60–120/mês)
- [ ] Instalar Ubuntu 22.04 no servidor
- [ ] Instalar Python, Docker, nginx, certbot (HTTPS)
- [ ] Trocar SQLite por PostgreSQL
- [ ] Trocar `ASAAS_BASE_URL` para `https://api.asaas.com/v3`
- [ ] Trocar `DEBUG=False` no settings.py
- [ ] Configurar domínio próprio (ex: api.mindnutri.com.br)
- [ ] Substituir ngrok pela URL do servidor nos webhooks
- [ ] Gerar política de privacidade e termos de uso (LGPD)
- [ ] Testar fluxo completo em produção antes de divulgar

---

## Resumo dos custos operacionais estimados

| Serviço | Custo mensal |
|---------|-------------|
| VPS (Hetzner CX21) | ~R$ 70 |
| Claude API (por ficha gerada) | ~R$ 0,10–0,30 |
| OpenAI Whisper (por áudio) | ~R$ 0,01/min |
| Asaas (por cobrança) | 0,99% + R$ 0,49 |
| Evolution API (self-hosted) | incluso no VPS |
| **Total com 50 clientes** | **~R$ 300–500/mês** |
| **Receita com 50 clientes** | **R$ 2.995/mês** |

---

## Suporte e próximos passos

Para dúvidas técnicas durante a implementação, volte aqui com prints
ou mensagens de erro — continuamos de onde paramos.

**Módulos entregues:**
- ✅ Gerador de XLSX e PDF (6 arquivos de exemplo)
- ✅ Painel web Django (dashboard, assinantes, fichas, notificações)
- ✅ Agente conversacional WhatsApp (Claude + Evolution API)
- ✅ Sistema de assinaturas Asaas (ciclo de vida completo)
- ✅ Este guia de integração
