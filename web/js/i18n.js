// Constants, the TR/EN T dictionary and favourite-club storage.
const WS_URL = new URLSearchParams(location.search).get("ws")
  || (location.protocol.startsWith("http") ? `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws` : "ws://localhost:8765");
const JITTER_S = 0.3;  // how far behind the server clock we play, so packets arrive before they are due
// Broadcast delay of the fan modes: the server sends the first DELAY_S of match data at once and stays that far ahead, which is the
// live commentator's time budget. Everything (sound, callouts, narration, commentary, pitch, timeline, stats) follows the same play
// clock, so it stays together. Analyst plays at JITTER_S. Chosen at Start; a mode change mid-session keeps it.
const DELAY_S = 20;
const PENTA = [0, 3, 5, 7, 10, 12, 15, 17, 19, 22, 24].map(s => 220 * Math.pow(2, s / 12));
const $ = id => document.getElementById(id);
const COLOR = { red: "#f06a4f", blue: "#5b9cf5", yellow: "#e8d44d", orange: "#f39a3d", white: "#e8efe9", purple: "#b18cf5" };
const LABEL = { tr: { shot: "Şut", save: "Kurtarış", goal: "GOL", out: "Top dışarıda", foul: "Faul", kickoff: "Santra", yellow: "Sarı kart", red: "Kırmızı kart" },
  en: { shot: "Shot", save: "Save", goal: "GOAL", out: "Ball out", foul: "Foul", kickoff: "Kick-off", yellow: "Yellow card", red: "Red card" } };
// One dictionary for every UI string, in the interface language. The commentary language (what is spoken) is set apart.
const T = {
  tr: { sub: "Maçı sesle takip et.", headphones: "Kulaklıkla dinle", matchView: "Maç görünümü",
    pitchAria: "Topun saha üzerindeki konumu", home: "Ev sahibi", away: "Deplasman", blindTitle: "Saha gizli",
    blindSub: "Maçı yalnızca sesle takip ediyorsun.", tagIdle: "Anlatım",
    captionIdle: "\"Dinlemeye başla\"ya bas. Anlatıcı yalnızca top oyun dışındayken ya da tehlike düşükken konuşur.",
    captionListen: "Dinleniyor · anlatıcı birkaç saniye içinde konuşur.", captionListenAnalyst: "Dinleniyor · bir şey değiştiğinde taktik notlar burada görünür.",
    idle: "Dinlemeye başla", stop: "Durdur", blindBtn: "Sahayı gizle", showBtn: "Sahayı göster", modeLabel: "Dinleme modu",
    mode_eyes_free: "Sadece ses", mode_casual: "Rahat", mode_analyst: "Analist", favLabel: "Favori oyuncu (kulaklık sesi)", favNone: "Yok",
    recapTitle: "Ne kaçırdım?", recapBtn: "Beni özetle", recapEmpty: "Henüz anlatım yok.", recapScore: "Skor",
    preparing: "Hazırlanıyor…", recapTag: "Özet", fullTime: "Maç sonu özeti", missedSince: "Dakika", recapSince: "sonrası",
    fullTimeLog: "Maç sonu", halfTimeLog: "Devre arası", ftShort: "MS",
    tourOffer: "Yeni misin? 60 saniyelik ses turu", tourSkip: "Turu geç", tourTag: "Ses turu", tourStart: "Turu başlat", tourDismiss: "Kapat", settingsTitle: "Ayarlar", sumNoClub: "Favori kulüp yok",
    nowTitle: "Şu an", danger: "Tehlike", pressure: "Baskı", wing: "Kanat", earL: "sol kulak", earR: "sağ kulak",
    left: "sol", right: "sağ", mid: "orta", logEmpty: "Olaylar burada akacak.",
    layersTitle: "Katmanlar", lBall: "Top sesi (tehlike, kanat, takım)", lPress: "Baskı nabzı", lCrowd: "Tribün", lCue: "Olay sesleri", lCallout: "Kısa anonslar (isim, şut, taç…)", lVoice: "Anlatım",
    matchBar: "Maç ve izleme biçimi", matchLabel: "Maç seç", watchLabel: "İzleme biçimi", watchLive: "Canlı", watchHl: "Önemli anlar",
    liveFrom: "Canlı, başlangıç", ready: "Hazır:", hlCount: "an", cutTo: "Sıradaki an:", halfTimeRecap: "Devre arası özeti",
    pausedHidden: "Sekme gizliyken dinleme durdu. Başlat'a basınca şuradan sürer:",
    feedTitle: "Canlı anlatım", feedEmpty: "Anlatıcının son cümleleri, söylendikçe burada görünür.",
    mo_goal: "Gol", mo_save: "Kurtarış", mo_yellow: "Sarı kart", mo_red: "Kırmızı kart", startBefore: "30 saniye önceden başla", playClip: "bu anın klibini oynat",
    tlHint: "İlk gol {m}. dakikada · 30 saniye önceden başlamak için işaretini seç.",
    spaceKey: "Boşluk", nextBtn: "Sonraki an", delayWord: "gecikme", secs: "sn", liveTag: "canlı", fallbackTag: "yedek", clubLabel: "Favori kulüp", clubNone: "Yok", yourTeam: "senin takımın",
    off: "Bağlı değil.", wait: "Sunucuya bağlanıldı, maç bekleniyor.", lost: "Bağlantı koptu. Başlat'a basınca kaldığı yerden sürer.", reconnecting: "Bağlantı koptu, yeniden bağlanılıyor…",
    fail: "Sunucuya bağlanılamadı. run_local çalışıyor mu?", novoice: "Bu dilde cihaz sesi yok; anlatım altyazı olarak görünür.",
    voice: "Ses", voiceTail: "(cihaz sesi; sunucu Azure klibi gönderirse o çalar)", uiLangLabel: "Arayüz dili", commLabel: "Anlatım dili", install: "Uygulamayı yükle",
    tlTitle: "Zaman çizelgesi · bir yere ya da ana dokun, oradan başla; oynanmış işaret kanıtını gösterir", tlLegendIns: "Tespit (dolu = anlatıldı)", tlInsight: "Tespit", tlShot: "Şut", tlGoal: "Gol", tlMoment: "An (seç: oradan dinle)",
    whyTitle: "Neden?", whyIdle: "Zaman çizelgesinde bir işaret seç: dayandığı olaylar sahada parlar, sayıları burada görünür.",
    evidenceN: "Dayanak: maçtaki {n} olay (sahada işaretli).", evidence1: "Dayanak: maçtaki 1 olay (sahada işaretli).", speed: "Top hızı",
    fx_window: "Karşılaştırma", fx_windowVal: "son {n} dk, öncesine göre", fx_press: "Baskı altında top kullanımı ({opp})",
    fx_gap: "Paslar arası tipik süre", fx_slower: "Yavaşlama", fx_flank: "{side} kanatta biten paslar", side_left: "Sol", side_right: "Sağ",
    fx_player: "Oyuncu", fx_hsr: "Yüksek tempolu koşu, önceki dakikalara göre", fx_scorer: "Golü atan", fx_score: "Skor",
    fx_trigger: "Tetikleyen", fx_shot: "Şut", fx_danger: "Tehlikeli atak", fx_outcome: "Sonuç", spoken: "anlatıldı", notSpoken: "anlatılmadı", kmh: "km/s",
    ins_pressure_shift: "{team} baskıyı artırdı", ins_tempo_change: "{team} oyunu yavaşlattı", ins_flank_overload: "{team} {side} kanada yüklendi",
    ins_physical_drop: "{player} yoruldu", ins_chance: "{team} için pozisyon", ins_goal: "{team} golü",
    outcome: { saved: "kurtarıldı", off_target: "isabetsiz", blocked: "engellendi", goal: "gol" },
    statsTitle: "Takım istatistikleri", statsMatch: "Maç", statsLast10: "Son 10 dk", statsStat: "İstatistik", longPass: "Uzun pas",
    st_possession_pct: "Topla oynama", st_shots: "Şut (isabetli)", st_pass_completion_pct: "Pas isabeti", st_pressing_pct: "Pres",
    st_corners: "Korner", st_fouls: "Faul", statsWait: "İlk sayılar maç başlayınca gelir.",
    statsNote: "Pres: rakibin topla yaptığı hareketlerin bu takımın baskısı altında yapılan payı. Her 10 saniyede güncellenir.",
    toListen: "Dinleme görünümü", toDesk: "Sahayı ve veriyi göster",
    listenSub: "Sesle izlenen futbol. Kulaklığını tak.", chooseMatch: "Maç seç", versus: "{home} – {away} maçı",
    keysLine: "Tuşlar: Boşluk başlatır ya da durdurur, N sonraki ana geçer.",
    touchLine: "Telefonunu kilitle, maç çalmaya devam eder. Kulaklıkta sesin yönü sahanın tarafını söyler." },
  en: { sub: "Follow the match by sound.", headphones: "Best with headphones", matchView: "Match view",
    pitchAria: "Ball position on the pitch", home: "Home", away: "Away", blindTitle: "Pitch hidden",
    blindSub: "You follow the match by sound alone.", tagIdle: "Narration",
    captionIdle: "Press \"Start listening\". The narrator only speaks when the ball is dead or danger is low.",
    captionListen: "Listening · the commentator speaks in a few seconds.", captionListenAnalyst: "Listening · tactical notes appear when something changes.",
    idle: "Start listening", stop: "Stop", blindBtn: "Hide pitch", showBtn: "Show pitch", modeLabel: "Listening mode",
    mode_eyes_free: "Audio only", mode_casual: "Casual", mode_analyst: "Analyst", favLabel: "Favourite player (headphone cue)", favNone: "None",
    recapTitle: "What did I miss?", recapBtn: "Catch me up", recapEmpty: "No narration yet.", recapScore: "Score",
    preparing: "Preparing…", recapTag: "Recap", fullTime: "Full-time recap", missedSince: "Since minute", recapSince: "",
    fullTimeLog: "Full time", halfTimeLog: "Half-time", ftShort: "FT",
    tourOffer: "New here? 60-second sound tour", tourSkip: "Skip tour", tourTag: "Sound tour", tourStart: "Take the tour", tourDismiss: "Dismiss", settingsTitle: "Settings", sumNoClub: "No favourite club",
    nowTitle: "Right now", danger: "Danger", pressure: "Pressure", wing: "Wing", earL: "left ear", earR: "right ear",
    left: "left", right: "right", mid: "centre", logEmpty: "Events will flow here.",
    layersTitle: "Layers", lBall: "Ball sound (danger, wing, team)", lPress: "Pressure pulse", lCrowd: "Crowd", lCue: "Event sounds", lCallout: "Callouts (names, shots, throw-ins…)", lVoice: "Narration",
    matchBar: "Match and how to watch", matchLabel: "Pick a match", watchLabel: "How to watch", watchLive: "Live", watchHl: "Highlights",
    liveFrom: "Live from", ready: "Ready:", hlCount: "moments", cutTo: "Next highlight:", halfTimeRecap: "Half-time recap",
    pausedHidden: "Listening stopped while the tab was hidden. Start picks up at",
    feedTitle: "Live commentary", feedEmpty: "The commentator's latest lines show here as they are spoken.",
    mo_goal: "Goal", mo_save: "Save", mo_yellow: "Yellow card", mo_red: "Red card", startBefore: "start 30 seconds before", playClip: "play this moment's clip",
    tlHint: "First goal at {m}' · select its marker to start 30 s before.",
    spaceKey: "Space", nextBtn: "Next moment", delayWord: "delay", secs: "s", liveTag: "live", fallbackTag: "fallback", clubLabel: "Favourite club", clubNone: "None", yourTeam: "your team",
    off: "Not connected.", wait: "Connected, waiting for the match.", lost: "Connection lost. Start picks up where it stopped.", reconnecting: "Connection lost, reconnecting…",
    fail: "Cannot reach the server. Is run_local running?", novoice: "No device voice for this language; narration shows as captions.",
    voice: "Voice", voiceTail: "(device voice; an Azure clip from the server plays instead when present)", uiLangLabel: "Interface language", commLabel: "Commentary language", install: "Install the app",
    tlTitle: "Timeline · select a minute or a moment to start there; a played marker shows its evidence", tlLegendIns: "Insight (filled = spoken)", tlInsight: "Insight", tlShot: "Shot", tlGoal: "Goal", tlMoment: "Moment (select to listen from there)",
    whyTitle: "Why?", whyIdle: "Select a marker on the timeline: the events behind it light up on the pitch and its numbers show here.",
    evidenceN: "Based on {n} match events (marked on the pitch).", evidence1: "Based on 1 match event (marked on the pitch).", speed: "Ball speed",
    fx_window: "Compared", fx_windowVal: "last {n} min vs before", fx_press: "On-ball actions under pressure ({opp})",
    fx_gap: "Typical time between passes", fx_slower: "Slower by", fx_flank: "Passes ending on the {side} flank", side_left: "left", side_right: "right",
    fx_player: "Player", fx_hsr: "High-speed running vs earlier minutes", fx_scorer: "Scorer", fx_score: "Score",
    fx_trigger: "Trigger", fx_shot: "Shot", fx_danger: "Dangerous attack", fx_outcome: "Result", spoken: "spoken", notSpoken: "not spoken", kmh: "km/h",
    ins_pressure_shift: "{team} pressing", ins_tempo_change: "{team} slowing the tempo", ins_flank_overload: "{team} overloading the {side} flank",
    ins_physical_drop: "{player} tiring", ins_chance: "{team} chance", ins_goal: "{team} goal",
    outcome: { saved: "saved", off_target: "off target", blocked: "blocked", goal: "goal" },
    statsTitle: "Team stats", statsMatch: "Match", statsLast10: "Last 10 min", statsStat: "Statistic", longPass: "Long pass",
    st_possession_pct: "Possession", st_shots: "Shots (on target)", st_pass_completion_pct: "Pass completion", st_pressing_pct: "Pressing",
    st_corners: "Corners", st_fouls: "Fouls", statsWait: "The first numbers arrive when the match starts.",
    statsNote: "Pressing: share of the opponent's on-ball actions made under this team's pressure. Updates every 10 s.",
    toListen: "Listening view", toDesk: "Show the pitch & data",
    listenSub: "Football you can hear. Put on headphones.", chooseMatch: "Choose a match", versus: "{home} versus {away}",
    keysLine: "Keys: Space starts or stops, N jumps to the next moment.",
    touchLine: "Lock your phone, the match keeps playing. Headphones tell you the side of the pitch." } };
const MODES = ["eyes_free", "casual", "analyst"];
const store = { get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} } };
const LANGS = ["en", "tr"];
let uiLang = LANGS.includes(store.get("htg.lang")) ? store.get("htg.lang") : (navigator.language || "en").toLowerCase().startsWith("tr") ? "tr" : "en";
let commLang = LANGS.includes(store.get("htg.commentary")) ? store.get("htg.commentary") : null;  // null: follows the interface language
let mode = MODES.includes(store.get("htg.mode")) ? store.get("htg.mode") : "casual";
// Favourite club: a club id of the league ("" = none). It applies to whichever match includes that club; `club` is its side in the
// current match ("", "HOME" or "AWAY"). Stores from before the league held the side of the one demo match.
let favClub = (v => ({ HOME: "northport", AWAY: "valemont" })[v] || v || "")(store.get("htg.club")), club = "";
let league = null;  // /matches.json: { default, clubs, matches }; null when opened as a file (run_local: one match, no picker)
let matchId = store.get("htg.match"), watch = store.get("htg.watch") === "highlights" ? "highlights" : "live";
let startT = 0;  // Live: the match second the session starts from (a timeline click, a moment, or where listening stopped)
const curMatch = () => league && (league.matches.find(m => m.id === matchId) || league.matches.find(m => m.id === league.default));
const t = k => T[uiLang][k];
const lang = () => commLang || uiLang;  // the commentary language: narration, recaps, tour voice

