import discord
from discord.ext import commands
from flask import Flask
from threading import Thread
import requests
import base64
from nacl import encoding, public
import os
import time

# ==========================================
# ĐIỀN 4 THÔNG TIN CỦA BẠN VÀO ĐÂY LÀ XONG!
# ==========================================
GITHUB_TOKEN = 'ghp_dán_token_github_all_quyền_vào_đây'
DISCORD_BOT_TOKEN = 'dán_token_bot_discord_vào_đây'
TAILSCALE_AUTH_KEY = 'tskey-auth-dán_key_tailscale_vào_đây'
DISCORD_WEBHOOK_URL = 'dán_link_webhook_discord_vào_đây'
# ==========================================

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot đang chạy 24/7!"

def run_web():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

REPO_NAME = "AISTV-AUTO-RDP"
WORKFLOW_FILE = "rdp.yml"

# Đoạn code YAML này sẽ được Bot tự động viết vào GitHub
YAML_CONTENT = """name: 🚀 AI STV AUTO RDP
on:
  workflow_dispatch:
    inputs:
      duration:
        description: 'Thời gian'
        default: '1h'
        type: choice
        options: ['1h', '3h', '5h40m']

jobs:
  Setup:
    runs-on: windows-latest
    timeout-minutes: 340
    steps:
      - name: 🎯 KHỞI ĐỘNG
        env:
          DISCORD_WEBHOOK: ${{ secrets.DISCORD_WEBHOOK }}
        run: |
          $payload = @{ content = "📊 **LOG:** Đang khởi tạo máy chủ GitHub Actions..." } | ConvertTo-Json
          Invoke-RestMethod -Uri $env:DISCORD_WEBHOOK -Method Post -Body $payload -ContentType "application/json"
          
      - name: 🔧 CẤU HÌNH RDP & TAILSCALE
        env:
          TAILSCALE_AUTH_KEY: ${{ secrets.TAILSCALE_AUTH_KEY }}
          DISCORD_WEBHOOK: ${{ secrets.DISCORD_WEBHOOK }}
        run: |
          # Bật RDP
          Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name "fDenyTSConnections" -Value 0 -Force
          netsh advfirewall firewall add rule name="RDP" dir=in action=allow protocol=TCP localport=3389
          
          # Cài Tailscale
          $msiPath = "$env:TEMP\\ts.msi"
          Invoke-WebRequest -Uri "https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi" -OutFile $msiPath
          Start-Process msiexec.exe -ArgumentList "/i", "`"$msiPath`"", "/quiet", "/norestart" -Wait
          Start-Sleep -Seconds 10
          
          # Kết nối Tailscale bằng Auth Key
          & "$env:ProgramFiles\\Tailscale\\tailscale.exe" up --authkey=$env:TAILSCALE_AUTH_KEY --hostname=ai-stv-premium --reset
          $ip = & "$env:ProgramFiles\\Tailscale\\tailscale.exe" ip -4
          
          # Tạo User AISTV
          $pw = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 8 | % {[char]$_})
          $sp = ConvertTo-SecureString $pw -AsPlainText -Force
          New-LocalUser -Name "AISTV" -Password $sp -AccountNeverExpires
          Add-LocalGroupMember -Group "Administrators" -Member "AISTV"
          Add-LocalGroupMember -Group "Remote Desktop Users" -Member "AISTV"
          
          # Gửi log đã xong Tailscale
          $log = "✅ Đã kết nối Tailscale thành công! Đang tạo tài khoản..."
          $payload = @{ content = $log } | ConvertTo-Json
          Invoke-RestMethod -Uri $env:DISCORD_WEBHOOK -Method Post -Body $payload -ContentType "application/json"

          # Gửi Tài khoản / Mật khẩu về Discord
          $embed = @{
            content = "@here 🚀 **RDP PREMIUM ĐÃ SẴN SÀNG!**"
            embeds = @(@{
              title = "🔗 Thông tin kết nối RDP"
              color = 65280
              fields = @(
                @{ name = "🌐 Địa chỉ IP"; value = "```$ip```"; inline = $false },
                @{ name = "👤 Tài khoản"; value = "```AISTV```"; inline = $true },
                @{ name = "🔐 Mật khẩu"; value = "```$pw```"; inline = $true }
              )
              footer = @{ text = "Powered by AI STV" }
            })
          } | ConvertTo-Json -Depth 5
          Invoke-RestMethod -Uri $env:DISCORD_WEBHOOK -Method Post -Body $embed -ContentType "application/json"

      - name: ⏳ DUY TRÌ
        run: |
          $endTime = (Get-Date).AddHours(1)
          while ((Get-Date) -lt $endTime) { Start-Sleep -Seconds 60 }
"""

def github_api(method, endpoint, data=None):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    url = f"https://api.github.com{endpoint}"
    res = requests.request(method, url, headers=headers, json=data)
    return res

def create_github_secret(owner, repo, secret_name, secret_value):
    # Lấy Public Key của Repo
    key_res = github_api("GET", f"/repos/{owner}/{repo}/actions/secrets/public-key").json()
    pub_key = public.PublicKey(key_res['key'].encode(), encoding.Base64Encoder())
    sealed_box = public.SealedBox(pub_key)
    # Mã hóa giá trị Secret
    encrypted = sealed_box.encrypt(secret_value.encode())
    secret_b64 = base64.b64encode(encrypted).decode()
    
    # Tạo Secret
    github_api("PUT", f"/repos/{owner}/{repo}/actions/secrets/{secret_name}", {
        "encrypted_value": secret_b64,
        "key_id": key_res['key_id']
    })

def setup_github_repo():
    # 1. Lấy tên tài khoản GitHub
    user_info = github_api("GET", "/user").json()
    owner = user_info['login']
    
    # 2. Tạo Repo mới (Private) - Nếu đã có rồi thì bỏ qua lỗi
    github_api("POST", "/user/repos", {"name": REPO_NAME, "private": True})
    time.sleep(3) # Chờ GitHub tạo xong
    
    # 3. Tạo file Workflow (rdp.yml)
    content_b64 = base64.b64encode(YAML_CONTENT.encode()).decode()
    github_api("PUT", f"/repos/{owner}/{REPO_NAME}/contents/.github/workflows/{WORKFLOW_FILE}", {
        "message": "Auto create RDP workflow",
        "content": content_b64
    })
    
    # 4. Tự động tạo Secret TAILSCALE_AUTH_KEY và DISCORD_WEBHOOK
    create_github_secret(owner, REPO_NAME, "TAILSCALE_AUTH_KEY", TAILSCALE_AUTH_KEY)
    create_github_secret(owner, REPO_NAME, "DISCORD_WEBHOOK", DISCORD_WEBHOOK_URL)
    
    return owner

@bot.event
async def on_ready():
    print(f'Bot {bot.user} đã online và sẵn sàng!')

@bot.command()
async def rdp(ctx):
    msg = await ctx.send("🤖 Đang tự động tạo Repo GitHub và nạp Code RDP...")
    
    try:
        owner = setup_github_repo()
        await msg.edit(content="✅ Đã thiết lập xong Repo & Tailscale! Đang gửi lệnh chạy RDP...")
        
        # Tự động bấm Run Workflow
        payload = {"ref": "main", "inputs": {"duration": "1h"}}
        res = github_api("POST", f"/repos/{owner}/{REPO_NAME}/actions/workflows/{WORKFLOW_FILE}/dispatches", payload)
        
        if res.status_code == 204:
            await msg.edit(content="🚀 Lệnh đã được gửi! GitHub đang chạy. Hãy đợi vài phút để nhận IP, Tài khoản và Mật khẩu về kênh này.")
        else:
            await msg.edit(content=f"❌ Lỗi kích hoạt GitHub: {res.text}")
    except Exception as e:
        await msg.edit(content=f"❌ Lỗi hệ thống: {e}")

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_BOT_TOKEN)
