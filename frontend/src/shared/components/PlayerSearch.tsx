import PlayerSearchBase, { type PlayerSearchProps } from './PlayerSearchBase'
import { searchPlayers } from '../../features/predictions/api'

export default function PlayerSearch(props: PlayerSearchProps) {
  return <PlayerSearchBase {...props} searchPlayers={searchPlayers} />
}
