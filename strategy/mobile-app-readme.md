# Master Agent — Phone App (Flutter)

A simple Flutter app that sends commands to the Master Agent bridge and displays results. Works on Android and iOS.

## Setup

1. Make sure the bridge is running on the computer:
   ```bash
   python3 operations/phone-bridge.py --port 8765 --host 0.0.0.0
   ```

2. Configure the bridge URL in `lib/main.dart`:
   ```dart
   final _bridgeUrl = 'http://10.0.2.2:8765'; // Android emulator
   // For real phone: 'http://<computer-ip>:8765'
   ```

3. Run the app:
   ```bash
   flutter pub get
   flutter run
   ```

4. Build for phone:
   ```bash
   flutter build apk    # Android
   flutter build ipA    # iOS
   ```

## Features

- Send commands in natural language (Turkish or English)
- See results in a chat interface
- Quick suggestion chips for common commands
- Works on both phone and tablet

## Commands

Try these from the phone:

- `gelen mailleimi kontrol et` — Check emails
- `bugünkü randevularıma bak` — Check today's appointments
- `sunum dosyası hazırla` — Prepare a presentation
- `bu alanda şirketler bul` — Find companies to sell to
- `muhasebe evraklarını kontrol et` — Check accounting documents
- `aylık döküm hazırla` — Prepare monthly statement
- `fiyat isteyenlere fiyat ver` — Give prices to requesters
- `teklif al` — Receive offers

## Network

- The app connects to the bridge via HTTP
- Make sure the computer and phone are on the same network (or use port forwarding)
- For remote access, put the bridge behind a VPN or tunnel
