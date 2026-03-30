from django.db import models
from django.utils import timezone
from datetime import timedelta


class Assinante(models.Model):
    NICHO_CHOICES = [
        ('hamburguer', 'Hambúrguer'),
        ('pizza', 'Pizza'),
        ('sobremesa', 'Sobremesa'),
        ('comida_brasileira', 'Comida Brasileira'),
        ('outro', 'Outro'),
    ]
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('ativo', 'Ativo'),
        ('bloqueado', 'Bloqueado'),
        ('inadimplente', 'Inadimplente'),
        ('cancelado', 'Cancelado'),
    ]

    # Dados pessoais
    nome              = models.CharField(max_length=200, default="")
    telefone          = models.CharField(max_length=30, unique=True)
    estabelecimento   = models.CharField(max_length=200, default="")
    nicho             = models.CharField(max_length=50, choices=NICHO_CHOICES, default='outro')
    cidade            = models.CharField(max_length=100, blank=True)
    instagram         = models.CharField(max_length=100, blank=True)
    cpf               = models.CharField(max_length=14, blank=True)
    funcionarios      = models.PositiveIntegerField(default=1)
    faturamento_estimado = models.CharField(max_length=50, blank=True)

    # Assinatura
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    data_inicio       = models.DateField(default=timezone.localdate)
    proxima_cobranca  = models.DateField(null=True, blank=True)
    asaas_id          = models.CharField(max_length=100, blank=True)
    payment_link_id   = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # Fichas
    fichas_geradas_mes = models.PositiveIntegerField(default=0)
    fichas_limite_mes  = models.PositiveIntegerField(default=30)
    total_fichas_geradas = models.PositiveIntegerField(default=0)

    # Controle
    criado_em         = models.DateTimeField(auto_now_add=True)
    atualizado_em     = models.DateTimeField(auto_now=True)
    observacoes       = models.TextField(blank=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Assinante'
        verbose_name_plural = 'Assinantes'

    def __str__(self):
        return f"{self.nome} — {self.estabelecimento}"

    @property
    def fichas_restantes(self):
        return max(0, self.fichas_limite_mes - self.fichas_geradas_mes)

    @property
    def percentual_fichas(self):
        if self.fichas_limite_mes == 0:
            return 0
        return int((self.fichas_geradas_mes / self.fichas_limite_mes) * 100)

    @property
    def dias_ate_cobranca(self):
        if not self.proxima_cobranca:
            return None
        delta = self.proxima_cobranca - timezone.localdate()
        return delta.days

    def save(self, *args, **kwargs):
        if not self.proxima_cobranca and self.data_inicio:
            self.proxima_cobranca = self.data_inicio + timedelta(days=30)
        super().save(*args, **kwargs)


class FichaTecnica(models.Model):
    TIPO_CHOICES = [
        ('tecnica', 'Ficha Técnica (XLSX)'),
        ('operacional', 'Ficha Operacional (PDF)'),
        ('custo_rapido', 'Cálculo de Custo Rápido'),
    ]

    assinante     = models.ForeignKey(Assinante, on_delete=models.CASCADE, related_name='fichas')
    nome_prato    = models.CharField(max_length=200)
    tipo          = models.CharField(max_length=20, choices=TIPO_CHOICES)
    codigo        = models.CharField(max_length=20, blank=True)
    custo_total   = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    custo_porcao  = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    num_porcoes   = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True)
    arquivo_url   = models.CharField(max_length=500, blank=True)
    criada_em     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criada_em']
        verbose_name = 'Ficha Técnica'
        verbose_name_plural = 'Fichas Técnicas'

    def __str__(self):
        return f"{self.nome_prato} — {self.assinante.nome}"


class Notificacao(models.Model):
    TIPO_CHOICES = [
        ('inadimplencia', 'Inadimplência'),
        ('limite_fichas', 'Limite de Fichas'),
        ('erro_sistema',  'Erro de Sistema'),
        ('sem_entender',  'Agente Não Entendeu'),
        ('novo_assinante','Novo Assinante'),
        ('cancelamento',  'Cancelamento'),
    ]
    NIVEL_CHOICES = [
        ('info',    'Informação'),
        ('aviso',   'Aviso'),
        ('critico', 'Crítico'),
    ]

    tipo        = models.CharField(max_length=30, choices=TIPO_CHOICES)
    nivel       = models.CharField(max_length=10, choices=NIVEL_CHOICES, default='info')
    titulo      = models.CharField(max_length=200)
    mensagem    = models.TextField()
    assinante   = models.ForeignKey(Assinante, on_delete=models.SET_NULL, null=True, blank=True)
    lida        = models.BooleanField(default=False)
    criada_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criada_em']
        verbose_name = 'Notificação'
        verbose_name_plural = 'Notificações'

    def __str__(self):
        return f"[{self.nivel.upper()}] {self.titulo}"

class Conversa(models.Model):
    assinante = models.ForeignKey(Assinante, on_delete=models.CASCADE, related_name='conversas', null=True, blank=True)
    telefone = models.CharField(max_length=30, db_index=True)
    role = models.CharField(max_length=50)
    content = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['telefone', '-criado_em'], name='idx_conversa_tel_data'),
        ]

    def __str__(self):
        return f"{self.telefone} ({self.role})"

class Ingrediente(models.Model):
    assinante = models.ForeignKey(Assinante, on_delete=models.CASCADE, related_name='ingredientes', null=True, blank=True)
    telefone = models.CharField(max_length=30)
    nome = models.CharField(max_length=200)
    unidade = models.CharField(max_length=20, default='kg')
    custo_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fc = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    ic = models.DecimalField(max_digits=5, decimal_places=2, default=1.0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('telefone', 'nome')
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.telefone})"

class EstadoConversa(models.Model):
    telefone = models.CharField(max_length=30, primary_key=True)
    estado = models.CharField(max_length=100, default='inicio')
    dados_temp = models.TextField(default='{}')
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Estado de {self.telefone}: {self.estado}"


class ConfiguracaoIA(models.Model):
    """Singleton — configuração do modelo de IA editável pelo admin."""

    # Seções do prompt
    persona = models.TextField(
        verbose_name='Persona',
        help_text='Quem é a IA, tom de voz e regras críticas de comportamento.',
        default=''
    )
    metodologia = models.TextField(
        verbose_name='Metodologia',
        help_text='Didática, clareza, eficiência, linguagem acessível e jornada tripla.',
        default=''
    )
    instrucoes_geracao = models.TextField(
        verbose_name='Instruções de Geração',
        help_text='Como gerar cada parte: relatórios, fichas, cálculos matemáticos.',
        default=''
    )
    formato_saida = models.TextField(
        verbose_name='Formato de Saída',
        help_text='Template esperado na resposta.',
        default=''
    )

    # Parâmetros do modelo
    modelo_ia = models.CharField(max_length=50, default='gpt-4.1-mini')
    max_tokens = models.IntegerField(default=3000)
    temperatura = models.FloatField(default=0.7)

    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração IA'
        verbose_name_plural = 'Configuração IA'

    def __str__(self):
        return f"Configuração IA ({self.modelo_ia})"

    def get_system_prompt(self):
        """Concatena as 4 seções em um único system prompt."""
        partes = [
            self.persona,
            self.metodologia,
            self.instrucoes_geracao,
            self.formato_saida,
        ]
        return '\n\n---\n\n'.join(p.strip() for p in partes if p.strip())

    @classmethod
    def get_config(cls):
        """Retorna a configuração singleton, criando com defaults se necessário."""
        from .prompt_defaults import PERSONA_DEFAULT, METODOLOGIA_DEFAULT, INSTRUCOES_DEFAULT, FORMATO_DEFAULT
        obj, created = cls.objects.get_or_create(
            pk=1,
            defaults={
                'persona': PERSONA_DEFAULT,
                'metodologia': METODOLOGIA_DEFAULT,
                'instrucoes_geracao': INSTRUCOES_DEFAULT,
                'formato_saida': FORMATO_DEFAULT,
            }
        )
        return obj


class Cupom(models.Model):
    """Cupom de desconto — aplica valor especial no primeiro pagamento."""
    codigo = models.CharField(max_length=50, unique=True)
    valor_primeiro_pagamento = models.DecimalField(max_digits=10, decimal_places=2, help_text='Valor do primeiro pagamento com cupom')
    ativo = models.BooleanField(default=True)
    usos = models.PositiveIntegerField(default=0, help_text='Quantas vezes foi usado')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Cupom'
        verbose_name_plural = 'Cupons'

    def __str__(self):
        return f"{self.codigo} — R$ {self.valor_primeiro_pagamento}"

    @classmethod
    def validar(cls, codigo: str):
        """Retorna o cupom se válido, None se inválido."""
        try:
            cupom = cls.objects.get(codigo__iexact=codigo.strip(), ativo=True)
            return cupom
        except cls.DoesNotExist:
            return None

    def usar(self):
        """Incrementa contador de usos atomicamente via F()."""
        from django.db.models import F
        Cupom.objects.filter(pk=self.pk).update(usos=F('usos') + 1)
        self.refresh_from_db(fields=['usos'])


class PerdaIngrediente(models.Model):
    """Base de conhecimento de perdas padrão — editável pelo painel."""

    CATEGORIA_CHOICES = [
        ('carnes', 'Carnes e Proteínas'),
        ('laticinios', 'Laticínios e Ovos'),
        ('vegetais', 'Vegetais e Legumes'),
        ('frutas', 'Frutas'),
        ('graos', 'Grãos e Cereais'),
        ('padaria', 'Farinhas e Panificação'),
        ('oleos_molhos', 'Óleos, Gorduras e Molhos'),
        ('doces', 'Açúcar e Doces'),
    ]
    TIPO_PERDA_CHOICES = [
        ('limpeza', 'Limpeza'),
        ('coccao', 'Cocção'),
        ('ganho', 'Ganho (absorve água)'),
        ('nenhuma', 'Nenhuma'),
    ]

    nome = models.CharField(max_length=200, unique=True)
    categoria = models.CharField(max_length=30, choices=CATEGORIA_CHOICES)
    perda_percentual = models.IntegerField(default=0, help_text='Positivo=perda, Negativo=ganho. Ex: 30 perde 30%, -200 ganha 200% (triplica)')
    tipo_perda = models.CharField(max_length=20, choices=TIPO_PERDA_CHOICES, default='nenhuma')
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['categoria', 'nome']
        verbose_name = 'Perda de Ingrediente'
        verbose_name_plural = 'Perdas de Ingredientes'

    def __str__(self):
        return f"{self.nome} — {self.perda_percentual}% ({self.tipo_perda})"

    @classmethod
    def carregar_todas(cls):
        """Retorna lista de dicts com todas as perdas."""
        cls.inicializar_defaults()
        return list(cls.objects.values('nome', 'categoria', 'perda_percentual', 'tipo_perda'))

    @classmethod
    def inicializar_defaults(cls):
        """Cria entradas faltantes a partir de perdas_defaults.py."""
        from .perdas_defaults import PERDAS_PADRAO
        existentes = set(cls.objects.values_list('nome', flat=True))
        novas = []
        for p in PERDAS_PADRAO:
            if p['nome'] not in existentes:
                novas.append(cls(
                    nome=p['nome'],
                    categoria=p['categoria'],
                    perda_percentual=p['perda_percentual'],
                    tipo_perda=p['tipo_perda'],
                ))
        if novas:
            cls.objects.bulk_create(novas)

    @classmethod
    def buscar_perdas_para_ingredientes(cls, nomes_ingredientes: list[str]) -> dict:
        """Busca perdas para uma lista de nomes de ingredientes (match parcial)."""
        todas = cls.objects.filter(perda_percentual__gt=0)
        resultado = {}
        for nome_ing in nomes_ingredientes:
            nome_lower = nome_ing.lower().strip()
            for perda in todas:
                perda_lower = perda.nome.lower()
                if nome_lower in perda_lower or perda_lower in nome_lower:
                    resultado[nome_ing] = {
                        'nome_base': perda.nome,
                        'perda_percentual': perda.perda_percentual,
                        'tipo_perda': perda.tipo_perda,
                    }
                    break
        return resultado


class MensagemBot(models.Model):
    """Mensagens configuráveis do bot — editáveis pelo painel."""

    CATEGORIA_CHOICES = [
        ('boas_vindas', 'Boas-vindas'),
        ('menu', 'Menu Principal'),
        ('coleta', 'Coleta de Dados'),
        ('pagamento', 'Pagamento'),
        ('fichas', 'Fichas Técnicas'),
        ('operacional', 'Ficha Operacional (PDF)'),
        ('erros', 'Erros e Alertas'),
        ('renovacao', 'Renovação'),
        ('webhook', 'Webhook / Pós-pagamento'),
    ]

    chave = models.CharField(max_length=80, primary_key=True)
    categoria = models.CharField(max_length=30, choices=CATEGORIA_CHOICES)
    descricao = models.CharField(max_length=300, blank=True)
    texto = models.TextField()
    variaveis = models.CharField(max_length=200, blank=True,
                                  help_text='Variáveis disponíveis separadas por vírgula')
    ordem = models.PositiveIntegerField(default=0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['categoria', 'ordem']
        verbose_name = 'Mensagem do Bot'
        verbose_name_plural = 'Mensagens do Bot'

    def __str__(self):
        return f"[{self.categoria}] {self.chave}"

    @classmethod
    def carregar_todas(cls):
        """Retorna dict {chave: texto} de todas as mensagens."""
        cls.inicializar_defaults()
        return dict(cls.objects.values_list('chave', 'texto'))

    @classmethod
    def inicializar_defaults(cls):
        """Cria entradas faltantes a partir de mensagem_defaults.py."""
        from .mensagem_defaults import MENSAGENS_PADRAO
        existentes = set(cls.objects.values_list('chave', flat=True))
        novas = []
        for m in MENSAGENS_PADRAO:
            if m['chave'] not in existentes:
                novas.append(cls(
                    chave=m['chave'],
                    categoria=m['categoria'],
                    descricao=m.get('descricao', ''),
                    texto=m['texto'],
                    variaveis=m.get('variaveis', ''),
                    ordem=m.get('ordem', 0),
                ))
        if novas:
            cls.objects.bulk_create(novas)


class WebhookProcessado(models.Model):
    """Registro de webhooks já processados para garantir idempotência."""
    evento_id = models.CharField(max_length=200, unique=True)
    evento_tipo = models.CharField(max_length=80)
    processado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Webhook Processado'
        verbose_name_plural = 'Webhooks Processados'

    def __str__(self):
        return f"{self.evento_tipo} — {self.evento_id}"

    @classmethod
    def ja_processado(cls, evento_id: str) -> bool:
        return cls.objects.filter(evento_id=evento_id).exists()

    @classmethod
    def registrar(cls, evento_id: str, evento_tipo: str) -> None:
        cls.objects.get_or_create(evento_id=evento_id, defaults={"evento_tipo": evento_tipo})

    @classmethod
    def limpar_antigos(cls, dias: int = 30) -> int:
        limite = timezone.now() - timedelta(days=dias)
        qtd, _ = cls.objects.filter(processado_em__lt=limite).delete()
        return qtd
