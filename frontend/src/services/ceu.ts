/** Client for the Céu API (Bible passages, search, originals, lexicon). */

export interface CeuBook {
  ordinal: number;
  name: string;
  abbrev: string;
  testament: "AT" | "NT";
  group: string;
  chapters: number;
}

export interface CeuVerse {
  ref: string;
  book: string;
  book_ordinal: number;
  chapter: number;
  verse: number;
  text: string;
}

export interface CeuPassage {
  reference: string;
  verses: CeuVerse[];
  truncated: boolean;
  attribution: string;
}

export interface CeuOriginalWord {
  word: string;
  translit: string;
  gloss: string;
  strong: string;
  morph: string;
  meaning: string;
  editions: string;
}

export interface CeuOriginal {
  reference: string;
  language: "hebraico" | "grego";
  verses: { ref: string; words: CeuOriginalWord[] }[];
  attribution: string;
}

export interface CeuWordStudy {
  strong: string;
  language: string;
  lemma: string;
  translit: string;
  morph: string;
  gloss: string;
  definition: string;
  occurrences: number;
  sample_refs: string[];
  attribution: string;
}

export interface CeuRelated {
  ref: string;
  votes: number;
  text: string;
}

async function get<T>(path: string, params: Record<string, string | number>): Promise<T> {
  const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
  const res = await fetch(`/api/v1/ceu${path}?${qs}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `Erro ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface CeuVision {
  title: string;
  image: { url: string; caption: string; credit: string; source: string } | null;
  facts: { ref: string; text: string }[];
}

export interface CeuDaily {
  date: string;
  reference: string;
  text: string;
  proclamation: string;
  attribution: string;
}

export const ceuApi = {
  daily: () => get<CeuDaily>("/daily", {}),
  books: () => get<{ books: CeuBook[]; attribution: string }>("/books", {}),
  passage: (ref: string) => get<CeuPassage>("/passage", { ref }),
  original: (ref: string) => get<CeuOriginal>("/original", { ref }),
  word: (q: string) => get<CeuWordStudy>("/word", { q }),
  related: (ref: string) => get<{ related: CeuRelated[] }>("/related", { ref, limit: 8 }),
  search: (q: string) => get<{ results: CeuVerse[] }>("/search", { q, limit: 20 }),
};
