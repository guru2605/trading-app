export interface IndexSymbol {
  tradingsymbol: string;
  exchange: string;
}

// Helper to build NSE symbol arrays concisely
const nse = (symbols: string[]): IndexSymbol[] =>
  symbols.map((s) => ({ tradingsymbol: s, exchange: "NSE" }));

// ── Broad Market ──

export const NIFTY_50 = nse([
  "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO",
  "BAJFINANCE", "BAJAJFINSV", "BEL", "BPCL", "BHARTIARTL",
  "BRITANNIA", "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT",
  "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
  "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
  "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT",
  "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
  "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN",
  "SUNPHARMA", "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL",
  "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]);

export const NIFTY_NEXT_50 = nse([
  "ABB", "ADANIENT", "ADANIGREEN", "AMBUJACEM", "ATGL",
  "BAJAJHLDNG", "BANKBARODA", "BHEL", "BOSCHLTD", "CANBK",
  "CHOLAFIN", "COLPAL", "DABUR", "DLF", "GAIL",
  "GODREJCP", "HAL", "HAVELLS", "HINDPETRO", "ICICIPRULI",
  "INDHOTEL", "INDIGO", "IOC", "IRCTC", "IRFC",
  "JIOFIN", "JSWENERGY", "LICI", "LODHA", "LTIM",
  "MARICO", "MAXHEALTH", "MOTHERSON", "NHPC", "NAUKRI",
  "OBEROIRLTY", "PFC", "PIDILITIND", "PNB", "POLYCAB",
  "RECLTD", "SBICARD", "SIEMENS", "SRF", "TATAPOWER",
  "TORNTPHARM", "UNIONBANK", "VBL", "VEDL",
]);

export const NIFTY_MIDCAP_100 = nse([
  "AARTIIND", "ACC", "ABFRL", "ASTRAL", "AUROPHARMA",
  "BALKRISIND", "BHARATFORG", "BATAINDIA", "BHEL", "BDL",
  "CANFINHOME", "CGPOWER", "COFORGE", "CONCOR", "CROMPTON",
  "CUMMINSIND", "DALBHARAT", "DEEPAKNTR", "DIXON", "ESCORTS",
  "EXIDEIND", "FEDERALBNK", "FORTIS", "GLENMARK", "GMRAIRPORT",
  "GODREJPROP", "HATSUN", "HINDCOPPER", "HONAUT",
  "IDFCFIRSTB", "INDHOTEL", "JUBLFOOD", "KAJARIACER", "KEI",
  "KPITTECH", "LAURUSLABS", "LICHSGFIN", "LUPIN", "M&MFIN",
  "MANAPPURAM", "MFSL", "MPHASIS", "MRF", "MUTHOOTFIN",
  "NATIONALUM", "NAVINFLUOR", "NMDC", "OBEROIRLTY", "PAGEIND",
  "PERSISTENT", "PETRONET", "PIIND", "POLYCAB", "PVRINOX",
  "RAMCOCEM", "RELAXO", "SAIL", "SOLARINDS", "SRF",
  "SYNGENE", "TATACHEM", "TATACOMM", "TATAELXSI", "TATAPOWER",
  "TORNTPHARM", "VOLTAS", "ZYDUSLIFE", "LTTS", "POLICYBZR",
  "MAXHEALTH", "AFFLE", "AMBER", "APTUS", "BRIGADE",
  "CDSL", "CLEAN", "DMART", "GNFC",
  "HAPPSTMNDS", "IEX", "INDIAMART", "IRB", "IRCTC",
  "JKCEMENT", "JUBLINGREA", "LALPATHLAB", "LTIM", "METROPOLIS",
  "NATCOPHARM", "PHOENIXLTD", "PRESTIGE", "RADICO", "RAJESHEXPO",
  "STARHEALTH", "SUPREMEIND", "TATASTEEL", "TRIDENT", "VEDL",
]);

export const NIFTY_SMALLCAP_100 = nse([
  "ABCAPITAL", "ANGELONE", "APLLTD", "ASHOKLEY", "BSOFT",
  "CAMPUS", "CANFINHOME", "CENTRALBK", "CHAMBLFERT", "COCHINSHIP",
  "DATAPATTNS", "EASEMYTRIP", "ENGINERSIN", "EQUITASBNK", "FINEORG",
  "FLUOROCHEM", "GALAXYSURF", "GRANULES", "GRINDWELL", "HEG",
  "HSCL", "INDIACEM", "IRCON", "ISGEC", "ITI",
  "JSWINFRA", "JYOTHYLAB", "KPIL", "KEC", "KNRCON",
  "LXCHEM", "MAHABANK", "MANAPPURAM", "MAZDOCK", "MCX",
  "MOTILALOFS", "NAZARA", "NHPC", "NLCINDIA", "OFSS",
  "PGHH", "POLYMED", "POONAWALLA", "RBLBANK", "RVNL",
  "ROUTE", "SANOFI", "SAREGAMA", "SJVN",
  "SONACOMS", "SUNTV", "THERMAX", "TIINDIA", "TRITURBINE",
  "TVSMOTOR", "UJJIVANSFB", "UNIONBANK", "WHIRLPOOL", "YESBANK",
  "ZEEL", "AIAENG", "ATUL", "BASF", "BEL",
  "BLUESTARCO", "CESC", "COLPAL", "COROMANDEL", "CRISIL",
  "EIHOTEL", "ELGIEQUIP", "EMAMILTD", "ENDURANCE", "ERIS",
  "FINCABLES", "GLAXO", "GESHIP", "GILLETTE", "GUJGASLTD",
  "HINDPETRO", "IOB", "IOC", "JKPAPER",
  "JUSTDIAL", "KANSAINER", "KSB", "CIEINDIA", "MMTC",
  "NIACL", "ORIENTELEC", "PFC", "RECLTD",
  "SCHAEFFLER", "SHREECEM", "SUMICHEM", "SUNDRMFAST",
]);

// ── Sectors ──

export const NIFTY_BANK = nse([
  "AUBANK", "AXISBANK", "BANDHANBNK", "BANKBARODA", "FEDERALBNK",
  "HDFCBANK", "ICICIBANK", "IDFCFIRSTB", "INDUSINDBK", "KOTAKBANK",
  "PNB", "SBIN",
]);

export const NIFTY_IT = nse([
  "COFORGE", "HCLTECH", "INFY", "LTIM", "LTTS",
  "MPHASIS", "PERSISTENT", "TCS", "TECHM", "WIPRO",
]);

export const NIFTY_AUTO = nse([
  "ASHOKLEY", "BAJAJ-AUTO", "BALKRISIND", "BHARATFORG", "BOSCHLTD",
  "EICHERMOT", "EXIDEIND", "HEROMOTOCO", "M&M", "MARUTI",
  "MOTHERSON", "MRF", "TATAMOTORS", "TIINDIA", "TVSMOTOR",
]);

export const NIFTY_PHARMA = nse([
  "ALKEM", "AUROPHARMA", "BIOCON", "CIPLA", "DIVISLAB",
  "DRREDDY", "GLENMARK", "IPCALAB", "LUPIN", "SUNPHARMA",
  "TORNTPHARM", "ZYDUSLIFE",
]);

export const NIFTY_FMCG = nse([
  "BRITANNIA", "COLPAL", "DABUR", "GODREJCP", "HINDUNILVR",
  "ITC", "MARICO", "NESTLEIND", "TATACONSUM", "UBL",
  "VBL",
]);

export const NIFTY_ENERGY = nse([
  "ADANIGREEN", "BPCL", "GAIL", "HINDPETRO", "IOC",
  "JSWENERGY", "NTPC", "ONGC", "POWERGRID", "TATAPOWER",
]);

export const NIFTY_METAL = nse([
  "COALINDIA", "HINDALCO", "HINDCOPPER", "HINDZINC", "JSWSTEEL",
  "MOIL", "NATIONALUM", "NMDC", "RATNAMANI", "SAIL",
  "TATASTEEL", "VEDL", "WELCORP", "APLAPOLLO", "JINDALSTEL",
]);

export const NIFTY_REALTY = nse([
  "BRIGADE", "DLF", "GODREJPROP", "LODHA", "MAHLIFE",
  "OBEROIRLTY", "PHOENIXLTD", "PRESTIGE", "SOBHA", "SUNTECK",
]);

export const NIFTY_PSU_BANK = nse([
  "BANKBARODA", "BANKINDIA", "CANBK", "CENTRALBK", "INDIANB",
  "IOB", "MAHABANK", "PNB", "PSB", "SBIN",
  "UCOBANK", "UNIONBANK",
]);

export const NIFTY_PVT_BANK = nse([
  "AUBANK", "AXISBANK", "BANDHANBNK", "FEDERALBNK", "HDFCBANK",
  "ICICIBANK", "IDFCFIRSTB", "INDUSINDBK", "KOTAKBANK", "RBLBANK",
]);

export const NIFTY_FIN_SERVICES = nse([
  "AXISBANK", "BAJFINANCE", "BAJAJFINSV", "CHOLAFIN", "HDFCBANK",
  "HDFCLIFE", "ICICIBANK", "ICICIGI", "ICICIPRULI", "INDUSINDBK",
  "KOTAKBANK", "LICHSGFIN", "M&MFIN", "MUTHOOTFIN", "PFC",
  "RECLTD", "SBICARD", "SBILIFE", "SBIN", "SHRIRAMFIN",
]);

export const NIFTY_INFRA = nse([
  "ADANIPORTS", "BHARTIARTL", "DLF", "GAIL", "GMRAIRPORT",
  "IRB", "LT", "NTPC", "OBEROIRLTY", "POWERGRID",
  "RECLTD", "SIEMENS", "TATAPOWER", "ULTRACEMCO", "ENGINERSIN",
]);

export const NIFTY_CONSUMER_DURABLES = nse([
  "AMBER", "BATAINDIA", "BLUESTARCO", "CROMPTON", "DIXON",
  "HAVELLS", "KAJARIACER", "PAGEIND", "POLYCAB", "RAJESHEXPO",
  "RELAXO", "TITAN", "TRENT", "VOLTAS", "WHIRLPOOL",
]);

export const NIFTY_HEALTHCARE = nse([
  "ALKEM", "APOLLOHOSP", "AUROPHARMA", "BIOCON", "CIPLA",
  "DIVISLAB", "DRREDDY", "FORTIS", "GLENMARK", "IPCALAB",
  "LALPATHLAB", "LUPIN", "MAXHEALTH", "METROPOLIS", "NATCOPHARM",
  "SUNPHARMA", "SYNGENE", "TORNTPHARM", "ZYDUSLIFE", "LAURUSLABS",
]);

export const NIFTY_MEDIA = nse([
  "HATHWAY", "NAZARA", "NETWORK18", "PVRINOX", "SAREGAMA",
  "SUNTV", "TVSMOTOR", "ZEEL",
]);

// ── Additional Nifty 500 stocks (not in other tabs) ──

export const NIFTY_500_EXTRA = nse([
  // Chemicals & Fertilizers
  "ATUL", "DEEPAKNTR", "PIIND", "SUMICHEM", "CHAMBLFERT",
  "COROMANDEL", "GNFC", "GUJALKALI", "TATACHEM", "UPL",
  "PIDILITIND", "SRF", "BASF", "SUDARSCHEM",
  // Construction & Engineering
  "KPIL", "KEC", "KNRCON", "NBCC", "NLCINDIA",
  "THERMAX", "TRITURBINE", "ENGINERSIN", "ISGEC", "HSCL",
  // Cement
  "DALBHARAT", "JKCEMENT", "RAMCOCEM", "SHREECEM", "STARCEMENT",
  "JKLAKSHMI", "HEIDELBERG", "PRSMJOHNSN", "ORIENTCEM",
  // Diversified / Conglomerate
  "3MINDIA", "PGHH", "SANOFI", "GILLETTE", "GLAXO",
  "HONAUT", "CRISIL", "OFSS", "NAUKRI", "DMART",
  // Insurance
  "ICICIGI", "ICICIPRULI", "HDFCLIFE", "SBILIFE", "STARHEALTH",
  "NIACL", "GICRE",
  // Power & Utilities
  "NHPC", "SJVN", "CESC", "TATAPOWER", "NTPC",
  "ADANIGREEN", "JPPOWER", "RTNINDIA", "TORNTPOWER",
  // Telecom
  "BHARTIARTL", "IDEA", "TTML",
  // Textiles & Apparel
  "PAGEIND", "RAYMOND", "ARVIND", "KITEX", "TRIDENT",
  "GARFIBRES",
  // Paper
  "JKPAPER", "ANDHRAPAP",
  // Oil & Gas
  "MRPL", "CHENNPETRO", "CASTROLIND", "IGL",
  "MGL", "PETRONET",
  // Logistics
  "CONCOR", "BLUEDART", "ALLCARGO", "MAHSEAMLES", "GESHIP",
  // Hospitality & Tourism
  "INDHOTEL", "EIHOTEL", "LEMONTREE",
  // Agri & Sugar
  "DHANUKA", "BALRAMCHIN", "DALMIASUG", "RENUKA",
  // Electronics & IT
  "TATAELXSI", "KPITTECH", "HAPPSTMNDS", "MASTEK",
  "ZENSARTECH", "CYIENT", "INTELLECT", "TANLA", "RATEGAIN",
  // Defence
  "HAL", "BDL", "BEL", "MAZDOCK", "COCHINSHIP",
  "DATAPATTNS",
  // Miscellaneous Large/Mid
  "MCX", "BSE", "CDSL", "CAMS", "ANGELONE",
  "MOTILALOFS", "CHOLAFIN", "SUNDRMFAST", "SCHAEFFLER", "SKFINDIA",
  "TIMKEN", "CUMMINSIND", "AIAENG", "FINCABLES", "ELGIEQUIP",
  "GRINDWELL", "EMAMILTD", "JYOTHYLAB", "GALAXYSURF", "ORIENTELEC",
  "ENDURANCE", "ERIS", "JUSTDIAL", "INDIAMART",
  "KANSAINER", "KSB", "CIEINDIA", "MMTC",
  "LXCHEM", "POLYMED", "POONAWALLA", "RBLBANK", "ROUTE",
  "SOLARINDS", "SONACOMS", "EQUITASBNK", "IEX", "UJJIVANSFB",
  "AFFLE", "CAMPUS", "CLEAN", "FINEORG", "FLUOROCHEM",
  "RADICO", "SUPREMEIND",
]);

// Additional Nifty 500 constituents not covered by the indices above
export const NIFTY_500_REMAINING = nse([
  "360ONE", "AADHARHFC", "AAVAS", "ABBOTINDIA", "ABDL",
  "ABLBL", "ABREL", "ABSLAMC", "ACE", "ACMESOLAR",
  "ACUTAAS", "ADANIENSOL", "ADANIPOWER", "AEGISLOG", "AEGISVOPAK",
  "AFCONS", "AIIL", "AJANTPHARM", "ANANDRATHI", "ANANTRAJ",
  "ANTHEM", "ANURAS", "APARINDS", "APOLLOTYRE", "ARE&M",
  "ASAHIINDIA", "ASTERDM", "ATHERENERG", "AWL", "BAJAJHFL",
  "BAYERCROP", "BBTC", "BELRISE", "BEML", "BERGEPAINT",
  "BHARTIHEXA", "BIKAJI", "BLS", "BLUEJET", "CANHLIFE",
  "CAPLIPOINT", "CARBORUNIV", "CARTRADE", "CCL", "CEATLTD",
  "CEMPRO", "CGCL", "CHALET", "CHOICEIN", "CHOLAHLDNG",
  "COHANCE", "CONCORDBIO", "CPPLUS", "CRAFTSMAN", "CREDITACC",
  "CUB", "DCMSHRIRAM", "DEEPAKFERT", "DELHIVERY", "DEVYANI",
  "DOMS", "ECLERX", "EIDPARRY", "ELECON", "EMCURE",
  "EMMVEE", "ENRIN", "FACT", "FIRSTCRY", "FIVESTAR",
  "FORCEMOT", "FSL", "GABRIEL", "GALLANTT", "GLAND",
  "GMDCLTD", "GODFRYPHLP", "GODIGIT", "GODREJIND", "GPIL",
  "GRAPHITE", "GRAVITA", "GROWW", "GRSE", "GVT&D",
  "HBLENGINE", "HDBFS", "HDFCAMC", "HEXT", "HFCL",
  "HOMEFIRST", "HONASA", "HUDCO", "HYUNDAI", "ICICIAMC",
  "IDBI", "IFCI", "IGIL", "IIFL", "IKS",
  "INDGN", "INDUSTOWER", "INOXWIND", "IREDA", "ITCHOTELS",
  "J&KBANK", "JAINREC", "JBCHEPHARM", "JBMA", "JINDALSAW",
  "JKTYRE", "JMFINANCIL", "JSL", "JSWCEMENT", "JSWDULUX",
  "JUBLPHARMA", "JWL", "JYOTICNC", "KALYANKJIL", "KARURVYSYA",
  "KAYNES", "KFINTECH", "KIMS", "KIRLOSENG", "KPRMILL",
  "LATENTVIEW", "LENSKART", "LGEINDIA", "LINDEINDIA", "LLOYDSME",
  "LTF", "LTFOODS", "LTM", "MANKIND", "MAPMYINDIA",
  "MEDANTA", "MEESHO", "MINDACORP", "MSUMI", "NAM-INDIA",
  "NAVA", "NCC", "NETWEB", "NEULANDLAB", "NEWGEN",
  "NH", "NIVABUPA", "NSLNISP", "NTPCGREEN", "NUVAMA",
  "NUVOCO", "NYKAA", "OIL", "OLAELEC", "OLECTRA",
  "ONESOURCE", "PARADEEP", "PATANJALI", "PAYTM", "PCBL",
  "PFIZER", "PGEL", "PINELABS", "PIRAMALFIN", "PNBHOUSING",
  "POWERINDIA", "PPLPHARMA", "PREMIERENE", "PTCIL", "PWL",
  "RAILTEL", "RAINBOW", "REDINGTON", "RHIM", "RITES",
  "RKFORGE", "RPOWER", "RRKABEL", "SAGILITY", "SAILIFE",
  "SAMMAANCAP", "SAPPHIRE", "SARDAEN", "SBFC", "SCHNEIDER",
  "SCI", "SHYAMMETL", "SIGNATURE", "SONATSOFTW", "SPLPETRO",
  "SUNDARMFIN", "SUZLON", "SWANCORP", "SWIGGY", "SYRMA",
  "TARIL", "TATACAP", "TATAINVEST", "TATATECH", "TBOTEK",
  "TECHNOE", "TEGA", "TEJASNET", "TENNIND", "THELEELA",
  "TITAGARH", "TMCV", "TMPV", "TRAVELFOOD", "UNITDSPR",
  "UNOMINDA", "URBANCO", "USHAMART", "UTIAMC", "VIJAYA",
  "VMM", "VTL", "WAAREEENER", "WELSPUNLIV", "WOCKPHARMA",
  "ZENTEC", "ZFCVINDIA", "ZYDUSWELL",
]);

// ── Tab config ──

export type ScannerTab =
  | "top10"
  | "all"
  | "watchlist"
  | "nifty50"
  | "niftynext50"
  | "niftymidcap100"
  | "niftysmallcap100"
  | "nifty500extra"
  | "nifty500remaining"
  | "niftybank"
  | "niftyit"
  | "niftyauto"
  | "niftypharma"
  | "niftyfmcg"
  | "niftyenergy"
  | "niftymetal"
  | "niftyrealty"
  | "niftypsubank"
  | "niftypvtbank"
  | "niftyfinservices"
  | "niftyinfra"
  | "niftyconsumerdurables"
  | "niftyhealthcare"
  | "niftymedia";

export interface TabConfig {
  key: ScannerTab;
  label: string;
  group?: string;
  symbols?: IndexSymbol[];
}

export const SCANNER_TABS: TabConfig[] = [
  // Core
  { key: "top10", label: "Top 10", group: "Core" },
  { key: "all", label: "All Signals", group: "Core" },
  { key: "watchlist", label: "Watchlist", group: "Core" },
  { key: "nifty50", label: "Nifty 50", group: "Broad Market", symbols: NIFTY_50 },
  { key: "niftynext50", label: "Nifty Next 50", group: "Broad Market", symbols: NIFTY_NEXT_50 },
  { key: "niftymidcap100", label: "Midcap 100", group: "Broad Market", symbols: NIFTY_MIDCAP_100 },
  { key: "niftysmallcap100", label: "Smallcap 100", group: "Broad Market", symbols: NIFTY_SMALLCAP_100 },
  { key: "nifty500extra", label: "Nifty 500 Others", group: "Broad Market", symbols: NIFTY_500_EXTRA },
  { key: "nifty500remaining", label: "Nifty 500 Rest", group: "Broad Market", symbols: NIFTY_500_REMAINING },
  // Sectors
  { key: "niftybank", label: "Bank", group: "Sector", symbols: NIFTY_BANK },
  { key: "niftypsubank", label: "PSU Bank", group: "Sector", symbols: NIFTY_PSU_BANK },
  { key: "niftypvtbank", label: "Pvt Bank", group: "Sector", symbols: NIFTY_PVT_BANK },
  { key: "niftyfinservices", label: "Fin Services", group: "Sector", symbols: NIFTY_FIN_SERVICES },
  { key: "niftyit", label: "IT", group: "Sector", symbols: NIFTY_IT },
  { key: "niftyauto", label: "Auto", group: "Sector", symbols: NIFTY_AUTO },
  { key: "niftypharma", label: "Pharma", group: "Sector", symbols: NIFTY_PHARMA },
  { key: "niftyhealthcare", label: "Healthcare", group: "Sector", symbols: NIFTY_HEALTHCARE },
  { key: "niftyfmcg", label: "FMCG", group: "Sector", symbols: NIFTY_FMCG },
  { key: "niftyenergy", label: "Energy", group: "Sector", symbols: NIFTY_ENERGY },
  { key: "niftymetal", label: "Metal", group: "Sector", symbols: NIFTY_METAL },
  { key: "niftyrealty", label: "Realty", group: "Sector", symbols: NIFTY_REALTY },
  { key: "niftyinfra", label: "Infra", group: "Sector", symbols: NIFTY_INFRA },
  { key: "niftyconsumerdurables", label: "Consumer Dur.", group: "Sector", symbols: NIFTY_CONSUMER_DURABLES },
  { key: "niftymedia", label: "Media", group: "Sector", symbols: NIFTY_MEDIA },
];
