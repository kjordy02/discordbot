import discord

class StatsFormatter:
    @staticmethod
    def format_top_list(data, unit="sips"):
        if not data:
            return "_No data._"
        return "\n".join(
            f"{i+1}. <@{uid}> – {val} {unit}" for i, (uid, val) in enumerate(data[:3])
        )

    @staticmethod
    def format_endgame_list(data):
        if not data:
            return "_No data._"
        return "\n".join(
            f"{i+1}. <@{uid}> – {sips} sips, {tries} tries"
            for i, (uid, sips, tries) in enumerate(data[:3])
        )

    @staticmethod
    def build_embed(title, stats_dict: dict[str, dict[str, str]]):
        """
        Build an embed from grouped stats.

        stats_dict = {
            "🏆 Global": {
                "🍻 Most Drunk": "<formatted text>",
                "🎯 Most Given": "<formatted text>",
                ...
            },
            "🌙 Today": {
                ...
            }
        }
        """
        embed = discord.Embed(
        title=title,
        color=discord.Color.blurple()
        )

        first = True
        for section_title, fields in stats_dict.items():
            if not first:
                embed.add_field(name="⠀", value="⠀", inline=False)  # Leerzeile (unsichtbares Zeichen)
            first = False

            embed.add_field(name=f"__{section_title}__", value="** **", inline=False)  # Unterstrichen
            for field_name, value in fields.items():
                embed.add_field(name=field_name, value=value, inline=False)

        return embed