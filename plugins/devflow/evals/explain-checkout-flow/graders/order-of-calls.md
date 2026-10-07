---
type: regex
target: last_message
pattern: 'reserveStock[\s\S]*chargeCard[\s\S]*releaseStock|reserv[\s\S]*(charg|cobr)[\s\S]*(releas|liber)'
flags: i
weight: 2
---

The answer follows the real order: reserve stock, charge the card, release stock on failure.
