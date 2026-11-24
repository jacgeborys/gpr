# QA report — GPR 2025

## Sections

| metric | value |
|---|---|
| sections in GPR | 2424 (18,364 km) |
| sections placed | 2424 (18,364 km) |
| with SDRR | 2402 |
| length within ±20–25% of GPR length | 2158 sections, 17,351 km (94.5%) |
| median len_ratio | 1.004 |

Placement: strict 2367, attached+strict 50, loose 4, loose+strict 3

## QA flags

| flag | sections | meaning |
|---|---|---|
| stitched | 569 | end extended (along roads, or straight) to meet the next section / node |
| scale | 150 | km between counting points disagrees with route length by >25–33% |
| gap_closed | 74 | a break to the next section of the road was bridged (half of it added here) |
| foreign | 51 | extension had to follow a road with a different number |
| clipped | 41 | road ended before the section's km ran out |
| chain_break | 28 | route between counting points broken (missing link in BDOT10k); run split |
| trimmed | 23 | line cut where a section of another road starts at the same-named interchange |
| none | 3 | extension found nothing to follow |
| partial | 1 | one of the section's chainage pieces could not be placed |

## Status (from GPR remarks)

| status | sections |
|---|---|
| measured | 2400 |
| pending_2026 | 14 |
| opened_after_count | 7 |
| provisional | 2 |
| not_counted | 1 |

## Model network

| metric | value |
|---|---|
| nodes | 6523 |
| links (counted / uncounted) | 3191 / 5085 |
| uncounted link km | 30,628 |
| connected components | 50 (largest 97.8%) |
| dead ends > 3 km from the border: national roads / regional roads | 24 / 559 → `qa_dead_ends.csv` |
| traffic work | 270.8 M veh-km/day |

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

## Visible gaps

27 uncovered stretches between sections of the same road (249 km); 20 next to a city-limit section (city-managed, not counted by GPR) → `qa_gaps.csv`. Largest others:

| road | km | between |
|---|---|---|
| 20 | 7.0 | W. SZCZECINEK ŚRÓDMIEŚCIE /S11/ - GWDA MAŁA /DW201/ / SZCZECINEK /OBWODNICA (SITNO)/ - W. SZCZECINEK PŁD. |
| S3 | 3.23 | W. ŚWINOUJŚCIE ŁUNOWO - W. MIĘDZYZDROJE /DW102/ / W. ŚWINOUJŚCIE ŁUNOWO - W. MIĘDZYZDROJE /DW102/ |
| A2 | 1.24 | W. SIEDLCE PŁD. - W. SIEDLCE WSCH. /DK92/ / W. SIEDLCE ZACH. /DK92/ - W. SIEDLCE PŁD. |
| A1 | 0.82 | W. ŻORY /UL. RYBNICKA/ - W. ŚWIERKLANY /UL. ŻORSKA (DW932)/ / W. ŻORY /UL. RYBNICKA/ - W. ŚWIERKLANY /UL. ŻORSKA (DW932)/ |
| A1 | 0.77 | W. ŻORY /UL. RYBNICKA/ - W. ŚWIERKLANY /UL. ŻORSKA (DW932)/ / W. ŻORY /UL. RYBNICKA/ - W. ŚWIERKLANY /UL. ŻORSKA (DW932)/ |
| A4 | 0.63 | W. CHORZÓW /UL. BATOREGO/ - W. KATOWICE MIKOŁOWSKA /UL. MIKOŁOWSKA/ / W. CHORZÓW /UL. BATOREGO/ - W. KATOWICE MIKOŁOWSKA /UL. MIKOŁOWSKA/ |
| 94 | 0.31 | TARNÓW /OBWODNICA 1: UL. KRAKOWSKA - UL. TUCHOWSKA (DW977)/ / TARNÓW /OBWODNICA 1: UL. KRAKOWSKA - UL. TUCHOWSKA (DW977)/ |

742 sections to review → `qa_sections_to_review.csv`
