import os
import shutil
from pathlib import Path
from datetime import datetime
from django.conf import settings as config

PASTA_BASE = Path(config.STORAGE_LOCAL_PATH)


def garantir_pasta():
    PASTA_BASE.mkdir(parents=True, exist_ok=True)


def salvar_arquivo(telefone: str, nome_arquivo: str, dados: bytes = None,
                   caminho_origem: str = None) -> str:
    """
    Salva um arquivo no storage local.
    Retorna o caminho completo do arquivo salvo.
    """
    garantir_pasta()
    pasta_cliente = PASTA_BASE / telefone
    pasta_cliente.mkdir(exist_ok=True)

    destino = str(pasta_cliente / nome_arquivo)

    if caminho_origem:
        shutil.copy2(caminho_origem, destino)
    elif dados:
        with open(destino, "wb") as f:
            f.write(dados)

    return destino


def gerar_nome_arquivo(telefone: str, nome_prato: str, tipo: str) -> str:
    """Gera nome único para o arquivo."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_limpo = "".join(c for c in nome_prato if c.isalnum() or c in " _-")
    nome_limpo = nome_limpo.replace(" ", "_")[:30]
    ext = ".xlsx" if tipo == "tecnica" else ".pdf"
    return f"{nome_limpo}_{ts}{ext}"
