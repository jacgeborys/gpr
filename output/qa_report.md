# QA report — GPR 2025

## Sections

| metric | value |
|---|---|
| sections in GPR | 2424 (18,364 km) |
| sections placed | 2424 (18,364 km) |
| with SDRR | 2402 |
| length within ±20–25% of GPR length | 2202 sections, 17,457 km (95.1%) |
| median len_ratio | 1.003 |

Placement: strict 2352, attached+strict 61, loose 6, loose+strict 5

## QA flags

| flag | sections | meaning |
|---|---|---|
| stitched | 614 | end extended (along roads, or straight) to meet the next section / node |
| gap_closed | 73 | a break to the next section of the road was bridged (half of it added here) |
| scale | 56 | km between counting points disagrees with route length by >25–33% |
| clipped | 50 | road ended before the section's km ran out |
| foreign | 42 | extension had to follow a road with a different number |
| chain_break | 12 | route between counting points broken (missing link in BDOT10k); run split |
| trimmed | 9 | line cut where a section of another road starts at the same-named interchange |
| none | 2 | extension found nothing to follow |

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
| nodes | 6704 |
| links (counted / uncounted) | 3296 / 5188 |
| uncounted link km | 30,744 |
| connected components | 63 (largest 97.4%) |
| dead ends > 3 km from the border: national roads / regional roads | 34 / 590 → `qa_dead_ends.csv` |
| traffic work | 271.4 M veh-km/day |

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

63 uncovered stretches between sections of the same road (269 km); 20 next to a city-limit section (city-managed, not counted by GPR) → `qa_gaps.csv`. Largest others:

| road | km | between |
|---|---|---|
| 8 | 14.98 | KORYCIN /UL. BROWARNA (DW671)/ - SUCHOWOLA /DW670/ / KORYCIN /UL. BROWARNA (DW671)/ - SUCHOWOLA /DW670/ |
| 42 | 5.23 | SKARŻYSKO-KAMIENNA /UL. LEGIONÓW/ - WĄCHOCK /OBWODNICA (UL. KIELECKA)/ / WĄCHOCK /OBWODNICA 2: UL. KIELECKA - WYGODA/ |
| 31 | 5.09 | W. RADZISZEWO /A6/ - GRYFINO /OBWODNICA (UL. POMORSKA)/ / GRYFINO /OBWODNICA (RONDO KOŃCOWE)/ - PNIEWO /UL. GRYFIŃSKA (DW121)/ |
| 9 | 3.46 | OPATÓW /UL. 1 MAJA (DK74)/ - LIPNIK /DK77/ / OSTROWIEC ŚW. /OBWODNICA (UL. OPATOWSKA)/ - OPATÓW /OBWODNICA/ |
| 42 | 3.18 | WOŁCZYN /UL. PRZEMYSŁOWA/ - KLUCZBORK /OBWODNICA (DK42, DK45)/ / KLUCZBORK /PRZEJŚCIE: OBWODNICA (DK42) - (DK11)/ |
| 32 | 2.54 | GRANOWO /UL. POZNAŃSKA (DW431)/ - W. STĘSZEW (S5) / GRANOWO /UL. POZNAŃSKA (DW431)/ - W. STĘSZEW (S5) |
| 25 | 1.45 | CZŁUCHÓW /UL. PLANTOWA (DW188)/ - ZAMARTE /DW212/ / CZŁUCHÓW /UL. PLANTOWA (DW188)/ - ZAMARTE /DW212/ |
| 15 | 1.31 | SZABDA /DW543/ - BRODNICA /OBWODNICA (UL. SĄDOWA (DW543))/ / BRODNICA /PRZEJŚCIE: UL. KOLEJOWA - UL. OLSZTYŃSKA/ |
| 8 | 1.3 | KORYCIN /UL. BROWARNA (DW671)/ - SUCHOWOLA /DW670/ / KORYCIN /UL. BROWARNA (DW671)/ - SUCHOWOLA /DW670/ |
| 28 | 1.18 | SANOK /PRZEJŚCIE 2: UL. BEKSIŃSKIEGO - UL. KOLEJOWA/ / SANOK /PRZEJŚCIE 1: OBWODNICA (UL. LIPIŃSKIEGO) - UL. BEKSIŃSKIEGO/ |
| 75 | 0.97 | NIEPOŁOMICE /UL. BATOREGO (DW964)/ - W. TARGOWISKO /A4, DW963/ / NIEPOŁOMICE /UL. BATOREGO (DW964)/ - W. TARGOWISKO /A4, DW963/ |
| A1 | 0.82 | W. ŻORY /UL. RYBNICKA/ - W. ŚWIERKLANY /UL. ŻORSKA (DW932)/ / W. RYBNIK /UL. ZWYCIĘSTWA (DW925)/ - W. ŻORY /UL. RYBNICKA/ |

729 sections to review → `qa_sections_to_review.csv`
