"""
Base de conhecimento de perdas padrao — FC (Fator de Correcao) e IC (Indice de Coccao).
Valores baseados em tabelas tecnicas de food service (TACO, Ornellas, Philippi).

FC = peso_bruto / peso_liquido (perda na limpeza: casca, osso, sementes, gordura visivel)
IC = peso_cozido / peso_cru (perda ou ganho na coccao)

perda_percentual = percentual que se PERDE do peso original
- Limpeza: perda = (1 - 1/FC) * 100
- Coccao: perda = (1 - IC) * 100

Editavel pelo painel em Configuracoes > Perdas.
"""

PERDAS_PADRAO = [
    # ══════════════════════════════════════════════════════════════
    # CARNES BOVINAS
    # ══════════════════════════════════════════════════════════════
    {"nome": "Blend bovino (hamburguer)", "categoria": "carnes", "perda_percentual": 22, "tipo_perda": "coccao"},
    {"nome": "Carne moida", "categoria": "carnes", "perda_percentual": 28, "tipo_perda": "coccao"},
    {"nome": "Picanha", "categoria": "carnes", "perda_percentual": 30, "tipo_perda": "coccao"},
    {"nome": "Alcatra", "categoria": "carnes", "perda_percentual": 25, "tipo_perda": "coccao"},
    {"nome": "Contra-file", "categoria": "carnes", "perda_percentual": 25, "tipo_perda": "coccao"},
    {"nome": "Costela bovina", "categoria": "carnes", "perda_percentual": 42, "tipo_perda": "coccao"},
    {"nome": "Acem", "categoria": "carnes", "perda_percentual": 35, "tipo_perda": "coccao"},
    {"nome": "Patinho", "categoria": "carnes", "perda_percentual": 25, "tipo_perda": "coccao"},
    {"nome": "Musculo", "categoria": "carnes", "perda_percentual": 35, "tipo_perda": "coccao"},
    {"nome": "Cupim", "categoria": "carnes", "perda_percentual": 40, "tipo_perda": "coccao"},
    {"nome": "File mignon", "categoria": "carnes", "perda_percentual": 20, "tipo_perda": "coccao"},
    {"nome": "Maminha", "categoria": "carnes", "perda_percentual": 28, "tipo_perda": "coccao"},
    {"nome": "Fraldinha", "categoria": "carnes", "perda_percentual": 30, "tipo_perda": "coccao"},
    {"nome": "Coxao mole", "categoria": "carnes", "perda_percentual": 25, "tipo_perda": "coccao"},
    {"nome": "Coxao duro", "categoria": "carnes", "perda_percentual": 28, "tipo_perda": "coccao"},
    {"nome": "Lagarto", "categoria": "carnes", "perda_percentual": 30, "tipo_perda": "coccao"},
    {"nome": "Paleta bovina", "categoria": "carnes", "perda_percentual": 35, "tipo_perda": "coccao"},
    {"nome": "T-bone / Bisteca", "categoria": "carnes", "perda_percentual": 30, "tipo_perda": "coccao"},
    {"nome": "Carne seca / charque", "categoria": "carnes", "perda_percentual": 15, "tipo_perda": "coccao"},
    {"nome": "Carne de sol", "categoria": "carnes", "perda_percentual": 20, "tipo_perda": "coccao"},
    {"nome": "Rabada", "categoria": "carnes", "perda_percentual": 45, "tipo_perda": "coccao"},
    {"nome": "Figado bovino", "categoria": "carnes", "perda_percentual": 20, "tipo_perda": "coccao"},

    # ══════════════════════════════════════════════════════════════
    # AVES
    # ══════════════════════════════════════════════════════════════
    {"nome": "Frango inteiro", "categoria": "carnes", "perda_percentual": 33, "tipo_perda": "limpeza"},
    {"nome": "Peito de frango", "categoria": "carnes", "perda_percentual": 25, "tipo_perda": "coccao"},
    {"nome": "Peito de frango (com pele)", "categoria": "carnes", "perda_percentual": 30, "tipo_perda": "coccao"},
    {"nome": "Coxa de frango", "categoria": "carnes", "perda_percentual": 30, "tipo_perda": "coccao"},
    {"nome": "Sobrecoxa de frango", "categoria": "carnes", "perda_percentual": 28, "tipo_perda": "coccao"},
    {"nome": "Coxa e sobrecoxa", "categoria": "carnes", "perda_percentual": 30, "tipo_perda": "coccao"},
    {"nome": "File de frango", "categoria": "carnes", "perda_percentual": 20, "tipo_perda": "coccao"},
    {"nome": "Asa de frango", "categoria": "carnes", "perda_percentual": 30, "tipo_perda": "coccao"},
    {"nome": "Frango desfiado", "categoria": "carnes", "perda_percentual": 35, "tipo_perda": "coccao"},
    {"nome": "Peru (peito)", "categoria": "carnes", "perda_percentual": 25, "tipo_perda": "coccao"},

    # ══════════════════════════════════════════════════════════════
    # SUINOS E EMBUTIDOS
    # ══════════════════════════════════════════════════════════════
    {"nome": "Bacon", "categoria": "carnes", "perda_percentual": 52, "tipo_perda": "coccao"},
    {"nome": "Bacon em cubos", "categoria": "carnes", "perda_percentual": 48, "tipo_perda": "coccao"},
    {"nome": "Pancetta", "categoria": "carnes", "perda_percentual": 45, "tipo_perda": "coccao"},
    {"nome": "Linguica calabresa", "categoria": "carnes", "perda_percentual": 18, "tipo_perda": "coccao"},
    {"nome": "Linguica toscana", "categoria": "carnes", "perda_percentual": 25, "tipo_perda": "coccao"},
    {"nome": "Linguica de frango", "categoria": "carnes", "perda_percentual": 22, "tipo_perda": "coccao"},
    {"nome": "Pernil suino", "categoria": "carnes", "perda_percentual": 35, "tipo_perda": "coccao"},
    {"nome": "Lombo suino", "categoria": "carnes", "perda_percentual": 25, "tipo_perda": "coccao"},
    {"nome": "Costela suina", "categoria": "carnes", "perda_percentual": 40, "tipo_perda": "coccao"},
    {"nome": "Bisteca suina", "categoria": "carnes", "perda_percentual": 28, "tipo_perda": "coccao"},
    {"nome": "Presunto", "categoria": "carnes", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Salame", "categoria": "carnes", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Pepperoni", "categoria": "carnes", "perda_percentual": 12, "tipo_perda": "coccao"},
    {"nome": "Salsicha", "categoria": "carnes", "perda_percentual": 10, "tipo_perda": "coccao"},
    {"nome": "Mortadela", "categoria": "carnes", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Tender", "categoria": "carnes", "perda_percentual": 15, "tipo_perda": "coccao"},

    # ══════════════════════════════════════════════════════════════
    # PEIXES E FRUTOS DO MAR
    # ══════════════════════════════════════════════════════════════
    {"nome": "Salmao (file)", "categoria": "carnes", "perda_percentual": 20, "tipo_perda": "coccao"},
    {"nome": "Salmao inteiro", "categoria": "carnes", "perda_percentual": 45, "tipo_perda": "limpeza"},
    {"nome": "Tilapia (file)", "categoria": "carnes", "perda_percentual": 18, "tipo_perda": "coccao"},
    {"nome": "Bacalhau", "categoria": "carnes", "perda_percentual": 33, "tipo_perda": "limpeza"},
    {"nome": "Camarao com casca", "categoria": "carnes", "perda_percentual": 40, "tipo_perda": "limpeza"},
    {"nome": "Camarao limpo", "categoria": "carnes", "perda_percentual": 15, "tipo_perda": "coccao"},
    {"nome": "Atum (file)", "categoria": "carnes", "perda_percentual": 18, "tipo_perda": "coccao"},
    {"nome": "Sardinha", "categoria": "carnes", "perda_percentual": 35, "tipo_perda": "limpeza"},
    {"nome": "Lula", "categoria": "carnes", "perda_percentual": 30, "tipo_perda": "limpeza"},
    {"nome": "Polvo", "categoria": "carnes", "perda_percentual": 40, "tipo_perda": "coccao"},
    {"nome": "Mexilhao", "categoria": "carnes", "perda_percentual": 55, "tipo_perda": "limpeza"},

    # ══════════════════════════════════════════════════════════════
    # LATICINIOS E OVOS
    # ══════════════════════════════════════════════════════════════
    {"nome": "Queijo mussarela", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Queijo mussarela (gratinado)", "categoria": "laticinios", "perda_percentual": 15, "tipo_perda": "coccao"},
    {"nome": "Queijo cheddar", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Queijo prato", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Queijo parmesao", "categoria": "laticinios", "perda_percentual": 5, "tipo_perda": "limpeza"},
    {"nome": "Queijo coalho", "categoria": "laticinios", "perda_percentual": 10, "tipo_perda": "coccao"},
    {"nome": "Queijo gorgonzola", "categoria": "laticinios", "perda_percentual": 5, "tipo_perda": "limpeza"},
    {"nome": "Queijo brie", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Cream cheese", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Requeijao", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Catupiry", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Leite", "categoria": "laticinios", "perda_percentual": 8, "tipo_perda": "coccao"},
    {"nome": "Creme de leite", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Leite condensado", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Manteiga", "categoria": "laticinios", "perda_percentual": 8, "tipo_perda": "coccao"},
    {"nome": "Ovo inteiro (com casca)", "categoria": "laticinios", "perda_percentual": 12, "tipo_perda": "limpeza"},
    {"nome": "Ovo (cozido/frito)", "categoria": "laticinios", "perda_percentual": 10, "tipo_perda": "coccao"},
    {"nome": "Nata", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Iogurte natural", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Leite de coco", "categoria": "laticinios", "perda_percentual": 0, "tipo_perda": "nenhuma"},

    # ══════════════════════════════════════════════════════════════
    # VEGETAIS — FOLHAS
    # ══════════════════════════════════════════════════════════════
    {"nome": "Alface americana", "categoria": "vegetais", "perda_percentual": 29, "tipo_perda": "limpeza"},
    {"nome": "Alface crespa", "categoria": "vegetais", "perda_percentual": 25, "tipo_perda": "limpeza"},
    {"nome": "Alface lisa", "categoria": "vegetais", "perda_percentual": 22, "tipo_perda": "limpeza"},
    {"nome": "Rucula", "categoria": "vegetais", "perda_percentual": 20, "tipo_perda": "limpeza"},
    {"nome": "Espinafre", "categoria": "vegetais", "perda_percentual": 35, "tipo_perda": "limpeza"},
    {"nome": "Espinafre (refogado)", "categoria": "vegetais", "perda_percentual": 60, "tipo_perda": "coccao"},
    {"nome": "Couve", "categoria": "vegetais", "perda_percentual": 20, "tipo_perda": "limpeza"},
    {"nome": "Repolho", "categoria": "vegetais", "perda_percentual": 15, "tipo_perda": "limpeza"},
    {"nome": "Agriao", "categoria": "vegetais", "perda_percentual": 30, "tipo_perda": "limpeza"},
    {"nome": "Acelga", "categoria": "vegetais", "perda_percentual": 22, "tipo_perda": "limpeza"},
    {"nome": "Chicoria", "categoria": "vegetais", "perda_percentual": 25, "tipo_perda": "limpeza"},

    # ══════════════════════════════════════════════════════════════
    # VEGETAIS — FRUTOS, RAIZES E TUBERCULOS
    # ══════════════════════════════════════════════════════════════
    {"nome": "Tomate", "categoria": "vegetais", "perda_percentual": 12, "tipo_perda": "limpeza"},
    {"nome": "Tomate (sem semente)", "categoria": "vegetais", "perda_percentual": 25, "tipo_perda": "limpeza"},
    {"nome": "Tomate cereja", "categoria": "vegetais", "perda_percentual": 5, "tipo_perda": "limpeza"},
    {"nome": "Cebola", "categoria": "vegetais", "perda_percentual": 13, "tipo_perda": "limpeza"},
    {"nome": "Cebola roxa", "categoria": "vegetais", "perda_percentual": 13, "tipo_perda": "limpeza"},
    {"nome": "Cebola (caramelizada)", "categoria": "vegetais", "perda_percentual": 50, "tipo_perda": "coccao"},
    {"nome": "Alho", "categoria": "vegetais", "perda_percentual": 25, "tipo_perda": "limpeza"},
    {"nome": "Alho-poro", "categoria": "vegetais", "perda_percentual": 40, "tipo_perda": "limpeza"},
    {"nome": "Batata", "categoria": "vegetais", "perda_percentual": 17, "tipo_perda": "limpeza"},
    {"nome": "Batata (frita)", "categoria": "vegetais", "perda_percentual": 35, "tipo_perda": "coccao"},
    {"nome": "Batata-doce", "categoria": "vegetais", "perda_percentual": 17, "tipo_perda": "limpeza"},
    {"nome": "Mandioca", "categoria": "vegetais", "perda_percentual": 23, "tipo_perda": "limpeza"},
    {"nome": "Mandioca (frita)", "categoria": "vegetais", "perda_percentual": 30, "tipo_perda": "coccao"},
    {"nome": "Inhame", "categoria": "vegetais", "perda_percentual": 18, "tipo_perda": "limpeza"},
    {"nome": "Cenoura", "categoria": "vegetais", "perda_percentual": 17, "tipo_perda": "limpeza"},
    {"nome": "Beterraba", "categoria": "vegetais", "perda_percentual": 17, "tipo_perda": "limpeza"},
    {"nome": "Pimentao verde", "categoria": "vegetais", "perda_percentual": 18, "tipo_perda": "limpeza"},
    {"nome": "Pimentao vermelho", "categoria": "vegetais", "perda_percentual": 18, "tipo_perda": "limpeza"},
    {"nome": "Pimenta jalapeño", "categoria": "vegetais", "perda_percentual": 15, "tipo_perda": "limpeza"},
    {"nome": "Pepino", "categoria": "vegetais", "perda_percentual": 10, "tipo_perda": "limpeza"},
    {"nome": "Abobrinha", "categoria": "vegetais", "perda_percentual": 5, "tipo_perda": "limpeza"},
    {"nome": "Berinjela", "categoria": "vegetais", "perda_percentual": 10, "tipo_perda": "limpeza"},
    {"nome": "Quiabo", "categoria": "vegetais", "perda_percentual": 15, "tipo_perda": "limpeza"},
    {"nome": "Jilo", "categoria": "vegetais", "perda_percentual": 10, "tipo_perda": "limpeza"},
    {"nome": "Chuchu", "categoria": "vegetais", "perda_percentual": 15, "tipo_perda": "limpeza"},
    {"nome": "Vagem", "categoria": "vegetais", "perda_percentual": 12, "tipo_perda": "limpeza"},
    {"nome": "Brocolis", "categoria": "vegetais", "perda_percentual": 40, "tipo_perda": "limpeza"},
    {"nome": "Couve-flor", "categoria": "vegetais", "perda_percentual": 40, "tipo_perda": "limpeza"},
    {"nome": "Milho verde (espiga)", "categoria": "vegetais", "perda_percentual": 55, "tipo_perda": "limpeza"},
    {"nome": "Milho verde (lata/congelado)", "categoria": "vegetais", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Ervilha (lata/congelado)", "categoria": "vegetais", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Palmito", "categoria": "vegetais", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Azeitona (com caroco)", "categoria": "vegetais", "perda_percentual": 20, "tipo_perda": "limpeza"},
    {"nome": "Azeitona (sem caroco)", "categoria": "vegetais", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Cogumelo/champignon", "categoria": "vegetais", "perda_percentual": 12, "tipo_perda": "limpeza"},
    {"nome": "Cogumelo shimeji", "categoria": "vegetais", "perda_percentual": 15, "tipo_perda": "limpeza"},
    {"nome": "Cogumelo shiitake", "categoria": "vegetais", "perda_percentual": 30, "tipo_perda": "limpeza"},
    {"nome": "Abobora/moranga", "categoria": "vegetais", "perda_percentual": 25, "tipo_perda": "limpeza"},
    {"nome": "Nabo", "categoria": "vegetais", "perda_percentual": 20, "tipo_perda": "limpeza"},
    {"nome": "Rabanete", "categoria": "vegetais", "perda_percentual": 10, "tipo_perda": "limpeza"},

    # ══════════════════════════════════════════════════════════════
    # ERVAS E TEMPEROS FRESCOS
    # ══════════════════════════════════════════════════════════════
    {"nome": "Salsa/cheiro-verde", "categoria": "vegetais", "perda_percentual": 30, "tipo_perda": "limpeza"},
    {"nome": "Cebolinha", "categoria": "vegetais", "perda_percentual": 25, "tipo_perda": "limpeza"},
    {"nome": "Coentro", "categoria": "vegetais", "perda_percentual": 30, "tipo_perda": "limpeza"},
    {"nome": "Manjericao fresco", "categoria": "vegetais", "perda_percentual": 20, "tipo_perda": "limpeza"},
    {"nome": "Alecrim fresco", "categoria": "vegetais", "perda_percentual": 35, "tipo_perda": "limpeza"},
    {"nome": "Hortela", "categoria": "vegetais", "perda_percentual": 25, "tipo_perda": "limpeza"},
    {"nome": "Gengibre", "categoria": "vegetais", "perda_percentual": 20, "tipo_perda": "limpeza"},

    # ══════════════════════════════════════════════════════════════
    # FRUTAS
    # ══════════════════════════════════════════════════════════════
    {"nome": "Banana", "categoria": "frutas", "perda_percentual": 35, "tipo_perda": "limpeza"},
    {"nome": "Banana (caramelizada)", "categoria": "frutas", "perda_percentual": 20, "tipo_perda": "coccao"},
    {"nome": "Morango", "categoria": "frutas", "perda_percentual": 8, "tipo_perda": "limpeza"},
    {"nome": "Abacaxi", "categoria": "frutas", "perda_percentual": 40, "tipo_perda": "limpeza"},
    {"nome": "Manga", "categoria": "frutas", "perda_percentual": 32, "tipo_perda": "limpeza"},
    {"nome": "Mamao", "categoria": "frutas", "perda_percentual": 30, "tipo_perda": "limpeza"},
    {"nome": "Melancia", "categoria": "frutas", "perda_percentual": 40, "tipo_perda": "limpeza"},
    {"nome": "Melao", "categoria": "frutas", "perda_percentual": 35, "tipo_perda": "limpeza"},
    {"nome": "Limao", "categoria": "frutas", "perda_percentual": 50, "tipo_perda": "limpeza"},
    {"nome": "Laranja", "categoria": "frutas", "perda_percentual": 45, "tipo_perda": "limpeza"},
    {"nome": "Maracuja", "categoria": "frutas", "perda_percentual": 52, "tipo_perda": "limpeza"},
    {"nome": "Uva", "categoria": "frutas", "perda_percentual": 5, "tipo_perda": "limpeza"},
    {"nome": "Kiwi", "categoria": "frutas", "perda_percentual": 15, "tipo_perda": "limpeza"},
    {"nome": "Maca", "categoria": "frutas", "perda_percentual": 10, "tipo_perda": "limpeza"},
    {"nome": "Pera", "categoria": "frutas", "perda_percentual": 10, "tipo_perda": "limpeza"},
    {"nome": "Pessego", "categoria": "frutas", "perda_percentual": 15, "tipo_perda": "limpeza"},
    {"nome": "Acai (polpa)", "categoria": "frutas", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Polpa de frutas (congelada)", "categoria": "frutas", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Coco ralado", "categoria": "frutas", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Coco fresco", "categoria": "frutas", "perda_percentual": 50, "tipo_perda": "limpeza"},
    {"nome": "Abacate", "categoria": "frutas", "perda_percentual": 33, "tipo_perda": "limpeza"},
    {"nome": "Goiaba", "categoria": "frutas", "perda_percentual": 15, "tipo_perda": "limpeza"},
    {"nome": "Acerola", "categoria": "frutas", "perda_percentual": 10, "tipo_perda": "limpeza"},
    {"nome": "Framboesa", "categoria": "frutas", "perda_percentual": 5, "tipo_perda": "limpeza"},
    {"nome": "Mirtilo/blueberry", "categoria": "frutas", "perda_percentual": 3, "tipo_perda": "limpeza"},
    {"nome": "Tamarindo (polpa)", "categoria": "frutas", "perda_percentual": 60, "tipo_perda": "limpeza"},

    # ══════════════════════════════════════════════════════════════
    # GRAOS, CEREAIS E LEGUMINOSAS
    # ══════════════════════════════════════════════════════════════
    # Graos secos → cozidos: GANHAM peso (absorvem agua). Valor negativo = ganho.
    {"nome": "Arroz branco (cru para cozido)", "categoria": "graos", "perda_percentual": -200, "tipo_perda": "ganho"},
    {"nome": "Arroz integral (cru para cozido)", "categoria": "graos", "perda_percentual": -180, "tipo_perda": "ganho"},
    {"nome": "Feijao preto (cru para cozido)", "categoria": "graos", "perda_percentual": -120, "tipo_perda": "ganho"},
    {"nome": "Feijao carioca (cru para cozido)", "categoria": "graos", "perda_percentual": -120, "tipo_perda": "ganho"},
    {"nome": "Lentilha (cru para cozido)", "categoria": "graos", "perda_percentual": -100, "tipo_perda": "ganho"},
    {"nome": "Grao-de-bico (cru para cozido)", "categoria": "graos", "perda_percentual": -100, "tipo_perda": "ganho"},
    {"nome": "Aveia (hidratada/mingau)", "categoria": "graos", "perda_percentual": -250, "tipo_perda": "ganho"},
    {"nome": "Granola", "categoria": "graos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Quinoa (cru para cozido)", "categoria": "graos", "perda_percentual": -200, "tipo_perda": "ganho"},
    {"nome": "Cuscuz (hidratado)", "categoria": "graos", "perda_percentual": -150, "tipo_perda": "ganho"},
    {"nome": "Amendoim torrado", "categoria": "graos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Castanha de caju", "categoria": "graos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Castanha-do-para", "categoria": "graos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Nozes", "categoria": "graos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Semente de girassol", "categoria": "graos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Chia (hidratada)", "categoria": "graos", "perda_percentual": -900, "tipo_perda": "ganho"},
    {"nome": "Linhaça", "categoria": "graos", "perda_percentual": 0, "tipo_perda": "nenhuma"},

    # ══════════════════════════════════════════════════════════════
    # FARINHAS E PANIFICACAO
    # ══════════════════════════════════════════════════════════════
    {"nome": "Farinha de trigo", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Farinha de trigo integral", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Fermento biologico", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Fermento quimico", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Pao de hamburguer", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Pao de hamburguer (tostado)", "categoria": "padaria", "perda_percentual": 8, "tipo_perda": "coccao"},
    {"nome": "Pao australiano", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Pao brioche", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Pao de forma", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Pao frances", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Massa de pizza", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Massa de pizza (assada)", "categoria": "padaria", "perda_percentual": 12, "tipo_perda": "coccao"},
    {"nome": "Massa folhada", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Massa de lasanha (seca para cozida)", "categoria": "padaria", "perda_percentual": -100, "tipo_perda": "ganho"},
    {"nome": "Massa de macarrao (seca para cozida)", "categoria": "padaria", "perda_percentual": -110, "tipo_perda": "ganho"},
    {"nome": "Massa fresca (cozida)", "categoria": "padaria", "perda_percentual": -50, "tipo_perda": "ganho"},
    {"nome": "Massa de pastel", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Polvilho azedo", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Polvilho doce", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Amido de milho", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Farinha de rosca", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Farinha de mandioca", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Farinha de milho (fuba)", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Farinha de aveia", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Farinha de amendoas", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Farinha de arroz", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Tapioca (goma hidratada)", "categoria": "padaria", "perda_percentual": -80, "tipo_perda": "ganho"},
    {"nome": "Biscoito/bolacha (triturado)", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Pao de queijo (massa)", "categoria": "padaria", "perda_percentual": 0, "tipo_perda": "nenhuma"},

    # ══════════════════════════════════════════════════════════════
    # OLEOS, GORDURAS E MOLHOS
    # ══════════════════════════════════════════════════════════════
    {"nome": "Oleo de soja", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Oleo de canola", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Oleo de coco", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Azeite de oliva", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Gordura vegetal", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Banha de porco", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Molho de tomate", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Molho de tomate (reduzido)", "categoria": "oleos_molhos", "perda_percentual": 30, "tipo_perda": "coccao"},
    {"nome": "Maionese", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Maionese artesanal", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Ketchup", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Mostarda", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Molho shoyu", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Molho barbecue", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Molho ranch", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Vinagre", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Molho ingles", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Molho pesto", "categoria": "oleos_molhos", "perda_percentual": 0, "tipo_perda": "nenhuma"},

    # ══════════════════════════════════════════════════════════════
    # ACUCAR E DOCES
    # ══════════════════════════════════════════════════════════════
    {"nome": "Acucar refinado", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Acucar mascavo", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Acucar demerara", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Chocolate em barra (derretido)", "categoria": "doces", "perda_percentual": 5, "tipo_perda": "coccao"},
    {"nome": "Chocolate em po", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Chocolate branco", "categoria": "doces", "perda_percentual": 5, "tipo_perda": "coccao"},
    {"nome": "Mel", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Leite em po", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Pacoca", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Nutella/creme de avela", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Calda de chocolate", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Calda de caramelo", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Granulado/confeito", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Doce de leite", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Gelatina em po (hidratada)", "categoria": "doces", "perda_percentual": -400, "tipo_perda": "ganho"},
    {"nome": "Essencia de baunilha", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Xarope de glucose", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Chantilly", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
    {"nome": "Leite de ninho", "categoria": "doces", "perda_percentual": 0, "tipo_perda": "nenhuma"},
]

CATEGORIAS_PERDA = [
    ("carnes", "Carnes e Proteinas"),
    ("laticinios", "Laticinios e Ovos"),
    ("vegetais", "Vegetais e Legumes"),
    ("frutas", "Frutas"),
    ("graos", "Graos e Cereais"),
    ("padaria", "Farinhas e Panificacao"),
    ("oleos_molhos", "Oleos, Gorduras e Molhos"),
    ("doces", "Acucar e Doces"),
]
