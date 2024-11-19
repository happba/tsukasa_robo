from discord.ext import commands
from openSlotsEmbed import OpenSlotsEmbed
from discord import Option, SlashCommandOptionType

class Hours(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
            
    @commands.command(name="hours", description="Gets the number of open slots for the current event")
    async def openSlots(self, ctx, standby: Option(
            SlashCommandOptionType.boolean,
            description="show standby hours",
            default=False)
    ):
        
        start = 1732316400
        end = 1732856399

        days = [int(start - 3600 * 15)]
        while days[-1] < end:
            days.append(days[-1] + 86400)
            
        days.append(days[-1] + 86400)
        
        timestamps = []
        
        timestamp = int(start)
        while timestamp < days[-1]:
            timestamps.append(timestamp)
            timestamp += 3600

        indexes = [0] + [i for i, x in enumerate(timestamps) if x in days]
        view = OpenSlotsEmbed(indexes, timestamps, start, standby)

        view.set_message(await ctx.reply(embed=view.generateEmbed(), view=view))


def setup(bot):
    bot.add_cog(Hours(bot))