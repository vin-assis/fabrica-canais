"""Fontes oficiais para canais de dados (ex.: Poder em Números)."""
import datetime as dt

import requests

UA = {"User-Agent": "fabrica-canais/1.0 (github.com/vin-assis/fabrica-canais)"}


def oficial(nome_ou_url, dominios):
    s = (nome_ou_url or "").lower()
    return any(d.lower() in s for d in dominios)


def ptax_dolar():
    """Última cotação PTAX de venda do dólar (Banco Central). Devolve texto pronto para o dossiê ou ''."""
    fim = dt.date.today()
    ini = fim - dt.timedelta(days=10)
    url = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
           "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)")
    try:
        r = requests.get(url, params={"@dataInicial": f"'{ini:%m-%d-%Y}'", "@dataFinalCotacao": f"'{fim:%m-%d-%Y}'",
                                      "$format": "json"}, headers=UA, timeout=30)
        r.raise_for_status()
        vals = r.json().get("value") or []
        if not vals:
            return ""
        v = vals[-1]
        quando = v["dataHoraCotacao"][:10]
        d = dt.date.fromisoformat(quando)
        return (f"Cotação PTAX de venda do dólar em {d:%d/%m/%Y}: R$ {v['cotacaoVenda']:.4f} "
                f"(fonte oficial: Banco Central do Brasil, {r.url})")
    except Exception as e:  # noqa: BLE001
        print(f"  PTAX indisponível: {e}", flush=True)
        return ""
