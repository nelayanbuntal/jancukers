import discord
from discord.ext import commands
from discord import ui, Interaction
import asyncio
import random
import os
from datetime import datetime

# Import modules kita
from redeem_core import run_redeem_process
import config
from database import (
    init_database, get_balance, deduct_balance, 
    create_redeem, get_user_stats, get_topup_by_order_id,
    create_topup, get_redeem_queue_count
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
# Multi-user data & active channel tracking
# ==============================
user_data = {}          # user_id -> parameter data
active_channels = {}    # user_id -> channel_id

# ==============================
# Live log panel
# ==============================
live_logs = {}            # channel_id -> list of log lines
live_panel_message = {}   # channel_id -> discord.Message
last_update = {}          # channel_id -> timestamp terakhir update

# ==============================
# Queue login task
# ==============================
login_queue = asyncio.Queue()

# ==============================
# Midtrans instance
# ==============================
midtrans = MidtransPayment(
    server_key=config.MIDTRANS_SERVER_KEY,
    is_production=config.MIDTRANS_IS_PRODUCTION
)

async def login_worker():
    """Worker untuk proses redeem"""
    while True:
        task = await login_queue.get()
        user_id = task["user_id"]
        email = task["email"]
        password = task["password"]
        channel = task["channel"]
        android_choice = task["android_choice"]
        region = task["region"]
        code_file = task["code_file"]

        loop = asyncio.get_event_loop()

        def login_task():
            return run_redeem_process(
                code_file=code_file,
                email=email,
                password=password,
                region_input=region,
                android_choice=android_choice,
                progress_callback=make_progress_callback(channel),
                user_id=user_id
            )

        # Jalankan redeem di thread executor
        result = await loop.run_in_executor(None, login_task)
        
        # Split message jika terlalu panjang (Discord limit: 2000 chars)
        max_length = 1900  # Beri margin untuk markdown
        result_text = f"✅ Redeem selesai:\n```\n{result}\n```"
        
        if len(result_text) <= 2000:
            await channel.send(result_text)
        else:
            # Split menjadi beberapa pesan
            await channel.send("✅ Redeem selesai! (Output panjang, dibagi beberapa pesan)")
            
            # Split result by lines
            lines = result.split('\n')
            current_chunk = "```\n"
            
            for line in lines:
                if len(current_chunk) + len(line) + 5 > max_length:  # +5 untuk \n dan ```
                    current_chunk += "```"
                    await channel.send(current_chunk)
                    current_chunk = "```\n" + line + "\n"
                else:
                    current_chunk += line + "\n"
            
            if current_chunk != "```\n":
                current_chunk += "```"
                await channel.send(current_chunk)
            
            # Kirim summary
            success_file = f"success_{user_id}.txt"
            invalid_file = f"invalid_{user_id}.txt"
            
            success_count = 0
            invalid_count = 0
            
            if os.path.exists(success_file):
                with open(success_file, 'r') as f:
                    success_count = len([l for l in f.readlines() if l.strip()])
            
            if os.path.exists(invalid_file):
                with open(invalid_file, 'r') as f:
                    invalid_count = len([l for l in f.readlines() if l.strip()])
            
            summary_embed = discord.Embed(
                title="📊 Ringkasan Redeem",
                color=0x00ff00
            )
            summary_embed.add_field(name="✅ Success", value=str(success_count), inline=True)
            summary_embed.add_field(name="❌ Invalid", value=str(invalid_count), inline=True)
            summary_embed.add_field(name="📁 File Log", value=f"`{success_file}` | `{invalid_file}`", inline=False)
            
            await channel.send(embed=summary_embed)

        login_queue.task_done()

# ==============================
# Fungsi Live Log Update
# ==============================
async def update_live_panel(channel):
    """Update live log panel di channel"""
    if channel.id not in live_panel_message:
        msg = await channel.send(embed=discord.Embed(title="Live Redeem Log", description="Memuat...", color=0x00ff00))
        live_panel_message[channel.id] = msg

    last = last_update.get(channel.id, 0)
    now = asyncio.get_event_loop().time()
    if now - last < 5:
        return  # throttling 5 detik

    log_lines = live_logs.get(channel.id, [])
    embed = discord.Embed(
        title="Live Redeem Log",
        description="\n".join(log_lines[-10:]) if log_lines else "Tidak ada log saat ini.",
        color=0x00ff00
    )
    try:
        await live_panel_message[channel.id].edit(embed=embed)
    except discord.HTTPException:
        pass
    last_update[channel.id] = now

def make_progress_callback(channel):
    """Callback untuk update progress redeem"""
    def progress_callback(key, text):
        if channel.id not in live_logs:
            live_logs[channel.id] = []
        live_logs[channel.id].append(text)
        asyncio.run_coroutine_threadsafe(update_live_panel(channel), bot.loop)
    return progress_callback

# ==============================
# Bot class dengan setup_hook
# ==============================
class MyBot(commands.Bot):
    async def setup_hook(self):
        # Inisialisasi database
        init_database()
        
        # Start login workers
        for _ in range(config.MAX_LOGIN_WORKERS):
            asyncio.create_task(login_worker())
        
        # Tambahkan persistent views
        self.add_view(MainMenuView())
        self.add_view(StartFormButton())
        
        print("✅ Bot setup complete")

bot = MyBot(command_prefix="!", intents=intents)

# ==============================
# Main Menu View dengan Buttons
# ==============================
class MainMenuView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="🟩 Start Redeem",
        style=discord.ButtonStyle.green,
        custom_id="start_redeem_button"
    )
    async def start_redeem(self, interaction: Interaction, button: ui.Button):
        """Buat channel privat untuk redeem"""
        user = interaction.user

        # CEK SALDO TERLEBIH DAHULU
        user_balance = get_balance(user.id)
        min_balance = config.REDEEM_COST_PER_CODE  # Minimal 1 kode
        
        if user_balance < min_balance:
            return await interaction.response.send_message(
                f"❌ **Saldo tidak cukup untuk redeem!**\n\n"
                f"Saldo kamu: **{format_rupiah(user_balance)}**\n"
                f"Minimal saldo: **{format_rupiah(min_balance)}** (untuk 1 kode)\n\n"
                f"💡 Silakan topup terlebih dahulu dengan klik tombol **💰 Topup Saldo**",
                ephemeral=True
            )

        if user.id in active_channels:
            ch_id = active_channels[user.id]
            existing_channel = interaction.guild.get_channel(ch_id)
            if existing_channel:
                return await interaction.response.send_message(
                    f"❌ Kamu sudah punya channel aktif: {existing_channel.mention}",
                    ephemeral=True
                )
            else:
                active_channels.pop(user.id)

        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="Redeem Tools")
        if category is None:
            category = await guild.create_category("Redeem Tools")

        rand = random.randint(1000, 9999)
        channel_name = f"redeem-{rand}"

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
            f"📩 Channel privat telah dibuat: {redeem_channel.mention}", ephemeral=True
        )

        await redeem_channel.send(
            f"👋 Halo {user.mention}! Klik tombol di bawah untuk mengisi parameter redeem.",
            view=StartFormButton()
        )

    @ui.button(
        label="💰 Topup Saldo",
        style=discord.ButtonStyle.blurple,
        custom_id="topup_button"
    )
    async def topup(self, interaction: Interaction, button: ui.Button):
        """Buka modal topup"""
        await interaction.response.send_modal(TopupModal())

    @ui.button(
        label="💳 Cek Saldo",
        style=discord.ButtonStyle.gray,
        custom_id="check_balance_button"
    )
    async def check_balance(self, interaction: Interaction, button: ui.Button):
        """Cek saldo user"""
        user_id = interaction.user.id
        balance = get_balance(user_id)
        stats = get_user_stats(user_id)
        
        embed = discord.Embed(
            title="💳 Informasi Saldo",
            color=0x3498db
        )
        embed.add_field(name="Saldo Saat Ini", value=format_rupiah(balance), inline=False)
        embed.add_field(name="Total Topup", value=format_rupiah(stats['total_topup']), inline=True)
        embed.add_field(name="Total Spent", value=format_rupiah(stats['total_spent']), inline=True)
        embed.add_field(name="Redeem Success", value=str(stats['success_redeem']), inline=True)
        embed.add_field(name="Redeem Failed", value=str(stats['failed_redeem']), inline=True)
        embed.set_footer(text=f"User ID: {user_id}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(
        label="📊 Status Bot",
        style=discord.ButtonStyle.gray,
        custom_id="status_button"
    )
    async def status(self, interaction: Interaction, button: ui.Button):
        """Cek status bot dan antrian"""
        queue_count = get_redeem_queue_count()
        
        embed = discord.Embed(
            title="📊 Status Bot",
            color=0xe67e22
        )
        embed.add_field(name="Antrian Redeem", value=f"{queue_count} task", inline=True)
        embed.add_field(name="Max Workers", value=str(config.MAX_LOGIN_WORKERS), inline=True)
        embed.add_field(name="Biaya Per Kode", value=format_rupiah(config.REDEEM_COST_PER_CODE), inline=False)
        embed.set_footer(text="Bot sedang berjalan normal")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ==============================
# Topup Modal
# ==============================
class TopupModal(ui.Modal, title="Topup Saldo"):
    amount = ui.TextInput(
        label="Jumlah Topup (Rupiah)",
        placeholder=f"Minimal {config.MIN_TOPUP_AMOUNT}",
        min_length=4,
        max_length=10
    )

    async def on_submit(self, interaction: Interaction):
        try:
            amount_value = int(self.amount.value.strip())
            
            if amount_value < config.MIN_TOPUP_AMOUNT:
                return await interaction.response.send_message(
                    f"❌ Minimal topup adalah {format_rupiah(config.MIN_TOPUP_AMOUNT)}",
                    ephemeral=True
                )
            
            # Generate order ID
            order_id = generate_order_id(interaction.user.id)
            
            # Buat transaksi Midtrans
            customer_details = {
                "first_name": interaction.user.name,
                "email": f"{interaction.user.id}@discord.user",
                "phone": "08123456789"
            }
            
            await interaction.response.defer(ephemeral=True)
            
            transaction = midtrans.create_qris_transaction(
                order_id=order_id,
                amount=amount_value,
                customer_details=customer_details
            )
            
            if not transaction:
                return await interaction.followup.send(
                    "❌ Gagal membuat transaksi. Silakan coba lagi.",
                    ephemeral=True
                )
            
            # Simpan ke database
            create_topup(interaction.user.id, amount_value, order_id)
            
            # Ambil QR code URL
            qr_url = transaction.get('actions', [{}])[0].get('url', '')
            
            # Kirim ke DM user
            try:
                embed = discord.Embed(
                    title="💳 Pembayaran QRIS",
                    description=f"Scan QR code di bawah untuk membayar **{format_rupiah(amount_value)}**",
                    color=0x00ff00
                )
                embed.add_field(name="Order ID", value=order_id, inline=False)
                embed.add_field(name="Jumlah", value=format_rupiah(amount_value), inline=False)
                embed.set_image(url=qr_url)
                embed.set_footer(text="Pembayaran akan otomatis terverifikasi • Berlaku 15 menit")
                
                await interaction.user.send(embed=embed)
                
                await interaction.followup.send(
                    f"✅ Invoice pembayaran telah dikirim ke DM kamu!\n"
                    f"Order ID: `{order_id}`\n"
                    f"Jumlah: **{format_rupiah(amount_value)}**",
                    ephemeral=True
                )
                
            except discord.Forbidden:
                await interaction.followup.send(
                    f"⚠️ Tidak bisa mengirim DM. Pastikan DM terbuka!\n\n"
                    f"**QR Code:** {qr_url}\n"
                    f"Order ID: `{order_id}`",
                    ephemeral=True
                )
                
        except ValueError:
            await interaction.response.send_message(
                "❌ Jumlah harus berupa angka!",
                ephemeral=True
            )

# ==============================
# Button to open modal
# ==============================
class StartFormButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="📋 Input Parameter",
        style=discord.ButtonStyle.blurple,
        custom_id="input_parameter_button"
    )
    async def open_form(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_modal(RedeemModal())

# ==============================
# Modal for redeem parameters
# ==============================
class RedeemModal(ui.Modal, title="Parameter Redeem"):
    email = ui.TextInput(label="Email", placeholder="Email akun Redfinger")
    password = ui.TextInput(label="Password", placeholder="Password akun", style=discord.TextStyle.short)
    region = ui.TextInput(label="Region", placeholder="hk sg th")
    android = ui.TextInput(label="Android Version (1/2/3)", placeholder="1=8.1 | 2=10 | 3=12")

    async def on_submit(self, interaction: Interaction):
        try:
            android_choice = int(self.android.value.strip())
            if android_choice not in [1, 2, 3]:
                raise ValueError()
        except:
            return await interaction.response.send_message(
                "❌ Android version invalid.",
                ephemeral=True
            )

        user_data[interaction.user.id] = {
            "email": self.email.value.strip(),
            "password": self.password.value.strip(),
            "region": self.region.value.strip(),
            "android_choice": android_choice,
            "user": interaction.user
        }

        await interaction.response.send_message(
            "✅ Parameter diterima! Silakan upload `code.txt` di channel ini.",
            ephemeral=False
        )

# ==============================
# Handle file upload in channel
# ==============================
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    if isinstance(message.channel, discord.TextChannel):
        if message.channel.name.startswith("redeem-") and len(message.attachments) > 0:
            user_info = user_data.get(message.author.id)
            if not user_info:
                return await message.channel.send("❌ Parameter redeem belum diisi.")

            attachment = message.attachments[0]

            if not attachment.filename.endswith(".txt"):
                return await message.channel.send("❌ File harus berekstensi `.txt`.")

            # Hitung jumlah kode
            content = await attachment.read()
            codes = [line.strip() for line in content.decode('utf-8').split('\n') if line.strip()]
            code_count = len(codes)
            
            if code_count == 0:
                return await message.channel.send("❌ File code kosong!")
            
            # Limit maksimal kode per upload (opsional, untuk mencegah abuse)
            if code_count > config.MAX_CODES_PER_UPLOAD:
                return await message.channel.send(
                    f"❌ Terlalu banyak kode!\n"
                    f"Maksimal: **{config.MAX_CODES_PER_UPLOAD} kode** per upload\n"
                    f"Kode kamu: **{code_count} kode**\n\n"
                    f"💡 Silakan split file menjadi beberapa bagian."
                )
            
            # Hitung total biaya
            total_cost = code_count * config.REDEEM_COST_PER_CODE
            user_balance = get_balance(message.author.id)
            
            # Cek saldo dengan pesan yang lebih jelas
            if user_balance < total_cost:
                shortage = total_cost - user_balance
                embed = discord.Embed(
                    title="❌ Saldo Tidak Cukup",
                    description="Saldo kamu tidak mencukupi untuk proses redeem ini.",
                    color=0xe74c3c
                )
                embed.add_field(name="Jumlah Kode", value=f"{code_count} kode", inline=True)
                embed.add_field(name="Total Biaya", value=format_rupiah(total_cost), inline=True)
                embed.add_field(name="Saldo Kamu", value=format_rupiah(user_balance), inline=True)
                embed.add_field(name="Kekurangan", value=format_rupiah(shortage), inline=True)
                embed.add_field(
                    name="💡 Solusi", 
                    value="Klik tombol **💰 Topup Saldo** di channel utama untuk isi saldo.",
                    inline=False
                )
                return await message.channel.send(embed=embed)
            
            # Kurangi saldo
            if not deduct_balance(message.author.id, total_cost):
                return await message.channel.send("❌ Gagal mengurangi saldo. Silakan coba lagi.")
            
            # Simpan file
            temp_code_file = f"code_temp_{user_info['user'].id}.txt"
            await attachment.save(temp_code_file)

            # Masukkan ke antrian
            await login_queue.put({
                "user_id": user_info['user'].id,
                "email": user_info["email"],
                "password": user_info["password"],
                "region": user_info["region"],
                "android_choice": user_info["android_choice"],
                "channel": message.channel,
                "code_file": temp_code_file
            })

            new_balance = get_balance(message.author.id)
            
            await message.channel.send(
                f"✅ File diterima dan saldo telah dipotong!\n"
                f"Jumlah kode: **{code_count}**\n"
                f"Biaya: **{format_rupiah(total_cost)}**\n"
                f"Saldo tersisa: **{format_rupiah(new_balance)}**\n\n"
                f"⚙️ Task masuk antrian. Mohon tunggu..."
            )

    await bot.process_commands(message)

# ==============================
# Commands
# ==============================
@bot.command(name='saldo')
async def check_balance_command(ctx):
    """Command untuk cek saldo"""
    user_id = ctx.author.id
    balance = get_balance(user_id)
    await ctx.send(f"💰 Saldo kamu saat ini: **{format_rupiah(balance)}**")

@bot.command(name='stats')
async def stats_command(ctx):
    """Command untuk cek statistik"""
    stats = get_user_stats(ctx.author.id)
    
    embed = discord.Embed(
        title="📊 Statistik Kamu",
        color=0x9b59b6
    )
    embed.add_field(name="Saldo", value=format_rupiah(stats['balance']), inline=True)
    embed.add_field(name="Total Topup", value=format_rupiah(stats['total_topup']), inline=True)
    embed.add_field(name="Total Spent", value=format_rupiah(stats['total_spent']), inline=True)
    embed.add_field(name="Success Redeem", value=str(stats['success_redeem']), inline=True)
    embed.add_field(name="Failed Redeem", value=str(stats['failed_redeem']), inline=True)
    embed.add_field(name="Total Redeem", value=str(stats['total_redeem']), inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='close')
async def close_channel_command(ctx):
    """Command untuk close channel redeem privat"""
    # Cek apakah di channel redeem privat
    if not ctx.channel.name.startswith("redeem-"):
        return await ctx.send("❌ Command ini hanya bisa digunakan di channel redeem privat!")
    
    # Cek apakah user adalah owner channel atau admin
    is_owner = ctx.author.id in active_channels and active_channels[ctx.author.id] == ctx.channel.id
    admin_role = discord.utils.get(ctx.guild.roles, name=config.ADMIN_ROLE_NAME)
    is_admin = admin_role in ctx.author.roles if admin_role else False
    
    if not (is_owner or is_admin):
        return await ctx.send("❌ Kamu tidak bisa close channel ini!")
    
    # Hapus dari tracking
    if ctx.author.id in active_channels:
        active_channels.pop(ctx.author.id)
    
    await ctx.send("🗑️ Channel ini akan dihapus dalam 5 detik...")
    await asyncio.sleep(5)
    await ctx.channel.delete(reason=f"Closed by {ctx.author.name}")

@bot.command(name='commands', aliases=['cmd', 'bothelp'])
async def commands_list(ctx):
    """Command untuk menampilkan daftar command"""
    embed = discord.Embed(
        title="📖 Daftar Command",
        description="Command yang tersedia untuk semua user",
        color=0x3498db
    )
    
    commands_list = [
        ("!saldo", "Cek saldo kamu saat ini"),
        ("!stats", "Lihat statistik lengkap (topup, redeem, dll)"),
        ("!close", "Tutup channel redeem privat (hanya di channel redeem)"),
        ("!commands", "Tampilkan pesan ini (alias: !cmd, !bothelp)"),
    ]
    
    for cmd, desc in commands_list:
        embed.add_field(name=cmd, value=desc, inline=False)
    
    embed.add_field(
        name="💡 Tips",
        value="Gunakan tombol di channel utama untuk akses fitur utama:\n"
              "🟩 Start Redeem | 💰 Topup Saldo | 💳 Cek Saldo | 📊 Status Bot",
        inline=False
    )
    
    embed.set_footer(text="Untuk admin commands, ketik !adminhelp (khusus admin)")
    
    await ctx.send(embed=embed)

# ==============================
# READY
# ==============================
@bot.event
async def on_ready():
    print(f"✅ Bot login sebagai {bot.user}")
    setup_admin_commands(bot) // untuk mengaktifkan command admin
    # Start webhook server
    webhook_server.set_discord_bot(bot)
    webhook_server.start_webhook_server()

    # Kirim main menu ke public channel
    channel = bot.get_channel(config.PUBLIC_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🤖 Bot Redeem CloudEmulator",
            description="Pilih menu di bawah untuk memulai:",
            color=0x2ecc71
        )
        embed.add_field(
            name="🟩 Start Redeem",
            value="Buat channel privat untuk redeem kode",
            inline=False
        )
        embed.add_field(
            name="💰 Topup Saldo",
            value="Isi saldo via QRIS (Midtrans)",
            inline=False
        )
        embed.add_field(
            name="💳 Cek Saldo",
            value="Lihat saldo dan statistik kamu",
            inline=False
        )
        embed.add_field(
            name="📊 Status Bot",
            value="Lihat status bot dan antrian redeem",
            inline=False
        )
        embed.set_footer(text=f"Biaya redeem: {format_rupiah(config.REDEEM_COST_PER_CODE)} per kode")
        
        await channel.send(embed=embed, view=MainMenuView())

# ==============================
# RUN BOT
# ==============================
if __name__ == "__main__":
    bot.run(config.DISCORD_TOKEN)