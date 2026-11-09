# Fábrica de Canais

Motor que produz sozinho, para dois canais (PT e EN): pauta, pesquisa com fontes, roteiro, checagem de fatos,
narração, cenas de banco de vídeo, legendas, thumbnails, vídeo longo de 8 a 11 min e 3 Shorts de 61 a 80 s.
O pacote pronto vira uma "release" aqui no GitHub e o Claude deixa tudo como rascunho no Metricool.
Você aprova pelo celular.

## Como roda

| Peça | O que faz | Custo |
|---|---|---|
| GitHub Actions (`.github/workflows/fabrica.yml`) | Roda a fábrica em horário marcado: PT seg/qua/sex, EN ter/qui/sáb, de madrugada | grátis (repositório público) |
| Gemini API | Pesquisa na web, roteiro e checagem de fatos | plano grátis |
| edge-tts | Narração com voz neural | grátis |
| Pixabay API (ou Pexels) | Cenas de vídeo | grátis (100 buscas/minuto) |
| Claude (tarefa agendada) | Lê o pacote e cria rascunhos no Metricool | já incluso no seu plano |
| Metricool Starter | Publica no YouTube, TikTok, Instagram e Facebook | ~€16-20/mês (5 marcas) |

## Mexer sem programar

- `config/channels.yaml`: nicho, público, tom, voz, duração, quantos Shorts.
- `config/topics/pt.txt` e `en.txt`: fila de temas. Escreva um por linha; a fábrica usa de cima para baixo.
- `assets/music/`: coloque mp3 de música sem direitos autorais (Biblioteca de áudio do YouTube) e ela entra baixinho no fundo.
- Rodar na hora: aba **Actions → Fabrica → Run workflow**, escolha o canal e, se quiser, um tema.

## Segredos (Settings → Secrets and variables → Actions)

- `GEMINI_API_KEY`: obrigatório (aistudio.google.com → Get API key)
- `PIXABAY_API_KEY`: obrigatório (pixabay.com/api/docs, logado)
- `PEXELS_API_KEY`: opcional (a Pexels pausou chaves novas em nov/2026)
- `ANTHROPIC_API_KEY`: opcional. Se colocar e criar a variável `LLM_PROVIDER=anthropic`, o roteiro passa a ser escrito pelo Claude (melhor texto, ~US$ 0,10-0,30 por vídeo).

## Teste local sem internet

```
pip install -r requirements.txt
python -m fabrica.main --canal pt --offline
```

O publicador do Claude está descrito em `docs/publicador.md`.
