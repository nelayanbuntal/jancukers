import discord
from discord.ext import commands
from discord import ui, Interaction, app_commands
import asyncio
import random
import os
from datetime import datetime
import traceback
import time
# Import modules
from redeem_core import run_redeem_process
import config
from database import (
    init_database, get_balance, deduct_balance, 
    create_redeem, get_user_stats, get_topup_by_order_id,
    create_topup, get_redeem_queue_count, get_database_stats
)
from payment_gateway import MidtransPayment, generate_order_id, format_rupiah
import webhook_server

# ==============================
# BOT CONFIG
# ==============================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# ==============================
# Global State Management
# ==============================
user_data = {}          # user_id -> parameter data
active_channels = {}    # user_id -> channel_id
live_logs = {}          # channel_id -> list of log lines
live_status_message = {}  # channel_id -> discord.Message (single status message)
session_stats = {}      # user_id -> {'success': 0, 'invalid': 0, 'total': 0}
last_update = {}        # channel_id -> timestamp

# Auto-close tracking
channel_last_activity = {}   # channel_id -> timestamp (last message time)
channel_completion_time = {} # channel_id -> timestamp (when redeem completed)
channel_close_warned = {}    # channel_id -> bool (warning sent?)

# ==============================
# Queue & Worker Management
# ==============================
login_queue = asyncio.Queue()
worker_status = {}      # worker_id -> status

# ==============================
# Payment Gateway
# ==============================
try:
    midtrans = MidtransPayment(
        server_key=config.MIDTRANS_SERVER_KEY,
        is_production=config.MIDTRANS_IS_PRODUCTION
    )
except Exception as e:
    print(f"⚠️ Midtrans initialization warning: {e}")
    midtrans = None

# ==============================
# Retry Decorator untuk Bot Operations
# ==============================
def retry_async(max_attempts=3, delay=2, backoff=2):
    """Decorator untuk retry async operations"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except discord.HTTPException as e:
                    if attempt < max_attempts - 1:
                        wait_time = delay * (backoff ** attempt)
                        print(f"⚠️ Discord API error, retrying in {wait_time}s: {e}")
                        await asyncio.sleep(wait_time)
                        continue
                    raise
                except Exception as e:
                    if attempt < max_attempts - 1:
                        print(f"⚠️ Error in {func.__name__}, retrying: {e}")
                        await asyncio.sleep(delay * (backoff ** attempt))
                        continue
                    raise
        return wrapper
    return decorator

# ==============================
# Login Worker dengan Error Recovery
# ==============================
async def login_worker(worker_id: int):
    """Worker untuk proses redeem dengan comprehensive error handling"""
    worker_status[worker_id] = "idle"
    
    while True:
        try:
            task = await login_queue.get()
            worker_status[worker_id] = "processing"
            
            user_id = task["user_id"]
            email = task["email"]
            password = task["password"]
            channel = task["channel"]
            android_version = task["android_version"]
            region = task["region"]
            code_file = task["code_file"]

            # Clean up old session files BEFORE starting
            cleanup_old_session_files(user_id)
            
            # Get new session files with timestamp
            session_files = get_session_files(user_id)
            
            # Load codes for stats tracking
            from redeem_core import load_codes
            codes = load_codes(code_file)
            
            # Initialize session stats
            session_stats[user_id] = {
                'success': 0,
                'invalid': 0,
                'total': len(codes)
            }

            loop = asyncio.get_event_loop()

            def login_task():
                return run_redeem_process(
                    code_file=code_file,
                    email=email,
                    password=password,
                    region_input=region,
                    android_version=android_version,
                    progress_callback=make_progress_callback(channel),
                    user_id=user_id,
                    session_files=session_files  # Pass session files
                )

            try:
                # Jalankan redeem dengan timeout protection
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, login_task),
                    timeout=1800  # 30 menit timeout
                )
                
                # Kirim completion message with session files
                await safe_send_completion(channel, user_id, result, session_files)
                
            except asyncio.TimeoutError:
                await safe_send(channel, 
                    "⏱️ **Proses redeem timeout**\n\n"
                    "Proses melebihi batas waktu yang ditentukan. "
                    "Silakan coba lagi dengan kode yang lebih sedikit atau hubungi admin."
                )
                # Mark completion for auto-close
                channel_completion_time[channel.id] = config.get_wib_time().timestamp()
                
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Worker {worker_id} error: {error_msg}")
                print(traceback.format_exc())
                
                await safe_send(channel,
                    "❌ **Terjadi Kesalahan**\n\n"
                    "Maaf, terjadi kesalahan saat memproses redeem Anda. "
                    "Tim kami telah menerima laporan error ini.\n\n"
                    "💡 Silakan coba lagi dalam beberapa saat atau hubungi admin untuk bantuan."
                )
                # Mark completion for auto-close
                channel_completion_time[channel.id] = config.get_wib_time().timestamp()
            
            finally:
                # Cleanup temp code file immediately
                try:
                    if os.path.exists(code_file):
                        os.remove(code_file)
                        print(f"🧹 Cleaned temp code file: {code_file}")
                except:
                    pass
                
                # Session files kept until channel auto-closes
                
                login_queue.task_done()
                worker_status[worker_id] = "idle"
                
        except Exception as e:
            print(f"❌ Critical error in worker {worker_id}: {e}")
            print(traceback.format_exc())
            worker_status[worker_id] = "error"
            await asyncio.sleep(5)  # Cooldown sebelum retry
            worker_status[worker_id] = "idle"

# ==============================
# Safe Message Sending
# ==============================
@retry_async(max_attempts=3)
async def safe_send(channel, content=None, embed=None, view=None):
    """Send message with retry logic"""
    try:
        return await channel.send(content=content, embed=embed, view=view)
    except discord.Forbidden:
        print(f"⚠️ Cannot send message to channel {channel.id} (no permission)")
        return None
    except discord.HTTPException as e:
        print(f"⚠️ HTTP error sending message: {e}")
        raise

async def safe_send_completion(channel, user_id, result, session_files):
    """Send completion message with statistics and file uploads"""
    try:
        # Parse result (can be dict or string)
        if isinstance(result, dict):
            success_count = result.get('success', 0)
            failed_count = result.get('failed', 0)
            total_count = result.get('total', 0)
        else:
            # Fallback: use session_stats if available
            stats = session_stats.get(user_id, {})
            success_count = stats.get('success', 0)
            failed_count = stats.get('failed', 0)
            total_count = stats.get('total', 0)
        
        # Header message
        await safe_send(channel, "✅ **Proses Redeem Selesai**")
        
        # Determine color and status
        if success_count > 0 and failed_count == 0:
            color = 0x2ecc71  # Green - all success
            status_emoji = "🎉"
            status_text = "Sempurna"
        elif success_count > 0:
            color = 0xe67e22  # Orange - mixed
            status_emoji = "⚠️"
            status_text = "Selesai dengan Peringatan"
        elif failed_count > 0:
            color = 0xe74c3c  # Red - all failed
            status_emoji = "❌"
            status_text = "Tidak Ada Kode Valid"
        else:
            color = 0x95a5a6  # Gray - no data
            status_emoji = "ℹ️"
            status_text = "Selesai"
        
        # Summary embed
        embed = discord.Embed(
            title=f"{status_emoji} Hasil Redeem Code",
            description="Berikut adalah ringkasan proses redeem Anda:",
            color=color
        )
        
        embed.add_field(
            name="✅ Kode Berhasil", 
            value=f"**{success_count}** kode", 
            inline=True
        )
        embed.add_field(
            name="❌ Kode Invalid/Gagal", 
            value=f"**{failed_count}** kode", 
            inline=True
        )
        embed.add_field(
            name="📦 Total Diproses",
            value=f"**{total_count}** kode",
            inline=True
        )
        
        # Success rate
        if total_count > 0:
            success_rate = (success_count / total_count) * 100
            embed.add_field(
                name="📊 Success Rate",
                value=f"**{success_rate:.1f}%**",
                inline=True
            )
        
        embed.set_footer(
            text=f"Status: {status_text} • {config.format_wib_datetime()}"
        )
        
        await safe_send(channel, embed=embed)
        
        # File upload section
        success_file = session_files.get('success')
        invalid_file = session_files.get('invalid')
        
        files_to_upload = []
        file_descriptions = []
        
        # Check and prepare success file
        if success_file and os.path.exists(success_file):
            size = os.path.getsize(success_file)
            if size > 0:
                files_to_upload.append(discord.File(success_file, filename=f"success_{user_id}.txt"))
                file_descriptions.append(f"✅ **Success Log** - {success_count} kode berhasil")
        
        # Check and prepare invalid file
        if invalid_file and os.path.exists(invalid_file):
            size = os.path.getsize(invalid_file)
            if size > 0:
                files_to_upload.append(discord.File(invalid_file, filename=f"invalid_{user_id}.txt"))
                file_descriptions.append(f"❌ **Invalid Log** - {failed_count} kode gagal")
        
        # Send files if any
        if files_to_upload:
            file_embed = discord.Embed(
                title="📁 File Log Detail",
                description="\n".join(file_descriptions) + "\n\n💡 Download file untuk melihat detail setiap kode.",
                color=0x3498db
            )
            file_embed.set_footer(text="File log akan otomatis terhapus setelah channel ditutup")
            
            await channel.send(embed=file_embed, files=files_to_upload)
        elif total_count > 0:
            # Has codes but no log files
            await safe_send(channel, 
                "ℹ️ Tidak ada file log (semua kode mungkin error atau tidak terproses)"
            )
        
        # Mark completion time for auto-close
        channel_completion_time[channel.id] = config.get_wib_time().timestamp()
        
        # Send auto-close info
        await asyncio.sleep(2)  # Small delay
        close_info = discord.Embed(
            title="ℹ️ Informasi Channel",
            description=f"Channel ini akan **otomatis tertutup** dalam **2 jam** "
                       f"setelah tidak ada aktivitas.\n\n"
                       f"💡 Anda akan menerima peringatan 10 menit sebelum channel ditutup.",
            color=0x3498db
        )
        close_info.set_footer(text="Kirim pesan apa saja untuk reset timer inactivity")
        await safe_send(channel, embed=close_info)
        
    except Exception as e:
        print(f"⚠️ Error sending completion: {e}")
        traceback.print_exc()
        # Fallback simple message
        await safe_send(channel, f"✅ Proses redeem selesai. Berhasil: {success_count}, Gagal: {failed_count}")

# ==============================
# Live Log Update (Single Message Edit)
# ==============================
async def update_live_panel(channel):
    """Update live log panel dengan single message edit"""
    try:
        # Get recent logs
        log_lines = live_logs.get(channel.id, [])
        recent_logs = log_lines[-10:] if log_lines else ["⏳ Memulai proses..."]
        
        # Create embed
        embed = discord.Embed(
            title="📊 Status Redeem",
            description="\n".join(recent_logs),
            color=0x3498db
        )
        embed.set_footer(text=f"Log diperbarui secara real-time • {config.format_wib_time_only()}")
        
        # Create or edit single message
        if channel.id not in live_status_message:
            # First time - create new message
            msg = await safe_send(channel, embed=embed)
            if msg:
                live_status_message[channel.id] = msg
        else:
            # Edit existing message
            try:
                await live_status_message[channel.id].edit(embed=embed)
            except discord.NotFound:
                # Message deleted, create new one
                msg = await safe_send(channel, embed=embed)
                if msg:
                    live_status_message[channel.id] = msg
            except discord.HTTPException as e:
                # Rate limit or other error, skip this update
                print(f"⚠️ Could not update status: {e}")
        
        # Update activity timestamp
        channel_last_activity[channel.id] = config.get_wib_time().timestamp()
        
    except Exception as e:
        print(f"⚠️ Error updating live panel: {e}")

def make_progress_callback(channel):
    """Callback untuk update progress"""
    def progress_callback(key, text):
        if channel.id not in live_logs:
            live_logs[channel.id] = []
        live_logs[channel.id].append(text)
        asyncio.run_coroutine_threadsafe(update_live_panel(channel), bot.loop)
    return progress_callback

# ==============================
# File Management Utilities
# ==============================
def get_session_files(user_id):
    """Get all session-related files for a user"""
    timestamp = int(time.time())
    return {
        'code_temp': f"code_temp_{user_id}.txt",
        'success': f"success_{user_id}_{timestamp}.txt",
        'invalid': f"invalid_{user_id}_{timestamp}.txt",
        'timestamp': timestamp
    }

def cleanup_old_session_files(user_id):
    """Clean up old session files before starting new session"""
    import glob
    patterns = [
        f"code_temp_{user_id}.txt",
        f"success_{user_id}_*.txt",
        f"invalid_{user_id}_*.txt",
        f"success_{user_id}.txt",  # Legacy format
        f"invalid_{user_id}.txt"   # Legacy format
    ]
    
    cleaned = 0
    for pattern in patterns:
        for file in glob.glob(pattern):
            try:
                os.remove(file)
                cleaned += 1
                print(f"🧹 Cleaned: {file}")
            except Exception as e:
                print(f"⚠️ Could not clean {file}: {e}")
    
    return cleaned

def cleanup_session_files(user_id, session_files=None):
    """Clean up session files after completion"""
    if session_files is None:
        # Clean all files for user
        return cleanup_old_session_files(user_id)
    
    cleaned = 0
    for file_type, file_path in session_files.items():
        if file_type == 'timestamp':
            continue
        
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                cleaned += 1
                print(f"🧹 Cleaned: {file_path}")
            except Exception as e:
                print(f"⚠️ Could not clean {file_path}: {e}")
    
    return cleaned

# ==============================
# Bot Setup with Slash Commands
# ==============================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        
    async def setup_hook(self):
        """Initialize bot components"""
        try:
            # Database
            init_database()
            print("✅ Database initialized")
            
            # Start workers
            for i in range(config.MAX_LOGIN_WORKERS):
                asyncio.create_task(login_worker(i))
            print(f"✅ Started {config.MAX_LOGIN_WORKERS} workers")
            
            # Add persistent views
            self.add_view(MainMenuView())
            self.add_view(PrivateChannelButtons())
            self.add_view(AdminControlPanel())
            print("✅ Persistent views added")
            
            # Sync slash commands - FIXED: Force sync for all guilds
            try:
                # Global sync (takes up to 1 hour)
                synced = await self.tree.sync()
                print(f"✅ Synced {len(synced)} global command(s)")
                
                # Guild-specific sync for instant availability (optional but recommended)
                for guild in self.guilds:
                    try:
                        guild_synced = await self.tree.sync(guild=guild)
                        print(f"✅ Synced {len(guild_synced)} command(s) for guild: {guild.name}")
                    except Exception as e:
                        print(f"⚠️ Failed to sync for guild {guild.name}: {e}")
                        
            except Exception as e:
                print(f"⚠️ Failed to sync commands: {e}")
                print(traceback.format_exc())
            
        except Exception as e:
            print(f"❌ Setup error: {e}")
            print(traceback.format_exc())

bot = MyBot()

# ==============================
# Main Menu View (Public Channel)
# ==============================
class MainMenuView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="🎮 Mulai Redeem",
        style=discord.ButtonStyle.green,
        custom_id="start_redeem_button",
        row=0
    )
    async def start_redeem(self, interaction: Interaction, button: ui.Button):
        """Buat channel privat untuk redeem"""
        user = interaction.user

        # Cek saldo
        user_balance = get_balance(user.id)
        min_balance = config.REDEEM_COST_PER_CODE
        
        if user_balance < min_balance:
            shortage = min_balance - user_balance
            embed = discord.Embed(
                title="💳 Saldo Tidak Mencukupi",
                description="Maaf, saldo Anda belum cukup untuk memulai redeem.",
                color=0xe74c3c
            )
            embed.add_field(
                name="Saldo Anda", 
                value=format_rupiah(user_balance), 
                inline=True
            )
            embed.add_field(
                name="Minimal Saldo", 
                value=format_rupiah(min_balance), 
                inline=True
            )
            embed.add_field(
                name="💡 Cara Top Up",
                value="Klik tombol **💰 Top Up Saldo** di menu utama untuk mengisi saldo.",
                inline=False
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Cek channel aktif
        if user.id in active_channels:
            ch_id = active_channels[user.id]
            existing_channel = interaction.guild.get_channel(ch_id)
            if existing_channel:
                return await interaction.response.send_message(
                    f"ℹ️ Anda sudah memiliki sesi aktif di {existing_channel.mention}",
                    ephemeral=True
                )
            else:
                active_channels.pop(user.id)

        try:
            guild = interaction.guild
            category = discord.utils.get(guild.categories, name="🎮 Redeem Sessions")
            if category is None:
                category = await guild.create_category("🎮 Redeem Sessions")

            rand = random.randint(1000, 9999)
            channel_name = f"redeem-{user.name[:10]}-{rand}"

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }

            admin_role = discord.utils.get(guild.roles, name=config.ADMIN_ROLE_NAME)
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            redeem_channel = await guild.create_text_channel(
                channel_name, overwrites=overwrites, category=category
            )

            active_channels[user.id] = redeem_channel.id

            await interaction.response.send_message(
                f"✅ Channel privat berhasil dibuat: {redeem_channel.mention}",
                ephemeral=True
            )

            welcome_embed = discord.Embed(
                title="👋 Selamat Datang di Sesi Redeem",
                description=f"Halo {user.mention}! Mari kita mulai proses redeem code Anda.",
                color=0x3498db
            )
            welcome_embed.add_field(
                name="📋 Langkah Selanjutnya",
                value="Klik tombol **Input Parameter** di bawah untuk mengisi informasi akun Anda.",
                inline=False
            )
            welcome_embed.add_field(
                name="💡 Tips",
                value="• Pastikan informasi akun sudah benar\n"
                      "• Siapkan file `code.txt` berisi kode redeem\n"
                      "• Satu baris untuk satu kode",
                inline=False
            )
            welcome_embed.set_footer(text="Gunakan tombol di bawah untuk bantuan atau menutup channel")

            await redeem_channel.send(embed=welcome_embed, view=PrivateChannelButtons())
            
        except Exception as e:
            print(f"❌ Error creating channel: {e}")
            await interaction.response.send_message(
                "❌ Maaf, terjadi kesalahan saat membuat channel. Silakan coba lagi atau hubungi admin.",
                ephemeral=True
            )

    @ui.button(
        label="💰 Top Up Saldo",
        style=discord.ButtonStyle.blurple,
        custom_id="topup_button",
        row=0
    )
    async def topup(self, interaction: Interaction, button: ui.Button):
        """Buka modal topup"""
        if not midtrans:
            return await interaction.response.send_message(
                "⚠️ Sistem pembayaran sedang dalam maintenance. Silakan hubungi admin.",
                ephemeral=True
            )
        await interaction.response.send_modal(TopupModal())

    @ui.button(
        label="💳 Info Saldo",
        style=discord.ButtonStyle.gray,
        custom_id="check_balance_button",
        row=0
    )
    async def check_balance(self, interaction: Interaction, button: ui.Button):
        """Cek saldo user"""
        user_id = interaction.user.id
        balance = get_balance(user_id)
        stats = get_user_stats(user_id)
        
        embed = discord.Embed(
            title="💳 Informasi Akun Anda",
            color=0x3498db
        )
        embed.add_field(
            name="💰 Saldo Tersedia", 
            value=format_rupiah(balance), 
            inline=False
        )
        embed.add_field(
            name="📊 Statistik",
            value=f"• Total Top Up: {format_rupiah(stats['total_topup'])}\n"
                  f"• Total Penggunaan: {format_rupiah(stats['total_spent'])}\n"
                  f"• Redeem Berhasil: {stats['success_redeem']}\n"
                  f"• Redeem Gagal: {stats['failed_redeem']}",
            inline=False
        )
        embed.set_footer(text=f"User ID: {user_id}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(
        label="📊 Status Bot",
        style=discord.ButtonStyle.gray,
        custom_id="bot_status_button",
        row=1
    )
    async def bot_status(self, interaction: Interaction, button: ui.Button):
        """Tampilkan status bot untuk user"""
        try:
            queue_count = get_redeem_queue_count()
            
            # Worker status
            workers_active = sum(1 for s in worker_status.values() if s == "processing")
            workers_idle = sum(1 for s in worker_status.values() if s == "idle")
            workers_total = config.MAX_LOGIN_WORKERS
            
            # Status color
            if workers_idle >= workers_total * 0.5:
                color = 0x2ecc71  # Green - Banyak worker tersedia
                status_text = "🟢 Optimal"
            elif workers_idle > 0:
                color = 0xf39c12  # Orange - Sedang sibuk
                status_text = "🟡 Sibuk"
            else:
                color = 0xe74c3c  # Red - Semua worker sibuk
                status_text = "🔴 Penuh"
            
            embed = discord.Embed(
                title="📊 Status Bot",
                description=f"Status: **{status_text}**",
                color=color
            )
            
            # Worker info
            embed.add_field(
                name="⚙️ Workers",
                value=f"• Tersedia: **{workers_idle}**\n"
                      f"• Sedang Bekerja: **{workers_active}**\n"
                      f"• Total: **{workers_total}**",
                inline=True
            )
            
            # Queue info
            queue_status = "✅ Kosong" if queue_count == 0 else f"⏳ {queue_count} task"
            embed.add_field(
                name="📦 Antrian",
                value=queue_status,
                inline=True
            )
            
            # Estimasi waktu tunggu
            if queue_count == 0:
                wait_time = "Langsung diproses"
            elif workers_idle > 0:
                wait_time = "< 5 menit"
            else:
                est_minutes = (queue_count * 3)
                wait_time = f"~{est_minutes} menit"
            
            embed.add_field(
                name="⏱️ Estimasi Tunggu",
                value=wait_time,
                inline=False
            )
            
            # Tips
            if workers_idle == 0:
                embed.add_field(
                    name="💡 Tips",
                    value="Semua worker sedang sibuk. Proses Anda akan dijalankan setelah ada worker yang tersedia.",
                    inline=False
                )
            elif queue_count > 5:
                embed.add_field(
                    name="💡 Tips",
                    value="Antrian sedang ramai. Anda bisa mulai redeem sekarang, proses akan berjalan otomatis.",
                    inline=False
                )
            else:
                embed.add_field(
                    name="💡 Tips",
                    value="Bot sedang dalam kondisi optimal. Waktu yang tepat untuk memulai redeem!",
                    inline=False
                )
            
            embed.timestamp = datetime.now()
            embed.set_footer(text="Data real-time • Refresh untuk update terbaru")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"❌ Error showing bot status: {e}")
            await interaction.response.send_message(
                "❌ Gagal mengambil status bot. Silakan coba lagi.",
                ephemeral=True
            )

    @ui.button(
        label="ℹ️ Bantuan",
        style=discord.ButtonStyle.gray,
        custom_id="help_button",
        row=1
    )
    async def help_menu(self, interaction: Interaction, button: ui.Button):
        """Tampilkan menu bantuan"""
        embed = discord.Embed(
            title="ℹ️ Panduan Penggunaan Bot",
            description="Berikut adalah cara menggunakan bot redeem code ini:",
            color=0x9b59b6
        )
        
        embed.add_field(
            name="1️⃣ Top Up Saldo",
            value="Klik tombol **💰 Top Up Saldo** untuk mengisi saldo via QRIS. "
                  "Pembayaran otomatis terverifikasi dalam hitungan detik.",
            inline=False
        )
        
        embed.add_field(
            name="2️⃣ Mulai Redeem",
            value="Klik tombol **🎮 Mulai Redeem** untuk membuat sesi privat. "
                  "Bot akan membuatkan channel khusus untuk Anda.",
            inline=False
        )
        
        embed.add_field(
            name="3️⃣ Input Parameter",
            value="Isi informasi akun CloudEmulator Anda (email, password, region, dll).",
            inline=False
        )
        
        embed.add_field(
            name="4️⃣ Upload File Kode",
            value="Upload file `code.txt` yang berisi kode redeem (satu kode per baris).",
            inline=False
        )
        
        embed.add_field(
            name="💰 Biaya",
            value=f"Biaya redeem: **{format_rupiah(config.REDEEM_COST_PER_CODE)}** per kode\n"
                  f"Top up minimal: **{format_rupiah(config.MIN_TOPUP_AMOUNT)}**",
            inline=False
        )
        
        embed.add_field(
            name="❓ Butuh Bantuan?",
            value="Hubungi admin jika mengalami kendala atau ada pertanyaan.",
            inline=False
        )
        
        embed.set_footer(text="Bot Redeem Code • CloudEmulator")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ==============================
# Private Channel Buttons (with Close button)
# ==============================
class PrivateChannelButtons(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="📝 Input Parameter",
        style=discord.ButtonStyle.blurple,
        custom_id="input_parameter_button",
        row=0
    )
    async def open_form(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_modal(RedeemModal())

    @ui.button(
        label="📖 Bantuan",
        style=discord.ButtonStyle.gray,
        custom_id="private_help_button",
        row=0
    )
    async def show_help(self, interaction: Interaction, button: ui.Button):
        """Show help in private channel"""
        embed = discord.Embed(
            title="📖 Bantuan & Command",
            description="Panduan lengkap untuk channel redeem ini:",
            color=0x3498db
        )
        
        embed.add_field(
            name="🔹 Cara Mulai Redeem",
            value="1. Klik tombol **📝 Input Parameter**\n"
                  "2. Isi email, password, region, dan versi Android\n"
                  "3. Upload file `code.txt` berisi kode redeem\n"
                  "4. Tunggu proses selesai",
            inline=False
        )
        
        embed.add_field(
            name="💰 Informasi Biaya",
            value=f"• Biaya per kode: **{format_rupiah(config.REDEEM_COST_PER_CODE)}**\n"
                  f"• Maksimal upload: **{config.MAX_CODES_PER_UPLOAD} kode**\n"
                  f"• Biaya dipotong otomatis dari saldo",
            inline=False
        )
        
        embed.add_field(
            name="📋 Format File code.txt",
            value="```\nDMA4-FY6T-ASFL\nABC1-XYZ2-DEF3\nGHI4-JKL5-MNO6\n```\nSatu kode per baris, tanpa spasi ekstra",
            inline=False
        )
        
        embed.add_field(
            name="📱 Versi Android",
            value="Pilih dengan angka:\n"
                  "`1` - Android 8.1\n"
                  "`2` - Android 10\n"
                  "`3` - Android 12\n"
                  "`4` - Android 15",
            inline=False
        )
        
        embed.add_field(
            name="🌍 Region",
            value="Pilih dari dropdown menu (bisa multiple):\n"
                  "🇭🇰 Hong Kong 2 • 🇭🇰 Hong Kong\n"
                  "🇹🇭 Thailand • 🇸🇬 Singapore\n"
                  "🇹🇼 Taiwan • 🇺🇸 United States",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ Perhatian",
            value="• Pastikan akun CloudEmulator valid\n"
                  "• Kode yang invalid tidak akan di-refund\n"
                  "• Proses mungkin memakan waktu beberapa menit\n"
                  "• Jangan tutup channel saat proses berlangsung",
            inline=False
        )
        
        embed.set_footer(text="Butuh bantuan lebih? Hubungi admin")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(
        label="🚪 Tutup Channel",
        style=discord.ButtonStyle.red,
        custom_id="close_channel_button",
        row=0
    )
    async def close_channel(self, interaction: Interaction, button: ui.Button):
        """Tutup channel redeem"""
        if not interaction.channel.name.startswith("redeem-"):
            return await interaction.response.send_message(
                "ℹ️ Button ini hanya bisa digunakan di channel redeem.",
                ephemeral=True
            )
        
        user = interaction.user
        is_owner = user.id in active_channels and active_channels[user.id] == interaction.channel.id
        admin_role = discord.utils.get(interaction.guild.roles, name=config.ADMIN_ROLE_NAME)
        is_admin = admin_role in user.roles if admin_role else False
        
        if not (is_owner or is_admin):
            return await interaction.response.send_message(
                "❌ Anda tidak memiliki izin untuk menutup channel ini.",
                ephemeral=True
            )
        
        if user.id in active_channels:
            active_channels.pop(user.id)
        
        await interaction.response.send_message(
            "👋 Channel ini akan ditutup dalam 5 detik. Terima kasih telah menggunakan layanan kami!"
        )
        await asyncio.sleep(5)
        
        try:
            await interaction.channel.delete(reason=f"Ditutup oleh {user.name}")
        except:
            pass

# ==============================
# Admin Control Panel
# ==============================
class AdminControlPanel(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="📊 System Stats",
        style=discord.ButtonStyle.blurple,
        custom_id="admin_stats_button",
        row=0
    )
    async def show_stats(self, interaction: Interaction, button: ui.Button):
        """Show system statistics"""
        # Check admin
        admin_role = discord.utils.get(interaction.guild.roles, name=config.ADMIN_ROLE_NAME)
        if not admin_role or admin_role not in interaction.user.roles:
            return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        
        try:
            stats = get_database_stats()
            queue_count = get_redeem_queue_count()
            
            # Worker status
            workers_active = sum(1 for s in worker_status.values() if s == "processing")
            workers_idle = sum(1 for s in worker_status.values() if s == "idle")
            
            embed = discord.Embed(
                title="📊 System Statistics",
                description="Real-time bot statistics",
                color=0xe74c3c
            )
            
            embed.add_field(
                name="👥 Users",
                value=f"**{stats['total_users']}** registered users",
                inline=True
            )
            
            embed.add_field(
                name="💰 Total Balance",
                value=format_rupiah(stats['total_balance']),
                inline=True
            )
            
            embed.add_field(
                name="📦 Queue",
                value=f"**{queue_count}** tasks waiting",
                inline=True
            )
            
            embed.add_field(
                name="📈 Top Up Stats",
                value=f"• Transactions: **{stats['successful_topups']}**\n"
                      f"• Total Amount: {format_rupiah(stats['total_topup_amount'])}",
                inline=False
            )
            
            total_redeems = stats['successful_redeems'] + stats['failed_redeems']
            success_rate = (stats['successful_redeems'] / total_redeems * 100) if total_redeems > 0 else 0
            
            embed.add_field(
                name="🎮 Redeem Stats",
                value=f"• Success: **{stats['successful_redeems']}**\n"
                      f"• Failed: **{stats['failed_redeems']}**\n"
                      f"• Pending: **{stats['pending_redeems']}**\n"
                      f"• Success Rate: **{success_rate:.1f}%**",
                inline=False
            )
            
            embed.add_field(
                name="⚙️ Workers",
                value=f"• Active: **{workers_active}**\n"
                      f"• Idle: **{workers_idle}**\n"
                      f"• Total: **{config.MAX_LOGIN_WORKERS}**",
                inline=True
            )
            
            embed.add_field(
                name="🌐 System",
                value=f"• Servers: **{len(bot.guilds)}**\n"
                      f"• Active Sessions: **{len(active_channels)}**",
                inline=True
            )
            
            embed.timestamp = datetime.now()
            embed.set_footer(text="Updated")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"❌ Error showing stats: {e}")
            await interaction.response.send_message("❌ Error fetching stats", ephemeral=True)

    @ui.button(
        label="📖 Admin Commands",
        style=discord.ButtonStyle.gray,
        custom_id="admin_help_button",
        row=0
    )
    async def show_admin_help(self, interaction: Interaction, button: ui.Button):
        """Show admin commands"""
        # Check admin
        admin_role = discord.utils.get(interaction.guild.roles, name=config.ADMIN_ROLE_NAME)
        if not admin_role or admin_role not in interaction.user.roles:
            return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        
        embed = discord.Embed(
            title="🛡️ Admin Commands Reference",
            description="Complete list of admin commands and their usage",
            color=0xe74c3c
        )
        
        embed.add_field(
            name="💰 Balance Management",
            value="`/admin addbalance @user [amount]`\n"
                  "Add balance to specific user manually",
            inline=False
        )
        
        embed.add_field(
            name="👥 User Management",
            value="`/admin checkuser @user`\n"
                  "View detailed user statistics and info",
            inline=False
        )
        
        embed.add_field(
            name="📊 System Monitoring",
            value="`/admin botstats`\n"
                  "View comprehensive bot statistics\n\n"
                  "Or use the **📊 System Stats** button above",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Bot Configuration",
            value=f"• Max Workers: **{config.MAX_LOGIN_WORKERS}**\n"
                  f"• Cost per Code: {format_rupiah(config.REDEEM_COST_PER_CODE)}\n"
                  f"• Min Top Up: {format_rupiah(config.MIN_TOPUP_AMOUNT)}\n"
                  f"• Max Codes: **{config.MAX_CODES_PER_UPLOAD}**\n"
                  f"• Admin Role: **{config.ADMIN_ROLE_NAME}**",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ Important Notes",
            value="• All admin actions are logged\n"
                  "• Use commands responsibly\n"
                  "• Balance changes are permanent",
            inline=False
        )
        
        embed.set_footer(text=f"Admin Role: {config.ADMIN_ROLE_NAME}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(
        label="🔄 Refresh Stats",
        style=discord.ButtonStyle.green,
        custom_id="admin_refresh_button",
        row=0
    )
    async def refresh_stats(self, interaction: Interaction, button: ui.Button):
        """Refresh and show updated stats"""
        # Check admin
        admin_role = discord.utils.get(interaction.guild.roles, name=config.ADMIN_ROLE_NAME)
        if not admin_role or admin_role not in interaction.user.roles:
            return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            stats = get_database_stats()
            queue_count = get_redeem_queue_count()
            
            workers_active = sum(1 for s in worker_status.values() if s == "processing")
            workers_idle = sum(1 for s in worker_status.values() if s == "idle")
            
            embed = discord.Embed(
                title="🔄 Refreshed System Statistics",
                description="Latest real-time data",
                color=0x2ecc71
            )
            
            embed.add_field(
                name="👥 Users", 
                value=f"**{stats['total_users']}**", 
                inline=True
            )
            embed.add_field(
                name="💰 Balance", 
                value=format_rupiah(stats['total_balance']), 
                inline=True
            )
            embed.add_field(
                name="📦 Queue", 
                value=f"**{queue_count}**", 
                inline=True
            )
            
            embed.add_field(
                name="⚙️ Workers",
                value=f"Active: **{workers_active}** | Idle: **{workers_idle}**",
                inline=False
            )
            
            embed.add_field(
                name="🎮 Redeems Today",
                value=f"Success: **{stats['successful_redeems']}** | "
                      f"Failed: **{stats['failed_redeems']}** | "
                      f"Pending: **{stats['pending_redeems']}**",
                inline=False
            )
            
            embed.timestamp = datetime.now()
            embed.set_footer(text="Refreshed at")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"❌ Error refreshing stats: {e}")
            await interaction.followup.send("❌ Error refreshing stats", ephemeral=True)

# ==============================
# Topup Modal
# ==============================
class TopupModal(ui.Modal, title="💰 Top Up Saldo"):
    amount = ui.TextInput(
        label="Jumlah Top Up (Rupiah)",
        placeholder=f"Minimal Rp {config.MIN_TOPUP_AMOUNT:,}",
        min_length=4,
        max_length=10
    )

    async def on_submit(self, interaction: Interaction):
        try:
            amount_value = int(self.amount.value.strip().replace('.', '').replace(',', ''))
            
            if amount_value < config.MIN_TOPUP_AMOUNT:
                return await interaction.response.send_message(
                    f"❌ Minimal top up adalah **{format_rupiah(config.MIN_TOPUP_AMOUNT)}**",
                    ephemeral=True
                )
            
            if amount_value > 10000000:  # Max 10 juta
                return await interaction.response.send_message(
                    "❌ Maksimal top up adalah **Rp 10.000.000** per transaksi",
                    ephemeral=True
                )
            
            # Generate order ID
            order_id = generate_order_id(interaction.user.id)
            
            # Customer details
            customer_details = {
                "first_name": interaction.user.name[:50],
                "email": f"{interaction.user.id}@discord.user",
                "phone": "08123456789"
            }
            
            await interaction.response.defer(ephemeral=True)
            
            # Create transaction
            transaction = midtrans.create_qris_transaction(
                order_id=order_id,
                amount=amount_value,
                customer_details=customer_details
            )
            
            if not transaction:
                return await interaction.followup.send(
                    "❌ Gagal membuat transaksi pembayaran. Silakan coba lagi dalam beberapa saat.",
                    ephemeral=True
                )
            
            # Simpan ke database
            create_topup(interaction.user.id, amount_value, order_id)
            
            # QR code URL
            qr_url = transaction.get('actions', [{}])[0].get('url', '')
            
            # Kirim ke DM
            try:
                embed = discord.Embed(
                    title="💳 Pembayaran QRIS",
                    description=f"Scan QR code di bawah untuk membayar **{format_rupiah(amount_value)}**",
                    color=0x00ff00
                )
                embed.add_field(name="🆔 Order ID", value=f"`{order_id}`", inline=False)
                embed.add_field(name="💰 Jumlah", value=format_rupiah(amount_value), inline=True)
                embed.add_field(name="⏱️ Berlaku", value="15 menit", inline=True)
                embed.set_image(url=qr_url)
                embed.add_field(
                    name="ℹ️ Informasi",
                    value="• Pembayaran otomatis terverifikasi\n"
                          "• Saldo akan langsung masuk setelah pembayaran berhasil\n"
                          "• Anda akan menerima notifikasi via DM",
                    inline=False
                )
                embed.set_footer(text="Terima kasih telah menggunakan layanan kami")
                
                await interaction.user.send(embed=embed)
                
                await interaction.followup.send(
                    f"✅ **Invoice pembayaran telah dikirim ke DM Anda!**\n\n"
                    f"📋 Order ID: `{order_id}`\n"
                    f"💰 Jumlah: **{format_rupiah(amount_value)}**\n"
                    f"⏱️ Berlaku: 15 menit\n\n"
                    f"💡 Silakan cek DM Anda dan scan QR code untuk melakukan pembayaran.",
                    ephemeral=True
                )
                
            except discord.Forbidden:
                embed = discord.Embed(
                    title="⚠️ Tidak Dapat Mengirim DM",
                    description="Silakan aktifkan DM untuk menerima invoice pembayaran.",
                    color=0xf39c12
                )
                embed.add_field(name="QR Code", value=f"[Klik di sini untuk membayar]({qr_url})", inline=False)
                embed.add_field(name="Order ID", value=f"`{order_id}`", inline=False)
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
        except ValueError:
            await interaction.response.send_message(
                "❌ Format jumlah tidak valid. Harap masukkan angka saja.",
                ephemeral=True
            )
        except Exception as e:
            print(f"❌ Topup error: {e}")
            print(traceback.format_exc())
            
            try:
                await interaction.followup.send(
                    "❌ Terjadi kesalahan saat memproses top up. Silakan coba lagi atau hubungi admin.",
                    ephemeral=True
                )
            except:
                pass

# ==============================
# Region Select Components (Step 2: Region Selection)
# ==============================
class RegionSelect(ui.Select):
    """Multi-select dropdown for region selection"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        
        # Build options from config
        options = []
        for region_opt in config.REGION_SELECT_OPTIONS:
            options.append(
                discord.SelectOption(
                    label=region_opt['label'],
                    value=region_opt['value'],
                    emoji=region_opt['emoji'],
                    description=region_opt['description']
                )
            )
        
        super().__init__(
            placeholder="🌍 Pilih region (bisa lebih dari 1)...",
            min_values=1,  # At least 1 region
            max_values=len(options),  # Can select all
            options=options,
            custom_id=f"region_select_{user_id}"
        )
    
    async def callback(self, interaction: Interaction):
        """Handle region selection"""
        try:
            # Get selected regions
            selected_regions = self.values
            
            # Verify user data exists
            if self.user_id not in user_data:
                return await interaction.response.send_message(
                    "❌ Data tidak ditemukan. Silakan isi parameter kembali.",
                    ephemeral=True
                )
            
            # Update user data with selected regions
            user_data[self.user_id]["region"] = " ".join(selected_regions)
            user_data[self.user_id]["step"] = "ready_for_upload"
            
            # Get region names for display
            region_names = []
            for region_code in selected_regions:
                region_info = config.get_region_info(region_code)
                if region_info:
                    emoji = next((r['emoji'] for r in config.REGION_SELECT_OPTIONS if r['value'] == region_code), '🌍')
                    region_names.append(f"{emoji} {region_info['name']}")
            
            # Get android info for summary
            android_version = user_data[self.user_id]["android_version"]
            android_name = config.get_android_name(android_version)
            
            # Create confirmation embed
            embed = discord.Embed(
                title="✅ Setup Selesai!",
                description="Semua parameter telah dikonfigurasi. Anda siap untuk redeem!",
                color=0x2ecc71
            )
            embed.add_field(
                name="📧 Email",
                value=user_data[self.user_id]["email"],
                inline=False
            )
            embed.add_field(
                name="📱 Android Version",
                value=android_name,
                inline=True
            )
            embed.add_field(
                name="🌍 Regions Dipilih",
                value="\n".join(region_names),
                inline=True
            )
            embed.add_field(
                name="📁 Langkah Terakhir",
                value="Silakan upload file **`code.txt`** yang berisi kode redeem Anda.\n\n"
                      "**Format file:**\n"
                      "• Satu kode per baris\n"
                      "• Format: `XXXX-XXXX-XXXX` atau `XXXXXXXXXXXX`\n"
                      f"• Maksimal: **{config.MAX_CODES_PER_UPLOAD}** kode per upload",
                inline=False
            )
            embed.set_footer(
                text="💡 Tip: File akan diproses otomatis setelah upload",
                icon_url=interaction.client.user.display_avatar.url if interaction.client.user.display_avatar else None
            )
            
            # Disable the select menu (no longer needed)
            self.disabled = True
            await interaction.response.edit_message(view=self.view)
            
            # Send confirmation in new message
            await interaction.followup.send(embed=embed, ephemeral=False)
            
        except Exception as e:
            print(f"❌ Error in RegionSelect callback: {e}")
            traceback.print_exc()
            await interaction.response.send_message(
                "❌ Terjadi kesalahan saat memproses pilihan region. Silakan coba lagi.",
                ephemeral=True
            )

class RegionSelectView(ui.View):
    """View containing the region selection dropdown"""
    
    def __init__(self, user_id: int):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.user_id = user_id
        self.add_item(RegionSelect(user_id))
    
    async def on_timeout(self):
        """Handle timeout"""
        # Disable all components
        for item in self.children:
            item.disabled = True

# ==============================
# Redeem Modal (Step 1: Basic Info)
# ==============================
class RedeemModal(ui.Modal, title="📋 Setup Akun Redeem"):
    email = ui.TextInput(
        label="Email",
        placeholder="Email akun CloudEmulator Anda"
    )
    password = ui.TextInput(
        label="Password",
        placeholder="Minimal 6 karakter",
        style=discord.TextStyle.short
    )
    android = ui.TextInput(
        label="Versi Android",
        placeholder="1=8.1 | 2=10 | 3=12 | 4=15",
        min_length=1,
        max_length=1
    )

    async def on_submit(self, interaction: Interaction):
        try:
            # Validate android number
            android_number = self.android.value.strip()
            
            if not config.is_valid_android_number(android_number):
                return await interaction.response.send_message(
                    "❌ **Versi Android tidak valid!**\n\n"
                    "Pilih salah satu:\n"
                    "• **1** - Android 8.1\n"
                    "• **2** - Android 10\n"
                    "• **3** - Android 12\n"
                    "• **4** - Android 15",
                    ephemeral=True
                )
            
            # Convert number to version
            android_version = config.get_android_version_from_number(android_number)
            android_name = config.get_android_name(android_version)
            
            # Basic email validation
            email = self.email.value.strip()
            if '@' not in email or '.' not in email:
                return await interaction.response.send_message(
                    "❌ **Format email tidak valid!**\n\n"
                    "Pastikan email Anda mengandung @ dan domain yang valid.",
                    ephemeral=True
                )
            
            # Basic password validation
            password = self.password.value.strip()
            if len(password) < 6:
                return await interaction.response.send_message(
                    "❌ **Password terlalu pendek!**\n\n"
                    "Password minimal 6 karakter untuk keamanan akun Anda.",
                    ephemeral=True
                )

            # Store partial data (will be completed after region selection)
            user_data[interaction.user.id] = {
                "email": email,
                "password": password,
                "android_version": android_version,
                "android_number": android_number,
                "user": interaction.user,
                "step": "awaiting_region"  # Track progress
            }

            # Create region selection view
            region_view = RegionSelectView(interaction.user.id)
            
            embed = discord.Embed(
                title="✅ Informasi Akun Tersimpan",
                description="Data akun Anda telah tersimpan dengan aman.",
                color=0x2ecc71
            )
            embed.add_field(name="📧 Email", value=email, inline=False)
            embed.add_field(name="📱 Android", value=f"{android_name} (Pilihan: {android_number})", inline=True)
            embed.add_field(
                name="🌍 Langkah Selanjutnya",
                value="Pilih **region** untuk redeem menggunakan menu di bawah.\n"
                      "Anda bisa memilih **lebih dari 1 region**.",
                inline=False
            )
            embed.set_footer(text="💡 Tip: Pilih beberapa region untuk meningkatkan peluang sukses")

            await interaction.response.send_message(
                embed=embed, 
                view=region_view,
                ephemeral=False
            )

        except Exception as e:
            print(f"❌ Error in RedeemModal: {e}")
            traceback.print_exc()
            await interaction.response.send_message(
                "❌ Terjadi kesalahan saat memproses data. Silakan coba lagi.",
                ephemeral=True
            )

# ==============================
# File Upload Handler
# ==============================
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    if isinstance(message.channel, discord.TextChannel):
        if message.channel.name.startswith("redeem-") and len(message.attachments) > 0:
            user_info = user_data.get(message.author.id)
            if not user_info:
                return await safe_send(message.channel,
                    "⚠️ Silakan isi parameter terlebih dahulu dengan klik tombol **Input Parameter**."
                )

            attachment = message.attachments[0]

            if not attachment.filename.endswith(".txt"):
                return await safe_send(message.channel,
                    "❌ File harus berformat **`.txt`**\n\n"
                    "💡 Pastikan file berisi kode redeem dengan format satu kode per baris."
                )

            try:
                # Read and validate codes
                content = await attachment.read()
                codes = [line.strip() for line in content.decode('utf-8').split('\n') if line.strip()]
                code_count = len(codes)
                
                if code_count == 0:
                    return await safe_send(message.channel,
                        "❌ File kode kosong!\n\n"
                        "💡 Pastikan file berisi minimal satu kode redeem."
                    )
                
                # Check limit
                if code_count > config.MAX_CODES_PER_UPLOAD:
                    return await safe_send(message.channel,
                        f"❌ **Terlalu Banyak Kode!**\n\n"
                        f"• Maksimal: **{config.MAX_CODES_PER_UPLOAD} kode** per upload\n"
                        f"• Kode Anda: **{code_count} kode**\n\n"
                        f"💡 Silakan bagi file menjadi beberapa bagian yang lebih kecil."
                    )
                
                # Calculate cost
                total_cost = code_count * config.REDEEM_COST_PER_CODE
                user_balance = get_balance(message.author.id)
                
                # Check balance
                if user_balance < total_cost:
                    shortage = total_cost - user_balance
                    embed = discord.Embed(
                        title="💳 Saldo Tidak Mencukupi",
                        description="Maaf, saldo Anda tidak cukup untuk memproses kode sebanyak ini.",
                        color=0xe74c3c
                    )
                    embed.add_field(name="📦 Jumlah Kode", value=f"{code_count} kode", inline=True)
                    embed.add_field(name="💰 Total Biaya", value=format_rupiah(total_cost), inline=True)
                    embed.add_field(name="💳 Saldo Anda", value=format_rupiah(user_balance), inline=True)
                    embed.add_field(name="⚠️ Kekurangan", value=format_rupiah(shortage), inline=True)
                    embed.add_field(
                        name="💡 Solusi",
                        value="Kembali ke channel utama dan klik tombol **💰 Top Up Saldo** untuk mengisi saldo.",
                        inline=False
                    )
                    return await safe_send(message.channel, embed=embed)
                
                # Deduct balance
                if not deduct_balance(message.author.id, total_cost):
                    return await safe_send(message.channel,
                        "❌ Gagal memproses pembayaran. Silakan coba lagi atau hubungi admin."
                    )
                
                # Save file
                temp_code_file = f"code_temp_{user_info['user'].id}.txt"
                await attachment.save(temp_code_file)

                # Add to queue
                await login_queue.put({
                    "user_id": user_info['user'].id,
                    "email": user_info["email"],
                    "password": user_info["password"],
                    "region": user_info["region"],
                    "android_version": user_info["android_version"],  # Updated parameter name
                    "channel": message.channel,
                    "code_file": temp_code_file
                })

                new_balance = get_balance(message.author.id)
                queue_size = login_queue.qsize()
                
                embed = discord.Embed(
                    title="✅ File Diterima & Saldo Terpotong",
                    description="Redeem code Anda sedang diproses!",
                    color=0x2ecc71
                )
                embed.add_field(name="📦 Jumlah Kode", value=f"{code_count} kode", inline=True)
                embed.add_field(name="💰 Biaya", value=format_rupiah(total_cost), inline=True)
                embed.add_field(name="💳 Saldo Tersisa", value=format_rupiah(new_balance), inline=True)
                embed.add_field(
                    name="📊 Status",
                    value=f"• Posisi antrian: **{queue_size}**\n"
                          f"• Status: Menunggu pemrosesan\n"
                          f"• Estimasi: {queue_size * 2}-{queue_size * 5} menit",
                    inline=False
                )
                embed.add_field(
                    name="ℹ️ Informasi",
                    value="Proses redeem akan dimulai segera. Anda akan menerima notifikasi saat selesai.",
                    inline=False
                )
                embed.set_footer(text="Mohon bersabar, proses mungkin memakan waktu beberapa menit")
                
                await safe_send(message.channel, embed=embed)
                
            except UnicodeDecodeError:
                await safe_send(message.channel,
                    "❌ File tidak dapat dibaca!\n\n"
                    "💡 Pastikan file adalah text file UTF-8 yang valid."
                )
            except Exception as e:
                print(f"❌ File processing error: {e}")
                print(traceback.format_exc())
                await safe_send(message.channel,
                    "❌ Terjadi kesalahan saat memproses file. Silakan coba lagi atau hubungi admin."
                )

    await bot.process_commands(message)

# ==============================
# SLASH COMMANDS (Admin Only)
# ==============================

# Create admin group
admin_group = app_commands.Group(name="admin", description="Admin commands")

@admin_group.command(name="addbalance", description="Tambah saldo ke user")
@app_commands.describe(user="User yang akan ditambah saldonya", amount="Jumlah saldo")
async def admin_addbalance(interaction: Interaction, user: discord.Member, amount: int):
    """[ADMIN] Tambah saldo manual"""
    # Check admin
    admin_role = discord.utils.get(interaction.guild.roles, name=config.ADMIN_ROLE_NAME)
    if not admin_role or admin_role not in interaction.user.roles:
        return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
    
    try:
        if amount <= 0:
            return await interaction.response.send_message("❌ Jumlah harus bernilai positif!", ephemeral=True)

        if amount > 100000000:
            return await interaction.response.send_message("⚠️ Jumlah terlalu besar! Maksimal Rp 100.000.000 per transaksi.", ephemeral=True)

        from database import add_balance
        new_balance = add_balance(user.id, amount)

        embed = discord.Embed(
            title="✅ Saldo Berhasil Ditambahkan",
            color=0x2ecc71
        )
        embed.add_field(name="👤 User", value=user.mention, inline=False)
        embed.add_field(name="➕ Jumlah Ditambahkan", value=format_rupiah(amount), inline=True)
        embed.add_field(name="💰 Saldo Baru", value=format_rupiah(new_balance), inline=True)
        embed.set_footer(text=f"Oleh: {interaction.user.name}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Notify user
        try:
            user_embed = discord.Embed(
                title="💰 Saldo Ditambahkan",
                description=f"Admin telah menambahkan **{format_rupiah(amount)}** ke akun Anda!",
                color=0x2ecc71
            )
            user_embed.add_field(name="💳 Saldo Baru", value=format_rupiah(new_balance), inline=False)
            user_embed.set_footer(text="Terima kasih telah menggunakan layanan kami")
            
            await user.send(embed=user_embed)
        except:
            pass

    except Exception as e:
        print(f"❌ Error in addbalance: {e}")
        print(traceback.format_exc())
        await interaction.response.send_message("❌ Terjadi kesalahan.", ephemeral=True)

@admin_group.command(name="checkuser", description="Cek detail user")
@app_commands.describe(user="User yang akan dicek")
async def admin_checkuser(interaction: Interaction, user: discord.Member):
    """[ADMIN] Cek detail user"""
    # Check admin
    admin_role = discord.utils.get(interaction.guild.roles, name=config.ADMIN_ROLE_NAME)
    if not admin_role or admin_role not in interaction.user.roles:
        return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
    
    try:
        stats = get_user_stats(user.id)

        embed = discord.Embed(
            title=f"📊 Informasi User: {user.name}",
            color=0x3498db
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        embed.add_field(name="🆔 User ID", value=f"`{user.id}`", inline=False)
        embed.add_field(name="💰 Saldo", value=format_rupiah(stats['balance']), inline=True)
        embed.add_field(name="📈 Total Top Up", value=format_rupiah(stats['total_topup']), inline=True)
        embed.add_field(name="📉 Total Pengeluaran", value=format_rupiah(stats['total_spent']), inline=True)
        embed.add_field(name="📦 Total Redeem", value=str(stats['total_redeem']), inline=True)
        embed.add_field(name="✅ Redeem Berhasil", value=str(stats['success_redeem']), inline=True)
        embed.add_field(name="❌ Redeem Gagal", value=str(stats['failed_redeem']), inline=True)
        
        # Success rate
        if stats['total_redeem'] > 0:
            success_rate = (stats['success_redeem'] / stats['total_redeem']) * 100
            embed.add_field(name="📊 Success Rate", value=f"{success_rate:.1f}%", inline=True)
        
        embed.set_footer(text=f"Dicek oleh: {interaction.user.name}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        print(f"❌ Error in checkuser: {e}")
        print(traceback.format_exc())
        await interaction.response.send_message("❌ Terjadi kesalahan.", ephemeral=True)

@admin_group.command(name="botstats", description="Statistik keseluruhan bot")
async def admin_botstats(interaction: Interaction):
    """[ADMIN] Bot statistics"""
    # Check admin
    admin_role = discord.utils.get(interaction.guild.roles, name=config.ADMIN_ROLE_NAME)
    if not admin_role or admin_role not in interaction.user.roles:
        return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
    
    try:
        stats = get_database_stats()
        queue_count = get_redeem_queue_count()
        
        workers_active = sum(1 for s in worker_status.values() if s == "processing")
        workers_idle = sum(1 for s in worker_status.values() if s == "idle")

        embed = discord.Embed(
            title="📊 Statistik Bot",
            description="Ringkasan keseluruhan sistem",
            color=0xe74c3c
        )
        
        embed.add_field(
            name="👥 User",
            value=f"Total: **{stats['total_users']}** user",
            inline=True
        )
        
        embed.add_field(
            name="💰 Saldo Sistem",
            value=format_rupiah(stats['total_balance']),
            inline=True
        )
        
        embed.add_field(
            name="📦 Antrian",
            value=f"**{queue_count}** task",
            inline=True
        )
        
        embed.add_field(
            name="📈 Top Up",
            value=f"• Jumlah: **{stats['successful_topups']}** transaksi\n"
                  f"• Total: {format_rupiah(stats['total_topup_amount'])}",
            inline=False
        )
        
        total_redeems = stats['successful_redeems'] + stats['failed_redeems']
        success_rate = (stats['successful_redeems'] / total_redeems * 100) if total_redeems > 0 else 0
        
        embed.add_field(
            name="🎮 Redeem",
            value=f"• Berhasil: **{stats['successful_redeems']}**\n"
                  f"• Gagal: **{stats['failed_redeems']}**\n"
                  f"• Pending: **{stats['pending_redeems']}**\n"
                  f"• Success Rate: **{success_rate:.1f}%**",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Workers",
            value=f"• Active: **{workers_active}**\n"
                  f"• Idle: **{workers_idle}**\n"
                  f"• Total: **{config.MAX_LOGIN_WORKERS}**",
            inline=True
        )
        
        embed.add_field(
            name="🌐 System",
            value=f"• Servers: **{len(bot.guilds)}**\n"
                  f"• Active Sessions: **{len(active_channels)}**",
            inline=True
        )
        
        embed.set_footer(text=f"Bot aktif di {len(bot.guilds)} server")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        print(f"❌ Error in botstats: {e}")
        print(traceback.format_exc())
        await interaction.response.send_message("❌ Terjadi kesalahan.", ephemeral=True)

# Register admin group to bot tree
bot.tree.add_command(admin_group)

# ==============================
# Manual Sync Command (for troubleshooting)
# ==============================
@bot.command(name='sync')
@commands.is_owner()
async def sync_commands(ctx):
    """Manual command sync (bot owner only)"""
    try:
        await ctx.send("🔄 Syncing commands...")
        
        # Global sync
        synced = await bot.tree.sync()
        
        # Guild sync
        guild_synced = await bot.tree.sync(guild=ctx.guild)
        
        await ctx.send(f"✅ Synced {len(synced)} global commands and {len(guild_synced)} guild commands!")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")
        print(traceback.format_exc())

# ==============================
# Error Handler
# ==============================
@bot.event
async def on_command_error(ctx, error):
    """Global error handler untuk commands"""
    if isinstance(error, commands.CommandNotFound):
        return
    
    print(f"❌ Command error: {error}")
    print(traceback.format_exc())

# ==============================
# Ready Event & Admin Channel Setup
# ==============================
@bot.event
async def on_ready():
    """Bot ready event"""
    print(f"✅ Bot berhasil login sebagai {bot.user}")
    print(f"📊 Connected to {len(bot.guilds)} server(s)")
    
    # Set bot status
    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="redeem codes | Use buttons"
            )
        )
    except:
        pass
    
    # Start webhook server
    try:
        webhook_server.set_discord_bot(bot)
        webhook_server.start_webhook_server()
        print(f"✅ Webhook server started on port {config.WEBHOOK_PORT}")
    except Exception as e:
        print(f"⚠️ Webhook server warning: {e}")

    # Send/update main menu
    try:
        channel = bot.get_channel(config.PUBLIC_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="🤖 Bot Redeem Code CloudEmulator",
                description="Selamat datang! Pilih menu di bawah untuk memulai:",
                color=0x2ecc71
            )
            
            embed.add_field(
                name="🎮 Mulai Redeem",
                value="Buat sesi privat untuk redeem code Anda secara otomatis",
                inline=False
            )
            embed.add_field(
                name="💰 Top Up Saldo",
                value="Isi saldo dengan mudah via QRIS (pembayaran otomatis terverifikasi)",
                inline=False
            )
            embed.add_field(
                name="💳 Info Saldo & 📊 Status Bot",
                value="Cek saldo, statistik, dan status worker yang tersedia",
                inline=False
            )
            embed.add_field(
                name="ℹ️ Bantuan",
                value="Panduan lengkap cara menggunakan bot ini",
                inline=False
            )
            
            embed.add_field(
                name="💰 Informasi Biaya",
                value=f"• Biaya redeem: **{format_rupiah(config.REDEEM_COST_PER_CODE)}** per kode\n"
                      f"• Top up minimal: **{format_rupiah(config.MIN_TOPUP_AMOUNT)}**\n"
                      f"• Maksimal kode per upload: **{config.MAX_CODES_PER_UPLOAD}** kode",
                inline=False
            )
            
            embed.set_footer(
                text="Bot Redeem Code • Powered by CloudEmulator",
                icon_url=bot.user.display_avatar.url if bot.user.display_avatar else None
            )
            
            await channel.send(embed=embed, view=MainMenuView())
            print(f"✅ Main menu sent to channel {channel.id}")
    except Exception as e:
        print(f"⚠️ Could not send main menu: {e}")

    # Setup Admin Channel
    try:
        for guild in bot.guilds:
            admin_category = discord.utils.get(guild.categories, name="🛡️ Admin Control")
            if not admin_category:
                admin_role = discord.utils.get(guild.roles, name=config.ADMIN_ROLE_NAME)
                
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                }
                
                if admin_role:
                    overwrites[admin_role] = discord.PermissionOverwrite(
                        read_messages=True, 
                        send_messages=True,
                        manage_messages=True
                    )
                
                admin_category = await guild.create_category(
                    "🛡️ Admin Control",
                    overwrites=overwrites
                )
                print(f"✅ Created admin category in {guild.name}")
            
            admin_channel = discord.utils.get(guild.text_channels, name="admin-dashboard")
            if not admin_channel:
                admin_channel = await guild.create_text_channel(
                    "admin-dashboard",
                    category=admin_category
                )
                print(f"✅ Created admin channel in {guild.name}")
            
            embed = discord.Embed(
                title="🛡️ Admin Control Panel",
                description="Selamat datang di dashboard admin. Gunakan tombol atau slash commands untuk monitoring.",
                color=0xe74c3c
            )
            
            embed.add_field(
                name="📊 System Stats",
                value="View real-time bot statistics and performance metrics",
                inline=False
            )
            
            embed.add_field(
                name="📖 Admin Commands",
                value="Complete reference of all available admin commands",
                inline=False
            )
            
            embed.add_field(
                name="🔄 Refresh Stats",
                value="Get the latest system statistics instantly",
                inline=False
            )
            
            embed.add_field(
                name="📝 Slash Commands",
                value="`/admin addbalance @user [amount]` - Add balance\n"
                      "`/admin checkuser @user` - Check user details\n"
                      "`/admin botstats` - View bot statistics",
                inline=False
            )
            
            embed.add_field(
                name="⚙️ Quick Info",
                value=f"• Bot Version: 2.1 (Slash Commands)\n"
                      f"• Max Workers: {config.MAX_LOGIN_WORKERS}\n"
                      f"• Admin Role: {config.ADMIN_ROLE_NAME}\n"
                      f"• Servers: {len(bot.guilds)}",
                inline=False
            )
            
            embed.set_footer(
                text="Admin Only • Use responsibly",
                icon_url=bot.user.display_avatar.url if bot.user.display_avatar else None
            )
            
            await admin_channel.send(embed=embed, view=AdminControlPanel())
            print(f"✅ Admin panel sent to {guild.name}")
            
    except Exception as e:
        print(f"⚠️ Could not setup admin channel: {e}")

# ==============================
# Run Bot
# ==============================
if __name__ == "__main__":
    try:
        # Validate config
        if not config.validate_config():
            print("\n🛑 Bot tidak dapat dijalankan karena konfigurasi tidak valid.")
            print("💡 Silakan perbaiki file .env terlebih dahulu.\n")
            exit(1)
        
        config.print_config()
        
        print("\n🚀 Starting bot...")
        print("💡 Menggunakan Slash Commands (/)")
        bot.run(config.DISCORD_TOKEN)
        
    except KeyboardInterrupt:
        print("\n👋 Bot dihentikan oleh user")
    except Exception as e:
        print(f"\n❌ Critical error: {e}")
        print(traceback.format_exc())