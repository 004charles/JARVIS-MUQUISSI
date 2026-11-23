import { BookOpen, ChevronLeft, Languages, Link2, Send, Sparkles, X } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  type CeuBook,
  type CeuDaily,
  type CeuVision,
  type CeuOriginal,
  type CeuPassage,
  type CeuRelated,
  type CeuWordStudy,
  ceuApi,
} from "../services/ceu";
import type { AssistantState, ChatMessageItem } from "../types/api";

/**
 * O Céu — the interface around the Arcanjo Miguel:
 * ask by text, read answers as cards with clickable Bible references and follow-up actions,
 * open any verse (text · original Hebrew/Greek word by word · related passages · word study),
 * and read the Bible by book and chapter.
 */

interface CeuPanelProps {
  messages: ChatMessageItem[];
  streamingText: string;
  assistantState: AssistantState;
  onAsk: (text: string) => void;
  vision?: CeuVision | null;
  onCloseVision?: () => void;
}

const glass = "border border-white/60 bg-white/70 shadow-xl shadow-rose-900/10 backdrop-blur-xl";
const scripture = { fontFamily: "Georgia, 'Times New Roman', serif" };

// ------------------------------------------------------------------ reference detection
function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function useRefRegex(books: CeuBook[]) {
  return useMemo(() => {
    if (!books.length) return null;
    const names = books.flatMap((b) => [b.name, b.abbrev]).filter(Boolean);
    names.sort((a, b) => b.length - a.length);
    return new RegExp(`\\b(${names.map(escapeRe).join("|")})\\.?\\s+(\\d{1,3})(?::(\\d{1,3})(?:\\s*[-–—\u2010\u2011]\\s*(\\d{1,3}))?)?`, "g");
  }, [books]);
}

/** Render answer text: paragraphs, **bold**, and Bible references as clickable chips. */
function RichAnswer({ text, refRe, onRef }: { text: string; refRe: RegExp | null; onRef: (ref: string) => void }) {
  const renderInline = (line: string, key: string): ReactNode[] => {
    const out: ReactNode[] = [];
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    parts.forEach((part, pi) => {
      const bold = part.startsWith("**") && part.endsWith("**");
      const content = bold ? part.slice(2, -2) : part;
      const nodes: ReactNode[] = [];
      if (refRe) {
        let last = 0;
        refRe.lastIndex = 0;
        let m: RegExpExecArray | null;
        while ((m = refRe.exec(content))) {
          if (m.index > last) nodes.push(content.slice(last, m.index));
          const ref = m[0].trim();
          nodes.push(
            <button
              key={`${key}-${pi}-${m.index}`}
              type="button"
              onClick={() => onRef(ref)}
              className="mx-0.5 inline-flex items-center rounded-full bg-amber-100/90 px-2 py-0.5 text-[0.85em] font-medium text-amber-900 ring-1 ring-amber-300/70 hover:bg-amber-200"
            >
              {ref}
            </button>,
          );
          last = m.index + m[0].length;
        }
        if (last < content.length) nodes.push(content.slice(last));
      } else {
        nodes.push(content);
      }
      out.push(bold ? <strong key={`${key}-b${pi}`}>{nodes}</strong> : <span key={`${key}-s${pi}`}>{nodes}</span>);
    });
    return out;
  };
  return (
    <div className="space-y-2 leading-relaxed">
      {text
        .split(/\n+/)
        .filter((l) => l.trim())
        .map((line, i) => {
          const bullet = /^\s*[-•*]\s+/.test(line);
          return (
            <p key={i} className={bullet ? "pl-4 before:-ml-3 before:mr-1.5 before:content-['•']" : ""}>
              {renderInline(line.replace(/^\s*[-•*]\s+/, "").replace(/^#+\s*/, ""), `l${i}`)}
            </p>
          );
        })}
    </div>
  );
}

// ------------------------------------------------------------------ verse card
function VerseCard({ reference, onClose, onReadChapter }: { reference: string; onClose: () => void; onReadChapter: (ref: string) => void }) {
  const [tab, setTab] = useState<"texto" | "original" | "relacionados">("texto");
  const [passage, setPassage] = useState<CeuPassage | null>(null);
  const [original, setOriginal] = useState<CeuOriginal | null>(null);
  const [related, setRelated] = useState<CeuRelated[] | null>(null);
  const [study, setStudy] = useState<CeuWordStudy | null>(null);
  const [current, setCurrent] = useState(reference);
  const [error, setError] = useState("");

  useEffect(() => setCurrent(reference), [reference]);
  useEffect(() => {
    setPassage(null);
    setOriginal(null);
    setRelated(null);
    setStudy(null);
    setError("");
    setTab("texto");
    ceuApi.passage(current).then(setPassage).catch((e: Error) => setError(e.message));
  }, [current]);
  useEffect(() => {
    if (tab === "original" && !original) ceuApi.original(current).then(setOriginal).catch((e: Error) => setError(e.message));
    if (tab === "relacionados" && !related) ceuApi.related(current).then((r) => setRelated(r.related)).catch((e: Error) => setError(e.message));
  }, [tab, current, original, related]);

  const tabBtn = (id: typeof tab, label: string, icon: ReactNode) => (
    <button
      type="button"
      onClick={() => setTab(id)}
      className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition ${
        tab === id ? "bg-amber-600 text-white shadow" : "text-stone-600 hover:bg-white/80"
      }`}
    >
      {icon}
      {label}
    </button>
  );

  return (
    <div className={`${glass} pointer-events-auto flex max-h-[78vh] w-[min(560px,92vw)] flex-col rounded-3xl p-5 text-stone-800`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-amber-700/80">Escrituras</div>
          <h3 className="text-xl font-semibold" style={scripture}>
            {passage?.reference || current}
          </h3>
        </div>
        <button type="button" onClick={onClose} className="rounded-full p-1.5 text-stone-500 hover:bg-white hover:text-stone-800">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mb-3 flex flex-wrap gap-1 rounded-full bg-stone-100/70 p-1">
        {tabBtn("texto", "Texto", <BookOpen className="h-3.5 w-3.5" />)}
        {tabBtn("original", "Original", <Languages className="h-3.5 w-3.5" />)}
        {tabBtn("relacionados", "Relacionados", <Link2 className="h-3.5 w-3.5" />)}
      </div>
      {error && <div className="mb-2 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {tab === "texto" && passage && (
          <div className="space-y-2 text-[1.02rem] leading-relaxed" style={scripture}>
            {passage.verses.map((v) => (
              <p key={v.ref}>
                <sup className="mr-1 text-[0.7em] font-sans font-semibold text-amber-700">{v.verse}</sup>
                {v.text}
              </p>
            ))}
            <button
              type="button"
              onClick={() => onReadChapter(current)}
              className="mt-2 text-sm font-sans text-amber-800 underline-offset-2 hover:underline"
            >
              Ler o capítulo completo →
            </button>
          </div>
        )}

        {tab === "original" && original && (
          <div className="space-y-4">
            <div className="text-xs text-stone-500">
              Texto original em {original.language}. Toca numa palavra para ver o seu significado.
            </div>
            {original.verses.map((v) => (
              <div key={v.ref}>
                <div className="mb-1 text-xs font-semibold text-amber-800">{v.ref}</div>
                <div className="flex flex-wrap gap-1.5" dir={original.language === "hebraico" ? "rtl" : "ltr"}>
                  {v.words.map((w, i) => (
                    <button
                      key={`${v.ref}-${i}`}
                      type="button"
                      onClick={() => ceuApi.word(w.strong).then(setStudy).catch(() => undefined)}
                      className="rounded-xl bg-white/80 px-2 py-1 text-center ring-1 ring-stone-200 hover:ring-amber-400"
                      dir="ltr"
                    >
                      <div className="text-lg leading-tight" style={scripture} dir={original.language === "hebraico" ? "rtl" : "ltr"}>
                        {w.word}
                      </div>
                      <div className="text-[10px] italic text-stone-500">{w.translit}</div>
                      <div className="text-[10px] text-stone-700">{w.gloss}</div>
                    </button>
                  ))}
                </div>
              </div>
            ))}
            {study && (
              <div className="rounded-2xl bg-amber-50/90 p-3 ring-1 ring-amber-200">
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl" style={scripture}>{study.lemma}</span>
                  <span className="italic text-stone-600">{study.translit}</span>
                  <span className="ml-auto text-xs text-stone-500">{study.strong}</span>
                </div>
                <div className="text-sm font-medium text-amber-900">
                  {study.gloss} · {study.occurrences} ocorrências
                </div>
                <p className="mt-2 max-h-40 overflow-y-auto whitespace-pre-line text-xs leading-relaxed text-stone-700">
                  {study.definition}
                </p>
                {study.sample_refs.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {study.sample_refs.map((r) => (
                      <button key={r} type="button" onClick={() => setCurrent(r)} className="rounded-full bg-white px-2 py-0.5 text-[11px] text-amber-800 ring-1 ring-amber-200 hover:bg-amber-100">
                        {r}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div className="text-[10px] text-stone-400">{original.attribution}</div>
          </div>
        )}

        {tab === "relacionados" && related && (
          <div className="space-y-2">
            {related.length === 0 && <div className="text-sm text-stone-500">Sem passagens relacionadas.</div>}
            {related.map((r) => (
              <button key={r.ref} type="button" onClick={() => setCurrent(r.ref)} className="block w-full rounded-2xl bg-white/80 p-3 text-left ring-1 ring-stone-200 hover:ring-amber-400">
                <div className="text-sm font-semibold text-amber-800">{r.ref}</div>
                <div className="text-sm text-stone-700" style={scripture}>{r.text}</div>
              </button>
            ))}
          </div>
        )}
      </div>
      {passage?.attribution && <div className="mt-3 border-t border-stone-200/70 pt-2 text-[10px] leading-snug text-stone-400">{passage.attribution}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ Bible reader
function BibleReader({ books, initialRef, onClose, onVerse }: { books: CeuBook[]; initialRef?: string; onClose: () => void; onVerse: (ref: string) => void }) {
  const [book, setBook] = useState<CeuBook | null>(null);
  const [chapter, setChapter] = useState<number | null>(null);
  const [passage, setPassage] = useState<CeuPassage | null>(null);

  useEffect(() => {
    if (!initialRef || !books.length) return;
    const m = initialRef.match(/^(.+?)\s+(\d+)/);
    if (!m) return;
    const found = books.find((b) => b.name.toLowerCase() === m[1].toLowerCase() || b.abbrev.toLowerCase() === m[1].toLowerCase());
    if (found) {
      setBook(found);
      setChapter(Number(m[2]));
    }
  }, [initialRef, books]);

  useEffect(() => {
    if (book && chapter) ceuApi.passage(`${book.name} ${chapter}`).then(setPassage).catch(() => setPassage(null));
  }, [book, chapter]);

  const groups = useMemo(() => {
    const g: Record<string, CeuBook[]> = {};
    books.forEach((b) => (g[`${b.testament === "AT" ? "Antigo Testamento" : "Novo Testamento"} · ${b.group}`] ||= []).push(b));
    return Object.entries(g);
  }, [books]);

  return (
    <div className={`${glass} pointer-events-auto flex max-h-[80vh] w-[min(440px,92vw)] flex-col rounded-3xl p-5 text-stone-800`}>
      <div className="mb-3 flex items-center gap-2">
        {(book || chapter) && (
          <button type="button" onClick={() => (chapter ? setChapter(null) : setBook(null))} className="rounded-full p-1 text-stone-500 hover:bg-white">
            <ChevronLeft className="h-4 w-4" />
          </button>
        )}
        <h3 className="text-lg font-semibold" style={scripture}>
          {book ? `${book.name}${chapter ? ` ${chapter}` : ""}` : "A Bíblia"}
        </h3>
        <button type="button" onClick={onClose} className="ml-auto rounded-full p-1.5 text-stone-500 hover:bg-white">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {!book &&
          groups.map(([name, list]) => (
            <div key={name} className="mb-3">
              <div className="mb-1 text-[11px] uppercase tracking-wider text-amber-700/80">{name}</div>
              <div className="flex flex-wrap gap-1">
                {list.map((b) => (
                  <button key={b.ordinal} type="button" onClick={() => setBook(b)} className="rounded-full bg-white/80 px-2.5 py-1 text-xs ring-1 ring-stone-200 hover:ring-amber-400">
                    {b.name}
                  </button>
                ))}
              </div>
            </div>
          ))}
        {book && !chapter && (
          <div className="grid grid-cols-8 gap-1.5">
            {Array.from({ length: book.chapters }, (_, i) => i + 1).map((c) => (
              <button key={c} type="button" onClick={() => setChapter(c)} className="rounded-lg bg-white/80 py-1.5 text-sm ring-1 ring-stone-200 hover:ring-amber-400">
                {c}
              </button>
            ))}
          </div>
        )}
        {book && chapter && passage && (
          <div className="space-y-1.5 text-[1.02rem] leading-relaxed" style={scripture}>
            {passage.verses.map((v) => (
              <p key={v.ref} onClick={() => onVerse(v.ref)} className="cursor-pointer rounded-lg px-1 hover:bg-amber-50">
                <sup className="mr-1 font-sans text-[0.7em] font-semibold text-amber-700">{v.verse}</sup>
                {v.text}
              </p>
            ))}
            <div className="flex justify-between pt-3 font-sans text-sm">
              <button type="button" disabled={chapter <= 1} onClick={() => setChapter(chapter - 1)} className="text-amber-800 disabled:opacity-30">
                ← Capítulo {chapter - 1}
              </button>
              <button type="button" disabled={chapter >= book.chapters} onClick={() => setChapter(chapter + 1)} className="text-amber-800 disabled:opacity-30">
                Capítulo {chapter + 1} →
              </button>
            </div>
            <div className="pt-2 font-sans text-[10px] text-stone-400">{passage.attribution}</div>
          </div>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ word of the day
async function speakArcanjo(text: string) {
  const res = await fetch("/api/v1/voice/synthesize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice: "Arcanjo" }),
  });
  if (!res.ok) return;
  const url = URL.createObjectURL(await res.blob());
  const audio = new Audio(url);
  audio.onended = () => URL.revokeObjectURL(url);
  await audio.play().catch(() => undefined);
}

function DailyWord({ daily, onAsk, onOpen, onClose }: { daily: CeuDaily; onAsk: (q: string) => void; onOpen: (ref: string) => void; onClose: () => void }) {
  const [speaking, setSpeaking] = useState(false);
  return (
    <div className={`${glass} pointer-events-auto w-[min(380px,92vw)] rounded-3xl p-5 text-stone-800`}>
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.2em] text-amber-700/80">
          <Sparkles className="h-3.5 w-3.5" /> Palavra do dia
        </div>
        <button type="button" onClick={onClose} className="rounded-full p-1 text-stone-400 hover:bg-white hover:text-stone-700">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <button type="button" onClick={() => onOpen(daily.reference)} className="mb-1 text-sm font-semibold text-amber-800 hover:underline">
        {daily.reference}
      </button>
      <p className="text-[1.05rem] leading-relaxed" style={scripture}>«{daily.text}»</p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <button
          type="button"
          disabled={speaking}
          onClick={() => {
            setSpeaking(true);
            void speakArcanjo(daily.proclamation).finally(() => setSpeaking(false));
          }}
          className="rounded-full bg-amber-600 px-3 py-1 text-xs font-medium text-white shadow disabled:opacity-50"
        >
          {speaking ? "A anunciar…" : "Ouvir o Arcanjo"}
        </button>
        <button type="button" onClick={() => onAsk(`Fala-me da palavra de hoje, ${daily.reference}.`)} className="rounded-full bg-amber-50 px-3 py-1 text-xs text-amber-900 ring-1 ring-amber-200 hover:bg-amber-100">
          Perguntar sobre ela
        </button>
      </div>
      <div className="mt-2 text-[9px] text-stone-400">Bíblia Livre (BLIVRE), CC BY 4.0</div>
    </div>
  );
}

// ------------------------------------------------------------------ vision
function VisionPanel({ vision, onClose, onOpen }: { vision: CeuVision; onClose: () => void; onOpen: (ref: string) => void }) {
  return (
    <div className={`${glass} pointer-events-auto flex max-h-[78vh] w-[min(520px,92vw)] flex-col overflow-hidden rounded-3xl text-stone-800 animate-[fadein_0.6s_ease-out]`}>
      <div className="relative">
        {vision.image ? (
          <img src={vision.image.url} alt={vision.image.caption} className="max-h-[40vh] w-full object-cover object-center sepia-[.25]" />
        ) : (
          <div className="h-40 w-full bg-gradient-to-b from-amber-100 via-white to-rose-100" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-white/95 via-white/10 to-transparent" />
        <h3 className="absolute bottom-3 left-5 text-3xl font-semibold text-stone-900 drop-shadow-sm" style={scripture}>
          {vision.title}
        </h3>
        <button type="button" onClick={onClose} className="absolute top-3 right-3 rounded-full bg-white/80 p-1.5 text-stone-600 hover:bg-white">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-5 pt-2 pb-4">
        {vision.facts.map((f) => (
          <div key={f.ref} className="border-l-2 border-amber-300/80 pl-3">
            <p className="text-[0.98rem] leading-relaxed" style={scripture}>{f.text}</p>
            <button type="button" onClick={() => onOpen(f.ref)} className="mt-0.5 text-[10px] tracking-wide text-amber-700/70 hover:text-amber-800 hover:underline">
              {f.ref}
            </button>
          </div>
        ))}
        {vision.image && <div className="pt-1 text-[9px] text-stone-400">{vision.image.caption} — {vision.image.credit}</div>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ main panel
export function CeuPanel({ messages, streamingText, assistantState, onAsk, vision, onCloseVision }: CeuPanelProps) {
  const [books, setBooks] = useState<CeuBook[]>([]);
  const [question, setQuestion] = useState("");
  const [openRef, setOpenRef] = useState<string | null>(null);
  const [readerRef, setReaderRef] = useState<string | undefined>(undefined);
  const [readerOpen, setReaderOpen] = useState(false);
  const [showConversation, setShowConversation] = useState(true);
  const refRe = useRefRegex(books);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Privacy: only show what is asked in this session, never older conversations
  const [sessionStart] = useState(() => Date.now());

  const [daily, setDaily] = useState<CeuDaily | null>(null);
  const [dailyHidden, setDailyHidden] = useState(false);
  useEffect(() => {
    ceuApi.books().then((r) => setBooks(r.books)).catch(() => undefined);
    ceuApi
      .daily()
      .then((d) => {
        setDaily(d);
        try {
          setDailyHidden(localStorage.getItem("ceu_daily_hidden") === d.date);
        } catch {
          /* storage unavailable */
        }
      })
      .catch(() => undefined);
  }, []);

  const recent = messages
    .filter((m) => m.role !== "system" && new Date(m.timestamp).getTime() >= sessionStart - 1000)
    .slice(-8);
  const thinking = assistantState === "processing" || assistantState === "executing";
  const lastAnswer = [...recent].reverse().find((m) => m.role === "assistant");

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [recent.length, streamingText]);

  const ask = (text: string) => {
    const t = text.trim();
    if (!t) return;
    onAsk(t);
    setShowConversation(true);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    ask(question);
    setQuestion("");
  };
  const firstRefIn = (text: string) => {
    if (!refRe) return null;
    refRe.lastIndex = 0;
    const m = refRe.exec(text);
    return m ? m[0].trim() : null;
  };
  const followUps = [
    { label: "Explicar mais profundamente", prompt: "Explica mais profundamente a tua última resposta." },
    { label: "Contexto histórico", prompt: "Mostra-me o contexto histórico dessa passagem: quem escreveu, para quem, quando e porquê." },
    { label: "Comparar interpretações", prompt: "Compara as principais interpretações das tradições cristãs sobre isto, dizendo o que é consensual e o que é debatido." },
  ];

  return (
    <div className="pointer-events-none fixed inset-0 z-20">
      {/* Vision: the Arcanjo steps aside and the scene opens in the centre */}
      {vision && !openRef && (
        <div className="absolute inset-x-0 top-20 flex justify-center px-4 md:justify-start md:pl-[20vw] [&>*]:md:w-[min(480px,44vw)]">
          <VisionPanel vision={vision} onClose={() => onCloseVision?.()} onOpen={setOpenRef} />
        </div>
      )}

      {/* Palavra do dia (left, when nothing else is open there) */}
      {daily && !dailyHidden && !readerOpen && !openRef && !vision && (
        <div className="absolute top-20 left-4">
          <DailyWord
            daily={daily}
            onAsk={ask}
            onOpen={setOpenRef}
            onClose={() => {
              setDailyHidden(true);
              try {
                localStorage.setItem("ceu_daily_hidden", daily.date);
              } catch {
                /* storage unavailable */
              }
            }}
          />
        </div>
      )}

      {/* Reader (left) */}
      {readerOpen && (
        <div className="absolute top-20 left-4 bottom-24">
          <BibleReader books={books} initialRef={readerRef} onClose={() => setReaderOpen(false)} onVerse={(r) => setOpenRef(r)} />
        </div>
      )}

      {/* Verse card: over the reader when it is open (left), otherwise centred */}
      {openRef && (
        <div className={readerOpen ? "absolute top-20 left-4" : "absolute inset-x-0 top-20 flex justify-center px-4"}>
          <VerseCard
            reference={openRef}
            onClose={() => setOpenRef(null)}
            onReadChapter={(r) => {
              setReaderRef(r);
              setReaderOpen(true);
              setOpenRef(null);
            }}
          />
        </div>
      )}

      {/* Conversation (right) */}
      {showConversation && (recent.length > 0 || streamingText) && (
        <div className="absolute top-20 right-4 bottom-24 flex w-[min(430px,92vw)] flex-col md:w-[min(430px,32vw)]">
          <div ref={scrollRef} className={`${glass} pointer-events-auto min-h-0 flex-1 space-y-3 overflow-y-auto rounded-3xl p-4 text-[0.95rem] text-stone-800`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.2em] text-amber-700/80">
                <Sparkles className="h-3.5 w-3.5" /> Arcanjo Miguel
              </div>
              <button type="button" onClick={() => setShowConversation(false)} className="rounded-full p-1 text-stone-400 hover:bg-white hover:text-stone-700">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            {recent.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className="ml-10 rounded-2xl rounded-br-md bg-stone-800/85 px-3 py-2 text-sm text-white">
                  {m.content}
                </div>
              ) : (
                <div key={m.id} className="rounded-2xl rounded-bl-md bg-white/80 px-4 py-3 ring-1 ring-white">
                  <RichAnswer text={m.content} refRe={refRe} onRef={setOpenRef} />
                  {m === lastAnswer && !streamingText && (
                    <div className="mt-3 flex flex-wrap gap-1.5 border-t border-stone-200/70 pt-3">
                      {followUps.map((f) => (
                        <button key={f.label} type="button" onClick={() => ask(f.prompt)} className="rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-900 ring-1 ring-amber-200 hover:bg-amber-100">
                          {f.label}
                        </button>
                      ))}
                      {firstRefIn(m.content) && (
                        <button
                          type="button"
                          onClick={() => {
                            setReaderRef(firstRefIn(m.content) || undefined);
                            setReaderOpen(true);
                          }}
                          className="rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-900 ring-1 ring-amber-200 hover:bg-amber-100"
                        >
                          Ler capítulo completo
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ),
            )}
            {streamingText && (
              <div className="rounded-2xl rounded-bl-md bg-white/80 px-4 py-3 ring-1 ring-white">
                <RichAnswer text={streamingText} refRe={refRe} onRef={setOpenRef} />
              </div>
            )}
            {thinking && !streamingText && <div className="animate-pulse text-sm italic text-stone-500">O Arcanjo está a consultar o Céu…</div>}
          </div>
        </div>
      )}

      {/* Ask bar (bottom) */}
      <form onSubmit={submit} className="pointer-events-auto absolute inset-x-0 bottom-5 mx-auto flex w-[min(720px,92vw)] items-center gap-2">
        <button
          type="button"
          onClick={() => setReaderOpen((v) => !v)}
          title="Ler a Bíblia"
          className={`${glass} flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-amber-800 hover:bg-white`}
        >
          <BookOpen className="h-5 w-5" />
        </button>
        <div className={`${glass} flex h-12 flex-1 items-center rounded-full pl-5 pr-1.5`}>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Pergunta ao Arcanjo Miguel… (ex.: O que significa Mateus 9:29?)"
            className="h-full flex-1 bg-transparent text-stone-800 placeholder:text-stone-500 focus:outline-none"
          />
          <button type="submit" disabled={!question.trim()} className="flex h-9 w-9 items-center justify-center rounded-full bg-amber-600 text-white shadow disabled:opacity-40">
            <Send className="h-4 w-4" />
          </button>
        </div>
      </form>
      <div className="pointer-events-none absolute inset-x-0 bottom-1 text-center text-[10px] text-stone-500/80">
        O Arcanjo Miguel é uma experiência criada com inteligência artificial · Escrituras: Bíblia Livre (CC BY 4.0)
      </div>
    </div>
  );
}
