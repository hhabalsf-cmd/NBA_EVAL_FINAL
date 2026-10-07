import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ChevronRight, Loader2 } from 'lucide-react'
import type { PlayerInfo } from '../../api/types'
import { getHeadshotUrl } from '../utils/nba'

export interface PlayerSearchProps {
  onSelect?: (player: PlayerInfo) => void
  autoFocus?: boolean
  placeholder?: string
  replace?: boolean
}

export default function PlayerSearchBase({
  searchPlayers,
  onSelect,
  autoFocus = false,
  placeholder = 'Search players...',
  replace = false,
}: PlayerSearchProps & { searchPlayers: (query: string, signal?: AbortSignal) => Promise<PlayerInfo[]> }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PlayerInfo[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [completedQuery, setCompletedQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    const term = query.trim()
    setResults([])
    setIsOpen(false)
    setSearchError('')
    setCompletedQuery('')
    setSelectedIndex(-1)
    if (term.length < 2) {
      abortRef.current?.abort()
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    const controller = new AbortController()
    abortRef.current = controller
    const timer = setTimeout(async () => {
      try {
        const players = await searchPlayers(term, controller.signal)
        if (controller.signal.aborted) return
        setResults(players)
        setIsOpen(players.length > 0)
        setCompletedQuery(term)
        setSelectedIndex(-1)
      } catch (err) {
        if (!controller.signal.aborted && (err as Error).name !== 'AbortError') {
          setResults([])
          setSearchError(err instanceof Error ? err.message : 'Player search unavailable. Try selecting a team manually.')
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }, 300)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, searchPlayers])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current && !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false)
        setQuery('')
        setResults([])
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSelect = useCallback((player: PlayerInfo) => {
    setQuery('')
    setIsOpen(false)
    if (onSelect) {
      onSelect(player)
    } else {
      navigate(`/player/${encodeURIComponent(player.player_name)}`, {
        replace,
        state: { headshot_url: player.headshot_url },
      })
    }
  }, [onSelect, navigate, replace])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || results.length === 0) return
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex(prev => (prev < results.length - 1 ? prev + 1 : prev))
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex(prev => (prev > 0 ? prev - 1 : prev))
        break
      case 'Enter':
        e.preventDefault()
        if (selectedIndex >= 0) handleSelect(results[selectedIndex])
        else if (results.length > 0) handleSelect(results[0])
        break
      case 'Escape':
        setIsOpen(false)
        break
    }
  }

  return (
    <div ref={containerRef} className={`relative w-full max-w-lg ${isOpen ? 'z-30' : ''}`}>
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          aria-label="Search players"
          aria-busy={isLoading}
          autoComplete="off"
          maxLength={80}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          autoFocus={autoFocus}
          className="w-full !pl-11 pr-4 py-3 bg-bg-secondary border border-border-subtle rounded-xl
                     text-text-primary placeholder-text-muted text-sm
                     focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/10
                     transition-all duration-150"
        />
        <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted">
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Search className="w-4 h-4" />
          )}
        </div>
      </div>

      {searchError && <p role="alert" className="text-xs text-accent-danger mt-2">{searchError}</p>}
      {isLoading && <p role="status" className="text-xs text-text-muted mt-2">Searching players… The first roster lookup can take a few seconds.</p>}
      {!isLoading && !searchError && completedQuery === query.trim() && completedQuery.length >= 2 && results.length === 0 && <p role="status" className="text-xs text-text-secondary mt-2">No players found. Try a first or last name.</p>}
      {isOpen && (
        <div ref={dropdownRef} className="absolute z-50 w-full mt-2 bg-bg-tertiary border border-border-subtle rounded-xl shadow-xl shadow-black/30 max-h-80 overflow-y-auto animate-slide-up">
          {results.map((player, index) => (
            <button
              type="button"
              key={player.player_id}
              onClick={() => handleSelect(player)}
              className={`w-full px-4 py-3 flex items-center gap-3 text-left transition-colors text-sm ${
                index === selectedIndex ? 'bg-bg-elevated' : 'hover:bg-bg-elevated/50'
              }`}
            >
              <img
                src={getHeadshotUrl(player.headshot_url, player.player_id)}
                alt=""
                className="w-10 h-10 rounded-full object-cover bg-bg-secondary flex-shrink-0"
                onError={e => {
                  const img = e.target as HTMLImageElement
                  img.src = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Ccircle cx='20' cy='20' r='20' fill='%23333'/%3E%3Ccircle cx='20' cy='15' r='7' fill='%23666'/%3E%3Cellipse cx='20' cy='36' rx='11' ry='8' fill='%23666'/%3E%3C/svg%3E`
                  img.onerror = null
                }}
              />
              <div className="flex-1 min-w-0">
                <div className="font-medium text-text-primary truncate">{player.player_name}</div>
                {player.team_abbrev && (
                  <div className="text-xs text-text-muted mt-0.5">{player.team_abbrev}</div>
                )}
              </div>
              <ChevronRight className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
