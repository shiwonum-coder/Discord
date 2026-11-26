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
MORNING_TIME = time(hour=9, minute=0, tzinfo=KST)
EVENING_TIME = time(hour=18, minute=30, tzinfo=KST)

WRAPUP_RATINGS = {
    "100": ("💯", "완벽 달성"),
    "fire": ("🔥", "거의 다 함"),
    "smile": ("🙂", "절반 이상"),
    "melt": ("🫠", "내일 이어서"),
}


def save_checkin(user: discord.abc.User, status: str, content: str, rating: str = "") -> str:
    """Appends a KST date-stamped record to checkins.csv and returns the date string."""
    now_kst = datetime.now(KST)
    date_str = now_kst.strftime("%Y-%m-%d")
    time_str = now_kst.strftime("%H:%M")

    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["date", "time_kst", "user_id", "username", "status", "note", "rating"])
        writer.writerow([date_str, time_str, user.id, user.display_name, status, content, rating])

    return date_str


def update_checkin_rating(user: discord.abc.User, date_str: str, rating_label: str) -> str | None:
    """Updates today's '출석' row for this user with their wrap-up rating. Returns focus text if found."""
    if not os.path.isfile(LOG_FILE):
        return None

    with open(LOG_FILE, mode="r", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    if len(rows) <= 1:
        return None

    header, data_rows = rows[0], rows[1:]
    if "rating" not in header:
        header.append("rating")
    for r in data_rows:
        while len(r) < len(header):
            r.append("")

    matched_focus = None
    for r in reversed(data_rows):
        if r[0] == date_str and r[2] == str(user.id) and r[4] == "출석":
            r[6] = rating_label
            matched_focus = r[5]
            break

    if matched_focus is not None:
        with open(LOG_FILE, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(data_rows)

    return matched_focus


# --- PERSISTENT 6:30 PM WRAP-UP BUTTONS (WORKS FOR BOTH USERS) ---
class EveningWrapUpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def handle_rating(self, interaction: discord.Interaction, key: str):
        now_kst = datetime.now(KST)
        date_str = now_kst.strftime("%Y-%m-%d")
        time_str = now_kst.strftime("%H:%M")
        emoji, label = WRAPUP_RATINGS[key]
        rating_text = f"{emoji} {label}"

        focus_text = update_checkin_rating(interaction.user, date_str, rating_text)

        if focus_text is None:
            # Fallback if they tapped wrap-up without submitting a morning check-in
            save_checkin(interaction.user, "마무리", "마무리 체크만 기록", rating_text)
            desc = f"**마무리 달성도:** {rating_text} *({time_str})*"
        else:
            desc = f"**오늘 할 일:** {focus_text}\n**마무리 달성도:** {rating_text} *({time_str})*"

        embed = discord.Embed(description=desc, color=0x2ECC71)
        embed.set_author(name=f"{interaction.user.display_name} • {date_str} 마무리 완료")
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(emoji="💯", style=discord.ButtonStyle.secondary, custom_id="centercoffee:wrap_100")
    async def rate_100(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating(interaction, "100")

    @discord.ui.button(emoji="🔥", style=discord.ButtonStyle.secondary, custom_id="centercoffee:wrap_fire")
    async def rate_fire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating(interaction, "fire")

    @discord.ui.button(emoji="🙂", style=discord.ButtonStyle.secondary, custom_id="centercoffee:wrap_smile")
    async def rate_smile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating(interaction, "smile")

    @discord.ui.button(emoji="🫠", style=discord.ButtonStyle.secondary, custom_id="centercoffee:wrap_melt")
    async def rate_melt(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating(interaction, "melt")


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


# --- PERSISTENT 9:00 AM BUTTON VIEW ---
class CheckinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

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
        self.add_view(CheckinView())
        self.add_view(EveningWrapUpView())
        await self.tree.sync()
        self.morning_prompt.start()
        self.evening_prompt.start()

    @tasks.loop(time=MORNING_TIME)
    async def morning_prompt(self):
        channel = self.get_channel(CHECKIN_CHANNEL_ID)
        if channel is None:
            channel = await self.fetch_channel(CHECKIN_CHANNEL_ID)
        today_str = datetime.now(KST).strftime("%Y-%m-%d (%a)")
        await channel.send(
            content=f"☕ **9:00 AM 출석 체크! ({today_str})**\n오늘의 포커스 한 줄 남기기. 오늘도 열심히 해 라희 <3",
            view=CheckinView(),
        )

    @morning_prompt.before_loop
    async def before_morning_prompt(self):
        await self.wait_until_ready()

    @tasks.loop(time=EVENING_TIME)
    async def evening_prompt(self):
        channel = self.get_channel(CHECKIN_CHANNEL_ID)
        if channel is None:
            channel = await self.fetch_channel(CHECKIN_CHANNEL_ID)
        today_str = datetime.now(KST).strftime("%Y-%m-%d (%a)")
        await channel.send(
            content=(
                f"🌙 **6:30 PM 오늘 공부 마무리 체크! ({today_str})**\n"
                "오늘 목표 얼마나 달성했는지 이모지 하나로 눌러줘!\n"
                "💯 완벽 달성  |  🔥 거의 다 함  |  🙂 절반 이상  |  🫠 내일 이어서"
            ),
            view=EveningWrapUpView(),
        )

    @evening_prompt.before_loop
    async def before_evening_prompt(self):
        await self.wait_until_ready()


bot = CenterCoffeeBot()


@bot.tree.command(name="checkin", description="수동으로 출석 체크 또는 데이오프 버튼을 띄웁니다")
async def manual_checkin(interaction: discord.Interaction):
    await interaction.response.send_message(
        content="오늘의 상태를 선택해 주세요:",
        view=CheckinView(),
        ephemeral=True,
    )


@bot.tree.command(name="wrapup", description="수동으로 오늘 공부 마무리 달성도 버튼을 띄웁니다")
async def manual_wrapup(interaction: discord.Interaction):
    await interaction.response.send_message(
        content="오늘 목표 달성도를 선택해 주세요:\n💯 완벽 달성  |  🔥 거의 다 함  |  🙂 절반 이상  |  🫠 내일 이어서",
        view=EveningWrapUpView(),
        ephemeral=True,
    )


@bot.tree.command(name="history", description="최근 출석 및 데이오프 기록을 확인합니다")
async def view_history(interaction: discord.Interaction, days: int = 7):
    if not os.path.isfile(LOG_FILE):
        await interaction.response.send_message("아직 저장된 기록이 없습니다.", ephemeral=True)
        return

    with open(LOG_FILE, mode="r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    recent = rows[-(days * 2) :]
    if not recent:
        await interaction.response.send_message("기록이 비어 있습니다.", ephemeral=True)
        return

    lines = []
    for r in recent:
        rating_badge = f" → {r['rating']}" if r.get("rating") else ""
        lines.append(f"`{r['date']}` **{r['username']}** [{r['status']}]: {r['note']}{rating_badge}")

    await interaction.response.send_message(
        content="📋 **최근 체크인 기록:**\n" + "\n".join(lines),
        ephemeral=True,
    )


bot.run(TOKEN)
