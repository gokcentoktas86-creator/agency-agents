import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

void main() {
  runApp(const MasterAgentApp());
}

class MasterAgentApp extends StatelessWidget {
  const MasterAgentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Master Agent',
      theme: ThemeData(
        primarySwatch: Colors.amber,
        scaffoldBackgroundColor: const Color(0xFF1a1a2e),
      ),
      home: const MasterAgentScreen(),
    );
  }
}

class MasterAgentScreen extends StatefulWidget {
  const MasterAgentScreen({super.key});

  @override
  State<MasterAgentScreen> createState() => _MasterAgentScreenState();
}

class _MasterAgentScreenState extends State<MasterAgentScreen> {
  final _commandController = TextEditingController();
  final _messages = <Map<String, dynamic>>[];
  final _bridgeUrl = 'http://10.0.2.2:8765'; // Android emulator → host computer
  bool _loading = false;

  @override
  void dispose() {
    _commandController.dispose();
    super.dispose();
  }

  void _addMessage(String role, String text, {Map<String, dynamic>? data}) {
    setState(() {
      _messages.add({
        'role': role,
        'text': text,
        'data': data,
        'time': DateTime.now().toString().substring(11, 16),
      });
    });
  }

  Future<void> _sendCommand() async {
    final command = _commandController.text.trim();
    if (command.isEmpty || _loading) return;

    _commandController.clear();
    _addMessage('user', command);
    setState(() => _loading = true);

    try {
      final response = await http.post(
        Uri.parse('$_bridgeUrl/command'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'command': command, 'channel': 'phone'}),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        _addMessage('agent', data['message'] ?? 'Command executed', data: data);
      } else {
        _addMessage('agent', 'Error: ${response.statusCode}');
      }
    } catch (e) {
      _addMessage('agent', 'Connection failed: $e\n\nMake sure the bridge is running on the computer.');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('👑 Master Agent', style: TextStyle(color: Colors.white)),
        backgroundColor: const Color(0xFF1a1a2e),
        elevation: 0,
      ),
      body: Column(
        children: [
          // Header bar
          Container(
            color: const Color(0xFF16213e),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                const Icon(Icons.phone_android, color: Colors.amber, size: 20),
                const SizedBox(width: 8),
                const Text('Phone → Computer Bridge', style: TextStyle(color: Colors.white70, fontSize: 13)),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(0xFF0f3460),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Text('Phone Mode', style: TextStyle(color: Colors.amber, fontSize: 11)),
                ),
              ],
            ),
          ),

          // Messages
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final msg = _messages[index];
                final isUser = msg['role'] == 'user';
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Flexible(
                        child: Container(
                          constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.82),
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                          decoration: BoxDecoration(
                            color: isUser ? const Color(0xFF0f3460) : const Color(0xFF16213e),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  if (!isUser) const Icon(Icons.star, size: 14, color: Colors.amber),
                                  const SizedBox(width: 4),
                                  Text(
                                    msg['time'] as String,
                                    style: const TextStyle(color: Colors.white54, fontSize: 10),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Text(
                                msg['text'] as String,
                                style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 14,
                                  height: 1.4,
                                ),
                              ),
                              if (msg['data'] != null) ...[
                                const SizedBox(height: 6),
                                Container(
                                  padding: const EdgeInsets.all(8),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF0d1b2a),
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(color: const Color(0xFF0f3460)),
                                  ),
                                  child: Text(
                                    jsonEncode(msg['data']),
                                    style: const TextStyle(
                                      fontFamily: 'monospace',
                                      fontSize: 11,
                                      color: Colors.amber,
                                    ),
                                  ),
                                ),
                              ]
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),

          // Suggested commands
          if (_messages.length < 3)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, bottom: 4),
              child: Wrap(
                spacing: 6,
                children: [
                  _suggestionChip('📧 Check emails', 'gelen mailleimi kontrol et'),
                  _suggestionChip('📅 Today\'s appointments', 'bugünkü randevularıma bak'),
                  _suggestionChip('📊 Presentation', 'sunum dosyası hazırla'),
                  _suggestionChip('🎯 Find companies', 'bu alanda şirketler bul'),
                  _suggestionChip('📒 Accounting', 'muhasebe evraklarını kontrol et'),
                ],
              ),
            ),

          // Input
          Container(
            padding: const EdgeInsets.all(12),
            color: const Color(0xFF16213e),
            child: SafeArea(
              top: false,
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _commandController,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _sendCommand(),
                      style: const TextStyle(color: Colors.white),
                      decoration: InputDecoration(
                        hintText: 'Send a command...',
                        hintStyle: const TextStyle(color: Colors.white54),
                        filled: true,
                        fillColor: const Color(0xFF0d1b2a),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(20),
                          borderSide: BorderSide.none,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  GestureDetector(
                    onTap: _loading ? null : _sendCommand,
                    child: Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: _loading ? const Color(0xFF333) : const Color(0xFFb8860b),
                        borderRadius: BorderRadius.circular(22),
                      ),
                      child: _loading
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.send, color: Colors.white),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _suggestionChip(String label, String command) {
    return GestureDetector(
      onTap: () {
        _commandController.text = command;
        _sendCommand();
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: const Color(0xFF0f3460),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Text(label, style: const TextStyle(color: Colors.amber, fontSize: 12)),
      ),
    );
  }
}
