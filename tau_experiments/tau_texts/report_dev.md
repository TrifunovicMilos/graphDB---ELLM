# tau variants, dev set

Tokens: cl100k_base. Entities: 1650 (1250 VideoGame, 400 VideoGameSeries).

| tau | class | chars mean | tokens mean | tokens p90 | tokens max | text shortened |
|---|---|---|---|---|---|---|
| A | VideoGame | 652 | 145.7 | 252 | 333 | 15% |
| A | VideoGameSeries | 735 | 160.3 | 257 | 326 | 23% |
| B | VideoGame | 669 | 151.3 | 255 | 335 | 16% |
| B | VideoGameSeries | 752 | 164.0 | 258 | 321 | 23% |
| C | VideoGame | 675 | 152.8 | 242 | 340 | 17% |
| C | VideoGameSeries | 750 | 163.6 | 248 | 305 | 24% |
| C-900 | VideoGame | 599 | 137.1 | 190 | 270 | 28% |
| C-900 | VideoGameSeries | 646 | 141.8 | 196 | 258 | 37% |
| C-600 | VideoGame | 471 | 109.9 | 137 | 199 | 51% |
| C-600 | VideoGameSeries | 488 | 107.9 | 135 | 165 | 62% |

## Leakage scan

Entities whose field names one of their own hidden values (genre, series, follows, followed by, franchise, has part).

| field | used in tau | entities with a hit | by property |
|---|---|---|---|
| description_screened (the field we add) | B, C, C-900, C-600 | 41 | genre 41 |

Examples (a hit is a leak only if a query asks about that value: see the next table):
- Civilization V: '2010 turn-based strategy video game' names 'turn-based strategy video game'
- Gunvalkyrie: '2002 science fiction video game published by Sega for the Xbox' names 'science fiction video game'
- Chaos: The Battle of Wizards: 'turn-based tactics computer game' names 'turn-based tactics'
- Alien vs. Predator: '1994 arcade game' names 'arcade'
- Guardian Heroes: "1996 beat 'em up video game" names "beat 'em up"

| label_lead (legitimate evidence) | all | 945 | series 534, genre 521, has part 116, franchise 61, follows 52, followed by 48 |
| description (control: the RAW description of graph.nt) | none | 94 | genre 88, series 5, franchise 3, follows 1 |

## Query answers stated in the screened description

The course screening blanks a description that names the exact hidden label. This checks for the answer of Q1, Q2 and Q4 in other words.

| query | inputs whose description_screened states the true answer | examples |
|---|---|---|
| Q1 | 0 of 200 | - |
| Q2 | 0 of 30 | - |
| Q4 | 9 of 444 | Metal Gear Solid 4: Guns of the Patriots: 2008 action-adventure stealth video game; Q*bert: action puzzle arcade game first released in 1982; Lunar: The Silver Star: 1992 RPG video game |
