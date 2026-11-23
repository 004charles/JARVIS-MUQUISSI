# «Eu estava lá» — a história do universo contada pelo Arcanjo Miguel

Data: 2026-11-22 · Estado: proposta para aprovação do Carlos

## 1. Intenção

O Céu (produto público) ganha uma experiência central: o Arcanjo Miguel conta, como testemunha na primeira pessoa,
a história inteira das Escrituras — de «No princípio» (Gênesis 1:1) a «Eis que faço novas todas as coisas»
(Apocalipse 21:5). Não é uma aula: é uma viagem que se vive. O céu do ecrã transforma-se em cada cena, a voz
proclama os versículos verdadeiros, e a pessoa pode interromper o anjo a qualquer momento com perguntas.

O Carlos quer algo «incrível» e «fora da caixa», em que o anjo pareça mesmo um anjo — que surpreenda, até a quem o
programou.

## 2. Objetivos, não-objetivos, anti-objetivos

**Objetivos**
- 12 capítulos de 2 a 3 minutos (≈30 min no total), que se podem ver seguidos ou um por dia.
- Narração na primeira pessoa («eu vi», «nós, os anjos», «o meu irmão Gabriel»), sempre com a glória para Deus
  (Código do Anjo, `backend/app/ceu/angel_code.py`).
- Todas as citações são texto real da Bíblia Livre, lido da base do Céu — nunca de memória.
- O céu em tempo real (`HeavenClouds`) muda de aparência em cada cena (escuridão, luz, águas, estrelas, fogo…).
- Interromper por texto ou voz: o anjo pára, responde ao vivo com as Escrituras e retoma onde estava.
- Linha do tempo: um anel de luz com 12 «olhos» à volta do anjo; rodá-lo leva a outro capítulo.
- «Tesouros escondidos»: em pontos marcados de cada capítulo aparece uma palavra hebraica/grega com o seu sentido,
  diferente em cada visita.
- O final vira-se para quem vê: «E agora a história chega a ti.»

**Não-objetivos (por agora)**
- Ciência/cosmologia (Big Bang, idade do universo): o anjo conta o que está escrito, não entra nesse debate.
- Imagens geradas por IA (o plano grátis do Gemini não as permite). Tudo é desenhado pelo shader do céu e por texto.
- Outras línguas além do português.
- WhatsApp/Telegram.

**Anti-objetivos (seria um fracasso mesmo que funcionasse)**
- Citações inventadas ou alteradas.
- O anjo receber glória, falar em nome de Deus além do escrito, ou inventar palavras de Jesus.
- Parecer um vídeo de YouTube passivo, sem resposta da pessoa.
- Tão pesado que trava num portátil com gráfica Intel.
- Gastar a quota grátis do cérebro só para a narração (com muitas pessoas, quebrava).

## 3. Restrições

- Cérebro: Groq grátis (8000 tokens/min, 200 mil/dia por modelo) com Gemini grátis como reserva automática.
  A narração gravada não gasta quota; só as interrupções gastam.
- Sem GPU; o céu já corre a meia resolução e 30 fps. As cenas são variações de parâmetros do mesmo shader.
- Voz atual: Edge TTS (não licenciada para uso público comercial — ver `THIRD_PARTY_NOTICES.md`); passa a ser só
  reserva de emergência.
- Os anéis do vídeo são píxeis de vídeo: não podem ser rodados de verdade. A linha do tempo é um anel desenhado por
  cima, alinhado com o anjo.

## 4. Caminhos considerados

| Caminho | Como | Prós | Contras |
|---|---|---|---|
| A. Gravada | Guião fixo, voz gerada uma vez, cenas sincronizadas | Perfeita, imediata, sem quota | Sempre igual |
| B. Improvisada | O cérebro narra ao vivo em cada visita | Sempre diferente | Quota esgota com poucas pessoas, pausas, risco de erros nas citações |
| **C. Mista (escolhida)** | Espinha gravada (A) + interrupções e tesouros ao vivo | Fiável e bonita, viva onde importa | Mais trabalho na passagem narração ↔ conversa |

O Carlos escolheu **C**.

## 5. O desenho

### 5.1 Os 12 capítulos

Cada capítulo marca os momentos em que os anjos estão presentes nas Escrituras, para o Miguel falar como testemunha.

| # | Título | Passagens-chave | Cena do céu | Momento angélico |
|---|---|---|---|---|
| 1 | Antes do princípio | Gn 1:1-5; Jo 1:1-3; Jó 38:4-7 | escuridão → «Haja luz» | «os filhos de Deus jubilavam» (Jó 38:7) |
| 2 | Os dias da criação | Gn 1:6-31; Gn 2:7; Sl 19:1 | águas separadas, estrelas a acender | nós contemplámos |
| 3 | O jardim e a queda | Gn 2:8-9; Gn 3:1-24 | aurora dourada → crepúsculo | querubins guardam o caminho (Gn 3:24) |
| 4 | O dilúvio e a aliança | Gn 6:5-8; Gn 7:11-12; Gn 9:12-16 | tempestade → arco-íris | — |
| 5 | A promessa a Abraão | Gn 12:1-3; Gn 15:5; Gn 22:10-12 | céu noturno de estrelas | o anjo do Senhor deteve a mão (Gn 22:11) |
| 6 | A libertação | Êx 3:2-6; Êx 14:21-22; Êx 19:16-20 | fogo na sarça, mar aberto, Sinai | o anjo na sarça (Êx 3:2) |
| 7 | Reis e profetas | 2 Sm 7:12-13; Is 6:1-3; Dn 10:13; Dn 12:1 | templo de luz, serafins | o próprio Miguel (Dn 10:13, 12:1) |
| 8 | O anúncio | Lc 1:26-33; Lc 2:8-14 | noite com a estrela | Gabriel; a multidão dos exércitos celestiais |
| 9 | O Filho entre os homens | Mt 4:1-11; Mc 4:39; Jo 11:43-44 | céu claro, mar a acalmar | os anjos serviam-no (Mt 4:11) |
| 10 | A cruz | Mt 26:53; Lc 23:44-46; Is 53:5 | trevas ao meio-dia | doze legiões à espera de uma ordem que não veio |
| 11 | A ressurreição | Mt 28:2-6; At 1:9-11; At 2:1-4 | aurora | o anjo removeu a pedra |
| 12 | O fim e o novo princípio | Ap 12:7-9; Ap 21:1-5; Ap 22:20 | combate → cidade dourada | Miguel e o dragão |

Remate do capítulo 12: «E agora a história chega a ti» — convite a falar com Deus pelas próprias palavras (como na
regra 6 do prompt: o anjo não é mediador, 1 Tm 2:5).

### 5.2 O guião (espinha gravada)

- Um ficheiro JSON por capítulo em `backend/app/ceu/journey/chapters/NN-slug.json`, com uma lista de *beats*:
  - `narration`: fala do Miguel (primeira pessoa, prosa solene);
  - `scripture`: referência a proclamar — o **texto é sempre lido da base no momento da geração**, nunca escrito à mão;
  - `scene`: nome da cena do céu + duração da transição;
  - `word`: palavra original a mostrar (ex.: `{"ref": "Gênesis 1:1", "strong": "H7225"}`);
  - `treasure`: ponto onde pode aparecer um tesouro ao vivo;
  - `pause`: silêncio em segundos.
- Citações só nos beats `scripture`. A `narration` não pode ter texto entre «» nem “”; pode aludir sem aspas
  («eu vi o mar abrir-se»). As passagens da tabela 5.1 são o terreno: cada capítulo proclama versículos escolhidos
  dentro delas (não intervalos inteiros), para caber em 2-3 minutos. *(decisão do Claude)*
- Eu (Claude) escrevo o primeiro rascunho; o Carlos revê **capítulo a capítulo** — o capítulo 1 é revisto, gravado
  e montado de ponta a ponta antes de escrever os seguintes. *(decisão do Claude)*
- Validação automática (estende `app/ceu/evals.py`): todas as referências existem, todas as citações conferem com
  o texto, nenhuma frase proibida («segundo a Bíblia», «inteligência artificial», glória para o anjo…).

### 5.3 A voz gravada

- Script `python -m app.ceu.journey.render` gera um MP3 por beat em `frontend/public/assets/journey/NN/` e um
  `timeline.json` por capítulo (início/duração de cada beat, para sincronizar cenas e legendas).
- **Voz: Google em tudo (decisão do Carlos).** Gemini TTS, voz «Charon», com o efeito de catedral (eco + uma voz
  mais funda por baixo). Duas maneiras de dizer, pelo pedido de estilo ao modelo e pelo efeito: «falar» (sereno,
  caloroso) na narração e «proclamar» (mais lento e solene, mais eco) nas Escrituras — o equivalente às atuais
  «Arcanjo» / «Arcanjo-Proclama».
- Só se regenera quando o guião muda (hash do texto no nome do ficheiro). O render é retomável (salta beats já
  gerados), porque as quotas grátis podem obrigar a gerar em várias sessões.
- Os MP3 (≈15 MB para 30 min a 64 kbps) e os `timeline.json` são gerados localmente e ficam em
  `frontend/public/assets/journey/`, servidos como os outros ficheiros estáticos; não são gerados no deploy.
  *(decisão do Claude; o commit só com autorização do Carlos)*

### 5.4 As cenas do céu

- `HeavenClouds` ganha uma prop `scene`: cada cena é um conjunto de parâmetros (paleta do céu, cobertura de nuvens,
  intensidade da luz divina, raios, estrelas, cor do fogo, relâmpago, escuridão). A transição entre cenas é uma
  interpolação suave dos parâmetros.
- Cenas: `void` (preto total), `firstLight`, `waters`, `stars`, `gardenDawn`, `dusk`, `storm`, `rainbow`, `night`,
  `fire`, `temple`, `noonDarkness`, `dawn`, `battle`, `goldenCity`, e `heaven` (o céu atual, fora da viagem).
- No `void` e nas trevas o vídeo do anjo esmorece (opacidade), para a escuridão ser real.

### 5.5 O ecrã durante a viagem

```
 ┌───────────────────────────────────────────────┐
 │  [Cap. 1 · Antes do princípio]          [✕]   │
 │                                               │
 │            ◯ anel de luz com 12 olhos         │
 │           (  o Arcanjo no centro  )           │
 │                                               │
 │        בְּרֵאשִׁית  bereshit — «no princípio»   │  ← palavra original (aparece e desvanece)
 │                                               │
 │   «No princípio criou Deus os céus e a terra.»│  ← legenda do que está a ser dito
 │              Gênesis 1:1                      │
 │  [❚❚]  ────●──────────  [Pergunta ao anjo…]  │
 └───────────────────────────────────────────────┘
```

- Entrada: botão «Eu estava lá» no ecrã principal (e o anjo pode propô-lo quando alguém pergunta pelo princípio
  do mundo).
- Anel de luz: SVG à volta do anjo, 12 olhos; arrastar roda o anel; ao largar no olho de um capítulo, salta para lá.
- Progresso guardado no navegador (localStorage, com try/catch) para continuar no dia seguinte.

### 5.6 Interromper o anjo

- Por texto (barra de pergunta) ou por voz (botão do microfone / ouvinte nativo com barge-in).
- Ao interromper: a narração pausa e o céu fica suspenso; a pergunta vai pelo WebSocket existente (`/ws`) com o
  contexto do capítulo (título + referências do beat atual) e com a marca `mode: "ceu"`.
- Segurança: no modo `ceu` o agente só recebe as ferramentas do Céu (`CEU_TOOLSET`: biblia_* e mostrar_visao),
  nunca run_command, câmara, apps ou ficheiros, mesmo com FULL_ACCESS ligado. Assim a mesma peça serve no painel
  local do Carlos e na futura versão pública (que terá ainda autenticação própria, fora deste projeto).
  *(decisão do Claude)*
- A resposta é falada ao vivo com a mesma voz do Google, frase a frase: a primeira frase é sintetizada logo que o
  texto chega e as seguintes enquanto ela toca (começa a falar 3-10 s depois da pergunta; o céu mostra-o a «meditar»
  nesse intervalo). Se a voz do Google falhar (quota/erro), recorre à voz Edge com o mesmo efeito, para nunca ficar
  mudo. Depois: «Retomemos…» e a narração continua no beat seguinte.
- Limites por pessoa (`security/guard.py`) aplicam-se às perguntas.

### 5.7 Tesouros escondidos (ao vivo, sem gastar quota)

- Endpoint `GET /api/v1/ceu/journey/treasure?chapter=N` escolhe, de forma aleatória, uma palavra original dos
  versículos-chave do capítulo (TAHOT/TAGNT + léxico TBESH/TBESG) e devolve palavra, transliteração e sentido.
- Mostra-se como cartão no ecrã (sem voz, para não misturar vozes). Sem chamada ao cérebro.

## 6. O que fica para quem constrói

Estrutura interna dos componentes React, formato exato do `timeline.json`, valores dos parâmetros de cada cena
(afinar vendo), animação do anel, testes e ordem de implementação (sugestão: capítulo 1 completo de ponta a ponta
primeiro, depois os outros 11).

## 7. Decisões que ainda são do Carlos

- **Voz**: Google em tudo (decidido). Os limites grátis da voz do Google com muito uso ainda não foram medidos —
  medir no capítulo 1.
- O que a pessoa deve sentir/fazer no fim: por agora, o remate da secção 5.1 (convite a falar com Deus).
