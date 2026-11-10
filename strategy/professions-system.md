# Professions System — TÜM MESLEKLERE UYUMLU SİSTEM

## Overview

The Master Agent system now covers **all 764 professions** from the Turkish Wikipedia "Meslekler listesi". **152 computer-based professions** are organized into **10 profession categories**, each with its own **master agent + 5 helper agents** — the same pattern as the original Operations Division.

## Architecture

```
                    ┌─────────────────────────┐
                    │   👑 MASTER AGENT       │
                    │   (Universal Coordinator)│
                    └───────────┬─────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
   ┌────┴────┐            ┌────┴────┐            ┌────┴────┐
   │ 📧 Email │            │💰 Finance│           │⚖️ Legal │
   │ 💰 Acct │            │⚕️ Health│           │📚 Edu    │
   │ 🎯 Sales│            │🎬 Media │           │🏢 Bus    │
   │ 📅 Appt │            │🔧 Eng    │           │🔬 Res    │
   │ 📊 Pres │            │🎨 Design│           │💻 IT     │
   └─────────┘            └─────────┘            └─────────┘
        │                       │                       │
   5 helper agents        5 helper agents        5 helper agents
```

## 10 Profession Categories

| # | Category | Master Agent | Color | Professions | Covers |
|---|---|---|---|---|---|
| 1 | IT & Software | 💻 IT Master | cyan | 14 | Bilgisayar mühendisi, Bilgisayar programcısı, Yazılım mühendisi, Ağ yöneticisi, Veritabanı yöneticisi |
| 2 | Finance & Accounting | 💰 Finance Master | green | 30 | Muhasebeci, Ekonomist, Vergi denetmeni, Bankacı, Fon yöneticisi, Sigortacı |
| 3 | Healthcare & Medical | ⚕️ Healthcare Master | red | 40 | Doktor, Aile hekimi, Eczacı, Radyolog, Laborant, Hemşire, Diyetisyen |
| 4 | Legal & Justice | ⚖️ Legal Master | purple | 15 | Avukat, Hakim, Savcı, Adli tabip, Dedektif, Müfettiş |
| 5 | Education & Training | 📚 Education Master | blue | 19 | Öğretmen, Eğitmen, Akademisyen, Profesör, Danışman, Çevirmen |
| 6 | Media & Creative | 🎬 Media Master | orange | 37 | Gazeteci, Yazar, Editör, Video editörü, Reklamcı, Spiker |
| 7 | Business & Management | 🏢 Business Master | indigo | 32 | Menajer, Müdür, Yönetici, HR uzmanı, Danışman, Satış elemanı |
| 8 | Engineering & Technical | 🔧 Engineering Master | teal | 56 | Mühendis, Elektrik mühendisi, Makine mühendisi, Kimya mühendisi, Jeolog |
| 9 | Research & Science | 🔬 Research Master | violet | 35 | Akademisyen, Bilim insanı, Araştırmacı, Kimyager, Biyolog, İstatistikçi |
| 10 | Design & Architecture | 🎨 Design Master | pink | 17 | Tasarımcı, Mimar, İç mimar, Şehir plancısı, Grafik tasarımcı, Animator |

**Total: 152 computer-based professions** across 10 categories.

## Routing Flow

When a command arrives from phone or computer:

1. **Master Agent** receives the command
2. **Identifies the profession** from the command keywords
3. **Routes to the category master agent** (e.g., IT Master, Finance Master)
4. **Category master spins up 5 helper agents** based on the task
5. **Helper agents execute** the work on the computer
6. **Results return** to the user (phone or computer)
7. **Skills, department records, and memory** are updated

## Example Routing

| Command | Profession | Category | Master |
|---|---|---|---|
| "program yaz" | Bilgisayar programcısı (096) | IT & Software | 💻 IT Master |
| "fatura hazırla" | Muhasebeci (484) | Finance & Accounting | 💰 Finance Master |
| "doktor randevusu" | Doktor (188) | Healthcare & Medical | ⚕️ Healthcare Master |
| "avukat danış" | Avukat (055) | Legal & Justice | ⚖️ Legal Master |
| "ders planı yap" | Öğretmen (509) | Education & Training | 📚 Education Master |
| "haber yaz" | Gazeteci (248) | Media & Creative | 🎬 Media Master |
| "iş planı oluştur" | Menajer (467) | Business & Management | 🏢 Business Master |
| "elektrik mühendisliği" | Mühendis (485) | Engineering & Technical | 🔧 Engineering Master |
| "araştırma yap" | Akademisyen (009) | Research & Science | 🔬 Research Master |
| "logo tasarla" | Tasarımcı (665) | Design & Architecture | 🎨 Design Master |

## Data Stores

### professions.json
The complete database — 764 professions, 10 categories. Each category has:
- `label`: Category name (Turkish)
- `master_pattern`: How the master agent handles tasks
- `helpers`: 5 helper agents with role, handles, and examples
- `professions`: List of {id, name, tasks}

### skills.json
20 skills total: 10 operational + 10 profession routing skills.

### department-records.json
20 departments: 10 operational + 10 profession categories.

## Bridge Integration

The phone bridge (`operations/phone-bridge.py`) routes commands to profession categories:

- **7 operational routes** (email, pricing, offer, accounting, sales, appointment, presentation)
- **10 profession routes** (profession-it, profession-finance, profession-healthcare, etc.)

**Total: 17 routes** — all tested and working.

## How to Extend

To add a new profession to a category:

1. Add the profession to `operations/professions.json` under the right category
2. Add keywords to the bridge's ROUTES dict for the category
3. The routing system picks it up automatically

To create a new category:

1. Add the category to `operations/professions.json`
2. Create a master agent file (e.g., `operations-{category}-master-agent.md`)
3. Add a route to the bridge's ROUTES dict
4. Add the skill to `skills.json`
5. Add the department to `department-records.json`
