"""Every amp the HX Stomp 3.80.0 lists, in its menu order (guitar, then bass): (model, the Stomp's preset id,
its DSP cost). Written by re/stomp_amps.py from the Stomp firmware; tools/verify_amps.py checks each row
against that firmware again."""

STOMP_AMPS = (
    ('HD2_AmpWhoWatt100', 44, 2629),                 # guitar: WhoWatt 100
    ('HD2_AmpSoupPro', 35, 1456),                    # guitar: Soup Pro
    ('HD2_AmpStoneAge185', 36, 2534),                # guitar: Stone Age 185
    ('HD2_AmpVoltageQueen', 397, 2610),               # guitar: Voltage Queen
    ('HD2_AmpTweedBluesNrm', 38, 2326),              # guitar: Tweed Blues Nrm
    ('HD2_AmpTweedBluesBrt', 37, 2324),              # guitar: Tweed Blues Brt
    ('HD2_AmpFullertonNrm', 541, 2800),               # guitar: Fullerton Nrm
    ('HD2_AmpFullertonBrt', 539, 2800),               # guitar: Fullerton Brt
    ('HD2_AmpFullertonJump', 540, 2800),              # guitar: Fullerton Jump
    ('HD2_AmpGrammaticoNrm', 535, 2925),              # guitar: GrammaticoLG Nrm
    ('HD2_AmpGrammaticoBrt', 533, 2925),              # guitar: GrammaticoLG Brt
    ('HD2_AmpGrammaticoJump', 534, 2925),             # guitar: GrammaticoLG Jmp
    ('HD2_AmpUSSmallTweed', 43, 1209),               # guitar: US Small Tweed
    ('HD2_AmpUSPrincess', 591, 2500),                 # guitar: US Princess
    ('HD2_AmpUSSuperNorm', 815, 2200),                # guitar: US Super Norm
    ('HD2_AmpUSSuperVib', 817, 2500),                 # guitar: US Super Vib
    ('HD2_AmpUSDeluxeNrm', 39, 2222),                # guitar: US Deluxe Nrm
    ('HD2_AmpUSDeluxeVib', 40, 2521),                # guitar: US Deluxe Vib
    ('HD2_AmpUSDoubleNrm', 41, 2324),                # guitar: US Double Nrm
    ('HD2_AmpUSDoubleVib', 42, 2499),                # guitar: US Double Vib
    ('HD2_AmpMailOrderTwin', 29, 2501),              # guitar: Mail Order Twin
    ('HD2_AmpDividedDuo', 19, 2155),                 # guitar: Divided Duo
    ('HD2_AmpInterstateZed', 24, 2113),              # guitar: Interstate Zed
    ('HD2_AmpDerailedIngrid', 384, 2525),             # guitar: Derailed Ingrid
    ('HD2_AmpGSG100', 778, 3100),                     # guitar: Grammatico GSG
    ('HD2_AmpJazzRivet120', 25, 1286),               # guitar: Jazz Rivet 120
    ('HD2_AmpEssexA15', 20, 2049),                   # guitar: Essex A15
    ('HD2_AmpEssexA30', 21, 2274),                   # guitar: Essex A30
    ('HD2_AmpA30FawnNrm', 8, 1930),                 # guitar: A30 Fawn Nrm
    ('HD2_AmpA30FawnBrt', 7, 1937),                 # guitar: A30 Fawn Brt
    ('HD2_AmpMatchstickCh1', 306, 2150),              # guitar: Matchstick Ch1
    ('HD2_AmpMatchstickCh2', 307, 2075),              # guitar: Matchstick Ch2
    ('HD2_AmpMatchstickJump', 308, 2690),             # guitar: Matchstick Jump
    ('HD2_AmpMandarin80', 30, 2608),                 # guitar: Mandarin 80
    ('HD2_AmpMandarinRocker', 618, 2875),             # guitar: Mandarin Rocker
    ('HD2_AmpMoonNrm', 663, 2650),                    # guitar: Moo)))n Nrm
    ('HD2_AmpMoonBrt', 665, 2650),                    # guitar: Moo)))n Brt
    ('HD2_AmpMoonJump', 667, 2850),                   # guitar: Moo)))n Jump
    ('HD2_AmpBritJ45Nrm', 12, 2428),                 # guitar: Brit J45 Nrm
    ('HD2_AmpBritJ45Brt', 11, 2428),                 # guitar: Brit J45 Brt
    ('HD2_AmpBritTremNrm', 478, 2650),                # guitar: Brit Trem Nrm
    ('HD2_AmpBritTremBrt', 479, 2650),                # guitar: Brit Trem Brt
    ('HD2_AmpBritTremJump', 480, 2940),               # guitar: Brit Trem Jump
    ('HD2_AmpBritPlexiNrm', 17, 2704),               # guitar: Brit Plexi Nrm
    ('HD2_AmpBritPlexiBrt', 15, 2760),               # guitar: Brit Plexi Brt
    ('HD2_AmpBritPlexiJump', 16, 3092),              # guitar: Brit Plexi Jump
    ('HD2_AmpBritP75Nrm', 14, 2438),                 # guitar: Brit P75 Nrm
    ('HD2_AmpBritP75Brt', 13, 2438),                 # guitar: Brit P75 Brt
    ('HD2_AmpBrit2203', 787, 2800),                   # guitar: Brit 2203
    ('HD2_AmpBrit2204', 10, 2656),                   # guitar: Brit 2204
    ('HD2_AmpPlacaterClean', 512, 2050),              # guitar: Placater Clean
    ('HD2_AmpPlacaterDirty', 500, 2800),              # guitar: Placater Dirty
    ('HD2_AmpCartographer', 484, 2550),               # guitar: Cartographer
    ('HD2_AmpGermanXtraBlue', 819, 2700),             # guitar: German Xtra Blue
    ('HD2_AmpGermanXtraRed', 821, 2900),              # guitar: German Xtra Red
    ('HD2_AmpGermanMahadeva', 22, 2827),             # guitar: German Mahadeva
    ('HD2_AmpGermanUbersonic', 23, 2623),            # guitar: German Ubersonic
    ('HD2_AmpCaliTexasCh1', 514, 2500),               # guitar: Cali Texas Ch1
    ('HD2_AmpCaliTexasCh2', 502, 2800),               # guitar: Cali Texas Ch2
    ('HD2_AmpCaliIVR1', 313, 2600),                   # guitar: Cali IV Rhythm 1
    ('HD2_AmpCaliIVR2', 314, 2600),                   # guitar: Cali IV Rhythm 2
    ('HD2_AmpCaliIVLead', 312, 2750),                 # guitar: Cali IV Lead
    ('HD2_AmpCaliRectifire', 18, 2672),              # guitar: Cali Rectifire
    ('HD2_AmpArchetypeClean', 335, 2305),             # guitar: Archetype Clean
    ('HD2_AmpArchetypeLead', 336, 2550),              # guitar: Archetype Lead
    ('HD2_AmpANGLMeteor', 9, 2500),                 # guitar: ANGL Meteor
    ('HD2_AmpSoloLeadClean', 32, 2538),              # guitar: Solo Lead Clean
    ('HD2_AmpSoloLeadCrunch', 33, 2538),             # guitar: Solo Lead Crunch
    ('HD2_AmpSoloLeadOD', 34, 2856),                 # guitar: Solo Lead OD
    ('HD2_AmpEVPanamaBlue', 825, 3000),               # guitar: EV Panama Blue
    ('HD2_AmpEVPanamaRed', 823, 3700),                # guitar: EV Panama Red
    ('HD2_AmpPVPanama', 31, 2593),                   # guitar: PV Panama
    ('HD2_AmpPVVitriolClean', 764, 3100),             # guitar: PV Vitriol Clean
    ('HD2_AmpPVVitriolCrunch', 681, 3700),            # guitar: PV VitriolCrunch
    ('HD2_AmpPVVitriolLead', 682, 3700),              # guitar: PV Vitriol Lead
    ('HD2_AmpRevvGenPurple', 561, 2900),              # guitar: Revv Gen Purple
    ('HD2_AmpRevvGenRed', 545, 2900),                 # guitar: Revv Gen Red
    ('HD2_AmpDasBenzinMega', 601, 2500),              # guitar: Das Benzin Mega
    ('HD2_AmpDasBenzinLead', 599, 3000),              # guitar: Das Benzin Lead
    ('HD2_AmpLine6Clarity', 672, 1700),               # guitar: Line6 Clarity
    ('HD2_AmpLine6Aristocrat', 673, 2350),            # guitar: Line6 Aristocrat
    ('HD2_AmpLine6Carillon', 674, 2250),              # guitar: Line 6 Carillon
    ('HD2_AmpLine6Voltage', 671, 2550),               # guitar: Line 6 Voltage
    ('HD2_AmpLine6Kinetic', 670, 2250),               # guitar: Line 6 Kinetic
    ('HD2_AmpLine6Oblivion', 669, 2700),              # guitar: Line 6 Oblivion
    ('HD2_AmpLine6Ventoux', 655, 1800),               # guitar: Line 6 Ventoux
    ('HD2_AmpLine6Elmsley', 762, 3100),               # guitar: Line 6 Elmsley
    ('HD2_AmpLine6Elektrik', 27, 1795),              # guitar: Line 6 Elektrik
    ('HD2_AmpLine6Doom', 26, 2290),                  # guitar: Line 6 Doom
    ('HD2_AmpLine6Epic', 28, 2095),                  # guitar: Line 6 Epic
    ('HD2_AmpLine62204Mod', 322, 2075),               # guitar: Line 6 2204 Mod
    ('HD2_AmpLine6Fatality', 328, 2185),              # guitar: Line 6 Fatality
    ('HD2_AmpLine6Litigator', 339, 1700),             # guitar: Line 6 Litigator
    ('HD2_AmpLine6Badonk', 349, 1625),                # guitar: Line 6 Badonk
    ('HD2_AmpTucknGo', 6, 2122),                    # bass: Ampeg B-15NF
    ('HD2_AmpSVBeastNrm', 5, 2667),                 # bass: Ampeg SVT Nrm
    ('HD2_AmpSVBeastBrt', 4, 2660),                 # bass: Ampeg SVT Brt
    ('HD2_AmpSVT4Pro', 519, 1650),                    # bass: Ampeg SVT-4 PRO
    ('HD2_AmpUSDripmanNorm', 784, 2500),              # bass: US Dripman Norm
    ('HD2_AmpWoodyBlue', 350, 1100),                  # bass: Woody Blue
    ('HD2_AmpAguaSledge', 760, 1000),                 # bass: Agua Sledge
    ('HD2_AmpAgua51', 486, 1900),                     # bass: Agua 51
    ('HD2_AmpMandarinBass200', 789, 2200),            # bass: Mandarin Bass 200
    ('HD2_AmpCaliBass', 2, 1147),                   # bass: Cali Bass
    ('HD2_AmpCali400Ch1', 0, 2064),                 # bass: Cali 400 Ch1
    ('HD2_AmpCali400Ch2', 1, 2064),                 # bass: Cali 400 Ch2
    ('HD2_AmpGCougar800', 3, 1530),                 # bass: G Cougar 800
    ('HD2_AmpDelSol300', 343, 775),                  # bass: Del Sol 300
    ('HD2_AmpBusyOneCh1', 363, 800),                 # bass: Busy One Ch1
    ('HD2_AmpBusyOneCh2', 364, 800),                 # bass: Busy One Ch2
    ('HD2_AmpBusyOneJump', 365, 1400),                # bass: Busy One Jump
)
