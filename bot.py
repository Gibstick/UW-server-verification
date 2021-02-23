import asyncio
import logging
import sys
import time
import uuid

import discord
from discord.ext import commands
from sqlitedict import SqliteDict

from config import settings
import db


class VerifyCog(commands.Cog):
    def __init__(
        self,
        bot: discord.Client,
        sm: db.SessionManager,
        check_interval: int,
        url: str,
        role_name: str,
        *args,
        **kwargs,
    ):
        self.bot = bot
        self.sm = sm
        self.check_interval = check_interval
        self.url = url
        self.role_name = role_name

        self.logger = logging.getLogger("AndrewBot")

        bot.loop.create_task(self.maintenance_loop())
        super().__init__(*args, **kwargs)

    @commands.Cog.listener()
    async def on_ready(self):
        # Search for a role called "UW Verified" in all servers and cache its
        # id by guild id
        self.logger.info("Assembling role cache")
        self.verified_roles = {}
        for guild in self.bot.guilds:
            for role in guild.roles:
                if role.name == self.role_name:
                    self.verified_roles[guild.id] = role.id
                    break
            else:
                self.logger.warning(
                    f"{self.role_name} role not found in guild {guild}")
        self.logger.info("Bot is ready")

    async def maintenance_loop(self):
        interval = self.check_interval
        self.logger.info(
            f"Sleeping {interval} seconds between maintenance iterations")
        while True:
            await self.bot.wait_until_ready()

            async for session in self.sm.verified_user_ids():
                user_id, guild_id = session.user_id, session.guild_id
                try:
                    guild = self.bot.get_guild(guild_id)
                    member = await guild.fetch_member(user_id)
                    role_id = self.verified_roles.get(guild_id, None)
                    if role_id is None:
                        self.logger.warning(
                            f"Skipping verification for {session.discord_name} because no role was found in {guild}"
                        )
                        continue
                    role = guild.get_role(role_id)
                    self.logger.info(
                        f"Adding role to ({session.discord_name}, {member.id})"
                    )
                    await member.add_roles(role, reason="Verification Bot")
                except Exception:
                    self.logger.exception(
                        f"Failed to add role to user in {guild_id}")
                    continue

            await self.sm.collect_garbage()
            await asyncio.sleep(interval)

    @commands.command()
    async def verify(self, ctx):
        # Ignore all DMs for now
        if not ctx.message.guild:
            return

        # HACK: only respond in certain channels
        if not "verification" in ctx.channel.name.lower():
            return

        user_id = ctx.author.id
        guild_id = ctx.guild.id
        name = f"{ctx.author.name}#{ctx.author.discriminator}"
        session_uuid = self.sm.try_new(user_id, guild_id, name)
        verification_link = f"{self.url}/start/{user_id}/{session_uuid}"

        embed = discord.Embed(
            title="Verification!",
            url=verification_link,
            description=
            "Please use this page to enter your email for verification. Your email will not be shared with Discord.",
            color=0xffc0cb,
        )
        embed.add_field(
            name="Verification Link",
            value=verification_link,
            inline=True,
        )
        embed.set_thumbnail(
            url=
            "https://uwaterloo.ca/library/sites/ca.library/files/uploads/images/img_0236_0.jpg"
        )
        try:
            await ctx.message.author.send(embed=embed)
        except discord.Forbidden:
            await ctx.message.reply("Unable to send DM. Are you sure you have DMs enabled on this server?")

    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def reset_session(self, ctx, member: discord.Member):
        """
        Reset the session for a user. For users with manage roles permission only.
        """
        if not ctx.message.guild:
            return
        self.sm.delete_session(member.id)
        await ctx.reply(f"Removed session for {member}")


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    logging.getLogger("sqlitedict").setLevel(logging.WARNING)

    expiry_seconds: int = settings.common.expiry_s
    database_file: int = settings.common.database_file
    sm = db.SessionManager(expiry_seconds, database_file)

    discordconf = settings.discord
    bot = commands.Bot(command_prefix=discordconf.prefix)
    bot.add_cog(
        VerifyCog(bot=bot,
                  sm=sm,
                  check_interval=discordconf.check_interval_s,
                  url=discordconf.url,
                  role_name=discordconf.role_name))
    bot.run(discordconf.token)


if __name__ == "__main__":
    main()
