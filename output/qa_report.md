# QA report — GPR 2025

## Sections

| metric | value |
|---|---|
| sections in GPR | 2424 (18,364 km) |
| sections placed | 2422 (18,353 km) |
| with SDRR | 2402 |
| length within ±20–25% of GPR length | 2299 sections, 17,747 km (96.7%) |
| median len_ratio | 1.000 |

Placement: strict 2350, attached+strict 60, loose+strict 6, loose 6

## QA flags

| flag | sections | meaning |
|---|---|---|
| scale | 189 | km between counting points disagrees with route length by >25–33% |
| chain_break | 47 | route between counting points broken (missing link in BDOT10k); run split |
| foreign | 30 | extension had to follow a road with a different number |
| clipped | 15 | road ended before the section's km ran out |
| none | 8 | extension found nothing to follow |

## Status (from GPR remarks)

| status | sections |
|---|---|
| measured | 2400 |
| pending_2026 | 13 |
| opened_after_count | 6 |
| provisional | 2 |
| not_counted | 1 |

## Model network

| metric | value |
|---|---|
| nodes | 3134 |
| links (counted / uncounted) | 3195 / 612 |
| uncounted link km | 1,895 |
| connected components | 13 (largest 98.7%) |
| traffic work | 290.5 M veh-km/day |

## Busiest sections

| road | section | SDRR |
|---|---|---|
| S8f | W. PRYMASA TYSIĄCLECIA /DK7/ - W. POWĄZKOWSKA | 195,600 |
| S8f | W. WISŁOSTRADA /DK7/ - W. MODLIŃSKA /DW801/ | 178,334 |
| S8f | W. POWĄZKOWSKA - W. BRONIEWSKIEGO | 169,007 |
| S8f | W. MARYMONCKA - W. WISŁOSTRADA /DK7/ | 164,928 |
| S8f | W. BRONIEWSKIEGO - W. MARYMONCKA | 162,605 |
| S8f | W. MODLIŃSKA /DW801/ - W. MARYWILSKA | 162,353 |
| S2 | W. OPACZ /S7, S8/ - W. AL. KRAKOWSKA /DW621/ | 161,367 |
| S2 | W. AL. KRAKOWSKA /DW621/ - W. WARSZAWA PŁD. /S79/ | 155,774 |
| S2 | W. AL. JEROZOLIMSKIE /DW719/ - W. OPACZ /S7, S8/ | 152,703 |
| S8f | W. MARYWILSKA - W. ŁABISZYŃSKA | 145,620 |

284 sections to review → `qa_sections_to_review.csv`
