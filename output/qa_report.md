# QA report — GPR 2025

## Sections

| metric | value |
|---|---|
| sections in GPR | 2424 (18,364 km) |
| sections placed | 2424 (18,364 km) |
| with SDRR | 2402 |
| length within ±20–25% of GPR length | 2355 sections, 18,081 km (98.5%) |
| median len_ratio | 1.000 |

Placement: strict 2352, attached+strict 61, loose 6, loose+strict 5

## QA flags

| flag | sections | meaning |
|---|---|---|
| gap_closed | 71 | a break to the next section of the road was bridged (half of it added here) |
| scale | 57 | km between counting points disagrees with route length by >25–33% |
| foreign | 26 | extension had to follow a road with a different number |
| chain_break | 12 | route between counting points broken (missing link in BDOT10k); run split |
| clipped | 8 | road ended before the section's km ran out |
| none | 1 | extension found nothing to follow |

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
| nodes | 2845 |
| links (counted / uncounted) | 2897 / 464 |
| uncounted link km | 1,533 |
| connected components | 5 (largest 99.4%) |
| traffic work | 280.1 M veh-km/day |

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

74 uncovered stretches between sections of the same road (302 km); 19 next to a city-limit section (city-managed, not counted by GPR) → `qa_gaps.csv`. Largest others:

| road | km | between |
|---|---|---|
| 50 | 7.52 | GRÓJEC /UL. POŚWIĘTNE/ - CHYNÓW / CHYNÓW - DĘBÓWKA /UL. PROSTA (DW683)/ |
| 12 | 6.03 | GOSTYŃ /OBWODNICA (W. PIASKI)/ - STRUMIANY /DW437/ / STRUMIANY /DW437/ - BOREK WLKP. /OBWODNICA (UL. GŁOSINY)/ |
| 72 | 5.36 | ŻDŻARY /A2/ - TULISZKÓW /PL. WOLNOŚCI (DW443)/ / TULISZKÓW /PL. WOLNOŚCI (DW443)/ - TUREK /AL. JANA PAWŁA II (DW470)/ |
| 42 | 5.23 | SKARŻYSKO-KAMIENNA /UL. LEGIONÓW/ - WĄCHOCK /OBWODNICA (UL. KIELECKA)/ / WĄCHOCK /OBWODNICA 2: UL. KIELECKA - WYGODA/ |
| 7 | 4.43 | PRZYBOROWICE /DW571/ - W. ZAKROCZYM / PRZYBOROWICE /DW571/ - W. ZAKROCZYM |
| 25 | 4.41 | CZŁUCHÓW /UL. PLANTOWA (DW188)/ - ZAMARTE /DW212/ / CZŁUCHÓW /UL. PLANTOWA (DW188)/ - ZAMARTE /DW212/ |
| 31 | 4.12 | GRYFINO /OBWODNICA 1: UL. POMORSKA - RONDO POŚREDNIE (DW120)/ / GRYFINO /OBWODNICA (RONDO KOŃCOWE)/ - PNIEWO /UL. GRYFIŃSKA (DW121)/ |
| 60 | 3.96 | DROBIN /UL. PŁOŃSKA (DK10)/ - GLINOJECK /DK7/ / DROBIN /UL. PŁOŃSKA (DK10)/ - GLINOJECK /DK7/ |
| S8 | 3.67 | W. RAWA MAZ. PŁD. /UL. KATOWICKA (DW726)/ - W. RAWA MAZ. PŁN. /DK72, DW725/ / W. RAWA MAZ. PŁD. /UL. KATOWICKA (DW726)/ - W. RAWA MAZ. PŁN. /DK72, DW725/ |
| 9 | 3.46 | OPATÓW /UL. 1 MAJA (DK74)/ - LIPNIK /DK77/ / OSTROWIEC ŚW. /OBWODNICA (UL. OPATOWSKA)/ - OPATÓW /OBWODNICA/ |
| 51 | 3.33 | LIDZBARK WARM. /UL. OLSZTYŃSKA (DW511)/ - DOBRE MIASTO /DW507/ / LIDZBARK WARM. /UL. OLSZTYŃSKA (DW511)/ - DOBRE MIASTO /DW507/ |
| 42 | 3.18 | WOŁCZYN /UL. PRZEMYSŁOWA/ - KLUCZBORK /OBWODNICA (DK42, DK45)/ / KLUCZBORK /PRZEJŚCIE: OBWODNICA (DK42) - (DK11)/ |

180 sections to review → `qa_sections_to_review.csv`
