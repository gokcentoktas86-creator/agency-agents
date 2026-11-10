# Daily Operations — Master Agent System

## Scenario

A business operator runs their entire company from their phone. The Master Agent system coordinates daily work across all departments — emails, pricing, offers, accounting, sales prospecting, appointments, and presentations — learning from every task so the next one runs faster.

## Mode

NEXUS-Full

## Duration

Continuous (heartbeat)

## Summary

One command in, everything done. The Master Agent routes phone commands to the right sub-agent, executes on the computer, and returns results. Skills improve with every task, department records grow, and memory makes the next job faster.

## The System

### Master Agent (👑)

The central coordinator. Receives commands from phone (Telegram/WhatsApp/Flutter) or computer, routes to sub-agents, manages the skills database, department records, and daily memory.

**Phone Bridge**: `operations/phone-bridge.py` — HTTP server on the computer that receives phone commands, routes them, executes on computer, and returns results.

### Sub-Agents

| Sub-Agent | Handles | Example Command |
|---|---|---|
| Email Ops (📧) | Inbox triage, replies, prices, offers | "gelen mailleimi kontrol et" |
| Accounting Ops (📒) | Document checks, monthly statements | "muhasebe evraklarını kontrol et" |
| Sales Ops (🎯) | Company research, lead qualification | "bu alanda şirketler bul" |
| Appointment Ops (📅) | Appointment checking, scheduling | "bugünkü randevularıma bak" |
| Presentation Ops (📊) | Presentation preparation | "sunum dosyası hazırla" |

### Data Stores

| Store | Purpose | Evolves |
|---|---|---|
| `operations/skills.json` | Skills database — success counts, improvements | Yes — updated after every task |
| `operations/department-records.json` | Department activity records | Yes — appended after every task |
| `operations/memory/YYYY-MM-DD.md` | Daily memory notes | Yes — written every day |

### Phone App

`operations/mobile-app/` — Flutter app for sending commands from phone.

## Workflow

1. **Start the bridge** on the computer: `python3 operations/phone-bridge.py`
2. **Connect phone** via Telegram/WhatsApp/Flutter app
3. **Send commands** from phone — natural language, any time
4. **Master Agent routes** to the right sub-agent
5. **Sub-agent executes** on the computer
6. **Result returns** to the phone
7. **System learns** — skills, records, and memory update

## Daily Routines

- **Morning (08:00)**: Check overnight emails, flag urgent items, check today's appointments, prepare a briefing
- **Midday (12:00)**: Check for new emails, follow up on pending tasks
- **End of day (18:00)**: Summarize the day, update memory, prepare tomorrow's priorities

## Critical Rules

- Every command gets a response — even if it's "I'll handle that"
- Every task gets tracked — in skills, in department records, in memory
- Every result gets delivered — back to the phone or computer
- The system gets smarter with every interaction — that's the whole point
