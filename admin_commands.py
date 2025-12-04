"""
Admin Commands Extension untuk bot.py
Tambahkan import ini di bot.py: from admin_commands import setup_admin_commands
Lalu panggil di on_ready: setup_admin_commands(bot)
"""

import discord
from discord.ext import commands
from database import get_user_stats, get_topup_by_order_id, get_balance, add_balance
from payment_gateway import format_rupiah
import config

def setup_admin_commands(bot: commands.Bot):
    """Setup admin commands"""

    def is_admin():
        """Check if user is admin"""
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
        if amount <= 0:
            return await ctx.send("❌ Amount harus positif!")

        new_balance = add_balance(user.id, amount)

        embed = discord.Embed(
            title="✅ Balance Added",
            color=0x00ff00
        )
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Amount Added", value=format_rupiah(amount), inline=True)
        embed.add_field(name="New Balance", value=format_rupiah(new_balance), inline=True)

        await ctx.send(embed=embed)

        # Notify user
        try:
            await user.send(
                f"💰 Admin telah menambahkan **{format_rupiah(amount)}** ke saldo kamu!\n"
                f"Saldo baru: **{format_rupiah(new_balance)}**"
            )
        except:
            pass

    @bot.command(name='checkuser')
    @is_admin()
    async def check_user_admin(ctx, user: discord.Member):
        """
        [ADMIN] Cek detail user
        Usage: !checkuser @user
        """
        stats = get_user_stats(user.id)

        embed = discord.Embed(
            title=f"📊 User Statistics: {user.name}",
            color=0x3498db
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User ID", value=str(user.id), inline=False)
        embed.add_field(name="Balance", value=format_rupiah(stats['balance']), inline=True)
        embed.add_field(name="Total Topup", value=format_rupiah(stats['total_topup']), inline=True)
        embed.add_field(name="Total Spent", value=format_rupiah(stats['total_spent']), inline=True)
        embed.add_field(name="Total Redeem", value=str(stats['total_redeem']), inline=True)
        embed.add_field(name="Success Redeem", value=str(stats['success_redeem']), inline=True)
        embed.add_field(name="Failed Redeem", value=str(stats['failed_redeem']), inline=True)

        await ctx.send(embed=embed)

    @bot.command(name='checktransaction')
    @is_admin()
    async def check_transaction_admin(ctx, order_id: str):
        """
        [ADMIN] Cek detail transaksi
        Usage: !checktransaction TOPUP-123-20241203120000
        """
        topup = get_topup_by_order_id(order_id)

        if not topup:
            return await ctx.send(f"❌ Transaction `{order_id}` tidak ditemukan!")

        user = await bot.fetch_user(topup['user_id'])

        embed = discord.Embed(
            title=f"💳 Transaction Details",
            color=0x9b59b6
        )
        embed.add_field(name="Order ID", value=topup['order_id'], inline=False)
        embed.add_field(name="User", value=f"{user.mention} ({topup['user_id']})", inline=False)
        embed.add_field(name="Amount", value=format_rupiah(topup['amount']), inline=True)
        embed.add_field(name="Status", value=topup['status'].upper(), inline=True)
        embed.add_field(name="Payment Type", value=topup['payment_type'], inline=True)
        embed.add_field(name="Created", value=topup['created_at'], inline=True)
        embed.add_field(name="Updated", value=topup['updated_at'], inline=True)

        await ctx.send(embed=embed)

    @bot.command(name='botstats')
    @is_admin()
    async def bot_stats_admin(ctx):
        """
        [ADMIN] Statistik keseluruhan bot
        Usage: !botstats
        """
        from database import get_redeem_queue_count
        import sqlite3

        with sqlite3.connect(config.DB_FILE) as conn:
            cursor = conn.cursor()

            # Total users
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            # Total balance di sistem
            cursor.execute("SELECT SUM(balance) FROM users")
            total_balance = cursor.fetchone()[0] or 0

            # Total topup
            cursor.execute("SELECT COUNT(*), SUM(amount) FROM topups WHERE status='success'")
            topup_count, topup_amount = cursor.fetchone()
            topup_amount = topup_amount or 0

            # Total redeem
            cursor.execute("SELECT COUNT(*) FROM redeems WHERE status='success'")
            success_redeem = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM redeems WHERE status IN ('invalid', 'error')")
            failed_redeem = cursor.fetchone()[0]

        queue_count = get_redeem_queue_count()

        embed = discord.Embed(
            title="📊 Bot Statistics",
            description="Statistik keseluruhan sistem",
            color=0xe74c3c
        )
        embed.add_field(name="Total Users", value=str(total_users), inline=True)
        embed.add_field(name="Total Balance", value=format_rupiah(total_balance), inline=True)
        embed.add_field(name="Queue", value=f"{queue_count} tasks", inline=True)
        embed.add_field(name="Topup Count", value=str(topup_count), inline=True)
        embed.add_field(name="Topup Amount", value=format_rupiah(topup_amount), inline=True)
        embed.add_field(name="Success Redeem", value=str(success_redeem), inline=True)
        embed.add_field(name="Failed Redeem", value=str(failed_redeem), inline=True)
        embed.set_footer(text=f"Max Workers: {config.MAX_LOGIN_WORKERS}")

        await ctx.send(embed=embed)

    @bot.command(name='broadcast')
    @is_admin()
    async def broadcast_admin(ctx, *, message: str):
        """
        [ADMIN] Broadcast pesan ke semua user yang pernah topup
        Usage: !broadcast Your message here
        """
        import sqlite3

        with sqlite3.connect(config.DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT user_id FROM topups WHERE status='success'")
            user_ids = [row[0] for row in cursor.fetchall()]

        success_count = 0
        fail_count = 0

        status_msg = await ctx.send(f"📤 Mengirim broadcast ke {len(user_ids)} users...")

        for user_id in user_ids:
            try:
                user = await bot.fetch_user(user_id)

                embed = discord.Embed(
                    title="📢 Announcement from Admin",
                    description=message,
                    color=0xf39c12
                )
                embed.set_footer(text="CloudEmulator Bot")

                await user.send(embed=embed)
                success_count += 1
            except:
                fail_count += 1

        await status_msg.edit(
            content=f"✅ Broadcast selesai!\n"
                    f"Berhasil: {success_count}\n"
                    f"Gagal: {fail_count}"
        )

    @bot.command(name='adminhelp')
    @is_admin()
    async def admin_help(ctx):
        """
        [ADMIN] List semua admin commands
        Usage: !adminhelp
        """
        embed = discord.Embed(
            title="🛡️ Admin Commands",
            description="Daftar command khusus admin",
            color=0xe74c3c
        )

        commands_list = [
            ("!addbalance @user [amount]", "Tambah saldo manual ke user"),
            ("!checkuser @user", "Cek detail statistik user"),
            ("!checktransaction [order_id]", "Cek detail transaksi"),
            ("!botstats", "Statistik keseluruhan bot"),
            ("!broadcast [message]", "Kirim pesan ke semua user"),
            ("!adminhelp", "List admin commands"),
        ]

        for cmd, desc in commands_list:
            embed.add_field(name=cmd, value=desc, inline=False)

        embed.set_footer(text="Hanya user dengan role Admin yang bisa menggunakan commands ini")

        await ctx.send(embed=embed)

    print("✅ Admin commands loaded")
