# QA report — GPR 2025

## Sections

| metric | value |
|---|---|
| sections in GPR | 2424 (18,364 km) |
| sections placed | 2423 (18,357 km) |
| with SDRR | 2402 |
| length within ±20–25% of GPR length | 2304 sections, 17,799 km (97.0%) |
| median len_ratio | 1.000 |

Placement: strict 2351, attached+strict 60, loose+strict 6, loose 6

## QA flags

| flag | sections | meaning |
|---|---|---|
| scale | 193 | km between counting points disagrees with route length by >25–33% |
| chain_break | 29 | route between counting points broken (missing link in BDOT10k); run split |
| foreign | 26 | extension had to follow a road with a different number |
| clipped | 12 | road ended before the section's km ran out |
| none | 5 | extension found nothing to follow |

## Status (from GPR remarks)

| status | sections |
|---|---|
| measured | 2400 |
| pending_2026 | 14 |
| opened_after_count | 6 |
| provisional | 2 |
| not_counted | 1 |

## Model network

| metric | value |
|---|---|
| nodes | 3077 |
| links (counted / uncounted) | 3122 / 580 |
| uncounted link km | 1,793 |
| connected components | 10 (largest 98.8%) |
| traffic work | 286.6 M veh-km/day |

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

273 sections to review → `qa_sections_to_review.csv`
