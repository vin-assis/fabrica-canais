"""Gera a ficha visual da família do Dico (canal infantil). Uso: python -m fabrica.ficha saida/"""
import os
import sys
from pathlib import Path

from . import visual

ESTILO = ("Children's cartoon character design for a YouTube kids music channel: flat 2D vector style, "
          "big round heads, large friendly eyes, simple rounded shapes, soft thin dark outlines, bright warm "
          "saturated colors, clean plain light background, consistent proportions, original characters. "
          "No text, no letters, no logos, no watermark.")

FAMILIA = ("a Brazilian family of six, all with warm brown skin: "
           "DICO, a 6-year-old boy with short curly dark-brown hair, yellow t-shirt and blue denim overalls, "
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
    "dico_ficha": ("Character turnaround model sheet of DICO, a 6-year-old Brazilian boy with warm brown skin, "
                   "short curly dark-brown hair, yellow t-shirt, blue denim overalls, orange sneakers: "
                   "front view, side view, back view, plus four facial expressions (happy, surprised, "
                   "sleepy, singing)", "16:9"),
    "vovo_cozinha": ("GRANDMA (vovó), plump smiling elderly Brazilian woman with warm brown skin, grey hair in "
                     "a bun, round red glasses, floral apron over a coral dress, kneading bread dough in a "
                     "colorful cozy kitchen while DICO (6-year-old boy, curly hair, yellow t-shirt, blue "
                     "overalls) and LILI (3-year-old girl, puffy pigtails with pink ribbons, lilac dress) watch "
                     "excitedly; flour, milk bottle and eggs on the table", "16:9"),
    "miniatura": ("YouTube thumbnail style scene: DICO, a 6-year-old Brazilian boy with warm brown skin, curly "
                  "dark-brown hair, yellow t-shirt and blue overalls, waving and singing happily on the left; "
                  "a big golden loaf of bread on the right; bright radial sunburst background in orange and "
                  "yellow", "16:9"),
}

DICO = ("DICO, a 6-year-old Brazilian boy with warm brown skin, short curly dark-brown hair, yellow t-shirt, "
        "blue denim overalls, orange sneakers")
VOVO = ("GRANDMA (vovó), plump smiling elderly Brazilian woman with warm brown skin, grey hair in a bun, round red "
        "glasses, floral apron over a coral dress")
FUNDO = "isolated on a perfectly plain pure white background, no shadow on the floor, nothing else in the image"

RIG = {
    "dico_rig": (f"Full-body {DICO}, standing straight facing the viewer, arms relaxed down at his sides slightly "
                 f"away from the body, legs slightly apart, mouth closed in a gentle smile, eyes open, "
                 f"centered, whole body visible with margin, {FUNDO}", "9:16"),
    "vovo_rig": (f"Full-body {VOVO}, standing straight facing the viewer, arms relaxed down at her sides slightly "
                 f"away from the body, mouth closed in a gentle smile, eyes open, centered, whole body visible "
                 f"with margin, {FUNDO}", "9:16"),
    "cozinha_vazia": ("Empty cozy colorful Brazilian home kitchen interior seen from the front, wooden table in the "
                      "foreground lower third, window with curtains, shelves with jars, stove, warm afternoon "
                      "light, no people, no characters, lots of open space in the center", "16:9"),
    "prop_pao": (f"A single big golden loaf of homemade bread, {FUNDO}", "1:1"),
    "prop_farinha": (f"A single paper bag of flour with a little flour spilling, {FUNDO}", "1:1"),
    "prop_leite": (f"A single glass bottle of milk, {FUNDO}", "1:1"),
    "prop_ovos": (f"Three brown eggs together, {FUNDO}", "1:1"),
    "prop_tigela": (f"A single colorful ceramic mixing bowl with a wooden spoon, {FUNDO}", "1:1"),
}

def _pose(desc, pron="his"):
    return (f"Full-body {desc}, standing straight facing the viewer, arms relaxed down at {pron} sides slightly "
            f"away from the body, legs slightly apart, mouth closed in a gentle smile, eyes open, centered, whole "
            f"body visible with margin, {FUNDO}", "9:16")

CENA = "seen from the front, no people, no characters, lots of open space in the center"
FAMILIA_RIG = {
    "lili_rig": _pose("LILI, a 3-year-old Brazilian girl with warm brown skin, two puffy curly pigtails tied with "
                      "pink ribbons, lilac dress with white dots, white sandals", "her"),
    "mae_rig": _pose("MOM, slim Brazilian woman with warm brown skin, long curly hair in a high ponytail, teal "
                     "blouse, white pants, simple flats", "her"),
    "pai_rig": _pose("DAD, tall chubby Brazilian man with warm brown skin, short beard, round glasses, green "
                     "striped polo shirt, jeans, sneakers"),
    "avo_rig": _pose("GRANDPA (vovô), thin elderly Brazilian man with warm brown skin, white mustache, straw hat, "
                     "brown suspenders, plaid shirt, beige trousers"),
    "quarto_dico": (f"Cozy colorful child's bedroom interior with a blue bed, yellow curtains, toy shelf and a rug, "
                    f"morning sun through the window, {CENA}", "16:9"),
    "banheiro": (f"Cheerful family bathroom interior with mint-green tiles, white bathtub with bubbles, sink with "
                 f"a step stool, yellow rubber duck, {CENA}", "16:9"),
    "quintal": (f"Sunny Brazilian backyard with green grass, a mango tree, clothesline, small vegetable garden "
                f"and a garden hose, blue sky, {CENA}", "16:9"),
    "sala": (f"Cozy colorful Brazilian living room with a blue sofa, striped rug, TV stand and plants, warm "
             f"light, {CENA}", "16:9"),
    "rua_bairro": (f"Colorful Brazilian neighborhood street with small houses in pastel colors, sidewalk, trees, "
                   f"a traffic light and a crosswalk, sunny day, {CENA}", "16:9"),
}

ESTILO_ADULTO = ("Clean modern 2D vector cartoon character design for a YouTube channel aimed at teenagers and young "
                 "adults: flat colors, subtle shading, slightly stylized adult proportions (not chibi, not childish), "
                 "expressive faces, soft dark outlines, contemporary urban Brazilian look. No text, no letters, no "
                 "logos, no watermark.")
CRESCI = {
    "leo_rig": _pose("LEO, a 22-year-old Brazilian young man with light-brown skin, short wavy black hair with a "
                     "small fade, light stubble, wearing an oversized mustard-yellow hoodie, black joggers and white "
                     "sneakers, a little backpack strap on one shoulder, friendly slightly clueless expression"),
    "tati_rig": _pose("TATI, a 27-year-old Brazilian young woman with dark-brown skin, shoulder-length box braids "
                      "tied half up, small round glasses, wearing a denim jacket over a white t-shirt, olive cargo "
                      "pants and black boots, confident slightly ironic smile", "her"),
    "ape_leo": ("Small simple rented studio apartment interior in Brazil, almost empty: mattress on the floor, a "
                "plastic chair, cardboard boxes, a small kitchenette, window with city buildings outside, "
                "late afternoon light, no people", "16:9"),
    "corredor_predio": ("Hallway of a simple Brazilian apartment building with two facing doors, tiled floor, "
                        "fluorescent light, mailbox, no people", "16:9"),
    "refeitorio": ("Office break room with long table, microwave, water cooler and a window, modern Brazilian "
                   "company, no people", "16:9"),
}

if __name__ == "__main__":
    if os.getenv("CONJUNTO") == "rig":
        PEDIDOS = RIG
    elif os.getenv("CONJUNTO") == "familia":
        PEDIDOS = FAMILIA_RIG
    elif os.getenv("CONJUNTO") == "cresci":
        PEDIDOS = CRESCI
        ESTILO = ESTILO_ADULTO
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "ficha")
    out.mkdir(parents=True, exist_ok=True)
    os.environ["IMAGENS_IA"] = "1"
    for nome, (prompt, ratio) in PEDIDOS.items():
        visual._disabled["image"] = False
        r = visual.gerar(prompt, out / f"{nome}.png", estilo=ESTILO, ratio=ratio)
        print(nome, "ok" if r else "falhou", flush=True)
