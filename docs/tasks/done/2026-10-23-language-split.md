# 2026-10-23 (small, after features B): interface language vs commentary language

Context: today one TR/EN switch changes both the page and the narration. The rules ask for experiences "shaped by language
preference" (4.1(e)) and "multi-language storytelling" (4.1(vi)), and the jury reads English. Splitting the two lets a judge keep
the page in English while hearing Turkish commentary. **English is the primary language**; Turkish is second. Client-side work,
about 1-2 hours. See "Scope and token budget" in CLAUDE.md.

Done when:
- Two selectors: **Interface** (EN/TR) and **Commentary** (EN/TR), both remembered (`localStorage`, try/catch).
- Interface language changes only the page; commentary language changes only what is spoken.
- When they differ, captions show the spoken sentence plus a smaller line in the interface language.
- `ruff check . && pytest` pass; deployed; owner checked EN page + TR commentary and the reverse.

## Steps
1. **Interface language:** browser language by default (EN if not Turkish); drives the `T` dictionary and every UI string,
   including the sound-tour captions and button labels. Its selector replaces today's single switch in the header.
2. **Commentary language:** defaults to the interface language until the listener changes it; drives narration, recap,
   sound-tour voice lines and the favourite-club / chapter announcements. Place it next to the listening mode, labelled
   "Commentary language". If the server needs it (e.g. it synthesizes or selects clips per language), send `set_lang`; otherwise
   keep it client-side.
3. **Dual caption:** when the two differ, the caption shows the commentary-language sentence and, under it in smaller muted
   text, the interface-language version. Narration `speech` messages and recaps already carry EN and TR; if any message type
   carries only one language, show only that one (no machine translation in the client).
4. Changing either selector mid-match takes effect from the next sentence; nothing restarts.
5. Check every new string in English first; keep labels short enough for phone width (no layout shift, as fixed in features A).
6. README: in the personalization section, one line on the two language settings; one line that more languages need their own
   Verifier rules, templates and voices (not built). STATUS. Move this file to `docs/tasks/done/` when finished.

## Out of scope
A third language, machine translation, changes to narration prompts or caches.
