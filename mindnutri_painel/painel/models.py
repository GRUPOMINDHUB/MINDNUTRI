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
        ('ativo', 'Ativo'),
        ('bloqueado', 'Bloqueado'),
        ('inadimplente', 'Inadimplente'),
        ('cancelado', 'Cancelado'),
    ]

    # Dados pessoais
    nome              = models.CharField(max_length=200)
    telefone          = models.CharField(max_length=30, unique=True)
    estabelecimento   = models.CharField(max_length=200)
    nicho             = models.CharField(max_length=50, choices=NICHO_CHOICES, default='outro')
    cidade            = models.CharField(max_length=100, blank=True)
    instagram         = models.CharField(max_length=100, blank=True)
    funcionarios      = models.PositiveIntegerField(default=1)
    faturamento_estimado = models.CharField(max_length=50, blank=True)

    # Assinatura
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ativo')
    data_inicio       = models.DateField(default=timezone.localdate)
    proxima_cobranca  = models.DateField(null=True, blank=True)
    asaas_id          = models.CharField(max_length=100, blank=True)

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
    telefone = models.CharField(max_length=30)
    role = models.CharField(max_length=50)
    content = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']

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
