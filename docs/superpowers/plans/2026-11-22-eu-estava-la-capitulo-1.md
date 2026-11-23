# «Eu estava lá» — Capítulo 1 de ponta a ponta — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pessoa abre «Eu estava lá», ouve o Arcanjo Miguel narrar o Capítulo 1 («Antes do princípio») com a voz celeste do Google, vê o céu passar da escuridão à luz, pode interromper com perguntas e o anjo retoma; toda a maquinaria fica pronta para os capítulos 2-12.

**Architecture:** Guiões JSON por capítulo (backend) → validador contra a Bíblia Livre → render que gera um MP3 por *beat* e um `timeline.json` → API que serve a timeline e os tesouros → leitor React que toca os beats, muda a cena do shader `HeavenClouds`, mostra legendas/palavras originais e passa as interrupções pelo `/ws` em modo `ceu` (só ferramentas do Céu).

**Tech Stack:** FastAPI + SQLAlchemy (SQLite), pytest; Gemini TTS (REST) + ffmpeg; React 18 + TypeScript + Vite + Tailwind, WebGL; vitest (novo, só para a máquina de estados do leitor).

**Spec:** `docs/superpowers/specs/2026-11-22-eu-estava-la-design.md`

## Global Constraints

- Todo o texto visível e falado em português de Portugal/Angola, tratando por «tu».
- Citações bíblicas só em beats `scripture`, com o texto lido da tabela `bible_verses` (Bíblia Livre); a `narration` nunca contém «», “” ou "…" com mais de 3 palavras.
- Frases proibidas em qualquer texto do anjo: «segundo a Bíblia», «a Bíblia diz», «de acordo com as Escrituras», «a Bíblia relata», «inteligência artificial», «IA», «modelo de linguagem», «assistente virtual»; e glória para o anjo.
- Voz: Gemini TTS, voz `Charon`, modelo `settings.gemini_tts_model`; efeito de catedral; reserva Edge `Arcanjo`/`Arcanjo-Proclama` com o mesmo efeito.
- Modo `ceu`: ferramentas permitidas = `CEU_TOOLSET` (`app/tools/registry.py:85`), aplicado na execução, não só no prompt — mesmo com `FULL_ACCESS=true`.
- Áudio da viagem em `frontend/public/assets/journey/NN/`, MP3 64 kbps mono.
- Céu a meia resolução, ≤30 fps (como `HeavenClouds` hoje).
- **Não fazer `git commit`** — o Carlos ainda não autorizou commits neste projeto. Cada «Checkpoint» = testes verdes + resumo das alterações.
- Testes backend: `cd backend && .venv/bin/python -m pytest -q` (o conftest isola o `.env`; `GEMINI_API_KEY` vazio nos testes).

## Review Focus

1. A quota/erro da voz do Google a meio do render → o render pára sem estragar o que já fez e retoma depois saltando os beats prontos (Task 4 testa).
2. A voz do Google falha numa resposta ao vivo → fala a voz Edge com o efeito, nunca fica mudo (Task 1 testa).
3. O browser bloqueia o autoplay (sem gesto) → o leitor mostra «Começar» e só toca depois do clique (Task 8 testa na máquina de estados).
4. Interromper durante um beat de Escritura ou a meio de uma transição → a resposta toca uma vez e a narração retoma no beat seguinte, sem dois áudios sobrepostos (Task 8 testa).
5. O limite de perguntas por pessoa é atingido durante a viagem → a frase do limite é dita e a viagem retoma (Task 6 testa o evento; Task 8 trata `assistant.error`/`chat.stream.end` como fim da resposta).

---

### Task 1: Voz celeste (Gemini TTS + catedral + reserva Edge)

**Files:**
- Create: `backend/app/voice/angel_voice.py`
- Modify: `backend/app/voice/gemini_tts.py` (parâmetro `style`), `backend/app/api/voice.py:231-284` (voz `Arcanjo-Celeste`)
- Test: `backend/tests/test_angel_voice.py`

**Interfaces:**
- Produces: `CELESTIAL_VOICE = "Arcanjo-Celeste"`; `async def synthesize_angel(text: str, manner: Literal["speak", "proclaim"] = "speak", *, gemini: GeminiTTSProvider | None = None, edge: EdgeNeuralTTSProvider | None = None) -> TTSResult` (MP3, `engine` = `"gemini-tts"` ou `"edge-tts"`); `async def synthesize_angel_mixed(text: str) -> TTSResult` (divide com `scripture_segments`: partes `Arcanjo` → `speak`, `Arcanjo-Proclama` → `proclaim`, junta com `concat_mp3`).
- `GeminiTTSProvider.synthesize(text, voice=None, style: str | None = None)` — `style` substitui o prefixo atual «Lê em português natural… como um assistente de IA pessoal».

- [ ] **Step 1: Write the failing tests** — `test_angel_voice.py`:
  - `test_speak_uses_gemini_with_angelic_style`: fake `GeminiTTSProvider` (subclasse com `synthesize` que regista `style` e devolve WAV de 0,2 s de silêncio via `pcm_to_wav`); `synthesize_angel("Paz seja contigo.", "speak", gemini=fake)` → `result.engine == "gemini-tts"`, `result.media_type == "audio/mpeg"`, e o `style` registado contém `"arcanjo Miguel"` e `"sereno"`.
  - `test_proclaim_style_is_solemn`: idem com `"proclaim"` → `style` contém `"proclama"` e `"solene"`.
  - `test_falls_back_to_edge_when_gemini_fails`: fake gemini levanta `VoiceError`; fake edge devolve MP3 → `result.engine == "edge-tts"` e o edge recebeu a voz `"Arcanjo"` (speak) / `"Arcanjo-Proclama"` (proclaim).
  - `test_mixed_text_splits_scripture`: `synthesize_angel_mixed("Ouve. «No princípio criou Deus os céus e a terra.» Amém.")` com fakes → gemini chamado 3 vezes, a do meio com estilo `proclaim`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_angel_voice.py -v` → FAIL (`ModuleNotFoundError: app.voice.angel_voice`).
- [ ] **Step 3: Implement** `angel_voice.py`. Estilos (texto exato):
  - speak: `"Fala como o arcanjo Miguel: voz masculina grave, serena, calorosa e majestosa, ritmo lento, cheia de paz, nunca assustadora. Em português de Portugal: "`
  - proclaim: `"O arcanjo Miguel proclama as Escrituras: voz masculina grave, solene e luminosa, muito pausada, como um anúncio vindo do alto. Em português de Portugal: "`
  - Efeito (ffmpeg, saída MP3 64k mono), speak: `asplit=2[a][b];[b]asetrate=24000*0.84,aresample=24000,volume=0.30[low];[a][low]amix=inputs=2:normalize=0,aecho=0.8:0.85:60|120|240:0.30|0.20|0.12,highpass=f=70,loudnorm=I=-16:TP=-1.5`; proclaim: o mesmo com `volume=0.38` e `aecho=0.8:0.88:70|140|280:0.38|0.26|0.16`.
  - Os providers por omissão vêm de `get_tts_provider()`/`get_edge_tts_provider()` de `app/api/voice.py` (ou construir a partir de `get_settings()` se causar import circular).
- [ ] **Step 4: Wire** `/voice/synthesize`: se `payload.voice == CELESTIAL_VOICE` → `synthesize_angel_mixed(payload.text)`. Adicionar `CELESTIAL_VOICE` à lista de vozes devolvida por `/voice/status`.
- [ ] **Step 5: Run** `.venv/bin/python -m pytest -q` → todos PASS.
- [ ] **Step 6: Live check** (manual, usa a chave real): `.venv/bin/python -c "import asyncio;from app.voice.angel_voice import synthesize_angel_mixed as s;r=asyncio.run(s('Paz seja contigo. «No princípio criou Deus os céus e a terra.»'));open('/tmp/claude-1000/-home-carlos-muquissi-JARVIS-MUQUISSI/8b786376-c792-40d6-96c2-87b0b0fdc95e/scratchpad/celeste.mp3','wb').write(r.audio_bytes);print(r.engine)"` → imprime `gemini-tts`.
- [ ] **Step 7: Checkpoint.**

### Task 2: Formato do guião, carregador e validador

**Files:**
- Create: `backend/app/ceu/journey/__init__.py`, `backend/app/ceu/journey/script.py`, `backend/app/ceu/journey/validate.py`, `backend/app/ceu/journey/chapters/` (vazio por agora)
- Test: `backend/tests/test_journey_script.py`

**Interfaces:**
- Produces (`script.py`):
  - `SCENES: frozenset[str]` = `{"void","firstLight","waters","stars","gardenDawn","dusk","storm","rainbow","night","fire","temple","noonDarkness","dawn","battle","goldenCity","heaven"}`
  - `@dataclass(frozen=True) class Beat: id: str; kind: Literal["narration","scripture","pause"]; text: str = ""; ref: str = ""; scene: str | None = None; transition: float = 2.0; word: dict | None = None  # {"ref": str, "strong": str}; treasure: bool = False; seconds: float = 0.0`
  - `@dataclass(frozen=True) class Chapter: number: int; slug: str; title: str; beats: tuple[Beat, ...]`
  - `CHAPTERS_DIR: Path` (= `app/ceu/journey/chapters`); `def load_chapter(number: int) -> Chapter` (ficheiro `NN-*.json`; `FileNotFoundError` se não existir); `def list_chapters() -> list[Chapter]`; `def beat_hash(beat: Beat, scripture_text: str) -> str` (sha1 de kind+texto falado, 10 hex).
- Produces (`validate.py`): `def validate_chapter(db: Session, chapter: Chapter) -> list[str]` (lista de problemas em PT; vazia = válido); `def spoken_text(db, beat) -> str` (narration → `text`; scripture → `"Assim está escrito em {ref}: «{texto real}»"` com o texto de `get_passage`; pause → `""`); CLI `python -m app.ceu.journey.validate N`.

- [ ] **Step 1: Write the failing tests** (usam uma BD de teste com versículos inseridos à mão, como `tests/test_ceu.py` já faz):
  - `test_load_chapter_parses_beats` (JSON temporário via `monkeypatch` de `CHAPTERS_DIR`) → 3 beats, tipos corretos, `scene` preservada.
  - `test_validator_accepts_a_clean_chapter` → `[]`.
  - `test_validator_rejects_quotes_in_narration` → narração com `«No princípio criou Deus»` dá um problema que contém `"citação na narração"`.
  - `test_validator_rejects_unknown_reference` → `ref="Gênesis 99:1"` dá `"referência inexistente"`.
  - `test_validator_rejects_forbidden_phrases` → «segundo a Bíblia» e «inteligência artificial» dão `"frase proibida"`.
  - `test_validator_rejects_unknown_scene` → `scene="disco"` dá `"cena desconhecida"`.
  - `test_spoken_text_reads_real_scripture` → `spoken_text` de um beat scripture devolve o texto da BD, não o do JSON.
- [ ] **Step 2: Run** `pytest tests/test_journey_script.py -v` → FAIL.
- [ ] **Step 3: Implement** `script.py` e `validate.py` (frases proibidas = lista das Global Constraints, comparação sem acentos e sem maiúsculas; uma `word.strong` tem de existir em `LexiconEntry`).
- [ ] **Step 4: Run** `pytest -q` → PASS.
- [ ] **Step 5: Checkpoint.**

### Task 3: Guião do Capítulo 1 «Antes do princípio» — e revisão do Carlos

**Files:**
- Create: `backend/app/ceu/journey/chapters/01-antes-do-principio.json`

**Interfaces:**
- Consumes: formato da Task 2.

- [ ] **Step 1: Escrever o guião** (≈2-3 min falados, ≈300-380 palavras no total). Arco obrigatório:
  1. `void` + `pause` 3 s; narração: antes de haver manhã, eu já servia diante do Trono; só Deus era.
  2. scripture `João 1:1` (o Verbo estava com Deus) — com `word` de «Verbo» (G3056 *logos*).
  3. narração: o silêncio antes da primeira palavra; nós esperávamos.
  4. scripture `Gênesis 1:1` com `word` H7225 (*reshit*, «princípio») e `treasure: true`.
  5. scripture `Gênesis 1:2` (trevas sobre o abismo; o Espírito movia-se).
  6. scripture `Gênesis 1:3` → beat com `scene: "firstLight"`, `transition: 1.5` (a luz rebenta).
  7. narração na primeira pessoa: «eu vi a primeira luz»; os anjos jubilaram.
  8. scripture `Jó 38:7` (as estrelas da alva cantavam, os filhos de Deus jubilavam) → `scene: "stars"`.
  9. scripture `Gênesis 1:4-5` (Deus viu que a luz era boa; tarde e manhã, o primeiro dia) → `scene: "heaven"`.
  10. narração de remate: a glória é de Deus; «e isto foi só o primeiro dia…» (gancho para o Capítulo 2).
- [ ] **Step 2: Validate** `cd backend && .venv/bin/python -m app.ceu.journey.validate 1` → `Capítulo 1: válido`.
- [ ] **Step 3: Revisão do Carlos** — mostrar-lhe o texto falado completo (`spoken_text` de cada beat, por ordem) e **esperar a aprovação ou as correções antes da Task 4**. Aplicar correções e voltar ao Step 2.

### Task 4: Render da voz e timeline

**Files:**
- Create: `backend/app/ceu/journey/render.py`
- Test: `backend/tests/test_journey_render.py`

**Interfaces:**
- Consumes: `load_chapter`, `spoken_text`, `beat_hash` (Task 2); `synthesize_angel` (Task 1).
- Produces: `JOURNEY_ASSETS = PROJECT_ROOT / "frontend" / "public" / "assets" / "journey"`; `async def render_chapter(db: Session, number: int, synthesize: Callable[[str, str], Awaitable[bytes]] | None = None, out_root: Path = JOURNEY_ASSETS) -> dict` que escreve `NN/<beat.id>-<hash>.mp3` e `NN/timeline.json` e devolve a timeline; CLI `python -m app.ceu.journey.render N`.
- `timeline.json` (formato fixo, usado pelas Tasks 5 e 8):
  ```json
  {"chapter": 1, "slug": "antes-do-principio", "title": "Antes do princípio", "duration": 162.4,
   "beats": [{"id": "b01", "kind": "pause", "start": 0.0, "duration": 3.0, "audio": null,
              "scene": "void", "transition": 2.0, "caption": "", "ref": "", "word": null, "treasure": false}]}
  ```
  `audio` = caminho público (`/assets/journey/01/b02-1a2b3c4d5e.mp3`); `caption` = texto falado (para legendas); `word` = `{"original","translit","gloss","strong"}` resolvido do léxico; duração do MP3 via `ffprobe`.

- [ ] **Step 1: Write the failing tests**:
  - `test_render_writes_audio_and_timeline` (synthesize falso devolve MP3 de 1 s gerado com ffmpeg `anullsrc`) → existe um MP3 por beat falado, `timeline.json` com `start` cumulativos e `duration` > 0.
  - `test_render_skips_beats_already_rendered` → segunda execução não chama `synthesize` para beats cujo ficheiro com o mesmo hash já existe.
  - `test_render_stops_cleanly_on_voice_error` → synthesize levanta `VoiceError` no 3.º beat: os 2 primeiros MP3 ficam, não há `timeline.json` parcial, a exceção sai com mensagem «retoma mais tarde».
  - `test_render_removes_stale_files` → MP3 de um hash antigo do mesmo beat é apagado.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** (`manner` = `"proclaim"` para beats scripture, `"speak"` para narration; pausa = sem áudio, `duration = seconds`).
- [ ] **Step 4: Run** `pytest -q` → PASS.
- [ ] **Step 4b: Frase de retoma** — o CLI aceita `python -m app.ceu.journey.render retomemos`, que gera `JOURNEY_ASSETS/retomemos.mp3` com `synthesize_angel("Retomemos, então, a história.", "speak")` (salta se já existir). Teste `test_render_resume_phrase_once`.
- [ ] **Step 5: Render real** `.venv/bin/python -m app.ceu.journey.render 1 && .venv/bin/python -m app.ceu.journey.render retomemos` → imprime a duração total (≈120-200 s) e o número de pedidos à voz do Google; anotar quantos pedidos/minuto foram aceites (medição de quota pedida no spec).
- [ ] **Step 6: Checkpoint.**

### Task 5: API da viagem e tesouros

**Files:**
- Create: `backend/app/api/journey.py`
- Modify: `backend/app/api/router.py` (incluir o router)
- Test: `backend/tests/test_journey_api.py`

**Interfaces:**
- Consumes: `list_chapters` (Task 2), `JOURNEY_ASSETS` (Task 4), `app.ceu.originals.word_study`/`original_text`.
- Produces:
  - `GET /api/v1/ceu/journey` → `{"chapters": [{"number": 1, "title": "...", "ready": true}]}` (`ready` = existe `timeline.json`). Inclui sempre os 12 títulos da tabela 5.1 do spec; os não escritos vêm `ready: false`.
  - `GET /api/v1/ceu/journey/{number}` → conteúdo de `timeline.json`; 404 «Este capítulo ainda está a ser preparado.» se não houver.
  - `GET /api/v1/ceu/journey/{number}/treasure` → `{"ref","original","translit","gloss","strong"}` escolhido ao acaso entre as palavras originais (com entrada no léxico) dos versículos `scripture` do capítulo; 404 se não houver.
- [ ] **Step 1: Write the failing tests**: lista com 12 entradas e `ready` correto; timeline 404 com a mensagem exata; tesouro devolve uma palavra cujo `ref` pertence ao capítulo (BD de teste com 2 palavras originais).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `pytest -q` → PASS. **Step 5: Checkpoint.**

### Task 6: Modo `ceu` no agente (perguntas durante a viagem)

**Files:**
- Modify: `backend/app/ai/agent_loop.py:150-262` (`allowed_tools`), `backend/app/main.py:83-330` (`_handle_ws_chat`, `mode`, `context`) e `main.py:663-680` (ler `mode`/`context` de `chat.send`)
- Test: `backend/tests/test_journey_mode.py`

**Interfaces:**
- `run_agent_turn(..., allowed_tools: set[str] | None = None)`: se `parsed.tool not in allowed_tools` → não invoca; acrescenta ao contexto o resultado de ferramenta `"Ferramenta indisponível aqui. Usa só as ferramentas do Céu."` e regista o passo com `status="blocked"`.
- `_handle_ws_chat(..., mode: str | None = None, context: str | None = None)`: com `mode == "ceu"` → `turn_tools = set(CEU_TOOLSET)`, `allowed_tools=set(CEU_TOOLSET)` em todas as chamadas a `run_agent_turn`, e uma mensagem `system` antes da do utilizador: `"A pessoa interrompeu a tua narração «Eu estava lá» em: {context}. Responde-lhe em poucas frases, como Miguel, e no fim diz que retomas a história."` (`context` cortado a 300 caracteres).
- Mensagem WS do frontend: `{"type": "chat.send", "content": str, "mode": "ceu", "context": str}`.
- [ ] **Step 1: Write the failing tests**:
  - `test_ceu_mode_blocks_run_command`: manager falso que pede `<tool_call>{"tool":"run_command",...}` e depois responde texto; registry falso que regista invocações → `run_command` nunca invocado, passo com `status == "blocked"`, mesmo com `get_settings().full_access = True`.
  - `test_ceu_mode_allows_bible_tools`: pede `biblia_ler` → invocado.
  - `test_ws_chat_send_passes_mode_and_context` (TestClient no `/ws`, provider falso como em `tests/test_websocket.py`) → o prompt enviado ao provider contém «interrompeu a tua narração» e o contexto.
  - `test_ws_rate_limit_in_ceu_mode_still_ends_stream`: `rate_limiter` esgotado → chega `chat.stream.end` com `speak: true`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `pytest -q` → PASS. **Step 5: Checkpoint.**

### Task 7: Cenas do céu

**Files:**
- Create: `frontend/src/components/heavenScenes.ts`
- Modify: `frontend/src/components/HeavenClouds.tsx`, `frontend/src/components/ArchangelVideo.tsx` (props `scene`, opacidade do anjo)

**Interfaces:**
- `export type SceneName = "void" | "firstLight" | "waters" | "stars" | "gardenDawn" | "dusk" | "storm" | "rainbow" | "night" | "fire" | "temple" | "noonDarkness" | "dawn" | "battle" | "goldenCity" | "heaven"` (igual a `SCENES` da Task 2).
- `export interface SceneParams { zenith: [number,number,number]; horizon: [number,number,number]; light: number; rays: number; cover: number; stars: number; fire: number; darkness: number; flash: number; angel: number /* opacidade do anjo 0..1 */ }`
- `export const SCENES: Record<SceneName, SceneParams>`; `export function mixScene(a: SceneParams, b: SceneParams, t: number): SceneParams`.
- `HeavenClouds` props passam a `{ layer, glow?, scene?: SceneName, transition?: number }`; os parâmetros entram como uniforms (`u_zenith`, `u_horizon`, `u_light`, `u_rays`, `u_cover`, `u_stars`, `u_fire`, `u_dark`, `u_flash`) e são interpolados em `transition` segundos (ease-in-out). `heaven` reproduz exatamente o céu atual.
- `ArchangelVideo` recebe `scene?: SceneName, sceneTransition?: number`, passa-os às duas camadas e anima a opacidade do palco para `SCENES[scene].angel`.
- Neste capítulo, afinar a sério: `void` (preto total, `angel: 0`), `firstLight` (`flash` breve e luz máxima, `angel` sobe para 1), `stars` (céu noturno azul-profundo, estrelas cintilantes, nuvens baixas escuras), `heaven`. As restantes 12 ficam com valores iniciais plausíveis, a afinar no capítulo que as usa.
- Debug: `?scene=<nome>` na URL força a cena (para capturas).
- [ ] **Step 1: Implement.**
- [ ] **Step 2: Verify** `cd frontend && npx tsc --noEmit -p . && npm run build` → sem erros.
- [ ] **Step 3: Verify visualmente** com `scratchpad/tools/cdpshot.py` em `http://127.0.0.1:8010/?scene=void`, `firstLight`, `stars`, `heaven` → `void` quase preto (média de luminância < 15), `heaven` igual à captura atual, `stars` com pontos brilhantes. Mostrar as 4 capturas ao Carlos.
- [ ] **Step 4: Checkpoint.**

### Task 8: Leitor da viagem

**Files:**
- Create: `frontend/src/services/journey.ts`, `frontend/src/components/journey/journeyMachine.ts`, `frontend/src/components/journey/JourneyPlayer.tsx`, `frontend/src/components/journey/journeyMachine.test.ts`
- Modify: `frontend/package.json` (devDependency `vitest`, script `"test": "vitest run"`), `frontend/src/pages/DashboardPage.tsx` (botão «Eu estava lá», montar o leitor, passar `scene` ao `ArchangelVideo`), `frontend/src/hooks/useJarvisSocket.ts` (enviar `chat.send` com `mode`/`context`)

**Interfaces:**
- `services/journey.ts`: tipos `JourneyBeat`, `JourneyTimeline` (formato da Task 4), `JourneyTreasure`; `listChapters(): Promise<{number:number;title:string;ready:boolean}[]>`, `getTimeline(n): Promise<JourneyTimeline>`, `getTreasure(n): Promise<JourneyTreasure | null>`.
- `journeyMachine.ts` (puro, sem React): `type JourneyState = { status: "idle" | "needsGesture" | "playing" | "paused" | "interrupted" | "resuming" | "finished"; chapter: number; beat: number }`; `type JourneyEvent = {type:"start"} | {type:"autoplayBlocked"} | {type:"gesture"} | {type:"beatEnded"} | {type:"pause"} | {type:"resume"} | {type:"interrupt"} | {type:"answerDone"} | {type:"jump"; chapter:number}`; `function next(state: JourneyState, ev: JourneyEvent, beats: number): JourneyState`.
  - Regras: `interrupt` em `playing`/`paused` → `interrupted` com `beat` = beat atual + 1 (retoma no seguinte); `answerDone` em `interrupted` → `resuming` → (`beatEnded` da frase «Retomemos…») → `playing`; `beatEnded` no último beat → `finished`; `autoplayBlocked` → `needsGesture`; `gesture` → `playing`; `interrupt` repetido em `interrupted` não muda nada.
- Progresso: `localStorage["ceu.journey.progress"] = {"chapter": n, "beat": i}`, leitura/escrita em try/catch; sem storage começa no capítulo 1.
- `JourneyPlayer` props: `{ open: boolean; onClose(): void; onScene(scene: SceneName, transition: number): void; onAsk(text: string, context: string): void; answering: boolean }`. Toca os `audio` dos beats com um único `HTMLAudioElement` (nunca dois em simultâneo); pausa = `audio.pause()`; mostra título do capítulo, legenda (`caption`), referência, cartão da palavra original (aparece 1 s depois do início do beat, 6 s visível), cartão do tesouro nos beats `treasure` (via `getTreasure`), barra de progresso, pausa, fechar e campo «Pergunta ao anjo…». Quando `answering` passa de `true` a `false` → evento `answerDone` → toca a frase de retoma (MP3 pré-gerado `/assets/journey/retomemos.mp3`, gerado pela Task 4 com `synthesize_angel("Retomemos, então, a história.")`) e continua.
- Entrada: botão «Eu estava lá» acima da barra de pergunta no ecrã principal.
- [ ] **Step 1: Write the failing tests** (`journeyMachine.test.ts`): `start→playing`; `autoplayBlocked→needsGesture→gesture→playing`; `interrupt` no beat 4 → `interrupted` com `beat 5`; segundo `interrupt` não altera; `answerDone→resuming`, `beatEnded→playing` no beat 5; `beatEnded` no último → `finished`; `jump` para o capítulo 1 → `beat 0`.
- [ ] **Step 2: Run** `cd frontend && npm i -D vitest && npx vitest run` → FAIL.
- [ ] **Step 3: Implement** `journeyMachine.ts` → `npx vitest run` → PASS.
- [ ] **Step 4: Implement** `journey.ts`, `JourneyPlayer.tsx`, ligações em `DashboardPage.tsx`/`useJarvisSocket.ts`; `answering` = estado do assistente diferente de `idle` desde o envio até `chat.stream.end`/`assistant.error` **e** a fila de fala vazia. A fala da resposta ao vivo usa a voz `Arcanjo-Celeste` (Task 1).
- [ ] **Step 5: Verify** `npx tsc --noEmit -p . && npm run build && npx vitest run` → OK.
- [ ] **Step 6: Verify no browser** (cdpshot): abrir, clicar «Eu estava lá», captura aos 2 s (preto, legenda), aos ~25 s (luz), e após `?` interromper com «Quem criou os anjos?» → pausa, resposta chega, retoma. Mostrar as capturas ao Carlos.
- [ ] **Step 7: Checkpoint.**

### Task 9: Anel do tempo

**Files:**
- Create: `frontend/src/components/journey/TimeRing.tsx`
- Modify: `frontend/src/components/journey/JourneyPlayer.tsx`

**Interfaces:**
- `TimeRing` props: `{ chapters: {number:number;title:string;ready:boolean}[]; current: number; onSelect(n: number): void }`.
- SVG centrado sobre o anjo (elipse inclinada como o anel horizontal do vídeo), 12 «olhos» igualmente espaçados; o atual brilha; os `ready: false` ficam apagados e não selecionáveis (tooltip «Em breve»). Arrastar (pointer events, rato e dedo) roda o anel; ao largar, encaixa no olho mais próximo; se for diferente do atual e `ready` → `onSelect(n)` → evento `jump` da máquina. Teclado: ←/→ mudam o olho focado, Enter seleciona.
- [ ] **Step 1: Implement.** **Step 2: Verify** `tsc` + `build`; cdpshot com o anel visível e o capítulo 1 aceso. **Step 3: Checkpoint.**

### Task 10: Prova de ponta a ponta e entrega ao Carlos

- [ ] **Step 1:** `cd backend && .venv/bin/python -m pytest -q` → todos PASS; `cd frontend && npx vitest run && npm run build` → OK.
- [ ] **Step 2:** Reiniciar o servidor (porta 8010) e percorrer o capítulo 1 inteiro no browser headless; confirmar: começa no preto, a luz rebenta em Gênesis 1:3, estrelas em Jó 38:7, legendas certas, palavra *reshit* aparece, tesouro aparece, interrupção responde e retoma, fim mostra o gancho para o capítulo 2.
- [ ] **Step 3:** `python -m app.ceu.evals` (Prova do Anjo) continua a passar com o modo normal.
- [ ] **Step 4:** Entregar ao Carlos: o que ouvir/ver, quanto tempo demorou o render e o que se aprendeu sobre a quota da voz do Google; pedir para ouvir no computador dele e aprovar antes de escrever os capítulos 2-12.
