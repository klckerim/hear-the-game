# Hear the Game

> **Original design (2026-10-20, Turkish).** The README describes what was built; items not built were cut on purpose.
> Notably: narration is one Foundry model call per Insight plus a deterministic Verifier, not a set of agents; there is no
> Event Hubs, Web PubSub or Cosmos DB. Measured numbers are in `eval/results/`, not here.

Sistem tasarımı · Oct 20, 2026

Hear the Game, sentetik maç event'lerini dinleyicinin cihazında anlık üretilen sese ve doğrulanmış, çok dilli kısa anlatıma çevirir. Sistem iki hızda çalışır: ses 100 ms'nin altında deterministik kodla, anlatım yaklaşık 2 saniyede Microsoft Foundry agent'larıyla üretilir. Hackathon teslimi Oct 28, 2026 09:59 (İstanbul).

## Bir bakışta


Event'ler Event Hubs üzerinden `engine` servisine girer. Durum paketleri doğrudan dinleyiciye gider (hızlı yol), anlatım ise Foundry'de doğrulanıp sese çevrildikten sonra aynı kanaldan ulaşır (yavaş yol).

## Tasarım ilkeleri

Aşağıdaki yedi kural, bu dokümandaki her teknik kararın gerekçesidir. Bir karar bunlardan biriyle çelişiyorsa yanlış karardır.

1. **Sayıları kod üretir, kelimeleri LLM.** xT, baskı, süre, skor gibi her sayı deterministik koddan gelir. LLM yalnızca hazır olguları cümleye çevirir.
2. **Kanıtı olmayan cümle yayınlanmaz.** Her Insight, dayandığı event `seq` numaralarını taşır. Verifier, cümledeki her sayıyı `claim_facts` ile karşılaştırır; tutmayan cümle reddedilir.
3. **Ses LLM'i asla beklemez.** Hızlı yol (ses) ile yavaş yol (anlatım) birbirinden bağımsız çalışır. Yavaş yol çökse bile ses kesilmez.
4. **Sunucu veri gönderir, sesi cihaz üretir.** Dinleyiciye ses akışı değil, saniyede 10 küçük durum paketi gider. Konuşma, bu kuralın tek istisnasıdır.
5. **Önce şema.** Event, Insight ve Cue şemaları katmanlar arasındaki sözleşmedir; değişiklik önce şemada yapılır, sonra kodda.
6. **Her maç tekrar oynatılabilir.** Aynı seed her zaman aynı maçı üretir. Eval, hata ayıklama ve demo videosu buna dayanır.
7. **Önce lokal, en son bulut.** Her katman önce dosyadan okuyup dosyaya yazarak çalışır. Azure servisleri, yerel arayüzlerin yerine aynı sözleşmeyle takılır.

## İki hızlı yol

Ses yolu 100 ms'nin altında, anlatım yolu yaklaşık 2 saniyede tamamlanır. İkisi aynı durum (state) verisinden beslenir ama birbirini beklemez.

**Hızlı yol (ses):** event → state engine → durum paketi → WebSocket → tarayıcıda Web Audio sentezi.

**Yavaş yol (anlatım):** event → state engine → detector → Insight → Director kuyruğu → Narrator agent → Verifier → Localizer → Azure AI Speech → ses klibi → WebSocket → tarayıcıda ducking ile çalma.

Gecikme bütçesi (tasarım hedefi; 5. günde ölçülüp güncellenecek):

| Adım | Yol | Hedef (p95) |
| --- | --- | --- |
| Event → state güncellemesi | ikisi | < 50 ms |
| State → WebSocket → cihaz | hızlı | < 150 ms (ağa bağlı) |
| Cihazda jitter buffer | hızlı | sabit 300 ms |
| Detector → Insight | yavaş | < 100 ms |
| Narrator + Verifier (LLM) | yavaş | < 1,5 sn |
| Azure AI Speech (TTS) | yavaş | < 0,5 sn |
| Ses klibi → cihaz | yavaş | < 0,3 sn |

Director, anlatımı zaten oyun durduğunda ya da tehlike düşükken çaldığı için yavaş yolun 2–3 saniyesi dinleyiciye gecikme olarak yansımaz. Karşılaştırma için: bazı stadyumlarda insan anlatımı 30 saniye gecikmeli.

## Bileşenler

Sistem iki Container App (`engine`, `api`), bir statik web istemcisi ve yönetilen Azure servislerinden oluşur. Tek kişiyle 7 günde yönetilebilmesi için servis sayısı bilinçli olarak düşük tutuldu.

| Bileşen | Sorumluluk | Teknoloji | Çalıştığı yer |
| --- | --- | --- | --- |
| Maç yayıncısı (replay) | Sentetik maçı gerçek zamanlı (1x, 4x) event akışı olarak yayınlar; canlı veri sağlayıcısının yerini tutar | Python, `htg.replay` | `engine` içinde ya da lokal |
| Event Hubs | Event akışını alır, sırayı korur, tüketiciyi yayıncıdan ayırır | Azure Event Hubs | Azure |
| State engine | Event'leri saniyede 10 durum paketine çevirir: tehlike (xT), baskı, kanat, tempo, kontrol | Python asyncio | `engine` Container App |
| Detector'lar | Durumdan kanıtlı Insight üretir: pres artışı, tempo değişimi, kanat yüklenmesi, fiziksel düşüş, fırsat, gol | Python (kural + change-point) | `engine` |
| Director | Hangi Insight'ın ne zaman anlatılacağına karar verir: öncelik kuyruğu, sessizlik bütçesi, konuşma pencereleri | Python (deterministik) | `engine` |
| Anlatım workflow'u | Narrator → Verifier → Localizer zinciri; dil ve mod başına cümle üretir | Microsoft Agent Framework + Foundry modeli | `engine`; vakit kalırsa Foundry hosted agent |
| TTS servisi | Cümleyi SSML ile ses klibine çevirir, önbelleğe alır | Azure AI Speech SDK | `engine` |
| Recap agent | "Neyi kaçırdım?" sorusunu maç verisini araçlarla sorgulayarak cevaplar | Agent Framework + MCP araçları | `api` |
| Maç verisi MCP server | `get_state`, `get_insights`, `query_events`, `get_player` araçlarını sunar | Python MCP SDK | `api` |
| API | Web PubSub token'ı, maç listesi, profil, recap uçları | FastAPI | `api` Container App |
| Gerçek zamanlı dağıtım | Durum paketlerini ve ses kliplerini maç grubundaki tüm dinleyicilere iletir | Azure Web PubSub | Azure |
| Dinleyici uygulaması | Sesi cihazda sentezler, anlatımı çalar, modları ve erişilebilirliği yönetir | TypeScript + Vite, Web Audio API | Azure Static Web Apps |
| Kalıcı veri | Profil, Insight ve anlatım günlüğü (denetim izi) | Azure Cosmos DB (NoSQL, serverless) | Azure |
| Dosya deposu | Sentetik maçlar, kalibrasyon, ses klibi önbelleği | Azure Blob Storage | Azure |
| İzleme | Log, metrik, dağıtık iz, agent izleri | Application Insights + Foundry tracing | Azure |

## Veri

Gerçek açık veri yalnızca kalibrasyon için kullanılır ve repoya girmez. Sistemin geri kalanı tamamen sentetik veriyle çalışır; bu, yarışma kuralının gereği. Veri altı katmandan geçer, her katmanı tek bir modül yazar.

| Katman | İçerik | Format | Nerede | Yazan |
| --- | --- | --- | --- | --- |
| L0 Ham | StatsBomb (40 PL maçı), SkillCorner (3 maç tracking + fiziksel veriler) | Orijinal JSON / JSONL / CSV | Lokal `data/raw`, git'e girmez | `download_data.sh` |
| L1 Kalibrasyon | xT grid'i, pas geçiş matrisi, süre ve hız dağılımları, rol başına koşu verileri | `calibration.json` (228 KB) | Repo + Blob | `htg.calibrate` |
| L2 Sentetik maç | Event akışı, 10 Hz top izi, dakikalık fiziksel veri, gizli senaryolar | `events.jsonl`, `ball.parquet`, `physical.jsonl`, `truth.json` | Repo (örnekler) + Blob | `htg.generate` |
| L3 Durum | Saniyede 10 paket: konum, takım, tehlike, baskı, kanat, tempo | Bellekte; arşiv için Parquet | `engine` belleği → Blob | State engine |
| L4 Insight | Kanıtlı iddia, `claim_facts`, öncelik, geçerlilik süresi | JSON (`insight.schema.json`) | Cosmos DB | Detector'lar |
| L5 Çıktı | Ses ipuçları, doğrulanmış cümleler, ses klipleri, overlay JSON | JSON (`cue.schema.json`) + MP3/Opus klip | Web PubSub, Cosmos (günlük), Blob (klip önbelleği) | Director, workflow, TTS |

**Cosmos DB konteynerleri** (partition key parantez içinde):

- `insights` (`/match_id`): her Insight ve onu anlatan cümleler. "Bu cümle hangi veriye dayanıyordu?" sorusunun kaydı.
- `narrations` (`/match_id`): dil, mod, ses, verifier sonucu, gecikme. Eval ve denetim için.
- `profiles` (`/user_id`): dil, mod, favori takım ve oyuncu, katman tercihleri. Anonim cihaz kimliğiyle; kişisel veri tutulmaz.

**Analiz:** Eval ve geliştirme sırasında Parquet dosyaları DuckDB ile doğrudan SQL'le sorgulanır. Ayrı bir veri ambarı kurulmaz.

## Agent akışı

Narrator'ın yazdığı her cümle deterministik Verifier'dan geçer; iki kez reddedilen Insight şablon cümleyle anlatılır. Localizer'ın çıktısı da yayına çıkmadan önce aynı kontrollerden geçer.

## Agent'lar ve Director

Dört agent dil gerektiren işleri yapar; Director ise agent değil, deterministik bir politika motorudur. Bu ayrım bilinçli bir karardır: gecikmeye duyarlı kararlar kodda, dil gerektiren kararlar agent'larda.

| Bileşen | Tür | Girdi | Çıktı | Araçlar | Hata olursa |
| --- | --- | --- | --- | --- | --- |
| Narrator | LLM agent | `claim_facts`, Insight tipi, mod (gözü kapalı / taraftar / analist) | Yapılandırılmış JSON: `text` + `used_facts` | Yok | Verifier reddederse gerekçeyle tekrar yazar |
| Verifier | Deterministik kod | Narrator çıktısı + `claim_facts` | Geçti / kaldı + gerekçe | Yok | En fazla 2 yeniden deneme; sonra şablon cümleye düşer |
| Localizer | LLM agent | Doğrulanmış İngilizce cümle, hedef dil, futbol sözlüğü | Hedef dilde cümle | Yok | Çıktı Verifier'dan tekrar geçer; kalırsa şablonun çevirisi kullanılır |
| Recap | LLM agent | "Dakika X'ten beri neyi kaçırdım?" | 3 cümlelik özet + kullanılan Insight id'leri | MCP: `get_insights`, `get_state`, `query_events`, `get_player` | Her sayı Verifier'dan geçer; araç hatasında "şu an özet hazırlanamıyor" der |
| Director | Deterministik kod | Insight kuyruğu + anlık durum | Konuşma izni ve sırası | — | Anlatım gelmezse sessiz kalır; ses yolu etkilenmez |

**Verifier'ın kontrolleri:** cümledeki her sayı ve oyuncu adı `claim_facts` içinde var mı; cümle mod için izin verilen uzunlukta mı; tıbbi ya da kesin nedensellik iddiası var mı (örneğin "yorgunluk yüzünden"). Amaç halisünasyonu yapısal olarak engellemek.

**Director kuralları** (değerler başlangıç parametresidir; 6. günde dinleme testiyle ayarlanır):

- Yalnızca top oyun dışındayken ya da tehlike 0,15'in altındayken konuşur. Tehlike yükselirse cümle beklemeye alınır.
- Gol gibi öncelik 5 olaylar, top zaten durduğu için hemen anlatılır.
- `expires_at` geçen Insight sessizce atılır; bayat bilgi söylenmez.
- Aynı tip ve takım için 5 dakika içinde ikinci anlatım yapılmaz.
- Sessizlik bütçesi: gözü kapalı modda 5 dakikalık pencerede konuşma süresinin üst sınırı var; taraftar modunda yalnızca öncelik 3 ve üstü anlatılır.

**Workflow:** Microsoft Agent Framework'te sıralı bir workflow; Verifier'dan Narrator'a koşullu geri dönüş kenarı ve şablon cümleye düşen bir yedek executor. Dil ve mod kombinasyonları paralel çalışır. Her adım Foundry tracing'e iz bırakır.

## Frontend

Dinleyici uygulaması TypeScript + Vite ile yazılan, ağır bir framework kullanmayan tek sayfalık bir web uygulamasıdır. Ses motoru imperatif bir yapı olduğu için React'in getirdiği soyutlama burada fayda sağlamaz; prototip sayfası doğrudan bu uygulamanın çekirdeği olur.

**Modüller:**

- `StreamClient`: Web PubSub bağlantısı, otomatik yeniden bağlanma, maç grubuna katılma. Paketleri 300 ms'lik jitter buffer'a yazar ve sunucu saatine göre senkronize eder.
- `Scheduler`: 25 ms'de bir çalışır, önündeki 120 ms'yi planlar. Prototipteki `schedule()` fonksiyonunun canlı veri sürümü.
- `AudioEngine`: Web Audio grafiği. Top, baskı, tribün, olay ve favori oyuncu katmanları, kompresör, ducking bus'ı ve konuşma klibi oynatıcısı.
- `Profile`: dil, mod, favori takım/oyuncu ve katman tercihleri. Cihazda saklanır, çevrim içiyken Cosmos'a eşlenir.
- `Views`: altyazı, saha görünümü (isteğe bağlı), analist zaman çizelgesi, ayarlar.

**Modlar:**

| Mod | Kim için | Ses | Anlatım | Ekran |
| --- | --- | --- | --- | --- |
| Gözü kapalı | Görme engelli taraftar, sürüş | Tüm katmanlar | Sık, betimleyici | Gerekmez |
| Taraftar | Ekrana arada bakan izleyici | Top + olay sesleri | Yalnızca önemli anlar | Altyazı + skor |
| Analist | Veri meraklası | İsteğe bağlı | Sayılarla | Insight zaman çizelgesi, tıklayınca kanıt event'leri |
| Az gören | Kalan görüşünü kullanan dinleyici | Tüm katmanlar | Betimleyici | Büyük, yüksek kontrastlı tek satır |

**Erişilebilirlik (zorunlu):**

- Tüm işlevler klavyeyle kullanılabilir (Boşluk: oynat/duraklat, oklar: ileri/geri sar, rakam tuşları: katmanları aç/kapat).
- Altyazı `aria-live` bölgesindedir. Ekran okuyucu kullananlar için bir seçenek: anlatımı TTS yerine ekran okuyucuya yönlendirmek; böylece iki ses üst üste binmez.
- Hiçbir bilgi yalnızca renkle ya da yalnızca ekranla verilmez. WCAG 2.2 AA hedeflenir.
- Tarayıcılar kullanıcı etkileşimi olmadan ses çalmaz; uygulama "Dinlemeye başla" butonuyla açılır.
- Ekran kilitliyken çalmaya devam etmek için Media Session API kullanılır. Mobil Safari'de bu davranışı test etmek gerekiyor; bkz. Riskler.

## Mesaj sözleşmeleri ve API

Canlı veri tek bir WebSocket kanalından, diğer her şey küçük bir REST API'den geçer. Her maçın bir Web PubSub grubu vardır (`match.<id>`); anlatım, dil ve mod başına alt gruplara gider (`match.<id>.tr.eyesfree`). Böylece her dinleyici yalnızca kendi dilindeki ve modundaki klipleri alır.

**WebSocket mesaj tipleri:**

| Tip | Sıklık | Alanlar | Kime |
| --- | --- | --- | --- |
| `state` | Saniyede 10 | `t`, `x`, `y`, `team`, `in_play`, `danger`, `pressure`, `pan`, `tempo` (\~80 bayt) | Maç grubundaki herkes |
| `event_cue` | Olay başına | `t`, `sound` (pass, shot, save, goal, whistle), `pan`, `team`, `player_id` | Maç grubundaki herkes |
| `speech` | Anlatım başına | `t`, `insight_id`, `priority`, `evidence`, `text`, `source` (`llm` doğrulanmış / `template`), `audio` (base64 MP3 veya `null`), `duration_s` (hackathon sürümünde iki dil de tek mesajda: alanlar `{en, tr}` sözlüğü; `lang`/`mode` alt grupları üretim yolu) | Dil ve mod alt grubu |
| `insight` | Insight başına | `insight.schema.json` nesnesi | Analist alt grubu |
| `control` | Nadiren | `kind` (kickoff, halftime, end, resync) | Maç grubundaki herkes |

Ses klibi hackathon sürümünde mesajın içinde base64 olarak gider: 5 saniyelik bir klip 30–50 KB tutar ve ayrı bir indirme isteğini ortadan kaldırır. Ölçek gerektiğinde bu alan Blob'daki klibin URL'siyle değiştirilir.

**REST uçları (FastAPI, `api` servisi):**

| Uç | Ne yapar |
| --- | --- |
| `POST /negotiate` | Dinleyiciye Web PubSub bağlantı adresi ve grup izinleri verir |
| `GET /matches`, `GET /matches/{id}` | Yayındaki ve arşivdeki maçlar, kadro bilgisi |
| `POST /matches/{id}/replay` | Demo için maçı belirli bir hızda yayınlamaya başlatır |
| `POST /recap` | `match_id`, `since_minute`, `lang`, `mode` alır; doğrulanmış özet metni ve ses klibi döner |
| `GET /insights/{match_id}` | Analist zaman çizelgesi ve denetim için Insight ve anlatım geçmişi |
| `GET` / `PUT /profile` | Dinleyici tercihleri |
| `/mcp` | Recap agent'ın kullandığı maç verisi MCP server'ı (streamable HTTP) |
| `GET /healthz` | Container Apps sağlık kontrolü |

## Azure dağıtımı

Tüm kaynaklar tek bir resource group'ta ve tek bir bölgede durur; altyapı `azd up` komutuyla Bicep şablonlarından kurulur. Bölge, Foundry modeli ile MAI-Voice Türkçe seslerinin birlikte bulunduğu bölgeye göre seçilir.

| Kaynak | Katman / ayar | Not |
| --- | --- | --- |
| Microsoft Foundry projesi + model deployment | Küçük, hızlı bir sohbet modeli; eval için aynı model yargıç olarak | Narrator, Localizer, Recap ve Foundry Evaluations |
| Azure AI Speech | S0 | Neural ve MAI-Voice sesleri; SSML ile stil |
| Container Apps ortamı | Consumption | `engine` (demo sırasında en az 1 replika), `api` (sıfıra ölçeklenir) |
| Container Registry | Basic | `azd` imajları buraya iter |
| Event Hubs | Basic, 1 throughput unit | Tek hub: `match-events` |
| Web PubSub | Geliştirmede Free, jüri döneminde Standard 1 unit | Free katman 20 eşzamanlı bağlantı ve günde 20.000 mesajla sınırlı; tek dinleyiciye 90 dakikalık maç bile bu sınırı aşar |
| Cosmos DB | NoSQL, serverless | `insights`, `narrations`, `profiles` |
| Storage account | Standard LRS | Maçlar, kalibrasyon, ses önbelleği |
| Static Web Apps | Free | Dinleyici uygulaması |
| Application Insights + Log Analytics | Pay-as-you-go, düşük saklama süresi | OpenTelemetry ile tüm servisler |
| Key Vault | Standard | Yalnızca managed identity ile erişilemeyen gizli bilgiler için |

**Mesaj bütçesi:** Durum paketleri 200 ms'lik gruplar halinde gönderilir (mesaj başına 2 paket). Bu, Web PubSub mesaj sayısını yarıya indirir; ek 200 ms, 300 ms'lik jitter buffer'ın içinde kalır.

**Kimlik ve gizli bilgiler:** Container Apps tek bir user-assigned managed identity kullanır. Bu kimliğe yalnızca gereken roller verilir: Foundry ve Speech için Cognitive Services / Azure AI User, Event Hubs Data Sender ve Receiver, Web PubSub Service Owner, Cosmos DB Data Contributor, Storage Blob Data Contributor. Kodda anahtar tutulmaz.

**Ortamlar ve soyutlamalar:** Her Azure servisi kodda bir arayüzün arkasındadır ve lokalde bir eşdeğeri vardır:

| Arayüz | Lokal | Azure |
| --- | --- | --- |
| `EventSource` | Dosyadan replay | Event Hubs |
| `Broadcaster` | Lokal WebSocket sunucusu | Web PubSub |
| `Store` | JSON dosyaları | Cosmos DB |
| `BlobStore` | Yerel klasör | Blob Storage |
| `Speech` | eSpeak NG (çevrimdışı) | Azure AI Speech |

**CI/CD (GitHub Actions):**

1. Her push'ta: lint, `pytest`, şema doğrulaması, istemci derlemesi.
2. `main` dalına merge'de: imajları derleyip ACR'ye itme, `azd deploy`.
3. Elle tetiklenen eval işi: 10 seed üzerinde detector ve anlatım eval'ı, sonucu README'ye ve Foundry'ye yazım.

Geliştirme sürecinde GitHub Copilot agent mode ve Azure MCP Server kullanılır; README'de ayrı bir bölümle belgelenir.

## Gözlemlenebilirlik ve değerlendirme

Gizli senaryolar sayesinde sistemin "doğru şeyi, doğru anda" söyleyip söylemediği gerçek bir cevap anahtarına karşı ölçülebilir. Bu tablo README'nin en üstüne taşınır; jürinin "AI gerçekten bir şey yapıyor mu?" sorusunun cevabıdır. Hedefler tasarım hedefidir, ölçülen değerler 2., 3. ve 5. günlerde eklenir.

| Metrik | Neyi ölçer | Nasıl | Hedef |
| --- | --- | --- | --- |
| Senaryo recall | Gizli senaryoların kaçı bulundu | Detector çıktısı vs `truth.json`, 10 seed | ≥ 0,8 |
| Senaryo precision | Bulunan değişimlerin kaçı gerçek | Aynı karşılaştırma | ≥ 0,8 |
| Tespit gecikmesi | Senaryo başlangıcı ile Insight arası | Maç zamanı cinsinden medyan | < 2 dk |
| Doğrulanmamış yayın | Verifier'dan geçmeden yayınlanan cümle | `narrations` günlüğü | 0 |
| İlk denemede geçme oranı | Narrator'ın ilk taslakta doğru yazması | Verifier sonuçları | ≥ %90 |
| Groundedness | Cümlenin olgulara dayanması | Foundry Evaluations (LLM yargıç) | Ortalama ≥ 4 / 5 |
| Akıcılık ve tutarlılık | TR ve EN dil kalitesi | Foundry Evaluations + 20 cümlelik elle kontrol | Ortalama ≥ 4 / 5 |
| Konuşma çakışması | Tehlike zirvesinde konuşma | Director günlüğü, tehlike > 0,5 anında konuşma | %0 |
| Gecikme | Hızlı ve yavaş yol, p50 / p95 | OpenTelemetry span'leri, Application Insights | İki hızlı yol bütçesi |
| Gözü kapalı dinleme testi | Topun hangi takımda, hangi kanatta olduğu ve tehlike artışı anlaşılıyor mu | 5+ kişi, 3 soru, 3 dakikalık klip | Her soruda ≥ %70 doğru |
| Maç başına maliyet | Token ve TTS karakter sayısı | Servis metrikleri | Raporlanır |

**Araçlar:** Tüm servisler OpenTelemetry ile Application Insights'a yazar; her durum paketi, Insight ve anlatım aynı `match_id` ve `insight_id` ile izlenebilir. Agent adımları Foundry tracing'de görünür. Eval scriptleri `eval/` klasöründedir ve CI'dan tetiklenebilir.

## Güvenlik, sorumlu AI ve maliyet

**Güvenlik:**

- Kimlik doğrulama managed identity ve RBAC ile yapılır; hiçbir anahtar kodda, repoda ya da tarayıcıda bulunmaz.
- Tarayıcı, Web PubSub'a yalnızca `api`'nin verdiği kısa ömürlü ve grup izinleri sınırlı token'la bağlanır. Dinleyici mesaj gönderemez, yalnızca alır.
- Replay ve yönetim uçları demo anahtarıyla korunur; jüri için test talimatında verilir.
- Kişisel veri tutulmaz: profil anonim cihaz kimliğine bağlıdır.

**Sorumlu AI:**

- LLM'e yalnızca `claim_facts` gider; kullanıcı serbest metni sadece Recap'te vardır ve Recap'in tüm sayıları Verifier'dan geçer.
- Foundry content safety filtreleri açıktır.
- Anlatım korelasyon diliyle konuşur, tıbbi ya da kesin nedensellik iddiası kurmaz ("sprint hızı düştü", "yorulduğu için kaybetti" değil).
- Erişilebilirlik iddiası abartılmaz: görme engelli kullanıcılarla test yapılmadıysa README ve videoda "doğrulandı" denmez.
- Takımlar ve oyuncular kurgusaldır; gerçek kulüp, oyuncu ya da Premier League markası kullanılmaz.
- Kalibrasyon verisinin kaynağı (StatsBomb, SkillCorner) README'de belirtilir; ham veri yeniden dağıtılmaz.

**Maliyet kontrolü:**

- `api` sıfıra ölçeklenir; `engine` yalnızca demo ve jüri döneminde çalışır.
- Aynı cümle bir kez sentezlenir: TTS önbelleği `hash(metin, ses, stil)` anahtarıyla Blob'da tutulur.
- Küçük model kullanılır; prompt'lar kısa tutulur, çünkü girdi yalnızca birkaç olgudur.
- Web PubSub geliştirmede Free, yalnızca jüri döneminde Standard.
- Kesin fiyatlar Azure fiyat sayfalarından ya da Pricing Calculator'dan kontrol edilir; bu doküman fiyat tahmini vermez.

## Riskler ve yedek planlar

En büyük risk teknik değil: bulut bütçesinin jüri dönemi bitmeden (10 Kasım) tükenmesi. Her risk için hazır bir yedek plan var.

| Risk | Etkisi | Önlem | Yedek plan |
| --- | --- | --- | --- |
| Bulut bütçesi jüri dönemi bitmeden tükenir | Canlı demo kapanır | Harcamayı izle, kaynakları sıfıra ölçekle | Demo videosu ve lokal çalıştırma talimatı her zaman hazır |
| Model ya da MAI-Voice sesleri seçilen bölgede yok, kota verilmiyor | Anlatım katmanı gecikir | Bölgeyi bugün test ederek seç | Emel ve Ahmet neural sesleri; başka bir küçük model |
| Foundry hosted agent dağıtımı zaman alır | 3. gün kayar | Varsayılan: workflow `engine` içinde, modeller Foundry'de | Hosted agent'ı ancak 5. günde vakit kalırsa dene |
| Mobil Safari arka planda Web Audio'yu durdurur | Telefonda ekran kilitlenince ses kesilir | 4. günde gerçek cihazda test | Demo masaüstünde; sınırlamayı README'de belirt |
| LLM gecikmesi ani artar | Anlatım geç kalır | Director süresi geçen Insight'ı atar | Deterministik şablon cümleler |
| Detector'lar bazı senaryoları kaçırır | Eval tablosu zayıf görünür | Eşikleri seed'lerde ayarla | Sonuçları dürüstçe raporla; zayıf senaryoyu ve nedenini README'de açıkla |
| Gerçek maç akışında sesler kakofoniye döner | UX puanı düşer | Katman sayısı sınırlı, sert miks | Mod başına katman azalt |
| Tek kişi: hastalık ya da kayıp gün | Teslim tehlikeye girer | 3. günün sonunda teslim edilebilir MVP | Kesme listesi: Recap → analist modu → ikinci dil → kullanıcı testi |
| Jüri projeyi test etmeden yalnızca videoyu izler | Yalnızca video puanlanır | Video 7. günün ilk işi; altyazılı, sessiz izlendiğinde de anlaşılır | — |
| Üçüncü taraf verisi kullanımı sorgulanır | Uygunluk sorusu | Yalnızca toplu istatistik, ham veri yok, kaynak gösterimi | Gerekirse kural karşısında yazılı açıklama iste |

## Yol haritası

22 Ekim akşamı teslim edilebilir bir MVP olur; sonraki günlerde gecikme olursa Riskler bölümündeki kesme listesi uygulanır. Demo, jüri dönemi bitene kadar (10 Kasım) çalışır durumda kalmalı.

## Repo yapısı

Tek bir monorepo; Python servisleri ortak `htg` paketini kullanır.

```
hear-the-game/
├── schemas/              event, insight, cue JSON şemaları
├── htg/                  ortak Python paketi
│   ├── pitch.py          saha geometrisi
│   ├── calibrate.py      gerçek veriden kalibrasyon
│   ├── generate.py       sentetik maç üretici
│   ├── validate.py       sentetik vs gerçek doğrulama
│   ├── replay.py         maçı gerçek zamanlı yayınlama
│   ├── engine/           state, detector'lar, Director
│   ├── narration/        Agent Framework workflow, Verifier, şablonlar
│   ├── speech/           Azure AI Speech, SSML, önbellek
│   └── adapters/         EventSource, Broadcaster, Store, BlobStore (lokal + Azure)
├── services/
│   ├── engine/           Container App giriş noktası + Dockerfile
│   └── api/              FastAPI + MCP server + Recap agent + Dockerfile
├── web/                  TypeScript + Vite dinleyici uygulaması
├── eval/                 senaryo, anlatım ve gecikme eval scriptleri
├── infra/                Bicep şablonları + azure.yaml (azd)
├── data/
│   ├── calibration/      toplu istatistikler
│   └── synthetic/        üretilmiş maçlar + doğrulama raporu
├── prototype/            0. gün ses prototipi
├── tests/                8 test
└── .github/workflows/    CI ve deploy
```

## Kaynaklar

- [Inside the Game Hackathon resmi kuralları](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md)
- [Agents in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/agents/overview)
- [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/overview/)
- [Agents in Workflows (Agent Framework)](https://learn.microsoft.com/agent-framework/workflows/agents-in-workflows)
- [Evaluation in Microsoft Foundry](https://learn.microsoft.com/azure/foundry/concepts/evaluation-overview)
- [Azure Speech dil ve ses desteği](https://learn.microsoft.com/azure/ai-services/speech-service/language-support#text-to-speech-voices)
- [MAI-Voice in Azure Speech](https://learn.microsoft.com/azure/ai-services/speech-service/mai-voices)
- [Azure Web PubSub limitleri](https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#azure-web-pubsub-limits)
- [Azure MCP Server](https://learn.microsoft.com/azure/developer/azure-mcp-server/overview)
- [StatsBomb Open Data](https://github.com/hudl/open-data)
- [SkillCorner Open Data](https://github.com/SkillCorner/opendata)
