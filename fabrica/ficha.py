"""Gera a ficha visual da família do Juca (canal infantil). Uso: python -m fabrica.ficha saida/"""
import os
import sys
from pathlib import Path

from . import visual

ESTILO = ("Children's cartoon character design for a YouTube kids music channel: flat 2D vector style, "
          "big round heads, large friendly eyes, simple rounded shapes, soft thin dark outlines, bright warm "
          "saturated colors, clean plain light background, consistent proportions, original characters. "
          "No text, no letters, no logos, no watermark.")

FAMILIA = ("a Brazilian family of six, all with warm brown skin: "
           "JUCA, a 6-year-old boy with short curly dark-brown hair, yellow t-shirt and blue denim overalls, "
           "orange sneakers, big gap-toothed smile; "
           "LILI, his 3-year-old little sister with two puffy curly pigtails tied with pink ribbons, "
           "lilac dress with white dots; "
           "MOM, slim woman with long curly hair in a high ponytail, teal blouse, white pants; "
           "DAD, tall chubby man with short beard and round glasses, green striped polo shirt; "
           "GRANDMA (vovó), plump smiling elderly woman with grey hair in a bun, round red glasses, "
           "floral apron over a coral dress, holding a wooden spoon; "
           "GRANDPA (vovô), thin elderly man with white mustache and straw hat, brown suspenders, plaid shirt")

PEDIDOS = {
    "familia_1": (f"Full-body lineup of {FAMILIA}, standing side by side facing the viewer, happy poses", "16:9"),
    "familia_2": (f"Group portrait of {FAMILIA}, joyful family hug in front of a simple cozy house", "16:9"),
    "juca_ficha": ("Character turnaround model sheet of JUCA, a 6-year-old Brazilian boy with warm brown skin, "
                   "short curly dark-brown hair, yellow t-shirt, blue denim overalls, orange sneakers: "
                   "front view, side view, back view, plus four facial expressions (happy, surprised, "
                   "sleepy, singing)", "16:9"),
    "vovo_cozinha": ("GRANDMA (vovó), plump smiling elderly Brazilian woman with warm brown skin, grey hair in "
                     "a bun, round red glasses, floral apron over a coral dress, kneading bread dough in a "
                     "colorful cozy kitchen while JUCA (6-year-old boy, curly hair, yellow t-shirt, blue "
                     "overalls) and LILI (3-year-old girl, puffy pigtails with pink ribbons, lilac dress) watch "
                     "excitedly; flour, milk bottle and eggs on the table", "16:9"),
    "miniatura": ("YouTube thumbnail style scene: JUCA, a 6-year-old Brazilian boy with warm brown skin, curly "
                  "dark-brown hair, yellow t-shirt and blue overalls, waving and singing happily on the left; "
                  "a big golden loaf of bread on the right; bright radial sunburst background in orange and "
                  "yellow", "16:9"),
}

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "ficha")
    out.mkdir(parents=True, exist_ok=True)
    os.environ["IMAGENS_IA"] = "1"
    for nome, (prompt, ratio) in PEDIDOS.items():
        visual._disabled["image"] = False
        r = visual.gerar(prompt, out / f"{nome}.png", estilo=ESTILO, ratio=ratio)
        print(nome, "ok" if r else "falhou", flush=True)
