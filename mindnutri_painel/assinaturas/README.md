# Mindnutri — Sistema de Assinaturas
### Integração completa com o Asaas

---

## Arquivos deste módulo

| Arquivo | O que faz |
|---------|-----------|
| `asaas_client.py` | Cliente HTTP da API Asaas — cria clientes, assinaturas, cobranças |
| `servico_assinaturas.py` | Lógica de negócio — ativar, bloquear, renovar, onboarding |
| `webhook_handler.py` | Roteia todos os eventos do Asaas para as ações corretas |
| `tarefas.py` | Jobs agendados — verifica vencimentos e limites de fichas |
| `testar_asaas.py` | Valida a integração com o Asaas Sandbox |

---

## Configuração do Asaas

### 1. Crie sua conta
- Sandbox: https://sandbox.asaas.com
- Produção: https://asaas.com

### 2. Obtenha a chave API
Asaas → Configurações → Integrações → Gerar token

### 3. Configure no .env
```env
ASAAS_API_KEY=$aact_...
ASAAS_BASE_URL=https://sandbox.asaas.com/api/v3
```
> Para produção: `https://api.asaas.com/v3`

### 4. Configure o webhook no Asaas
Asaas → Configurações → Notificações → Novo webhook:
```
URL:    https://SEU_DOMINIO/webhook/asaas/
Eventos marcar:
  ✅ PAYMENT_CONFIRMED
  ✅ PAYMENT_RECEIVED
  ✅ PAYMENT_OVERDUE
  ✅ PAYMENT_REFUNDED
  ✅ SUBSCRIPTION_INACTIVATED
```

---

## Teste a integração

```bash
cd mindnutri_assinaturas
python testar_asaas.py
```

---

## Ciclo de vida de uma assinatura

```
Cliente envia "quero assinar"
       ↓
iniciar_assinatura(telefone)
  → Cria cliente no Asaas
  → Cria assinatura recorrente mensal
  → Retorna link de pagamento

Cliente paga
       ↓
Webhook PAYMENT_CONFIRMED
  → ativar_assinante()
    → status = "ativo"
    → fichas_geradas_mes = 0
    → proxima_cobranca = hoje + 30 dias
    → Inicia onboarding (coleta nome, estabelecimento, etc.)

30 dias depois — renovação automática
       ↓
Webhook PAYMENT_CONFIRMED
  → renovar_assinante()
    → fichas_geradas_mes = 0
    → proxima_cobranca = hoje + 30 dias
    → Envia mensagem "renovado com sucesso"

Cliente não paga
       ↓
Webhook PAYMENT_OVERDUE
  → bloquear_por_inadimplencia()
    → status = "inadimplente"
    → Envia link de pagamento para regularizar

Cliente paga a dívida
       ↓
Webhook PAYMENT_CONFIRMED
  → ativar_assinante() (reativa)

Cliente cancela
       ↓
Webhook SUBSCRIPTION_INACTIVATED
  → cancelar_assinante()
    → status = "cancelado"
    → Envia mensagem de encerramento
```

---

## Tarefas agendadas (Windows — Agendador de Tarefas)

### Opção 1: Loop contínuo (mais simples)
```bash
# Deixe rodando em segundo plano
python tarefas.py --loop --intervalo 60
```

### Opção 2: Agendador de Tarefas do Windows
1. Abra "Agendador de Tarefas" → Criar Tarefa Básica
2. Configure para rodar diariamente às 09:00:
```
Programa: C:\caminho\para\venv\Scripts\python.exe
Argumentos: C:\caminho\para\mindnutri_assinaturas\tarefas.py --verificar-vencimentos
```
3. Repita para `--verificar-fichas` e `--resetar-fichas`

---

## Integração com o painel Django

O painel em `mindnutri_painel/` já exibe:
- Status de cada assinante (ativo/bloqueado/inadimplente)
- Botões para bloquear/ativar manualmente
- Central de notificações com todos os eventos

O banco SQLite é compartilhado entre o agente e o painel.
