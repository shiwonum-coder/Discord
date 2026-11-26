import csv
import os
from datetime import datetime, time, timezone, timedelta
import discord
from discord import app_commands
from discord.ext import commands, tasks

# --- CONFIGURATION ---
TOKEN = os.environ["DISCORD_BOT_TOKEN"]
CHECKIN_CHANNEL_ID = 1575354696367865990  # Your #check-in channel ID
LOG_FILE = "checkins.csv"
KST = timezone(timedelta(hours=9))
DAILY_TIME = time(hour=9, minute=0, tzinfo=KST)


def save_checkin(user: discord.abc.User, status: str, content: str) -> str:
    """Appends a KST date-stamped record to checkins.csv and returns the date string."""
    now_kst = datetime.now(KST)
    date_str = now_kst.strftime("%Y-%m-%d")
    time_str = now_kst.strftime("%H:%M")

    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["date", "time_kst", "user_id", "username", "status", "note"])
        writer.writerow([date_str, time_str, user.id, user.display_name, status, content])

    return date_str


# --- POP-UP MODALS ---
class StudyModal(discord.ui.Modal, title="☕ 오늘 출석 체크"):
    focus = discord.ui.TextInput(
        label="오늘 할 일 (한 줄 요약)",
        placeholder="예: 경제 기출 1-50 / 8-Puzzle + P-set 2",
        style=discord.TextStyle.short,
        max_length=150,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        date_str = save_checkin(interaction.user, "출석", self.focus.value)
        embed = discord.Embed(
            description=f"**오늘 할 일:** {self.focus.value}",
            color=0x6F4E37,  # Coffee brown
        )
        embed.set_author(name=f"{interaction.user.display_name} • {date_str} 출석")
        await interaction.response.send_message(embed=embed)


class DayOffModal(discord.ui.Modal, title="🛌 데이오프 사유 제출"):
    reason = discord.ui.TextInput(
        label="데이오프 사유 + 이모지 1개",
        placeholder="예: 뇌 휴식 및 카페 투어 🥐",
        style=discord.TextStyle.short,
        max_length=150,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        date_str = save_checkin(interaction.user, "데이오프", self.reason.value)
        embed = discord.Embed(
            description=f"**데이오프 사유:** {self.reason.value}",
            color=0x95A5A6,  # Soft gray
        )
        embed.set_author(name=f"{interaction.user.display_name} • {date_str} 데이오프")
        await interaction.response.send_message(embed=embed)


# --- PERSISTENT BUTTON VIEW ---
class CheckinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Never expires across bot restarts

    @discord.ui.button(
        label="출석 체크",
        emoji="☕",
        style=discord.ButtonStyle.success,
        custom_id="centercoffee:checkin_btn",
    )
    async def checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StudyModal())

    @discord.ui.button(
        label="데이오프",
        emoji="🛌",
        style=discord.ButtonStyle.secondary,
        custom_id="centercoffee:dayoff_btn",
    )
    async def dayoff_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DayOffModal())


# --- BOT SETUP ---
class CenterCoffeeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Re-register persistent buttons on startup
        self.add_view(CheckinView())
        await self.tree.sync()
        self.daily_prompt.start()

    @tasks.loop(time=DAILY_TIME)
    async def daily_prompt(self):
        channel = self.get_channel(CHECKIN_CHANNEL_ID)
        if channel is None:
            channel = await self.fetch_channel(CHECKIN_CHANNEL_ID)
        today_str = datetime.now(KST).strftime("%Y-%m-%d (%a)")
        await channel.send(
            content=f"☕ **9:00 AM 출석 체크! ({today_str})**\n오늘의 포커스 한 줄 남기기. 오늘도 열심히 해 라희 <3",
            view=CheckinView(),
        )

    @daily_prompt.before_loop
    async def before_daily_prompt(self):
        await self.wait_until_ready()


bot = CenterCoffeeBot()


@bot.tree.command(name="checkin", description="수동으로 출석 체크 또는 데이오프 버튼을 띄웁니다")
async def manual_checkin(interaction: discord.Interaction):
    await interaction.response.send_message(
        content="오늘의 상태를 선택해 주세요:",
        view=CheckinView(),
        ephemeral=True,  # Only visible to the person who ran /checkin
    )


@bot.tree.command(name="history", description="최근 출석 및 데이오프 기록을 확인합니다")
async def view_history(interaction: discord.Interaction, days: int = 7):
    if not os.path.isfile(LOG_FILE):
        await interaction.response.send_message("아직 저장된 기록이 없습니다.", ephemeral=True)
        return

    with open(LOG_FILE, mode="r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    recent = rows[-(days * 2) :]  # Roughly last N days for 2 people
    if not recent:
        await interaction.response.send_message("기록이 비어 있습니다.", ephemeral=True)
        return

    lines = [
        f"`{r['date']}` **{r['username']}** [{r['status']}]: {r['note']}"
        for r in recent
    ]
    await interaction.response.send_message(
        content="📋 **최근 체크인 기록:**\n" + "\n".join(lines),
        ephemeral=True,
    )


bot.run(TOKEN)