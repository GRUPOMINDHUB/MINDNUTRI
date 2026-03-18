# Mindnutri — Painel de Gestão
### Instalação e execução no Windows

---

## Pré-requisitos

1. **Python 3.11+** — https://www.python.org/downloads/
   - Durante a instalação, marque ✅ **"Add Python to PATH"**
2. **Git** (opcional) — https://git-scm.com/download/win

---

## Instalação passo a passo

Abra o **Prompt de Comando** (CMD) ou **PowerShell** e execute:

### 1. Entre na pasta do projeto
```
cd caminho\para\mindnutri_painel
```

### 2. Crie o ambiente virtual
```
python -m venv venv
```

### 3. Ative o ambiente virtual
```
venv\Scripts\activate
```
> O terminal vai mostrar `(venv)` no início — isso indica que está ativo.

### 4. Instale as dependências
```
pip install django
```

### 5. Crie as tabelas no banco de dados
```
python manage.py migrate
```

### 6. Crie o usuário administrador
```
python manage.py createsuperuser
```
> Vai pedir: nome de usuário, e-mail (pode deixar em branco) e senha.

### 7. Popule o banco com dados de exemplo
```
python manage.py popular_dados
```
> Cria 8 assinantes fictícios, fichas e notificações para visualização.

### 8. Rode o servidor
```
python manage.py runserver
```

### 9. Abra no navegador
```
http://127.0.0.1:8000
```

---

## Estrutura do projeto

```
mindnutri_painel/
├── manage.py
├── db.sqlite3                  ← banco de dados (criado automaticamente)
├── core/
│   ├── settings.py             ← configurações gerais
│   ├── urls.py                 ← rotas raiz
│   └── wsgi.py
└── painel/
    ├── models.py               ← Assinante, FichaTecnica, Notificacao
    ├── views.py                ← lógica de cada página
    ├── urls.py                 ← rotas do painel
    ├── templates/painel/       ← HTML de cada página
    │   ├── base.html           ← layout base com sidebar
    │   ├── login.html
    │   ├── dashboard.html
    │   ├── assinantes.html
    │   ├── assinante_detalhe.html
    │   ├── fichas.html
    │   └── notificacoes.html
    ├── static/painel/img/      ← logo Mindhub
    └── management/commands/
        └── popular_dados.py    ← comando para dados de exemplo
```

---

## Páginas disponíveis

| URL | Descrição |
|-----|-----------|
| `/login/` | Tela de login |
| `/` | Dashboard com métricas |
| `/assinantes/` | Lista de assinantes com filtros |
| `/assinantes/<id>/` | Detalhe + ações de bloqueio/ativação |
| `/fichas/` | Histórico de todas as fichas geradas |
| `/notificacoes/` | Central de alertas do sistema |

---

## Comandos úteis do dia a dia

```bash
# Ativar ambiente virtual (sempre que abrir o CMD)
venv\Scripts\activate

# Rodar o servidor
python manage.py runserver

# Resetar banco e dados de exemplo (útil para testes)
del db.sqlite3
python manage.py migrate
python manage.py createsuperuser
python manage.py popular_dados

# Criar novo superusuário
python manage.py createsuperuser
```

---

## Próximos módulos

- [ ] Agente conversacional WhatsApp (Evolution API)
- [ ] Sistema de assinaturas Asaas (pagamentos automáticos)
- [ ] Geração de XLSX e PDF via agente
- [ ] Integração banco de ingredientes por assinante
