"""
Fallback do system prompt — gerado a partir de prompt_defaults.py.
Usado apenas se ConfiguracaoIA nao existir no banco.
"""
from painel.prompt_defaults import (
    PERSONA_DEFAULT,
    METODOLOGIA_DEFAULT,
    INSTRUCOES_DEFAULT,
    FORMATO_DEFAULT,
)

SYSTEM_PROMPT = '\n\n---\n\n'.join([
    PERSONA_DEFAULT.strip(),
    METODOLOGIA_DEFAULT.strip(),
    INSTRUCOES_DEFAULT.strip(),
    FORMATO_DEFAULT.strip(),
])
