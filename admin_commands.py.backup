"""
Admin Commands Extension
Modul command khusus admin dengan error handling dan professional messaging
"""

import discord
from discord.ext import commands
from database import get_user_stats, get_topup_by_order_id, get_balance, add_balance
from payment_gateway import format_rupiah
import config
import traceback

def setup_admin_commands(bot: commands.Bot):
    """Setup admin commands dengan error handling"""

    def is_admin():
        """Check if user has admin role"""
        async def predicate(ctx):
            admin_role = discord.utils.get(ctx.guild.roles, name=config.ADMIN_ROLE_NAME)
            return admin_role in ctx.author.roles if admin_role else False
        return commands.check(predicate)

    @bot.command(name='addbalance')
    @is_admin()
    async def add_balance_admin(ctx, user: discord.Member, amount: int):
        """
        [ADMIN] Tambah saldo manual ke user
        Usage: !addbalance @user 10000
        """
        try:
            if amount <= 0:
                return await ctx.send("❌ Jumlah harus bernilai positif!")

            if amount > 100000000:  # Max 100 juta
                return await ctx.send("⚠️ Jumlah terlalu besar! Maksimal Rp 100.000.000 per transaksi.")

            new_balance = add_balance(user.id, amount)

            embed = discord.Embed(
                title="✅ Saldo Berhasil Ditambahkan",
                color=0x2ecc71
            )
            embed.add_field(name="👤 User", value=user.mention, inline=False)
            embed.add_field(name="➕ Jumlah Ditambahkan", value=format_rupiah(amount), inline=True)
            embed.add_field(name="💰 Saldo Baru", value=format_rupiah(new_balance), inline=True)
            embed.set_footer(text=f"Oleh: {ctx.author.name}")

            await ctx.send(embed=embed)

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
            except discord.Forbidden:
                await ctx.send(f"ℹ️ Tidak dapat mengirim notifikasi ke {user.mention} (DM tertutup)")
            except:
                pass

        except Exception as e:
            print(f"❌ Error in addbalance: {e}")
            print(traceback.format_exc())
            await ctx.send("❌ Terjadi kesalahan saat menambahkan saldo. Silakan coba lagi.")

    @bot.command(name='checkuser')
    @is_admin()
    async def check_user_admin(ctx, user: discord.Member):
        """
        [ADMIN] Cek detail user
        Usage: !checkuser @user
        """
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
            
            embed.set_footer(text=f"Dicek oleh: {ctx.author.name}")

            await ctx.send(embed=embed)

        except Exception as e:
            print(f"❌ Error in checkuser: {e}")
            print(traceback.format_exc())
            await ctx.send("❌ Terjadi kesalahan saat mengambil data user.")

    @bot.command(name='checktransaction')
    @is_admin()
    async def check_transaction_admin(ctx, order_id: str):
        """
        [ADMIN] Cek detail transaksi
        Usage: !checktransaction TOPUP-123-20241203120000
        """
        try:
            topup = get_topup_by_order_id(order_id)

            if not topup:
                return await ctx.send(f"❌ Transaksi dengan ID `{order_id}` tidak ditemukan!")

            try:
                user = await bot.fetch_user(topup['user_id'])
                user_mention = user.mention
                user_name = user.name
            except:
                user_mention = f"User ID: {topup['user_id']}"
                user_name = "Unknown"

            # Status color
            status_colors = {
                'pending': 0xf39c12,
                'success': 0x2ecc71,
                'failed': 0xe74c3c,
                'expired': 0x95a5a6
            }
            color = status_colors.get(topup['status'], 0x95a5a6)

            embed = discord.Embed(
                title=f"💳 Detail Transaksi",
                color=color
            )
            embed.add_field(name="🆔 Order ID", value=f"`{topup['order_id']}`", inline=False)
            embed.add_field(name="👤 User", value=f"{user_mention} ({user_name})", inline=False)
            embed.add_field(name="💰 Jumlah", value=format_rupiah(topup['amount']), inline=True)
            embed.add_field(name="📊 Status", value=topup['status'].upper(), inline=True)
            embed.add_field(name="💳 Metode", value=topup['payment_type'].upper(), inline=True)
            embed.add_field(name="📅 Dibuat", value=topup['created_at'], inline=True)
            embed.add_field(name="🔄 Diupdate", value=topup['updated_at'], inline=True)
            embed.set_footer(text=f"Dicek oleh: {ctx.author.name}")

            await ctx.send(embed=embed)

        except Exception as e:
            print(f"❌ Error in checktransaction: {e}")
            print(traceback.format_exc())
            await ctx.send("❌ Terjadi kesalahan saat mengambil data transaksi.")

    @bot.command(name='botstats')
    @is_admin()
    async def bot_stats_admin(ctx):
        """
        [ADMIN] Statistik keseluruhan bot
        Usage: !botstats
        """
        try:
            from database import get_redeem_queue_count, get_database_stats
            
            stats = get_database_stats()

            embed = discord.Embed(
                title="📊 Statistik Bot",
                description="Ringkasan keseluruhan sistem",
                color=0xe74c3c
            )
            
            # User stats
            embed.add_field(
                name="👥 User",
                value=f"Total: **{stats['total_users']}** user",
                inline=True
            )
            
            # Balance stats
            embed.add_field(
                name="💰 Saldo Sistem",
                value=format_rupiah(stats['total_balance']),
                inline=True
            )
            
            # Queue stats
            queue_count = get_redeem_queue_count()
            embed.add_field(
                name="📦 Antrian",
                value=f"**{queue_count}** task",
                inline=True
            )
            
            # Topup stats
            embed.add_field(
                name="📈 Top Up",
                value=f"• Jumlah: **{stats['successful_topups']}** transaksi\n"
                      f"• Total: {format_rupiah(stats['total_topup_amount'])}",
                inline=False
            )
            
            # Redeem stats
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
                name="⚙️ Konfigurasi",
                value=f"• Max Workers: **{config.MAX_LOGIN_WORKERS}**\n"
                      f"• Biaya per Kode: {format_rupiah(config.REDEEM_COST_PER_CODE)}",
                inline=False
            )
            
            embed.set_footer(text=f"Bot aktif di {len(bot.guilds)} server")

            await ctx.send(embed=embed)

        except Exception as e:
            print(f"❌ Error in botstats: {e}")
            print(traceback.format_exc())
            await ctx.send("❌ Terjadi kesalahan saat mengambil statistik bot.")

    @bot.command(name='broadcast')
    @is_admin()
    async def broadcast_admin(ctx, *, message: str):
        """
        [ADMIN] Broadcast pesan ke semua user yang pernah topup
        Usage: !broadcast Your message here
        """
        try:
            import sqlite3

            # Confirm broadcast
            confirm_embed = discord.Embed(
                title="⚠️ Konfirmasi Broadcast",
                description="Anda akan mengirim pesan ke semua user yang pernah melakukan top up.",
                color=0xf39c12
            )
            confirm_embed.add_field(name="📝 Pesan", value=message[:1000], inline=False)
            confirm_embed.add_field(
                name="❓ Lanjutkan?",
                value="Ketik `yes` dalam 30 detik untuk melanjutkan, atau `no` untuk membatalkan.",
                inline=False
            )
            
            await ctx.send(embed=confirm_embed)

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['yes', 'no']

            try:
                response = await bot.wait_for('message', timeout=30.0, check=check)
                
                if response.content.lower() == 'no':
                    return await ctx.send("✅ Broadcast dibatalkan.")
                
            except asyncio.TimeoutError:
                return await ctx.send("⏱️ Waktu konfirmasi habis. Broadcast dibatalkan.")

            # Get user IDs
            with sqlite3.connect(config.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT user_id FROM topups WHERE status='success'")
                user_ids = [row[0] for row in cursor.fetchall()]

            if not user_ids:
                return await ctx.send("ℹ️ Tidak ada user yang pernah melakukan top up.")

            success_count = 0
            fail_count = 0

            status_msg = await ctx.send(f"📤 Mengirim broadcast ke **{len(user_ids)}** user...")

            for user_id in user_ids:
                try:
                    user = await bot.fetch_user(user_id)

                    embed = discord.Embed(
                        title="📢 Pengumuman dari Admin",
                        description=message,
                        color=0x3498db
                    )
                    embed.set_footer(
                        text="Bot Redeem Code • CloudEmulator",
                        icon_url=bot.user.display_avatar.url if bot.user.display_avatar else None
                    )

                    await user.send(embed=embed)
                    success_count += 1
                    
                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.5)
                    
                except discord.Forbidden:
                    fail_count += 1
                except discord.HTTPException:
                    fail_count += 1
                except Exception as e:
                    print(f"⚠️ Failed to send to {user_id}: {e}")
                    fail_count += 1

            result_embed = discord.Embed(
                title="✅ Broadcast Selesai",
                color=0x2ecc71
            )
            result_embed.add_field(name="✅ Berhasil", value=str(success_count), inline=True)
            result_embed.add_field(name="❌ Gagal", value=str(fail_count), inline=True)
            result_embed.add_field(name="📊 Total", value=str(len(user_ids)), inline=True)
            
            await status_msg.edit(content=None, embed=result_embed)

        except Exception as e:
            print(f"❌ Error in broadcast: {e}")
            print(traceback.format_exc())
            await ctx.send("❌ Terjadi kesalahan saat melakukan broadcast.")

    @bot.command(name='adminhelp')
    @is_admin()
    async def admin_help(ctx):
        """
        [ADMIN] List semua admin commands
        Usage: !adminhelp
        """
        embed = discord.Embed(
            title="🛡️ Admin Commands",
            description="Daftar command khusus untuk admin",
            color=0xe74c3c
        )

        commands_list = [
            ("!addbalance @user [amount]", "Tambah saldo manual ke user tertentu"),
            ("!checkuser @user", "Lihat detail statistik dan informasi user"),
            ("!checktransaction [order_id]", "Cek detail transaksi berdasarkan Order ID"),
            ("!botstats", "Lihat statistik keseluruhan bot dan sistem"),
            ("!broadcast [message]", "Kirim pengumuman ke semua user (dengan konfirmasi)"),
            ("!adminhelp", "Tampilkan daftar admin commands ini"),
        ]

        for cmd, desc in commands_list:
            embed.add_field(name=cmd, value=desc, inline=False)

        embed.add_field(
            name="⚠️ Catatan Penting",
            value="• Semua command admin akan dicatat di log\n"
                  "• Gunakan dengan bijak dan bertanggung jawab\n"
                  "• Broadcast memerlukan konfirmasi sebelum dikirim",
            inline=False
        )

        embed.set_footer(text=f"Hanya user dengan role '{config.ADMIN_ROLE_NAME}' yang dapat menggunakan commands ini")

        await ctx.send(embed=embed)

    # Error handler untuk admin commands
    @add_balance_admin.error
    @check_user_admin.error
    @check_transaction_admin.error
    @bot_stats_admin.error
    @broadcast_admin.error
    @admin_help.error
    async def admin_command_error(ctx, error):
        """Error handler untuk admin commands"""
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Anda tidak memiliki izin untuk menggunakan command admin ini.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Parameter tidak lengkap. Gunakan: `!adminhelp` untuk melihat cara penggunaan.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Parameter tidak valid. Pastikan format sudah benar.")
        else:
            print(f"❌ Admin command error: {error}")
            print(traceback.format_exc())
            await ctx.send("❌ Terjadi kesalahan saat menjalankan command. Silakan coba lagi.")

    print("✅ Admin commands loaded successfully")