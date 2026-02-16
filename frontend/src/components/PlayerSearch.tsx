import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { searchPlayers, PlayerInfo } from '../api/client'

interface PlayerSearchProps {
  onSelect?: (player: PlayerInfo) => void
  autoFocus?: boolean
  placeholder?: string
}

export default function PlayerSearch({
  onSelect,
  autoFocus = false,
  placeholder = 'Search players...',
}: PlayerSearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PlayerInfo[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (query.length < 2) {
      setResults([])
      setIsOpen(false)
      return
    }
    const timer = setTimeout(async () => {
      setIsLoading(true)
      try {
        const players = await searchPlayers(query)
        setResults(players)
        setIsOpen(players.length > 0)
        setSelectedIndex(-1)
      } catch {
        setResults([])
      } finally {
        setIsLoading(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current && !inputRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false)
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
      navigate(`/player/${encodeURIComponent(player.player_name)}`)
    }
  }, [onSelect, navigate])

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
    <div className="relative w-full max-w-lg">
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          autoFocus={autoFocus}
          className="w-full pl-10 pr-4 py-3 bg-bg-tertiary border border-border-subtle rounded-lg
                     text-text-primary placeholder-text-muted text-sm
                     focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/15
                     transition-all duration-150"
        />
        <div className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted">
          {isLoading ? (
            <div className="spinner w-4 h-4" />
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          )}
        </div>
      </div>

      {isOpen && (
        <div ref={dropdownRef} className="absolute z-50 w-full mt-1 bg-bg-tertiary border border-border-subtle rounded-lg shadow-lg shadow-black/30 overflow-hidden animate-slide-up">
          {results.map((player, index) => (
            <button
              key={player.player_id}
              onClick={() => handleSelect(player)}
              className={`w-full px-4 py-2.5 flex items-center gap-3 text-left transition-colors text-sm ${index === selectedIndex ? 'bg-bg-elevated' : 'hover:bg-bg-elevated/50'}`}
            >
              <div className="flex-1 min-w-0">
                <div className="font-medium text-text-primary truncate">{player.player_name}</div>
                {player.team_abbrev && <div className="text-xs text-text-muted">{player.team_abbrev}</div>}
              </div>
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
