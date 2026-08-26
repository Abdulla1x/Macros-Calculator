// Announcement bodies are written in a deliberately tiny subset of Markdown:
// blank-line paragraph breaks, **bold** and *italic*. That is everything the
// bodies in announcements.py use, and everything supported -- more would want a
// real parser, and a dependency for three constructs is a poor trade. If a note
// ever needs a list or a link, this is the place that has to learn them, and it
// will be obvious because they will appear on screen as punctuation.
//
// This matters more than it looks, and it shipped wrong. `item.body` used to go
// straight into a single <p>, where HTML collapses the blank lines: every note
// arrived as one unbroken wall of text, and three of them printed their **
// markers literally. Nothing in code review shows that -- the string is correct
// and the JSX is valid -- it is only visible on screen.
//
// It lives in its own file so the modal and the /whats-new page render a note
// identically by construction. AlertDialog's docblock claims it "shares its
// shell with AnnouncementsModal so there is one dialog style rather than two
// that drift apart", while importing nothing and hand-copying every class --
// the two have already drifted. A shared claim is only true if there is a
// shared module.
const INLINE = /(\*\*[^*]+\*\*|\*[^*]+\*)/g

function inline(text: string, key: string) {
  return text
    .split(INLINE)
    .filter((part) => part !== '')
    .map((part, index) => {
      const id = `${key}-${index}`
      // Bold is tested first because the alternation above prefers it, so a
      // `**word**` run never reaches the italic branch.
      if (part.length > 4 && part.startsWith('**') && part.endsWith('**')) {
        return (
          <strong key={id} className="font-semibold text-slate-100">
            {part.slice(2, -2)}
          </strong>
        )
      }
      if (part.length > 2 && part.startsWith('*') && part.endsWith('*')) {
        return <em key={id}>{part.slice(1, -1)}</em>
      }
      return <span key={id}>{part}</span>
    })
}

export default function AnnouncementBody({ text }: { text: string }) {
  return (
    <div className="mt-1.5 space-y-2 text-sm text-slate-300">
      {text.split(/\n{2,}/).map((paragraph, index) => (
        <p key={index}>{inline(paragraph, String(index))}</p>
      ))}
    </div>
  )
}
