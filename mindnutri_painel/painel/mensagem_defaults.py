# -*- coding: utf-8 -*-
"""
Catálogo de todas as mensagens do bot com textos padrão.
Cada entrada define: chave, categoria, descrição, texto, variáveis disponíveis e ordem.
Os textos usam {variavel} para substituição dinâmica via str.format().
"""

CATEGORIAS = [
    ("boas_vindas", "Boas-vindas"),
    ("menu", "Menu Principal"),
    ("coleta", "Coleta de Dados"),
    ("pagamento", "Pagamento"),
    ("fichas", "Fichas Técnicas"),
    ("operacional", "Ficha Operacional (PDF)"),
    ("erros", "Erros e Alertas"),
    ("renovacao", "Renovação"),
    ("webhook", "Webhook / Pós-pagamento"),
]

MENSAGENS_PADRAO = [
    # ══════════════════════════════════════════════════════════════════
    # BOAS-VINDAS
    # ══════════════════════════════════════════════════════════════════
    {
        "chave": "boas_vindas_inicial",
        "categoria": "boas_vindas",
        "descricao": "Primeira mensagem enviada ao novo contato, com opções de segmento para demo",
        "texto": (
            "Olá! 👋 Sou o *Mindnutri*, o assistente de fichas técnicas da *Mindhub*.\n\n"
            "Ajudo profissionais da gastronomia a criar fichas técnicas e operacionais "
            "com cálculo de custos, detalhamento de ingredientes e layout profissional. 📋\n\n"
            "Que tal eu te mostrar um exemplo do que sou capaz antes de começarmos?\n\n"
            "Escolha um segmento:\n\n"
            "1️⃣ Hambúrguer\n"
            "2️⃣ Pizza\n"
            "3️⃣ Sobremesa"
        ),
        "variaveis": "",
        "ordem": 10,
    },
    {
        "chave": "exemplo_nicho_intro",
        "categoria": "boas_vindas",
        "descricao": "Mensagem antes de enviar os arquivos de exemplo do segmento escolhido",
        "texto": "Aqui está um exemplo de ficha técnica e ficha operacional para o segmento de *{nicho_label}*: 📋",
        "variaveis": "nicho_label",
        "ordem": 20,
    },
    {
        "chave": "interesse_pos_demo",
        "categoria": "boas_vindas",
        "descricao": "Pergunta de interesse após enviar os arquivos de exemplo",
        "texto": (
            "E aí, gostou do resultado? 😊\n\n"
            "Quer saber mais sobre como o Mindnutri pode te ajudar no dia a dia?"
        ),
        "variaveis": "",
        "ordem": 25,
    },
    {
        "chave": "nao_tem_interesse",
        "categoria": "boas_vindas",
        "descricao": "Resposta educada quando o contato não demonstra interesse após o demo",
        "texto": (
            "Sem problema! Foi um prazer te mostrar o Mindnutri. 😊\n\n"
            "Se mudar de ideia, é só mandar um *oi* que eu te atendo!"
        ),
        "variaveis": "",
        "ordem": 26,
    },
    {
        "chave": "retorno_apos_abandono",
        "categoria": "boas_vindas",
        "descricao": "Mensagem quando o contato volta após 60+ minutos de inatividade",
        "texto": "Oi! Vi que você estava por aqui antes 😊\n\nQuer *continuar* de onde parou ou *começar do zero*?",
        "variaveis": "",
        "ordem": 30,
    },
    {
        "chave": "retorno_continuando",
        "categoria": "boas_vindas",
        "descricao": "Confirmação de que vai continuar de onde parou",
        "texto": "Ótimo! Continuando de onde você parou 😊",
        "variaveis": "",
        "ordem": 40,
    },
    {
        "chave": "retorno_instrucao",
        "categoria": "boas_vindas",
        "descricao": "Instrução quando resposta de retorno não é clara",
        "texto": "Responda *CONTINUAR* para retomar ou *ZERO* para começar do zero.",
        "variaveis": "",
        "ordem": 50,
    },

    # ══════════════════════════════════════════════════════════════════
    # MENU PRINCIPAL
    # ══════════════════════════════════════════════════════════════════
    {
        "chave": "menu_principal",
        "categoria": "menu",
        "descricao": "Menu principal para assinante ativo com opções e fichas restantes",
        "texto": (
            "Olá, {nome}! 😊 Como posso te ajudar hoje?\n\n"
            "📋 *1* — Criar ficha técnica (XLSX)\n"
            "📄 *2* — Criar ficha operacional (PDF)\n"
            "💰 *3* — Calcular custo rápido de um prato\n"
            "📦 *4* — Ver meus ingredientes cadastrados\n\n"
            "Fichas disponíveis este mês: *{fichas_rest}/30*\n\n"
            "Responda com o número ou descreva o que precisa!"
        ),
        "variaveis": "nome,fichas_rest",
        "ordem": 10,
    },
    {
        "chave": "pedir_metodo_pagamento",
        "categoria": "menu",
        "descricao": "Corpo do menu de escolha de método de pagamento (cartão ou Pix)",
        "texto": (
            "{abertura}\n\n"
            "1️⃣ *Cartão de crédito*\n"
            "Pagamento único do plano mensal.\n\n"
            "2️⃣ *Pix*\n"
            "Pagamento único via Pix.\n\n"
            "Responda com *1*, *2*, *CARTÃO* ou *PIX*."
        ),
        "variaveis": "abertura",
        "ordem": 20,
    },

    # ══════════════════════════════════════════════════════════════════
    # COLETA DE DADOS
    # ══════════════════════════════════════════════════════════════════
    {
        "chave": "prompt_coleta",
        "categoria": "coleta",
        "descricao": "System prompt do LLM para coleta de Nome e Instagram (NÃO é mensagem do WhatsApp)",
        "texto": (
            "Você é o assistente de cadastro do Mindnutri. "
            "Seu objetivo é coletar exatamente 2 dados do usuário, UM DE CADA VEZ, nesta ordem:\n"
            "1. Nome completo\n"
            "2. @ do Instagram DA LOJA/ESTABELECIMENTO (não o pessoal)\n\n"
            "REGRAS IMPORTANTES:\n"
            "- Peça APENAS UM dado por mensagem. Nunca peça dois de uma vez.\n"
            "- Comece pedindo o nome. Quando receber o nome, agradeça e peça o @ do Instagram da loja.\n"
            "- Ao pedir o Instagram, deixe claro que é o da LOJA/ESTABELECIMENTO: "
            "'Qual o @ do Instagram da sua loja? Se não tiver, pode me dizer NAO.'\n"
            "- Se o usuário já informou algum dado espontaneamente, absorva-o e peça apenas o próximo da lista.\n"
            "- Se o usuário não tiver Instagram, aceite 'NAO' como valor.\n"
            "- Quando tiver os 2 dados confirmados, chame OBRIGATORIAMENTE a função 'concluir_coleta_dados'.\n"
            "- Seja educado, direto e acolhedor. Use mensagens curtas.\n"
            "- PROIBIDO ABSOLUTO: jamais pergunte dados de cartão de crédito, número de cartão, "
            "senha, CVV, data de validade, dados bancários, CPF ou qualquer informação financeira.\n"
            "- Se o usuário mencionar pagamento, cartão, PIX ou link, responda apenas: "
            "'Primeiro vamos finalizar seu cadastro! Me diz [dado que falta]?'"
        ),
        "variaveis": "",
        "ordem": 10,
    },
    {
        "chave": "dados_coletados_pagamento",
        "categoria": "coleta",
        "descricao": "Mensagem após coletar nome e Instagram — apresenta opções de pagamento",
        "texto": (
            "Perfeito, {nome}! 🎉\n\n"
            "Agora vamos para o pagamento.\n\n"
            "Como você prefere pagar?\n\n"
            "1️⃣ Cartão de crédito\n"
            "2️⃣ Pix\n\n"
            "Responda *1*, *2*, *CARTÃO* ou *PIX*."
        ),
        "variaveis": "nome",
        "ordem": 20,
    },
    {
        "chave": "dados_coleta_erro",
        "categoria": "coleta",
        "descricao": "Quando o LLM não conseguiu confirmar os dados do cadastro",
        "texto": "Não consegui confirmar os dados. Pode reenviar seu nome e @ do Instagram?",
        "variaveis": "",
        "ordem": 30,
    },
    {
        "chave": "dados_coleta_quase_la",
        "categoria": "coleta",
        "descricao": "Quando faltam dados no cadastro",
        "texto": "Quase lá! Me envie o que faltou: nome completo e @ do Instagram.",
        "variaveis": "",
        "ordem": 40,
    },
    {
        "chave": "dados_coleta_vazio",
        "categoria": "coleta",
        "descricao": "Quando o LLM não retorna conteúdo na coleta",
        "texto": "Estou aqui para finalizar seu cadastro. Me envie seu nome e @ do Instagram.",
        "variaveis": "",
        "ordem": 50,
    },
    {
        "chave": "dados_coleta_instabilidade",
        "categoria": "coleta",
        "descricao": "Erro de processamento durante a coleta de dados",
        "texto": "Tive uma instabilidade rápida. Pode me enviar seu nome e Instagram novamente?",
        "variaveis": "",
        "ordem": 60,
    },

    # ══════════════════════════════════════════════════════════════════
    # PAGAMENTO
    # ══════════════════════════════════════════════════════════════════
    {
        "chave": "oferta_pos_demo",
        "categoria": "pagamento",
        "descricao": "Oferta de assinatura após enviar exemplo do segmento",
        "texto": (
            "Gostou? Com o Mindnutri você cria fichas assim para todos os seus pratos, "
            "com seus ingredientes, seus custos e sua marca. 🚀\n\n"
            "*Plano Mensal: R$ {valor}/mês*\n"
            "✅ 30 fichas por mês\n"
            "✅ XLSX + PDF profissionais\n"
            "✅ Cálculo de custos instantâneo\n"
            "✅ Base de ingredientes sempre atualizada\n\n"
            "Quer assinar agora?\n\n"
            "Responda *ASSINAR* para continuar."
        ),
        "variaveis": "valor",
        "ordem": 10,
    },
    {
        "chave": "nao_quer_assinar",
        "categoria": "pagamento",
        "descricao": "Resposta quando o contato não quer assinar agora",
        "texto": "Sem problema! Quando quiser assinar é só responder *ASSINAR*. 😊",
        "variaveis": "",
        "ordem": 20,
    },
    {
        "chave": "troca_metodo_pagamento",
        "categoria": "pagamento",
        "descricao": "Confirmação de troca de método de pagamento",
        "texto": "Perfeito, vou trocar para *{metodo}*.",
        "variaveis": "metodo",
        "ordem": 30,
    },
    {
        "chave": "aguardando_pagamento",
        "categoria": "pagamento",
        "descricao": "Quando o contato manda mensagem durante aguardo de pagamento",
        "texto": (
            "Ainda aguardando a confirmação do seu pagamento.\n\n"
            "Assim que compensar, seu acesso é liberado automaticamente. 😊"
        ),
        "variaveis": "",
        "ordem": 40,
    },
    {
        "chave": "link_cartao",
        "categoria": "pagamento",
        "descricao": "Mensagem com link de pagamento por cartão de crédito",
        "texto": (
            "Aqui está seu link de pagamento por *cartão de crédito*:\n\n"
            "🔗 {link}\n\n"
            "Assim que aprovado, seu acesso é liberado na hora! 🎉"
        ),
        "variaveis": "link",
        "ordem": 50,
    },
    {
        "chave": "link_pix",
        "categoria": "pagamento",
        "descricao": "Mensagem com link de pagamento por Pix",
        "texto": (
            "Aqui está seu link de pagamento em *Pix*:\n\n"
            "🔗 {link}\n\n"
            "{bloco_codigo_pix}"
            "Assim que confirmado, seu acesso é liberado automaticamente! 🎉"
        ),
        "variaveis": "link,bloco_codigo_pix",
        "ordem": 60,
    },
    {
        "chave": "pix_nao_habilitado",
        "categoria": "pagamento",
        "descricao": "Quando o Pix não está habilitado no Asaas",
        "texto": (
            "O Pix ainda não está habilitado nesta conta.\n\n"
            "Posso te enviar o link por *cartão de crédito*. Responda *CARTÃO* para continuar."
        ),
        "variaveis": "",
        "ordem": 70,
    },
    {
        "chave": "erro_asaas_generico",
        "categoria": "pagamento",
        "descricao": "Erro genérico ao gerar link de pagamento no Asaas",
        "texto": (
            "Desculpe, tive um problema técnico ao gerar seu link. 😔\n\n"
            "Entre em contato com o suporte: {gestor_whatsapp}\n\n"
            "Ou responda *ASSINAR* para tentar novamente!"
        ),
        "variaveis": "gestor_whatsapp",
        "ordem": 80,
    },
    {
        "chave": "alerta_gestor_asaas",
        "categoria": "pagamento",
        "descricao": "Alerta enviado ao gestor quando o Asaas falha (NÃO é para o cliente)",
        "texto": (
            "🚨 *Alerta Mindnutri — Asaas Falhou*\n\n"
            "Cliente {telefone} tentou assinar mas o Asaas retornou erro:\n"
            "{erro}"
        ),
        "variaveis": "telefone,erro",
        "ordem": 90,
    },

    {
        "chave": "cupom_aplicado",
        "categoria": "pagamento",
        "descricao": "Confirmação de que o cupom foi aplicado com sucesso",
        "texto": (
            "🎟️ Cupom *{codigo}* aplicado!\n\n"
            "Seu primeiro pagamento será de *R$ {valor}* (em vez de R$ {valor_normal}).\n\n"
            "Pode continuar normalmente — o desconto já está garantido! 😊"
        ),
        "variaveis": "codigo,valor,valor_normal",
        "ordem": 95,
    },

    # ══════════════════════════════════════════════════════════════════
    # FICHAS TÉCNICAS
    # ══════════════════════════════════════════════════════════════════
    {
        "chave": "aviso_fichas_poucas",
        "categoria": "fichas",
        "descricao": "Aviso quando restam 3 ou menos fichas no mês",
        "texto": "⚠️ Atenção: você tem apenas *{fichas_rest} fichas restantes* este mês.",
        "variaveis": "fichas_rest",
        "ordem": 10,
    },
    {
        "chave": "limite_fichas_atingido",
        "categoria": "fichas",
        "descricao": "Quando o assinante atingiu o limite de fichas do mês",
        "texto": (
            "⚠️ Você atingiu o limite de 30 fichas este mês.\n\n"
            "Deseja renovar antecipadamente? Responda *SIM* para receber o link."
        ),
        "variaveis": "",
        "ordem": 20,
    },
    {
        "chave": "confirmar_cancelar_ficha",
        "categoria": "fichas",
        "descricao": "Pedido de confirmação para cancelar ficha em andamento",
        "texto": (
            "Tem certeza que quer cancelar esta ficha?\n\n"
            "Vai perder os dados do prato atual.\n\n"
            "Responda *SIM* para cancelar ou *NÃO* para continuar."
        ),
        "variaveis": "",
        "ordem": 30,
    },
    {
        "chave": "continuando_ficha_atual",
        "categoria": "fichas",
        "descricao": "Quando o assinante decide não cancelar a ficha atual",
        "texto": "Ok, continuando com a ficha atual!",
        "variaveis": "",
        "ordem": 40,
    },
    {
        "chave": "cancelei_geracao",
        "categoria": "fichas",
        "descricao": "Confirmação de cancelamento da geração de arquivo",
        "texto": "Ok, cancelei a geração. Se quiser ajustar algo, é só me dizer! 😊",
        "variaveis": "",
        "ordem": 50,
    },
    {
        "chave": "gerando_combo",
        "categoria": "fichas",
        "descricao": "Aviso de que está gerando ficha técnica + operacional",
        "texto": "⏳ Gerando sua Ficha Técnica e a Ficha Operacional de *{nome_prato}*... aguarde um instante!",
        "variaveis": "nome_prato",
        "ordem": 60,
    },
    {
        "chave": "gerando_ficha",
        "categoria": "fichas",
        "descricao": "Aviso de que está gerando uma ficha (single)",
        "texto": "⏳ Gerando sua ficha de *{nome_prato}*... aguarde um instante!",
        "variaveis": "nome_prato",
        "ordem": 70,
    },
    {
        "chave": "ficha_gerada_sucesso",
        "categoria": "fichas",
        "descricao": "Confirmação de que a ficha foi gerada com sucesso",
        "texto": (
            "✅ Ficha gerada com sucesso!\n\n"
            "Fichas restantes este mês: *{fichas_rest}/30*\n\n"
            "Quer criar outra ficha ou calcular algum custo?"
        ),
        "variaveis": "fichas_rest",
        "ordem": 80,
    },

    # ══════════════════════════════════════════════════════════════════
    # FICHA OPERACIONAL (PDF)
    # ══════════════════════════════════════════════════════════════════
    {
        "chave": "pergunta_ficha_operacional",
        "categoria": "operacional",
        "descricao": "Pergunta se quer gerar também o PDF operacional",
        "texto": "Deseja gerar também a Ficha Operacional ilustrada em PDF para sua cozinha?",
        "variaveis": "",
        "ordem": 10,
    },
    {
        "chave": "somente_tecnica",
        "categoria": "operacional",
        "descricao": "Confirmação de que vai gerar somente a ficha técnica (sem PDF)",
        "texto": "Beleza! Vou gerar somente a Ficha Técnica em Excel para você. Aguarde um instante! 📊",
        "variaveis": "",
        "ordem": 20,
    },
    {
        "chave": "confirmar_sim_nao_pdf",
        "categoria": "operacional",
        "descricao": "Pede confirmação SIM/NÃO para gerar o PDF operacional",
        "texto": "Me confirma com *SIM* para gerar o PDF operacional também, ou *NÃO* para seguir apenas com o Excel.",
        "variaveis": "",
        "ordem": 30,
    },
    {
        "chave": "aguardando_foto",
        "categoria": "operacional",
        "descricao": "Pedido de foto do prato para a ficha operacional",
        "texto": "Perfeito! Me envie agora a foto do prato para montar a ficha operacional ilustrada.",
        "variaveis": "",
        "ordem": 40,
    },
    {
        "chave": "aguardando_modo_preparo",
        "categoria": "operacional",
        "descricao": "Pedido do modo de preparo para a ficha operacional",
        "texto": "Agora me envie o modo de preparo (passo a passo) para completar o PDF operacional.",
        "variaveis": "",
        "ordem": 50,
    },
    {
        "chave": "foto_recebida",
        "categoria": "operacional",
        "descricao": "Confirmação de recebimento da foto do prato",
        "texto": "Foto recebida com sucesso! ✅",
        "variaveis": "",
        "ordem": 60,
    },
    {
        "chave": "sem_foto_seguir",
        "categoria": "operacional",
        "descricao": "Quando o contato não quer enviar foto e segue sem",
        "texto": "Sem problemas. Podemos seguir sem foto, mas o PDF fica melhor com imagem. Me envie o modo de preparo.",
        "variaveis": "",
        "ordem": 70,
    },
    {
        "chave": "foto_ainda_necessaria",
        "categoria": "operacional",
        "descricao": "Reforço pedindo a foto quando o contato manda texto em vez de imagem",
        "texto": "Ainda preciso da foto do prato. Envie uma imagem para continuar.",
        "variaveis": "",
        "ordem": 80,
    },
    {
        "chave": "modo_preparo_nao_identificado",
        "categoria": "operacional",
        "descricao": "Quando não consegue interpretar o modo de preparo enviado",
        "texto": "Não consegui identificar o passo a passo. Pode enviar o modo de preparo em texto (um passo por linha)?",
        "variaveis": "",
        "ordem": 90,
    },

    # ══════════════════════════════════════════════════════════════════
    # ERROS E ALERTAS
    # ══════════════════════════════════════════════════════════════════
    {
        "chave": "foto_nao_salva",
        "categoria": "erros",
        "descricao": "Quando não consegue salvar a foto enviada",
        "texto": "Não consegui salvar sua foto. Pode tentar enviar novamente?",
        "variaveis": "",
        "ordem": 10,
    },
    {
        "chave": "audio_nao_transcrito",
        "categoria": "erros",
        "descricao": "Quando não consegue transcrever o áudio enviado",
        "texto": "Não consegui transcrever o áudio. Pode repetir por texto?",
        "variaveis": "",
        "ordem": 20,
    },
    {
        "chave": "mensagem_nao_entendida",
        "categoria": "erros",
        "descricao": "Quando não consegue processar a mensagem recebida",
        "texto": "Não consegui entender sua mensagem. Pode repetir por texto?",
        "variaveis": "",
        "ordem": 30,
    },
    {
        "chave": "confirmar_reset",
        "categoria": "erros",
        "descricao": "Pedido de confirmação para começar do zero",
        "texto": (
            "Tem certeza que quer começar do zero?\n\n"
            "Vai perder o progresso atual.\n\n"
            "Responda *SIM* para confirmar ou *NÃO* para continuar."
        ),
        "variaveis": "",
        "ordem": 40,
    },
    {
        "chave": "continuar_de_onde_parou",
        "categoria": "erros",
        "descricao": "Quando o contato decide não resetar e continua",
        "texto": "Ok! Continuando de onde você parou.",
        "variaveis": "",
        "ordem": 50,
    },
    {
        "chave": "acesso_suspenso",
        "categoria": "erros",
        "descricao": "Quando o assinante está bloqueado ou inadimplente",
        "texto": (
            "Seu acesso está suspenso no momento.\n\n"
            "Para regularizar, acesse o link de pagamento ou entre em contato com o suporte Mindhub."
        ),
        "variaveis": "",
        "ordem": 60,
    },
    {
        "chave": "assinatura_cancelada",
        "categoria": "erros",
        "descricao": "Quando o assinante está cancelado",
        "texto": "Sua assinatura foi cancelada. Para reativar, entre em contato com a Mindhub.",
        "variaveis": "",
        "ordem": 70,
    },
    {
        "chave": "erro_gerar_ficha",
        "categoria": "erros",
        "descricao": "Erro durante a geração de arquivo (XLSX ou PDF)",
        "texto": "⚠️ Ocorreu um erro ao gerar a ficha. Nossa equipe foi notificada. Tente novamente em instantes!",
        "variaveis": "",
        "ordem": 80,
    },
    {
        "chave": "falha_entender_1",
        "categoria": "erros",
        "descricao": "Primeira falha de compreensão (1 de 3)",
        "texto": "Não consegui entender sua mensagem. Pode repetir de outra forma? 😊",
        "variaveis": "",
        "ordem": 90,
    },
    {
        "chave": "falha_entender_2",
        "categoria": "erros",
        "descricao": "Segunda falha de compreensão (2 de 3)",
        "texto": "Ainda não consegui entender. Tente descrever o que precisa em poucas palavras.",
        "variaveis": "",
        "ordem": 100,
    },
    {
        "chave": "falha_entender_3",
        "categoria": "erros",
        "descricao": "Terceira falha — aciona equipe (3 de 3)",
        "texto": "Parece que estou com dificuldade em entender. Vou acionar nossa equipe para te ajudar em breve! 🙏",
        "variaveis": "",
        "ordem": 110,
    },
    {
        "chave": "alerta_gestor_nao_entendeu",
        "categoria": "erros",
        "descricao": "Alerta ao gestor quando o bot não entende 3 vezes (NÃO é para o cliente)",
        "texto": (
            "⚠️ Alerta Mindnutri\n\n"
            "O cliente *{nome}* ({telefone}) enviou 3 mensagens que o agente não conseguiu interpretar.\n"
            "Pode ser necessário atendimento manual."
        ),
        "variaveis": "nome,telefone",
        "ordem": 120,
    },
    {
        "chave": "exemplo_nicho_erro",
        "categoria": "erros",
        "descricao": "Quando os arquivos de exemplo não são encontrados",
        "texto": (
            "Tive um problema técnico ao buscar esse exemplo. "
            "Pode assinar e testar com seus dados! 🚀\n\n"
            "Responda *ASSINAR* para começar."
        ),
        "variaveis": "",
        "ordem": 130,
    },

    # ══════════════════════════════════════════════════════════════════
    # RENOVAÇÃO
    # ══════════════════════════════════════════════════════════════════
    {
        "chave": "link_renovacao",
        "categoria": "renovacao",
        "descricao": "Link de renovação antecipada enviado ao assinante",
        "texto": (
            "Aqui está seu link para renovação via *{metodo}*:\n\n"
            "🔗 {link}\n\n"
            "Após o pagamento, suas fichas são renovadas automaticamente."
        ),
        "variaveis": "metodo,link",
        "ordem": 10,
    },
    {
        "chave": "erro_renovacao",
        "categoria": "renovacao",
        "descricao": "Erro ao gerar link de renovação",
        "texto": "Em instantes nossa equipe te enviará o link de renovação.",
        "variaveis": "",
        "ordem": 20,
    },

    # ══════════════════════════════════════════════════════════════════
    # WEBHOOK / PÓS-PAGAMENTO
    # ══════════════════════════════════════════════════════════════════
    {
        "chave": "webhook_pagamento_renovado",
        "categoria": "webhook",
        "descricao": "Mensagem quando pagamento recorrente é confirmado (renovação de ciclo)",
        "texto": (
            "Pagamento recebido com sucesso.\n\n"
            "Seu ciclo do Mindnutri foi renovado e suas fichas do mês foram liberadas novamente."
        ),
        "variaveis": "",
        "ordem": 10,
    },
    {
        "chave": "webhook_pagamento_atraso",
        "categoria": "webhook",
        "descricao": "Mensagem quando pagamento está em atraso e acesso é suspenso",
        "texto": (
            "Seu pagamento está em atraso e seu acesso foi suspenso.\n\n"
            "Para reativar, acesse o link abaixo ou entre em contato com nosso suporte."
        ),
        "variaveis": "",
        "ordem": 20,
    },
    {
        "chave": "webhook_boas_vindas",
        "categoria": "webhook",
        "descricao": "Boas-vindas enviada após confirmação do primeiro pagamento",
        "texto": (
            "🎉 Pagamento confirmado! Seja bem-vindo ao *Mindnutri*, {nome}!\n\n"
            "Sua assinatura está ativa. Você já pode criar fichas técnicas e operacionais "
            "profissionais para o seu negócio.\n\n"
            "Você tem *{fichas_rest} fichas disponíveis* neste mês.\n\n"
            "Por qual produto você quer começar? Me diga o nome do prato! 🍽️"
        ),
        "variaveis": "nome,fichas_rest",
        "ordem": 30,
    },
]
