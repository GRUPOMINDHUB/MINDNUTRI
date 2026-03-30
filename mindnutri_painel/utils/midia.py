import base64
import logging
import os
import tempfile

import anthropic
from django.conf import settings as config

logger = logging.getLogger(__name__)


# ── TRANSCRIÇÃO DE ÁUDIO (OpenAI Whisper) ────────────────────────

def transcrever_audio(audio_bytes: bytes, extensao: str = "ogg") -> str | None:
    """Transcreve áudio para texto usando Whisper."""
    tmp_path = None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=30.0)

        with tempfile.NamedTemporaryFile(suffix=f".{extensao}", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        with open(tmp_path, "rb") as f:
            resultado = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="pt",
            )
        return resultado.text.strip()
    except Exception as e:
        logger.error("[Whisper] Erro na transcricao: %s", e)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── ANÁLISE DE IMAGEM (Claude Vision) ────────────────────────────

def analisar_imagem(imagem_bytes: bytes, prompt: str) -> str:
    """Envia imagem para o Claude analisar (extração de ingredientes)."""
    try:
        client = anthropic.Anthropic(
            api_key=config.ANTHROPIC_API_KEY,
            timeout=30.0,
        )
        b64 = base64.standard_b64encode(imagem_bytes).decode("utf-8")

        msg = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return msg.content[0].text
    except Exception as e:
        logger.error("[Vision] Erro ao analisar imagem: %s", e)
        return "Não consegui analisar a imagem. Por favor, tente descrever os ingredientes em texto."


def extrair_ingredientes_de_imagem(imagem_bytes: bytes) -> str:
    """Extrai lista de ingredientes de uma foto de ficha ou receita."""
    prompt = (
        "Analise esta imagem e extraia todos os ingredientes que conseguir identificar.\n"
        "Para cada ingrediente, informe:\n"
        "- Nome do ingrediente\n"
        "- Quantidade/peso se visível\n"
        "- Unidade de medida se visível\n\n"
        "Responda em formato de lista simples, um ingrediente por linha.\n"
        "Se não for possível identificar ingredientes, diga que não encontrou."
    )
    return analisar_imagem(imagem_bytes, prompt)
