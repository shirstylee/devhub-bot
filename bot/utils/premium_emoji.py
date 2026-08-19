from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PremiumEmoji:
    """A Telegram custom emoji with its plain-text fallback glyph."""

    emoji_id: str
    fallback: str

    @property
    def html(self) -> str:
        return f'<tg-emoji emoji-id="{self.emoji_id}">{self.fallback}</tg-emoji>'


SETTINGS = PremiumEmoji("5904258298764334001", "⚙️")
PROFILE = PremiumEmoji("6035084557378654059", "👤")
PEOPLE = PremiumEmoji("6032609071373226027", "👥")
APPROVE_USER = PremiumEmoji("5891207662678317861", "👤")
REJECT_USER = PremiumEmoji("5893192487324880883", "👤")
FILE = PremiumEmoji("6037475557082403885", "📁")
SMILE = PremiumEmoji("6028315147754278596", "🙂")
GROWTH = PremiumEmoji("5938539885907415367", "📈")
STATISTICS = PremiumEmoji("5936143551854285132", "📊")
HOME = PremiumEmoji("6042137469204303531", "🏠")
LOCKED = PremiumEmoji("6037249452824072506", "🔒")
UNLOCKED = PremiumEmoji("6037496202990194718", "🔓")
BROADCAST = PremiumEmoji("6039422865189638057", "📣")
SUCCESS = PremiumEmoji("5774022692642492953", "✅")
ERROR = PremiumEmoji("6030757850274336631", "❌")
EDIT = PremiumEmoji("6039779802741739617", "✏️")
DELETE = PremiumEmoji("6039522349517115015", "🗑")
DOWN = PremiumEmoji("5893057118545646106", "📰")
ATTACHMENT = PremiumEmoji("6039451237743595514", "📎")
LINK = PremiumEmoji("5769289093221454192", "🔗")
INFO = PremiumEmoji("6028435952299413210", "ℹ️")
BOT = PremiumEmoji("6030400221232501136", "🤖")
SHOW = PremiumEmoji("6037397706505195857", "👁")
HIDE = PremiumEmoji("6037243349675544634", "👁")
SEND = PremiumEmoji("5963103826075456248", "⬆️")
DOWNLOAD = PremiumEmoji("6039802767931871481", "⬇️")
NOTIFICATION = PremiumEmoji("6039486778597970865", "🔔")
GIFT = PremiumEmoji("6032644646587338669", "🎁")
CLOCK = PremiumEmoji("5983150113483134607", "⏰")
CELEBRATION = PremiumEmoji("6041731551845159060", "🎉")
FONT = PremiumEmoji("5771851822897566479", "🔡")
WRITE = PremiumEmoji("6039614175917903752", "✏️")
MEDIA = PremiumEmoji("6035128606563241721", "🖼")
IMAGE = PremiumEmoji("6030466823290360017", "🖼")
LOCATION = PremiumEmoji("6042011682497106307", "📍")
WALLET = PremiumEmoji("5769126056262898415", "👛")
BOX = PremiumEmoji("5884479287171485878", "📦")
CRYPTO_BOT = PremiumEmoji("5983580310292402968", "🤖")
CALENDAR = PremiumEmoji("5890937706803894250", "📅")
TAG = PremiumEmoji("5886285355279193209", "🏷")
HISTORY = PremiumEmoji("5775896410780079073", "🕓")
APPS = PremiumEmoji("5778672437122045013", "📦")
BRUSH = PremiumEmoji("6050679691004612757", "🖌")
ADD_TEXT = PremiumEmoji("5771851822897566479", "🔡")
FORMAT = PremiumEmoji("5778479949572738874", "↔️")
MONEY = PremiumEmoji("5904462880941545555", "🪙")
SEND_MONEY = PremiumEmoji("5890848474563352982", "🪙")
RECEIVE_MONEY = PremiumEmoji("5879814368572478751", "🏧")
CODE = PremiumEmoji("5940433880585605708", "🔨")
LOADING = PremiumEmoji("5841359499146825803", "⌨️")

BACK = "◁"  # Legacy label used only by the disabled renderer module.
BACK_ICON = PremiumEmoji("5960671702059848143", "⬅️")
GLOBE = PremiumEmoji("5776233299424843260", "🌐")
TRANSLATE = PremiumEmoji("5769403725898584391", "🅰️")
RU_FLAG = PremiumEmoji("5449408995691341691", "🇷🇺")
EN_FLAG = PremiumEmoji("5202021044105257611", "🇺🇸")
DE_FLAG = PremiumEmoji("5409360418520967565", "🇩🇪")
FR_FLAG = PremiumEmoji("5202132623060640759", "🇫🇷")
GB_FLAG = PremiumEmoji("5202196682497859879", "🇬🇧")
TEXT = PremiumEmoji("5922693616953725714", "📝")
HASHTAG = PremiumEmoji("5924498929147189381", "#️⃣")
QR_CODE = PremiumEmoji("5766975922620076409", "📷")
PHONE = PremiumEmoji("6039605143601680423", "📞")
REFRESH = PremiumEmoji("6030657343744644592", "🔁")
