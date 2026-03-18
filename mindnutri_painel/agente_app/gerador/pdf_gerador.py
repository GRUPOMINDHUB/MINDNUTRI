from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from pathlib import Path
import os

LOGO_PATH = Path(__file__).parent.parent / "assets" / "logo_mindhub.png"
PAGE_W, PAGE_H = landscape(A4)

PRETO    = colors.HexColor("#1A1A1A")
VERMELHO = colors.HexColor("#CC0000")
CINZA    = colors.HexColor("#888888")
BRANCO   = colors.white


def _roundrect(c_obj, x, y, w, h, r=8, fill=None, stroke=None, sw=0.5):
    c_obj.saveState()
    if fill:
        c_obj.setFillColor(fill)
    if stroke:
        c_obj.setStrokeColor(stroke)
        c_obj.setLineWidth(sw)
    if fill and stroke:
        c_obj.roundRect(x, y, w, h, r, stroke=1, fill=1)
    elif fill:
        c_obj.roundRect(x, y, w, h, r, stroke=0, fill=1)
    elif stroke:
        c_obj.roundRect(x, y, w, h, r, stroke=1, fill=0)
    c_obj.restoreState()


def gerar_ficha_pdf(dados: dict, caminho_saida: str, foto_path: str = None) -> str:
    """
    Gera a ficha operacional PDF em paisagem.

    dados = {
        "nome_prato": str,
        "classificacao": str,
        "codigo": str,
        "estabelecimento": str,
        "ingredientes_op": [("quantidade", "descricao"), ...],
        "modo_preparo": [str, ...],
    }
    foto_path: caminho para a foto do prato (opcional)
    """
    c = canvas.Canvas(caminho_saida, pagesize=landscape(A4))
    c.setTitle(f"Ficha Operacional — {dados.get('nome_prato', '')}")

    W, H = PAGE_W, PAGE_H
    mg = 18 * mm
    area_w = W - 2 * mg

    # Fundo
    c.setFillColor(colors.HexColor("#FAFAFA"))
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Header preto
    c.setFillColor(PRETO)
    c.rect(0, H - 28*mm, W, 28*mm, fill=1, stroke=0)

    # Logo
    if LOGO_PATH.exists():
        try:
            c.drawImage(str(LOGO_PATH), mg, H - 28*mm + (28*mm - 32)/2,
                        width=110, height=32, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    c.setFillColor(BRANCO)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(W/2, H - 16*mm, dados.get("nome_prato", "").upper())
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#BBBBBB"))
    c.drawCentredString(W/2, H - 22*mm,
        f"{dados.get('classificacao','')}  •  {dados.get('codigo','')}  •  {dados.get('estabelecimento','')}")

    # Faixa vermelha
    c.setFillColor(VERMELHO)
    c.rect(0, H - 31*mm, W, 3*mm, fill=1, stroke=0)

    content_top = H - 35*mm
    content_bot = 18*mm
    content_h   = content_top - content_bot

    col_foto_w  = area_w * 0.26
    col_ing_w   = area_w * 0.38
    col_mont_w  = area_w * 0.36
    gap         = 5*mm

    x_foto = mg
    x_ing  = x_foto + col_foto_w + gap
    x_mont = x_ing  + col_ing_w  + gap

    # ── COLUNA 1: FOTO ──
    _roundrect(c, x_foto, content_bot, col_foto_w, content_h,
               r=10, fill=BRANCO, stroke=colors.HexColor("#DDDDDD"), sw=0.8)

    fmg = 4*mm
    fx  = x_foto + fmg
    fy  = content_bot + content_h * 0.22
    fw  = col_foto_w - 2*fmg
    fh  = content_h  * 0.64

    _roundrect(c, fx, fy, fw, fh, r=8, fill=colors.HexColor("#F0F0F0"),
               stroke=colors.HexColor("#DDDDDD"), sw=0.8)

    if foto_path and os.path.exists(foto_path):
        c.saveState()
        p = c.beginPath()
        p.roundRect(fx, fy, fw, fh, 8)
        c.clipPath(p, stroke=0)
        c.drawImage(foto_path, fx, fy, width=fw, height=fh,
                    preserveAspectRatio=True, anchor='c', mask='auto')
        c.restoreState()
    else:
        c.setFillColor(CINZA)
        c.setFont("Helvetica", 8)
        c.drawCentredString(fx+fw/2, fy+fh/2+3*mm, "Foto do produto")
        c.setFont("Helvetica", 7)
        c.drawCentredString(fx+fw/2, fy+fh/2-3*mm, "(enviar ao ativar)")

    c.setFillColor(PRETO)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(x_foto+col_foto_w/2, fy-10*mm, dados.get("nome_prato",""))
    c.setFont("Helvetica", 8)
    c.setFillColor(CINZA)
    c.drawCentredString(x_foto+col_foto_w/2, fy-15*mm, dados.get("classificacao",""))

    bw,bh = 28*mm,7*mm
    bx = x_foto + (col_foto_w-bw)/2
    by = content_bot + 6*mm
    _roundrect(c, bx, by, bw, bh, r=4, fill=VERMELHO)
    c.setFillColor(BRANCO)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(bx+bw/2, by+bh/2-1*mm, f"Cód: {dados.get('codigo','')}")

    # ── COLUNA 2: INGREDIENTES ──
    _roundrect(c, x_ing, content_bot, col_ing_w, content_h,
               r=10, fill=BRANCO, stroke=colors.HexColor("#DDDDDD"), sw=0.8)

    c.setFillColor(PRETO)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_ing+5*mm, content_bot+content_h-8*mm, "INGREDIENTES")
    c.setStrokeColor(VERMELHO)
    c.setLineWidth(1.5)
    c.line(x_ing+5*mm, content_bot+content_h-9.5*mm,
           x_ing+col_ing_w-5*mm, content_bot+content_h-9.5*mm)

    ingredientes = dados.get("ingredientes_op", [])
    ing_start_y  = content_bot + content_h - 13*mm
    lh = min((ing_start_y - content_bot - 4*mm) / max(len(ingredientes),1), 8*mm)

    for i, item in enumerate(ingredientes):
        qtd = item[0] if isinstance(item, (list,tuple)) else item.get("qtd","")
        ing = item[1] if isinstance(item, (list,tuple)) else item.get("nome","")
        y = ing_start_y - i*lh
        r_ = 3.2*mm
        cx_, cy_ = x_ing+5*mm+r_, y-1*mm
        c.setFillColor(VERMELHO)
        c.circle(cx_, cy_, r_, fill=1, stroke=0)
        c.setFillColor(BRANCO)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(cx_, cy_-1.5*mm, str(i+1))
        c.setFillColor(colors.HexColor("#444444"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x_ing+12*mm, y-1.5*mm, str(qtd))
        c.setFillColor(PRETO)
        c.setFont("Helvetica", 8)
        c.drawString(x_ing+32*mm, y-1.5*mm, str(ing)[:50])
        if i < len(ingredientes)-1:
            c.setStrokeColor(colors.HexColor("#EEEEEE"))
            c.setLineWidth(0.3)
            c.line(x_ing+4*mm, y-4*mm, x_ing+col_ing_w-4*mm, y-4*mm)

    # ── COLUNA 3: MODO DE PREPARO ──
    _roundrect(c, x_mont, content_bot, col_mont_w, content_h,
               r=10, fill=BRANCO, stroke=colors.HexColor("#DDDDDD"), sw=0.8)

    c.setFillColor(PRETO)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x_mont+5*mm, content_bot+content_h-8*mm, "MODO DE PREPARO")
    c.setStrokeColor(VERMELHO)
    c.setLineWidth(1.5)
    c.line(x_mont+5*mm, content_bot+content_h-9.5*mm,
           x_mont+col_mont_w-5*mm, content_bot+content_h-9.5*mm)

    passos      = dados.get("modo_preparo", [])
    mont_start  = content_bot + content_h - 13*mm
    lh2         = min((mont_start - content_bot - 4*mm) / max(len(passos),1), 14*mm)
    style_p     = ParagraphStyle("p", fontName="Helvetica", fontSize=7.5, leading=10, textColor=PRETO)

    for i, passo in enumerate(passos):
        y = mont_start - i*lh2
        r_ = 3.2*mm
        cx_, cy_ = x_mont+5*mm+r_, y-2*mm
        c.setFillColor(PRETO)
        c.circle(cx_, cy_, r_, fill=1, stroke=0)
        c.setFillColor(BRANCO)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(cx_, cy_-1.5*mm, str(i+1))
        par = Paragraph(str(passo), style_p)
        pw, ph = par.wrap(col_mont_w-16*mm, lh2)
        par.drawOn(c, x_mont+12*mm, y-ph-1*mm)
        if i < len(passos)-1:
            c.setStrokeColor(colors.HexColor("#EEEEEE"))
            c.setLineWidth(0.3)
            c.line(x_mont+4*mm, y-lh2+1*mm, x_mont+col_mont_w-4*mm, y-lh2+1*mm)

    # Rodapé
    c.setFillColor(PRETO)
    c.rect(0, 0, W, 14*mm, fill=1, stroke=0)
    c.setFillColor(BRANCO)
    c.setFont("Helvetica", 7)
    c.drawString(mg, 5*mm, "Documento gerado pelo Mindnutri — Agente de IA Mindhub")
    c.drawRightString(W-mg, 5*mm, "www.mindhub.com.br  |  Uso exclusivo interno")
    c.setFillColor(VERMELHO)
    c.rect(0, 14*mm, W, 1.5*mm, fill=1, stroke=0)

    c.save()
    return caminho_saida
