import type { JSX, ReactNode } from "react";

// Renderer markdown minimale → struttura .vk-doc (stili già nel design system vokari.css:
// h2=titolo, h3=sezione "## ", li/li.todo/li.clar, .vk-yaml per il frontmatter, .vk-clar
// per i marcatori [DA CHIARIRE]). Copre ciò che producono briefing/recap/nota Obsidian:
// frontmatter YAML, # / ##, elenchi -, checkbox - [ ], **bold**, [[wikilink]], paragrafi.
// NON è un parser markdown completo: solo il sottoinsieme che VOKARI genera.

const CLAR_RE = /^\[DA CHIARIRE:\s*([\s\S]*?)\]\s*$/;

/** Inline: **bold** e [[wikilink]]. Il resto è testo. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /\*\*([^*]+)\*\*|\[\[([^\]]+)\]\]/g;
  let last = 0;
  let k = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1] !== undefined) out.push(<b key={k++}>{m[1]}</b>);
    else out.push(<span className="lnk" key={k++}>{m[2]}</span>);
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** Contenuto di un item/paragrafo, con badge ambra se è un marcatore [DA CHIARIRE]. */
function bodyNodes(text: string): ReactNode[] {
  const m = text.match(CLAR_RE);
  if (!m) return inline(text);
  return [<span className="vk-clar" key="clar">DA CHIARIRE</span>, ...inline(m[1])];
}

export function MarkdownDoc({ md }: { md: string }): JSX.Element {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const blocks: JSX.Element[] = [];
  let key = 0;
  let i = 0;

  // Frontmatter YAML (--- ... ---) in testa → blocco .vk-yaml.
  if (lines[0]?.trim() === "---") {
    const fm: string[] = [];
    i = 1;
    while (i < lines.length && lines[i].trim() !== "---") fm.push(lines[i++]);
    i++; // salta il --- di chiusura
    blocks.push(
      <div className="vk-yaml" key={key++}>
        {fm.map((l, j) => {
          const idx = l.indexOf(":");
          if (idx === -1) return <div key={j}>{l}</div>;
          return (
            <div key={j}>
              <span className="k">{l.slice(0, idx + 1)}</span>
              <span className="v">{l.slice(idx + 1)}</span>
            </div>
          );
        })}
      </div>,
    );
  }

  // Corpo: accumula run di elenco in un <ul>.
  let list: JSX.Element[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(<ul key={key++}>{list}</ul>);
      list = [];
    }
  };

  for (; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) { flush(); continue; }
    if (line.startsWith("## ")) { flush(); blocks.push(<h3 key={key++}>{inline(line.slice(3))}</h3>); continue; }
    if (line.startsWith("# ")) { flush(); blocks.push(<h2 key={key++}>{inline(line.slice(2))}</h2>); continue; }
    if (line.startsWith("- ") || line.startsWith("* ")) {
      const item = line.slice(2);
      const todo = /^\[[ xX]\]\s/.test(item);
      const body = todo ? item.replace(/^\[[ xX]\]\s/, "") : item;
      const clar = CLAR_RE.test(body);
      list.push(
        <li key={list.length} className={clar ? "clar" : todo ? "todo" : undefined}>
          {bodyNodes(body)}
        </li>,
      );
      continue;
    }
    flush();
    blocks.push(<p key={key++}>{bodyNodes(line)}</p>);
  }
  flush();

  return <>{blocks}</>;
}
