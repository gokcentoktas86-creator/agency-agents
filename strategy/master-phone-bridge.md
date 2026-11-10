# Phone Bridge — Master Agent System

The phone bridge is the connection point between the user's phone and the computer where the agents run. It receives commands from the phone, routes them to the right sub-agent, executes on the computer, and returns results — then updates the skills database, department records, and memory.

## How It Works

```
┌─────────┐      HTTP      ┌──────────────────┐      route     ┌──────────┐
│  Phone   │ ────────────── │  Phone Bridge    │ ───────────── │ Sub-Agent│
│ Telegram │   POST /cmd    │  (computer, py)  │               │ (ops)    │
│ WhatsApp │ ◄────────────── │  port 8765       │               │          │
│ Flutter  │    Result JSON │                  │               │          │
└─────────┘                 └──────────────────┘               └──────────┘
                                        │
                                        ▼
                             ┌──────────────────┐
                             │  skills.json     │ ← updated after each task
                             │  department-     │
                             │  records.json    │
                             │  memory/*.md     │
                             └──────────────────┘
```

## Quick Start

```bash
# Start the bridge on the computer
python3 operations/phone-bridge.py --port 8765 --host 0.0.0.0

# Access the web UI from computer
# Open http://localhost:8765/

# Send a command from phone (or any HTTP client)
curl -X POST http://<computer-ip>:8765/command \
  -H "Content-Type: application/json" \
  -d '{"command": "gelen mailleimi kontrol et", "channel": "phone"}'
```

## Phone Integration Options

### Option 1: Telegram Bot

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather)
2. Get the bot token
3. Set up a webhook pointing to `POST /telegram`
4. Send commands to the bot on your phone

```bash
# Test with curl (simulating Telegram webhook)
curl -X POST http://<computer-ip>:8765/telegram \
  -H "Content-Type: application/json" \
  -d '{"command": "bugünkü randevularıma bak"}'
```

### Option 2: WhatsApp

1. Use a WhatsApp business API provider
2. Configure webhook to `POST /whatsapp`
3. Send commands via WhatsApp

### Option 3: Flutter App

The Flutter app (`operations/mobile-app/`) is a simple chat interface that sends commands to the bridge.

```bash
# Build and run on phone
cd operations/mobile-app
flutter run

# Configure the bridge URL in the app
# Default: http://<computer-ip>:8765
```

## Command Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | AI chat interface (ChatGPT-style) |
| `/command` | POST | Main command entry (any client) |
| `/telegram` | POST | Telegram webhook |
| `/whatsapp` | POST | WhatsApp webhook |
| `/status` | GET | System status |
| `/skills` | GET | Skills database |
| `/departments` | GET | Department records |
| `/health` | GET | Health check |
| `/upgrade` | GET | Premium upgrade page |
| `/upgrade` | POST | Mark IP as premium |
| `/usage` | GET | Current IP usage stats |
| `/api-key` | POST | Store API key (BYOK) |

## Usage & Monetization

### Free Tier
- **1 task per IP per day** — no password, no signup
- IP-based tracking (X-Forwarded-For, X-Real-IP, or client IP)
- After free tier is exhausted, the system shows a Premium upgrade prompt

### Premium Tier
- **Unlimited tasks** — ₺99/month
- Priority processing
- All profession categories
- Activated via `POST /upgrade` (marks IP as premium in usage.json)

### BYOK (Bring Your Own Key)
- Users can store their own AI API keys via `POST /api-key`
- The system uses the user's key for AI processing
- No system-level AI API key needed — zero AI cost for the operator

### Usage Tracking
- `operations/data/usage.json` — tracks tasks per IP per day
- Each entry: tasks count, first/last task time, command, result summary
- Premium IPs are stored separately in `premium_ips` list

### AI Interface
The web UI at `/` is a ChatGPT-style chat interface:
- Dark theme with gold accents
- Message bubbles (user right/gold, bot left/dark)
- Suggestion chips for quick commands
- Live usage badge in header
- Upgrade prompt when free tier is exceeded

## Command Routing

The bridge routes commands by keywords (Turkish + English):

| Keywords | Sub-Agent | Example |
|---|---|---|
| mail, e-posta, gelen, cevapla | Email Ops | "gelen mailleimi kontrol et" |
| fiyat, price, quote | Email Ops (pricing) | "fiyat isteyenlere fiyat ver" |
| teklif, offer | Email Ops (offers) | "teklif al" |
| muhasebe, belge, döküm | Accounting Ops | "muhasebe evraklarını kontrol et" |
| şirket, araştırma, potansiyel | Sales Ops | "bu alanda şirketler bul" |
| randevu, takvim, görüşme | Appointment Ops | "bugünkü randevularıma bak" |
| sunum, presentation, deck | Presentation Ops | "sunum dosyası hazırla" |

### Profession Routing

The bridge also routes commands to profession categories based on the Turkish Wikipedia "Meslekler listesi" (764 professions, 10 categories):

| Keywords | Profession Master | Example |
|---|---|---|
| program, kod, yazılım, bilgisayar, it, sistem, veritabanı | 💻 IT Master | "program yaz" |
| muhasebe, fatura, finance, finans, vergi, banka, yatırım, borsa | 💰 Finance Master | "banka transferi" |
| doktor, sağlık, hasta, eczacı, diş, radyoloji, laboratuvar, hemşire | ⚕️ Healthcare Master | "doktor randevusu" |
| avukat, hukuk, dava, mahkeme, hakim, savcı, adli | ⚖️ Legal Master | "avukat danış" |
| öğretmen, eğitim, eğitmen, ders, mürebbiye, akademik, üniversite | 📚 Education Master | "ders planı yap" |
| gazeteci, haber, yazar, editör, medya, reklam, video | 🎬 Media Master | "haber yaz" |
| işletme, menajer, yönetici, şirket, strateji, hr, müşteri | 🏢 Business Master | "iş planı oluştur" |
| mühendis, engineering, teknik, elektrik, makine, kimya, inşaat | 🔧 Engineering Master | "elektrik mühendisliği" |
| araştırma, research, akademik, bilim, tez, yayın, istatistik | 🔬 Research Master | "araştırma yap" |
| tasarım, design, mimar, grafik, 3d, afiş, logo, ux | 🎨 Design Master | "logo tasarla" |

Each profession master agent has 5 helper agents that handle the actual work. The complete database is in `operations/professions.json`.

## Data Flow After Each Task

1. **Route** — Command matched to sub-agent
2. **Execute** — Sub-agent workflow runs on computer
3. **Track** — `skills.json` updated (success count, improvements)
4. **Record** — `department-records.json` updated (activity log)
5. **Remember** — `memory/YYYY-MM-DD.md` updated (daily note)
6. **Respond** — Result returned to phone

## Security

- The bridge binds to `0.0.0.0` for remote phone access — put it behind a firewall or VPN in production
- For production, add authentication (API key, JWT, or OAuth)
- Never expose the bridge directly to the public internet without auth
- Department records and skills are internal — don't expose `/departments` externally

## Production Considerations

- Replace data stubs (`inbox.json`, `appointments.json`, `companies.json`) with real APIs
- Connect real email (IMAP/Gmail), calendar (Google Calendar/Exchange), and CRM systems
- Add a task queue for long-running operations
- Add approval workflows for sensitive actions (sending emails, financial decisions)
- Set up heartbeat/cron for daily routines (morning briefing, etc.)
- Add logging and monitoring
