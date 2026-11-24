# QA report — GPR 2025

## Sections

| metric | value |
|---|---|
| sections in GPR | 2424 (18,364 km) |
| sections placed | 2424 (18,364 km) |
| with SDRR | 2402 |
| length within ±20–25% of GPR length | 2354 sections, 18,071 km (98.4%) |
| median len_ratio | 1.000 |

Placement: strict 2352, attached+strict 60, loose+strict 6, loose 6

## QA flags

| flag | sections | meaning |
|---|---|---|
| scale | 56 | km between counting points disagrees with route length by >25–33% |
| gap_closed | 30 | a break to the next section of the road was bridged (half of it added here) |
| foreign | 26 | extension had to follow a road with a different number |
| chain_break | 14 | route between counting points broken (missing link in BDOT10k); run split |
| clipped | 10 | road ended before the section's km ran out |
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
| nodes | 2907 |
| links (counted / uncounted) | 2979 / 494 |
| uncounted link km | 1,631 |
| connected components | 7 (largest 99.3%) |
| traffic work | 282.9 M veh-km/day |

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

87 uncovered stretches between sections of the same road (341 km); 21 next to a city-limit section (city-managed, not counted by GPR) → `qa_gaps.csv`. Largest others:

| road | km | between |
|---|---|---|
| 8 | 14.24 | SZTABIN /OBWODNICA (DOMURATY)/ - W. AUGUSTÓW /DK16, DW665/ / SUCHOWOLA /DW670/ - SZTABIN /OBWODNICA (DOMURATY)/ |
| 8 | 14.23 | KORYCIN /UL. BROWARNA (DW671)/ - SUCHOWOLA /DW670/ / KORYCIN /UL. BROWARNA (DW671)/ - SUCHOWOLA /DW670/ |
| 8 | 9.75 | KORYCIN /UL. BROWARNA (DW671)/ - SUCHOWOLA /DW670/ / KORYCIN /UL. BROWARNA (DW671)/ - SUCHOWOLA /DW670/ |
| 50 | 7.52 | GRÓJEC /UL. POŚWIĘTNE/ - CHYNÓW / CHYNÓW - DĘBÓWKA /UL. PROSTA (DW683)/ |
| 72 | 6.62 | ŻDŻARY /A2/ - TULISZKÓW /PL. WOLNOŚCI (DW443)/ / TULISZKÓW /PL. WOLNOŚCI (DW443)/ - TUREK /AL. JANA PAWŁA II (DW470)/ |
| 42 | 5.23 | SKARŻYSKO-KAMIENNA /UL. LEGIONÓW/ - WĄCHOCK /OBWODNICA (UL. KIELECKA)/ / WĄCHOCK /OBWODNICA 2: UL. KIELECKA - WYGODA/ |
| 12 | 5.04 | BOREK WLKP. /OBWODNICA (SKOKÓWKO)/ - JAROCIN /UL. POWSTAŃCÓW WLKP./ / JAROCIN /PRZEJŚCIE 1: AL. NIEPODLEGŁOŚCI - UL. WROCŁAWSKA (DK15)/ |
| 25 | 4.41 | CZŁUCHÓW /UL. PLANTOWA (DW188)/ - ZAMARTE /DW212/ / CZŁUCHÓW /UL. PLANTOWA (DW188)/ - ZAMARTE /DW212/ |
| 9 | 4.13 | OPATÓW /UL. 1 MAJA (DK74)/ - LIPNIK /DK77/ / OSTROWIEC ŚW. /OBWODNICA (UL. OPATOWSKA)/ - OPATÓW /OBWODNICA/ |
| 60 | 3.96 | DROBIN /UL. PŁOŃSKA (DK10)/ - GLINOJECK /DK7/ / DROBIN /UL. PŁOŃSKA (DK10)/ - GLINOJECK /DK7/ |
| 65 | 3.78 | GR. PAŃSTWA /GOŁDAP/ - GOŁDAP /OBWODNICA (DG137524N)/ / KOWALE OLECKIE /UL. FILIPOWSKA (DW652)/ - OLECKO /OBWODNICA (DW653)/ |
| S8 | 3.67 | W. RAWA MAZ. PŁD. /UL. KATOWICKA (DW726)/ - W. RAWA MAZ. PŁN. /DK72, DW725/ / W. RAWA MAZ. PŁD. /UL. KATOWICKA (DW726)/ - W. RAWA MAZ. PŁN. /DK72, DW725/ |

143 sections to review → `qa_sections_to_review.csv`
