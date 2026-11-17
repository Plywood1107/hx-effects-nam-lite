"""Every preamp the HX Stomp 3.80.0 lists, in its menu order (guitar, then bass, then mic): (model, the Stomp's preset id,
its DSP cost). Written by re/stomp_amps.py from the Stomp firmware; tools/verify_amps.py checks each row
against that firmware again."""

STOMP_PREAMPS = (
    ('HD2_PreampWhoWatt100', 230, 1497),              # guitar: WhoWatt 100
    ('HD2_PreampSoupPro', 221, 1371),                 # guitar: Soup Pro
    ('HD2_PreampStoneAge185', 222, 1443),             # guitar: Stone Age 185
    ('HD2_PreampVoltageQueen', 398, 1639),            # guitar: Voltage Queen
    ('HD2_PreampTweedBluesNrm', 224, 1206),           # guitar: Tweed Blues Nrm
    ('HD2_PreampTweedBluesBrt', 223, 1206),           # guitar: Tweed Blues Brt
    ('HD2_PreampFullertonNrm', 544, 1200),            # guitar: Fullerton Nrm
    ('HD2_PreampFullertonBrt', 542, 1200),            # guitar: Fullerton Brt
    ('HD2_PreampFullertonJump', 543, 1600),           # guitar: Fullerton Jump
    ('HD2_PreampGrammaticoNrm', 538, 1400),           # guitar: GrammaticoLG Nrm
    ('HD2_PreampGrammaticoBrt', 536, 1400),           # guitar: GrammaticoLG Brt
    ('HD2_PreampGrammaticoJump', 537, 1850),          # guitar: GrammaticoLG Jmp
    ('HD2_PreampUSSmallTweed', 229, 1187),            # guitar: US Small Tweed
    ('HD2_PreampUSPrincess', 592, 1500),              # guitar: US Princess
    ('HD2_PreampUSSuperNorm', 816, 1300),             # guitar: US Super Norm
    ('HD2_PreampUSSuperVib', 818, 1500),              # guitar: US Super Vib
    ('HD2_PreampUSDeluxeNrm', 225, 1016),             # guitar: US Deluxe Nrm
    ('HD2_PreampUSDeluxeVib', 226, 1466),             # guitar: US Deluxe Vib
    ('HD2_PreampUSDoubleNrm', 227, 1201),             # guitar: US Double Nrm
    ('HD2_PreampUSDoubleVib', 228, 1407),             # guitar: US Double Vib
    ('HD2_PreampMailOrderTwin', 215, 1670),           # guitar: Mail Order Twin
    ('HD2_PreampDividedDuo', 205, 1212),              # guitar: Divided Duo
    ('HD2_PreampInterstateZed', 210, 1054),           # guitar: Interstate Zed
    ('HD2_PreampDerailedIngrid', 385, 1410),          # guitar: Derailed Ingrid
    ('HD2_PreampGSG100', 779, 2200),                  # guitar: Grammatico GSG
    ('HD2_PreampJazzRivet120', 211, 773),            # guitar: Jazz Rivet 120
    ('HD2_PreampEssexA15', 206, 1110),                # guitar: Essex A15
    ('HD2_PreampEssexA30', 207, 1204),                # guitar: Essex A30
    ('HD2_PreampA30FawnNrm', 194, 992),              # guitar: A30 Fawn Nrm
    ('HD2_PreampA30FawnBrt', 193, 1007),              # guitar: A30 Fawn Brt
    ('HD2_PreampMatchstickCh1', 309, 1090),           # guitar: Matchstick Ch1
    ('HD2_PreampMatchstickCh2', 310, 1025),           # guitar: Matchstick Ch2
    ('HD2_PreampMatchstickJump', 311, 1625),          # guitar: Matchstick Jump
    ('HD2_PreampMandarin80', 216, 1342),              # guitar: Mandarin 80
    ('HD2_PreampMandarinRocker', 619, 1342),          # guitar: Mandarin Rocker
    ('HD2_PreampMoonNrm', 664, 1700),                 # guitar: Moo)))n Nrm
    ('HD2_PreampMoonBrt', 666, 1600),                 # guitar: Moo)))n Brt
    ('HD2_PreampMoonJump', 668, 1900),                # guitar: Moo)))n Jump
    ('HD2_PreampBritJ45Nrm', 198, 1348),              # guitar: Brit J45 Nrm
    ('HD2_PreampBritJ45Brt', 197, 1345),              # guitar: Brit J45 Brt
    ('HD2_PreampBritTremNrm', 481, 1565),             # guitar: Brit Trem Nrm
    ('HD2_PreampBritTremBrt', 482, 1565),             # guitar: Brit Trem Brt
    ('HD2_PreampBritTremJump', 483, 1860),            # guitar: Brit Trem Jump
    ('HD2_PreampBritPlexiNrm', 203, 1318),            # guitar: Brit Plexi Nrm
    ('HD2_PreampBritPlexiBrt', 201, 1712),            # guitar: Brit Plexi Brt
    ('HD2_PreampBritPlexiJump', 202, 2043),           # guitar: Brit Plexi Jump
    ('HD2_PreampBritP75Nrm', 200, 1318),              # guitar: Brit P75 Nrm
    ('HD2_PreampBritP75Brt', 199, 1318),              # guitar: Brit P75 Brt
    ('HD2_PreampBrit2203', 788, 1950),                # guitar: Brit 2203
    ('HD2_PreampBrit2204', 196, 1846),                # guitar: Brit 2204
    ('HD2_PreampPlacaterClean', 513, 1050),           # guitar: Placater Clean
    ('HD2_PreampPlacaterDirty', 501, 1850),           # guitar: Placater Dirty
    ('HD2_PreampCartographer', 485, 1660),            # guitar: Cartographer
    ('HD2_PreampGermanXtraBlue', 820, 1700),          # guitar: German Xtra Blue
    ('HD2_PreampGermanXtraRed', 822, 2000),           # guitar: German Xtra Red
    ('HD2_PreampGermanMahadeva', 208, 1751),          # guitar: German Mahadeva
    ('HD2_PreampGermanUbersonic', 209, 1451),         # guitar: German Ubersonic
    ('HD2_PreampCaliTexasCh1', 515, 1500),            # guitar: Cali Texas Ch1
    ('HD2_PreampCaliTexasCh2', 503, 1800),            # guitar: Cali Texas Ch2
    ('HD2_PreampCaliIVR1', 316, 1425),                # guitar: Cali IV Rhythm 1
    ('HD2_PreampCaliIVR2', 317, 1425),                # guitar: Cali IV Rhythm 2
    ('HD2_PreampCaliIVLead', 315, 1575),              # guitar: Cali IV Lead
    ('HD2_PreampCaliRectifire', 204, 1775),           # guitar: Cali Rectifire
    ('HD2_PreampArchetypeClean', 337, 1325),          # guitar: Archetype Clean
    ('HD2_PreampArchetypeLead', 338, 1575),           # guitar: Archetype Lead
    ('HD2_PreampANGLMeteor', 195, 1714),              # guitar: ANGL Meteor
    ('HD2_PreampSoloLeadClean', 218, 1440),           # guitar: Solo Lead Clean
    ('HD2_PreampSoloLeadCrunch', 219, 1440),          # guitar: Solo Lead Crunch
    ('HD2_PreampSoloLeadOD', 220, 1755),              # guitar: Solo Lead OD
    ('HD2_PreampEVPanamaBlue', 826, 2200),            # guitar: EV Panama Blue
    ('HD2_PreampEVPanamaRed', 824, 2900),             # guitar: EV Panama Red
    ('HD2_PreampPVPanama', 217, 1529),                # guitar: PV Panama
    ('HD2_PreampPVVitriolClean', 765, 2200),          # guitar: PV Vitriol Clean
    ('HD2_PreampPVVitriolCrunch', 746, 2650),         # guitar: PV VitriolCrunch
    ('HD2_PreampPVVitriolLead', 747, 2650),           # guitar: PV Vitriol Lead
    ('HD2_PreampRevvGenPurple', 562, 2000),           # guitar: Revv Gen Purple
    ('HD2_PreampRevvGenRed', 546, 2000),              # guitar: Revv Gen Red
    ('HD2_PreampDasBenzinMega', 602, 1600),           # guitar: Das Benzin Mega
    ('HD2_PreampDasBenzinLead', 600, 1850),           # guitar: Das Benzin Lead
    ('HD2_PreampLine6Clarity', 705, 1700),            # guitar: Line6 Clarity
    ('HD2_PreampLine6Aristocrat', 706, 2350),         # guitar: Line6 Aristocrat
    ('HD2_PreampLine6Carillon', 707, 2250),           # guitar: Line 6 Carillon
    ('HD2_PreampLine6Voltage', 704, 2550),            # guitar: Line 6 Voltage
    ('HD2_PreampLine6Kinetic', 703, 2250),            # guitar: Line 6 Kinetic
    ('HD2_PreampLine6Oblivion', 702, 2700),           # guitar: Line 6 Oblivion
    ('HD2_PreampLine6Ventoux', 662, 1800),            # guitar: Line 6 Ventoux
    ('HD2_PreampLine6Elmsley', 763, 1800),            # guitar: Line 6 Elmsley
    ('HD2_PreampLine6Elektrik', 213, 1412),           # guitar: Line 6 Elektrik
    ('HD2_PreampLine6Doom', 212, 1455),               # guitar: Line 6 Doom
    ('HD2_PreampLine6Epic', 214, 1726),               # guitar: Line 6 Epic
    ('HD2_PreampLine62204ModV2', 330, 1830),          # guitar: Line 6 2204 Mod
    ('HD2_PreampLine6Fatality', 329, 1798),           # guitar: Line 6 Fatality
    ('HD2_PreampLine6Litigator', 342, 1685),          # guitar: Line 6 Litigator
    ('HD2_PreampLine6Badonk', 354, 1650),             # guitar: Line 6 Bigger
    ('HD2_PreampTucknGo', 192, 1131),                 # bass: Ampeg B-15NF
    ('HD2_PreampSVBeastNrm', 191, 1864),              # bass: Ampeg SVT Nrm
    ('HD2_PreampSVBeastBrt', 190, 1855),              # bass: Ampeg SVT Brt
    ('HD2_PreampSVT4Pro', 520, 1635),                 # bass: Ampeg SVT-4 PRO
    ('HD2_PreampUSDripmanNorm', 785, 1650),           # bass: US Dripman Norm
    ('HD2_PreampWoodyBlue', 353, 825),               # bass: Woody Blue
    ('HD2_PreampAguaSledge', 761, 1000),              # bass: Agua Sledge
    ('HD2_PreampAgua51', 487, 1889),                  # bass: Agua 51
    ('HD2_PreampMandarinBass200', 790, 1350),         # bass: Mandarin Bass 200
    ('HD2_PreampCaliBass', 188, 1173),                # bass: Cali Bass
    ('HD2_PreampCali400Ch1', 186, 1257),              # bass: Cali 400 Ch1
    ('HD2_PreampCali400Ch2', 187, 1257),              # bass: Cali 400 Ch2
    ('HD2_PreampGCougar800', 189, 1100),              # bass: G Cougar 800
    ('HD2_PreampDelSol300', 344, 360),               # bass: Del Sol 300
    ('HD2_PreampBusyOneCh1', 370, 725),              # bass: Busy One Ch1
    ('HD2_PreampBusyOneCh2', 371, 700),              # bass: Busy One Ch2
    ('HD2_PreampBusyOneJump', 372, 1375),             # bass: Busy One Jump
    ('HD2_PreampVintagePre', 231, 843),              # mic: Studio Tube Pre
)
