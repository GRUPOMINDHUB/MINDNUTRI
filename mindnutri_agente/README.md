# Mindnutri — Agente WhatsApp
### Instalação e configuração no Windows

---

## O que este módulo faz

- Recebe mensagens do WhatsApp via Evolution API (webhook)
- Processa texto, áudio (transcreve via Whisper) e imagens (analisa via Claude Vision)
- Conversa com o Claude para guiar a criação de fichas técnicas
- Gera arquivos XLSX e PDF profissionais e envia de volta ao cliente
- Controla assinaturas via Asaas (ativa, bloqueia, notifica)
- Envia alertas ao gestor via WhatsApp

---

## Pré-requisitos

1. Python 3.11+ com o painel já instalado
2. Conta na Anthropic: https://console.anthropic.com
3. Conta na OpenAI (para Whisper): https://platform.openai.com
4. Evolution API rodando (ver instruções abaixo)
5. Conta no Asaas: https://asaas.com

---

## Instalação

```bash
# Dentro da pasta mindnutri_agente:
cd mindnutri_agente

# Ative o ambiente virtual (o mesmo do painel)
..\venv\Scripts\activate

# Instale as dependências
pip install -r requirements.txt

# Execute o setup inicial
python setup.py
```

---

## Configuração do .env

Edite o arquivo `.env` criado pelo setup:

```env
ANTHROPIC_API_KEY=sk-ant-...        # Sua chave da Anthropic
OPENAI_API_KEY=sk-...               # Sua chave da OpenAI (Whisper)
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=sua-chave-evolution
EVOLUTION_INSTANCE=mindnutri
ASAAS_API_KEY=sua-chave-asaas
GESTOR_WHATSAPP=5511999999999       # Seu número para receber alertas
```

---

## Instalação da Evolution API (Windows)

A Evolution API é o gateway do WhatsApp. Use via Docker:

### 1. Instale o Docker Desktop
https://www.docker.com/products/docker-desktop/

### 2. Crie o arquivo docker-compose.yml
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
      - AUTHENTICATION_API_KEY=sua-chave-aqui
      - DATABASE_ENABLED=false
    restart: unless-stopped
```

### 3. Suba a Evolution API
```bash
docker-compose up -d
```

### 4. Crie a instância e conecte o WhatsApp
```bash
# Via curl ou Postman — cria a instância
curl -X POST http://localhost:8080/instance/create \
  -H "apikey: sua-chave-aqui" \
  -H "Content-Type: application/json" \
  -d '{"instanceName": "mindnutri", "qrcode": true}'

# QR Code fica disponível em:
# http://localhost:8080/instance/connect/mindnutri
```

Acesse a URL e escaneie o QR Code com o WhatsApp do número dedicado.

### 5. Configure o webhook para apontar ao Django
No painel da Evolution ou via API:
```
URL: http://localhost:8000/webhook/whatsapp/
Eventos: messages.upsert
```

---

## Rodando o servidor

```bash
# Com o venv ativo:
python manage.py runserver
```

O agente estará ouvindo em:
- `http://localhost:8000/webhook/whatsapp/` — mensagens do WhatsApp
- `http://localhost:8000/webhook/asaas/` — eventos de pagamento

---

## Expor para a internet (para webhooks funcionarem)

Para receber webhooks em ambiente de desenvolvimento, use ngrok:

```bash
# Instale ngrok: https://ngrok.com
ngrok http 8000
```

Copie a URL gerada (ex: `https://abc123.ngrok.io`) e configure nos webhooks:
- Evolution API: `https://abc123.ngrok.io/webhook/whatsapp/`
- Asaas: `https://abc123.ngrok.io/webhook/asaas/`

---

## Estrutura de arquivos gerados

```
arquivos_gerados/
└── 5511999999999/          ← pasta por número de telefone
    ├── BurgerClassico_20240315.xlsx
    ├── PizzaMargherita_20240315.pdf
    └── ...
```

---

## Fluxo completo de uma ficha técnica

```
Cliente: "oi"
Agente:  Apresentação + pergunta se quer ver exemplo

Cliente: "sim"
Agente:  Pergunta nicho → envia XLSX + PDF de exemplo

Cliente: "quero assinar"
Agente:  Envia link de pagamento Asaas

[Asaas confirma pagamento → webhook]
Agente:  Inicia onboarding (coleta nome, estabelecimento, etc.)

Cliente: "quero criar uma ficha"
Agente:  Pergunta nome do prato → ingredientes um a um
         → FC e IC (estima ou cliente informa)
         → custo de cada ingrediente
         → modo de preparo
         → "Posso gerar a ficha agora?"

Cliente: "sim"
Agente:  Gera XLSX ou PDF → envia no WhatsApp
```

---

## Webhooks do Asaas configurar

No painel do Asaas (Configurações → Notificações):
- URL: `https://seu-dominio/webhook/asaas/`
- Eventos: PAYMENT_CONFIRMED, PAYMENT_OVERDUE, SUBSCRIPTION_INACTIVATED
