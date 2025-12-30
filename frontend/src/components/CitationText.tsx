import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

const TOKEN_RE =
  /\[(?<alias>[A-Z]+\d+)\]|mem:(?<memId>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/g

export function CitationText(props: {
  text: string
  knownAliases?: Set<string>
  onClickAlias?: (alias: string) => void
  knownMemIds?: Set<string>
  onClickMemId?: (memId: string) => void
}) {
  const text = props.text ?? ''
  const known = props.knownAliases
  const onClick = props.onClickAlias
  const knownMem = props.knownMemIds
  const onClickMem = props.onClickMemId

  const nodes: ReactNode[] = []
  let lastIndex = 0

  for (const match of text.matchAll(TOKEN_RE)) {
    const index = match.index ?? 0
    const rawAlias = (match.groups?.alias ?? '').trim()
    const rawMemId = (match.groups?.memId ?? '').trim()
    if (index > lastIndex) nodes.push(text.slice(lastIndex, index))

    const token = match[0]
    const isKnownAlias = rawAlias && (!known || known.has(rawAlias))
    const isKnownMem = rawMemId && (!knownMem || knownMem.has(rawMemId))

    if (rawAlias && onClick && isKnownAlias) {
      nodes.push(
        <button
          key={`${rawAlias}_${index}`}
          type="button"
          onClick={() => onClick(rawAlias)}
          className="mx-0.5 inline-flex items-baseline rounded-sm px-0.5 font-mono text-accent underline underline-offset-2 hover:opacity-90"
          title={`Open evidence [${rawAlias}]`}
        >
          {token}
        </button>,
      )
    } else if (rawMemId && isKnownMem) {
      if (onClickMem) {
        nodes.push(
          <button
            key={`${rawMemId}_${index}`}
            type="button"
            onClick={() => onClickMem(rawMemId)}
            className="mx-0.5 inline-flex items-baseline rounded-sm px-0.5 font-mono text-accent underline underline-offset-2 hover:opacity-90"
            title={`Open memory mem:${rawMemId}`}
          >
            {token}
          </button>,
        )
      } else {
        nodes.push(
          <Link
            key={`${rawMemId}_${index}`}
            to={`/memories/${encodeURIComponent(rawMemId)}`}
            className="mx-0.5 inline-flex items-baseline rounded-sm px-0.5 font-mono text-accent underline underline-offset-2 hover:opacity-90"
            title={`Open memory mem:${rawMemId}`}
          >
            {token}
          </Link>,
        )
      }
    } else {
      nodes.push(
        <span key={`${rawAlias || rawMemId}_${index}`} className="font-mono">
          {token}
        </span>,
      )
    }

    lastIndex = index + token.length
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))

  return <span className="whitespace-pre-wrap">{nodes}</span>
}
